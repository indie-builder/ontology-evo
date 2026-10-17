import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate-analytics.py"
spec = importlib.util.spec_from_file_location("analytics_generator", SCRIPT)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class AnalyticsGeneratorTest(unittest.TestCase):
    def test_parquet_roundtrip_and_refuse_existing_data(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "sample"
            manifest = generator.generate(output, 1000)
            self.assertEqual(manifest["counts"]["orders"], 1000)
            self.assertTrue(all(manifest["checks"].values()))
            self.assertEqual(len(manifest["quarter_result"]), 4)
            prior = (output / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                generator.generate(output, 2000)
            self.assertEqual((output / "manifest.json").read_bytes(), prior)
            self.assertEqual(json.loads(prior)["fixture"], "synthetic-analytics-v1")

    def test_reject_invalid_scale_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "invalid"
            with self.assertRaises(ValueError):
                generator.generate(output, 1)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
