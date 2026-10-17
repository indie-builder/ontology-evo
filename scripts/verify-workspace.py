#!/usr/bin/env python3
"""Verify a recorded fresh Claude Code session against actual workspace tasks."""
import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(session):
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
    for required in ["prepare_ontology_workload", "start_ontology_task", "resolve_ontology_task",
                     "execute_ontology_query", "finish_ontology_task"]:
        assert required in names, f"Missing actual tool call: {required}"
    result = next(event for event in events if event.get("type") == "result")
    assert not result.get("is_error") and not result.get("permission_denials"), result
    ids = [call["input"]["task_id"] for call in calls if call["name"].endswith("__finish_ontology_task")]
    assert ids
    project = json.loads((ROOT / ".evoontology/project.json").read_text())
    db = Path(project["data_source"]["path"])
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    verified = []
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as connection:
        for task_id in ids:
            task = json.loads((ROOT / ".evoontology/trajectories" / f"{task_id}.json").read_text())
            assert task["task_status"] == "completed" and task["origin"] == "user"
            assert task_id in result["result"], "Final reply lacks traceable task id"
            assert task["semantic_calls"]
            queries = [event for event in task["native_tool_calls"] if event["tool"] == "sqlite_query"]
            assert queries
            for query in queries:
                assert not query["error"] and not query["result_truncated"]
                cursor = connection.execute(query["input"]["query"])
                assert [list(row) for row in cursor] == query["result"]["rows"]
            verified.append({"task_id": task_id, "question": task["question"], "queries": len(queries)})
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
    verify(parser.parse_args().session.resolve())
