#!/usr/bin/env python3
"""Bounded local DuckDB reads for one configured Workspace data source."""
import argparse
import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_ROWS = 100
MAX_BYTES = 65536
TIMEOUT = 15


def configuration(root):
    config = json.loads((root / "config/analytics.json").read_text())
    paths = {}
    for key in ["database", "ontology_workspace", "business_policy"]:
        path = (root / config[key]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError(f"Configured {key} must remain inside this Workspace")
        paths[key] = path
    if not paths["database"].is_file():
        raise FileNotFoundError("Analytics database missing; generate the configured sample before querying")
    project_file = paths["ontology_workspace"] / "project.json"
    if project_file.is_file():
        source = json.loads(project_file.read_text())["data_source"]
        if source.get("type") != "duckdb" or Path(source["path"]).resolve() != paths["database"]:
            raise ValueError("Configured database and ontology data source differ; reconfigure explicitly")
    return paths


def execute(database, sql):
    import duckdb

    if not isinstance(sql, str) or not sql.strip() or len(sql) > 20000:
        raise ValueError("Provide one nonempty SQL query of at most 20,000 characters")
    with tempfile.TemporaryDirectory(prefix="workspace-query-") as directory:
        with duckdb.connect(str(database), read_only=True, config={
            "enable_external_access": "false", "autoinstall_known_extensions": "false",
            "autoload_known_extensions": "false", "memory_limit": "512MB", "threads": "2",
            "temp_directory": directory, "max_temp_directory_size": "256MB",
        }) as connection:
            statements = connection.extract_statements(sql)
            if len(statements) != 1 or statements[0].type != duckdb.StatementType.SELECT:
                raise ValueError("Only one SELECT or WITH query is allowed")
            connection.execute("SET lock_configuration=true")
            timer = threading.Timer(10, connection.interrupt)
            timer.daemon = True
            timer.start()
            try:
                cursor = connection.execute(sql)
                columns = [column[0] for column in cursor.description]
                fetched = cursor.fetchmany(MAX_ROWS + 1)
            finally:
                timer.cancel()
            rows = []
            result = {"columns": columns, "rows": rows, "truncated": len(fetched) > MAX_ROWS,
                      "limits": {"max_rows": MAX_ROWS, "max_result_bytes": MAX_BYTES, "timeout_seconds": TIMEOUT,
                                 "memory_limit": "512MB", "temp_limit": "256MB"}}
            for row in fetched[:MAX_ROWS]:
                normalized = json.loads(json.dumps(list(row), default=str, ensure_ascii=False), parse_constant=str)
                rows.append(normalized)
                if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
                    rows.pop()
                    result["truncated"] = True
                    break
            if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
                raise ValueError("Result column metadata exceeds response byte limit")
            return result


def bounded_query(root, sql):
    paths = configuration(root)
    try:
        completed = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", str(paths["database"])],
            input=json.dumps({"sql": sql}), capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "Query exceeded the 15-second worker deadline"}
    if completed.returncode:
        return {"status": "error", "error": completed.stderr[-1000:] or "Query worker failed"}
    return json.loads(completed.stdout)


def schema_page(root, schema=None, table=None, cursor=0):
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        raise ValueError("Catalog cursor must be a nonnegative integer")
    predicates = ["table_schema NOT IN ('information_schema','pg_catalog')"]
    for column, value in [("table_schema", schema), ("table_name", table)]:
        if value is not None:
            if not isinstance(value, str) or len(value) > 256:
                raise ValueError("Catalog filters must be strings up to 256 characters")
            predicates.append(column + "='" + value.replace("'", "''") + "'")
    sql = ("SELECT table_schema,table_name,column_name,data_type,ordinal_position FROM information_schema.columns WHERE "
           + " AND ".join(predicates) + " ORDER BY table_schema,table_name,ordinal_position OFFSET " + str(cursor))
    result = bounded_query(root, sql)
    if result["status"] == "ok":
        count = len(result["result"]["rows"])
        result["next_cursor"] = cursor + count if result["result"]["truncated"] and count else None
        result["catalog_snapshot_requirement"] = "Keep the database schema unchanged while paging"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--query")
    args = parser.parse_args()
    if args.worker:
        try:
            result = {"status": "ok", "result": execute(args.worker, json.load(sys.stdin)["sql"])}
        except Exception as error:
            result = {"status": "error", "error": str(error)[:1000]}
        print(json.dumps(result, ensure_ascii=False, default=str))
        return
    if args.query:
        print(json.dumps(bounded_query(ROOT, args.query), ensure_ascii=False, default=str))
        return
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("workspace-analytics", instructions="Read only the configured local analytics database. Use SELECT queries; no arbitrary paths or external files. Record real results through EvoOntology task tools.")

    @server.tool()
    def analytics_status() -> dict:
        """Return the configured source, exact ontology workspace, policy and table columns."""
        paths = configuration(ROOT)
        schema = schema_page(ROOT)
        return {"source_type": "duckdb", **{key: str(path) for key, path in paths.items()}, "schema": schema}

    @server.tool()
    def schema(schema: str | None = None, table: str | None = None, cursor: int = 0) -> dict:
        """Read actual column metadata across schemas, optionally filtered; follow next_cursor until null."""
        return schema_page(ROOT, schema, table, cursor)

    @server.tool()
    def query(sql: str) -> dict:
        """Execute one bounded SELECT against the configured DuckDB source, returning actual rows or an error."""
        return bounded_query(ROOT, sql)

    server.run(transport="stdio")


if __name__ == "__main__":
    main()
