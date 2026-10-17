#!/usr/bin/env python3
"""Report workspace readiness without changing project or ontology state."""
import json
from pathlib import Path


def workspace_context(root):
    workspace = root / ".evoontology"
    summary = [f"当前Workspace是销售分析智能体。根目录={root}；EvoOntology workspace={workspace}。"]
    project_file = workspace / "project.json"
    active_file = workspace / "active.json"
    if not project_file.is_file():
        summary.append("状态=未初始化。需要构建时使用官方build-ontology技能，从用户数据和问题建立上下文。")
    else:
        project = json.loads(project_file.read_text(encoding="utf-8"))
        source = project["data_source"]
        summary.append("注册数据源=" + json.dumps(source, ensure_ascii=False) + "。")
        if isinstance(source, dict) and source.get("type") == "sqlite":
            database = Path(source["path"])
            if not database.is_absolute():
                summary.append("阻塞=注册SQLite路径不是绝对路径，需显式修正项目配置。")
            elif not database.is_file():
                summary.append("阻塞=注册SQLite文件不存在，先恢复数据或显式重新配置；不能猜用其他文件。")
        if not active_file.is_file():
            summary.append("状态=已配置但未发布本体。继续官方构建流程，不能假定已有active版本。")
        else:
            version = json.loads(active_file.read_text(encoding="utf-8"))["active_version"]
            if not isinstance(version, str) or not version or Path(version).name != version or version in {".", ".."}:
                raise ValueError("Invalid active version path component")
            summary.append(f"active_version={version}。")
            if not (workspace / "versions" / version).is_dir():
                summary.append("阻塞=激活版本文件缺失，先报告状态不一致，不覆盖重建。")
    summary.append("按CLAUDE.md路由请求；销售分析使用sales-analysis。此检查不证明MCP已连接，不自动构建或进化；进化提醒由官方插件hook负责。")
    return "".join(summary)


def main():
    root = Path(__file__).resolve().parents[2]
    try:
        context = workspace_context(root)
    except (OSError, ValueError, KeyError, TypeError) as error:
        context = f"当前Workspace是销售分析智能体。工作区配置异常：{error}。先报告并修复配置，不能声称已就绪。"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
