---
name: setup-workspace
description: Initialize this cloned sales-analysis Workspace from the public synthetic dataset and sample ontology using the official EvoOntology MCP tools.
disable-model-invocation: true
---

# 初始化克隆后的工作区

以根目录 `CLAUDE.md` 所在目录为当前Workspace。所有路径基于当前克隆位置解析，不使用其他机器的绝对路径。只操作当前工作区。

1. 确认官方 `evo-semantic` MCP 已连接，`data/sales.sqlite` 存在。数据库是公开合成样本，业务定义见 `docs/business-policy.md`。
2. 如果 `.evoontology/active.json` 已存在，报告已有版本并停止初始化，不覆盖。若仅有 project.json，则读取复用，发现不同数据源时先说明冲突。
3. 调用 `configure_ontology_project`，workspace 为当前根目录下 `.evoontology` 的绝对路径。project 使用 schema_version:1、mode:rolling_trajectory，data_source:{type:sqlite,path:当前data/sales.sqlite绝对路径}，workload_source:{type:project_workload,source:public synthetic sales example}，evaluation:{type:public_construction_checks,formal_evolution_evaluator:not_configured,provenance:synthetic}，boundary:{strategy:rolling_trajectory,scope:public construction demonstration; no formal evolution evaluator}。
4. 用原生只读工具检查SQLite结构和代表性值，与业务文档和 `examples/ontology_v0/` 中的证据核对。样例只适用于这份未修改的数据，发现差异时停止导入，改用官方 build-ontology 对实际数据重新构建。
5. 读取 `examples/ontology_v0/` 下 terms.json、mappings.json、relations.json、constraints.json、evidence.json。将五组原始记录交给官方 `save_version` 保存为 ontology_v0，不能自行替代官方发布生命周期。
6. 调用 `annotate_ontology_version`，说明这是公开合成样例的导入，不是新发现或独立评估，links 可为空；限制包括无生产数据、无独立进化评估、支付群组净额不代表财务确认收入。
7. 调用 `publish_ontology_build` 发布，初始化active和checkpoint。仅用户要求展示时打开浏览器，headless时传 open_browser:false。
8. 报告初始化结果，提示直接提出销售问题。任务和轨迹由后续真实分析产生，不从作者机器复制。

全新数据集或希望观察自动知识构建时，直接使用官方 `evoontology:build-ontology` 技能，以用户问题和底层数据证据构建，不导入本样例。
