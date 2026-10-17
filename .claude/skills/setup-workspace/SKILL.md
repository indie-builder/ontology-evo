---
name: setup-workspace
description: Initialize this cloned sales-analysis Workspace with its configured DuckDB analytics dataset and official EvoOntology sample, or the original SQLite example when explicitly requested.
disable-model-invocation: true
---

# 初始化克隆后的工作区

以根目录CLAUDE.md所在目录为Workspace。所有路径基于当前克隆位置。只操作当前工作区，不覆盖已有本体或生成数据。

## 选择数据源

默认读取 `config/analytics.json`，使用注册的database、ontology_workspace和business_policy。用户明确选择原12单SQLite样例时使用 `data/sales.sqlite`、根 `.evoontology`、`docs/business-policy.md` 和 `examples/ontology_v0`；否则使用 `examples/analytics_ontology_v0`。

DuckDB文件尚不存在时，说明将生成百万订单及Parquet副本。在当前根目录使用原生工具执行：

```bash
uv run --no-project --with duckdb==1.5.6 python -I scripts/generate-analytics.py --orders 1000000 --output data/generated/million-orders
```

命令输出目录必须为空。已存在但生成不完整时报告状态，不自动删除或覆盖。生成成功后检查manifest，确认合成数据来源和检查结果。若宿主禁止Shell，由宿主预先生成数据，不编造成功。

## 官方MCP发布

1. 确认官方evo-semantic已连接。DuckDB还需workspace-analytics MCP，调用analytics_status核对配置和实际schema；SQLite用原生只读工具核对。
2. 所选本体目录已有active.json时停止导入，报告已有版本。仅有project.json时复用，发现不同数据源先报告冲突。
3. 通过configure_ontology_project保存schema_version:1、mode:rolling_trajectory、data_source:{type:duckdb或sqlite,path:所选数据库绝对路径}，workload_source:{type:project_workload,source:public synthetic sales example}，evaluation:{type:public_construction_checks,formal_evolution_evaluator:not_configured,provenance:synthetic}，boundary:{strategy:rolling_trajectory,scope:public construction demonstration; no formal evolution evaluator}。DuckDB可追加query_tool:workspace-analytics.query。
4. 读取所选业务说明，查询元数据和代表性值，对照所选examples目录的证据。样例只适用于配套生成器，差异无法解释时停止导入，使用官方build-ontology为实际数据重新构建。
5. 将所选examples中的terms、mappings、relations、constraints、evidence五份JSON交给官方save_version写入ontology_v0。再annotate_ontology_version说明公开样例导入及限制，links可为空。最后publish_ontology_build初始化active和checkpoint，headless传open_browser:false。
6. 告知可直接提问。新任务由真实问答产生，不复制作者历史。用户希望观察从数据自主构建知识时改用官方evoontology:build-ontology，不将导入样例描述为自主发现。

EvoOntology内置execute_ontology_query仅执行SQLite。DuckDB数据查询使用workspace-analytics.query，并由主会话用record_ontology_task_event写入实际观察。
