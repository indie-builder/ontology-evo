import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("analytics_server", ROOT / "scripts/analytics-server.py")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class AnalyticsServerTest(unittest.TestCase):
    def test_actual_worker_enforces_readonly_external_and_row_limits(self):
        import duckdb
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            database = root / "sample.duckdb"
            with duckdb.connect(str(database)) as connection:
                connection.execute("CREATE TABLE orders AS SELECT i FROM range(200) t(i)")
            (root / "config/analytics.json").write_text(json.dumps({"database": "sample.duckdb", "ontology_workspace": ".evoontology", "business_policy": "policy.md"}))
            before = hashlib.sha256(database.read_bytes()).hexdigest()
            result = server.bounded_query(root, "SELECT * FROM orders ORDER BY i")
            self.assertEqual(result["status"], "ok", result)
            self.assertEqual(len(result["result"]["rows"]), 100)
            self.assertTrue(result["result"]["truncated"])
            for query in ["DELETE FROM orders", "SELECT 1; SELECT 2", "SET enable_external_access=true",
                          "COPY orders TO '/tmp/query-test.csv'", "SELECT * FROM read_csv('/etc/passwd')",
                          "SELECT * FROM read_parquet('https://example.com/data.parquet')", "INSTALL httpfs"]:
                self.assertEqual(server.bounded_query(root, query)["status"], "error", query)
            self.assertEqual(before, hashlib.sha256(database.read_bytes()).hexdigest())
            huge = server.bounded_query(root, "SELECT repeat('x',70000) AS big")
            self.assertEqual(huge["status"], "ok")
            self.assertEqual(huge["result"]["rows"], [])
            self.assertTrue(huge["result"]["truncated"])
            (root / ".evoontology").mkdir()
            (root / ".evoontology/project.json").write_text(json.dumps({"data_source": {"type": "duckdb", "path": str(root / "different.duckdb")}}))
            with self.assertRaisesRegex(ValueError, "data source differ"):
                server.configuration(root)

    def test_schema_pages_cover_large_catalog_without_main_filter(self):
        import duckdb
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            database = root / "catalog.duckdb"
            with duckdb.connect(str(database)) as connection:
                connection.execute("CREATE SCHEMA enterprise")
                columns = ",".join(f"c{i} INTEGER" for i in range(120))
                connection.execute(f"CREATE TABLE enterprise.orders ({columns})")
            (root / "config/analytics.json").write_text(json.dumps({"database": "catalog.duckdb", "ontology_workspace": ".evoontology", "business_policy": "policy.md"}))
            first = server.schema_page(root, schema="enterprise", table="orders")
            self.assertEqual(len(first["result"]["rows"]), 100)
            second = server.schema_page(root, schema="enterprise", table="orders", cursor=first["next_cursor"])
            self.assertEqual(len(second["result"]["rows"]), 20)
            self.assertIsNone(second["next_cursor"])
            names = [row[2] for page in [first,second] for row in page["result"]["rows"]]
            self.assertEqual(len(set(names)), 120)

    def test_result_budget_includes_metadata(self):
        import duckdb
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "budget.duckdb"
            duckdb.connect(str(database)).close()
            result = server.execute(database, "SELECT repeat('x',65460) AS value")
            self.assertLessEqual(len(json.dumps(result, ensure_ascii=False).encode()), server.MAX_BYTES)
            self.assertTrue(result["truncated"])

    def test_nonfinite_values_do_not_escape_as_invalid_json_numbers(self):
        import duckdb
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "nonfinite.duckdb"
            duckdb.connect(str(database)).close()
            result = server.execute(database, "SELECT 'NaN'::DOUBLE AS ratio,'Infinity'::DOUBLE AS unbounded")
            json.dumps(result, allow_nan=False)
            self.assertEqual(result["rows"], [["NaN", "Infinity"]])

    def test_worker_deadline_reports_timeout(self):
        with patch.object(server, "configuration", return_value={"database": Path("unused.duckdb")}), patch.object(server.subprocess, "run", side_effect=subprocess.TimeoutExpired("worker", 15)):
            result = server.bounded_query(ROOT, "SELECT 1")
            self.assertEqual(result["status"], "error")
            self.assertIn("deadline", result["error"])

    def test_configuration_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/analytics.json").write_text(json.dumps({"database": "../outside.duckdb", "ontology_workspace": ".evoontology", "business_policy": "policy.md"}))
            with self.assertRaises(ValueError):
                server.configuration(root)


if __name__ == "__main__":
    unittest.main()
