#!/usr/bin/env python3
"""Verify a recorded fresh Claude Code session against actual workspace tasks."""
import argparse
from contextlib import nullcontext
import hashlib
import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def observed_duckdb_results(events):
    calls = {}
    observed = []
    for event in events:
        for block in event.get("message", {}).get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == "mcp__workspace-analytics__query":
                calls[block["id"]] = block["input"]["sql"]
            if block.get("type") == "tool_result" and block.get("tool_use_id") in calls:
                if block.get("is_error"):
                    continue
                content = block.get("content", [])
                texts = [item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text"] if isinstance(content, list) else [content]
                for text in texts:
                    try:
                        value = json.loads(text)
                    except (ValueError, TypeError):
                        continue
                    if isinstance(value, dict) and value.get("status") in {"ok", "error"}:
                        observed.append((calls[block["tool_use_id"]], value))
    return observed


def verify(session, workspace=None):
    settings = json.loads((ROOT / ".claude/settings.json").read_text())
    assert settings["enabledPlugins"]["evoontology@evoontology"] is True
    hook = subprocess.run([sys.executable, "-I", str(ROOT / ".claude/hooks/session-start.py")],
                          input="{}", text=True, capture_output=True, check=True)
    assert json.loads(hook.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    events = [json.loads(line) for line in session.read_text().splitlines() if line.strip()]
    init = next(event for event in events if event.get("subtype") == "init")
    assert Path(init["cwd"]).resolve() == ROOT
    assert "sales-analysis" in init["skills"]
    assert any(server["name"] == "plugin:evoontology:evo-semantic" and server["status"] == "connected"
               for server in init["mcp_servers"])
    calls = [block for event in events if event.get("type") == "assistant"
             for block in event.get("message", {}).get("content", []) if block.get("type") == "tool_use"]
    assert any(call["name"] == "Skill" and call["input"]["skill"] == "sales-analysis" for call in calls)
    names = [call["name"].split("__")[-1] for call in calls]
    workspace = workspace or ROOT / ".evoontology"
    project = json.loads((workspace / "project.json").read_text())
    source = project["data_source"]
    is_duckdb = isinstance(source, dict) and source.get("type") == "duckdb"
    query_tool = "query" if is_duckdb else "execute_ontology_query"
    for required in ["prepare_ontology_workload", "start_ontology_task", "resolve_ontology_task", query_tool,
                     "finish_ontology_task"]:
        assert required in names, f"Missing actual tool call: {required}"
    result = next(event for event in events if event.get("type") == "result")
    assert not result.get("is_error") and not result.get("permission_denials"), result
    ids = [call["input"]["task_id"] for call in calls if call["name"].endswith("__finish_ontology_task")]
    assert ids
    db = Path(source["path"] if isinstance(source, dict) else source)
    observed = observed_duckdb_results(events) if is_duckdb else []
    if is_duckdb:
        assert any(value["status"] == "ok" for _, value in observed), "No successful DuckDB result observed in the actual host transcript"
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    verified = []
    if is_duckdb:
        spec = importlib.util.spec_from_file_location("analytics_replay", ROOT / "scripts/analytics-server.py")
        analytics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(analytics)
        assert analytics.configuration(ROOT)["database"] == db.resolve(), "Replay source differs from configured query source"
        connection = None
    else:
        connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    with connection if connection is not None else nullcontext():
        for task_id in ids:
            task = json.loads((workspace / "trajectories" / f"{task_id}.json").read_text())
            assert task["task_status"] == "completed" and task["origin"] == "user"
            assert task["data_source"] == source, "Task data source differs from the selected workspace"
            assert task_id in result["result"], "Final reply lacks traceable task id"
            assert task["semantic_calls"]
            tool_name = "workspace-analytics.query" if is_duckdb else "sqlite_query"
            queries = [event for event in task["native_tool_calls"] if event["tool"] == tool_name]
            assert queries
            succeeded = 0
            errors = 0
            for query in queries:
                assert not query["result_truncated"], "Trajectory preview cannot verify a complete result"
                sql = query["input"]["sql" if is_duckdb else "query"]
                if is_duckdb:
                    assert (sql, query["result"]) in observed, "Recorded DuckDB result does not match an actual host tool response"
                    assert query["error"] == (query["result"]["status"] == "error"), "Query error flag differs from actual result"
                if query["error"]:
                    errors += 1
                    continue
                recorded = query["result"]["result"] if is_duckdb else query["result"]
                if is_duckdb:
                    replay = analytics.bounded_query(ROOT, sql)
                    assert replay["status"] == "ok", replay
                    assert replay["result"] == recorded, "Bounded DuckDB replay differs from recorded result"
                else:
                    assert not recorded["truncated"]
                    cursor = connection.execute(sql)
                    assert [column[0] for column in cursor.description] == recorded["columns"], "Recorded result columns differ"
                    actual = json.loads(json.dumps([list(row) for row in cursor.fetchall()], default=str))
                    assert actual == recorded["rows"]
                succeeded += 1
            assert succeeded, "Completed task has no successful data query"
            verified.append({"task_id": task_id, "question": task["question"], "queries": len(queries), "successful_queries": succeeded, "recorded_errors": errors})
    assert before == hashlib.sha256(db.read_bytes()).hexdigest()
    assert any(event.get("hook_event") == "SessionStart" and "当前Workspace是销售分析智能体" in event.get("stdout", "")
               for event in events), "Project startup hook did not actually fire"
    report = {"passed": True, "session": str(session.relative_to(ROOT)), "cwd": str(ROOT),
              "skill_auto_invoked": True, "project_hook_fired": True, "mcp_connected": True,
              "permission_denials": [], "tasks": verified, "database_sha256": before,
              "final_answer": result["result"]}
    (ROOT / "artifacts/workspace-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    verify(args.session.resolve(), args.workspace.resolve() if args.workspace else None)
