import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_workspace", ROOT / "scripts/verify-workspace.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class TranscriptEvidenceTest(unittest.TestCase):
    def test_recovered_query_errors_remain_verifiable(self):
        error = {"status": "error", "error": "Binder Error: missing column"}
        events = [
            {"message": {"content": [{"type": "tool_use", "id": "bad", "name": "mcp__workspace-analytics__query", "input": {"sql": "SELECT missing"}}]}},
            {"message": {"content": [{"type": "tool_result", "tool_use_id": "bad", "content": json.dumps(error)}]}},
        ]
        self.assertEqual(verifier.observed_duckdb_results(events), [("SELECT missing", error)])

    def test_only_actual_successful_tool_results_count(self):
        result = {"status": "ok", "result": {"columns": ["n"], "rows": [[2]], "truncated": False}}
        events = [
            {"message": {"content": [{"type": "tool_use", "id": "query1", "name": "mcp__workspace-analytics__query", "input": {"sql": "SELECT 2 n"}}]}},
            {"message": {"content": [{"type": "tool_result", "tool_use_id": "unrelated", "content": json.dumps(result)}]}},
        ]
        self.assertEqual(verifier.observed_duckdb_results(events), [])
        events.append({"message": {"content": [{"type": "tool_result", "tool_use_id": "query1", "content": [{"type": "text", "text": json.dumps(result)}]}]}})
        self.assertEqual(verifier.observed_duckdb_results(events), [("SELECT 2 n", result)])
        events[-1]["message"]["content"][0]["is_error"] = True
        self.assertEqual(verifier.observed_duckdb_results(events), [])


if __name__ == "__main__":
    unittest.main()
