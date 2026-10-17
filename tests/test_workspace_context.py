import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude/hooks/session-start.py"
spec = importlib.util.spec_from_file_location("workspace_context", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class WorkspaceContextTest(unittest.TestCase):
    def test_uninitialized_workspace_can_start(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertIn("状态=未初始化", hook.workspace_context(Path(directory)))

    def test_configured_workspace_without_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / ".evoontology"
            workspace.mkdir()
            (workspace / "project.json").write_text(json.dumps({"data_source": {"type": "database", "id": "warehouse"}}))
            self.assertIn("状态=已配置但未发布", hook.workspace_context(root))

    def test_registered_sqlite_does_not_require_demo_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "another-dataset.sqlite"
            database.touch()
            workspace = root / ".evoontology"
            (workspace / "versions/ontology_v8").mkdir(parents=True)
            (workspace / "project.json").write_text(json.dumps({"data_source": {"type": "sqlite", "path": str(database)}}))
            (workspace / "active.json").write_text(json.dumps({"active_version": "ontology_v8"}))
            context = hook.workspace_context(root)
            self.assertIn("active_version=ontology_v8", context)
            self.assertNotIn("阻塞=", context)
            database.unlink()
            self.assertIn("阻塞=注册数据源文件不存在", hook.workspace_context(root))
            (workspace / "active.json").write_text(json.dumps({"active_version": "../outside"}))
            with self.assertRaisesRegex(ValueError, "Invalid active version"):
                hook.workspace_context(root)


if __name__ == "__main__":
    unittest.main()
