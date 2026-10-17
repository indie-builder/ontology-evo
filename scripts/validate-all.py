#!/usr/bin/env python3
"""Run local tests, relational checks and optional real-session evidence verification."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--workspace", type=Path, default=ROOT / ".evoontology/analytics")
    args = parser.parse_args()
    commands = [
        [sys.executable, "-I", "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-I", "design/enterprise/verify-design.py"],
        [sys.executable, "-I", "demo.py", "check"],
    ]
    if args.session:
        commands.append([sys.executable, "-I", "scripts/verify-workspace.py", str(args.session.resolve()), "--workspace", str(args.workspace.resolve())])
    report = {"passed": True, "checks": [], "enterprise_runtime_implemented": False,
              "limitations": ["36-table schema and public counterexamples only; full enterprise agent pipeline is not implemented.",
                              "No independent reviewer or production concurrency test."]}
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=120)
        public_args = []
        for argument in command[2:]:
            path = Path(argument)
            public_args.append(str(path.relative_to(ROOT)) if path.is_absolute() and path.is_relative_to(ROOT) else argument)
        item = {"command": public_args, "passed": result.returncode == 0}
        if result.returncode:
            item["output"] = (result.stdout + result.stderr)[-6000:]
            report["passed"] = False
        else:
            try:
                value = json.loads(result.stdout)
                item["summary"] = {key: value[key] for key in ["status", "schema_table_count", "passed", "tasks", "read_only_verified"] if key in value}
                if "tasks" in item["summary"]:
                    item["summary"]["tasks"] = [{"question": task["question"], "queries": task["queries"]} for task in value["tasks"]]
            except ValueError:
                item["summary"] = result.stderr.strip().splitlines()[-3:]
        report["checks"].append(item)
    (ROOT / "artifacts").mkdir(exist_ok=True)
    (ROOT / "artifacts/full-validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
