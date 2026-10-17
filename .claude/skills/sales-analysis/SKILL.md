---
name: sales-analysis
description: Analyze this Workspace's sales data or explain its business metrics, including sales, net revenue, refunds, channels, orders, customers and average order value. This skill applies to questions such as “第三季度净收入是多少”, “各渠道收入” and “退款怎么算”, using EvoOntology grounding and real query trajectories.
argument-hint: "<销售分析问题>"
---

# 销售分析

保持主会话执行，以用户实际问题为目标。通过当前实际可见的 `evo-semantic` 工具操作；延迟工具先按宿主方式发现，缺失工具时明确报告，不自行写 JSON 模拟 MCP。

## 定位和恢复

读取本工作区 `.evoontology/project.json` 和 `active.json`，以 `.evoontology` 的绝对路径作为每次 MCP 的 `workspace`。没有项目上下文或 active 版本时按根目录 `CLAUDE.md` 的初始化路由处理，不假定一定已有本体。

用 `ontology_workflow_status` 恢复与当前问题、本体版本和用户意图一致的未完成任务。不要结束其他任务；用户要求重新查询时新建任务，不把已有结果当成新执行。

## 按需访问语义

若宿主提供资源读取能力，在会话首次使用本体时读取 `evo-semantic://session-manifest` 的简洁工具说明；宿主未暴露资源读取时依据实际工具定义继续，不把缺少可选读取能力当作数据不可访问。

概念未知时用 `browse_semantics` 发现相关项。已知语义 ID 或明确概念时可直接解析，不强制先 browse。通过 `resolve_semantics` 或任务绑定的 `resolve_ontology_task` 获取 Mapping、Relation、Constraint、Evidence。每次最多解析五项，按分析需要继续导航，避免把整个本体塞入上下文。

派生指标沿依赖解析相关原始指标。遇到证据不足、业务口径冲突或数据结构变化时，再读取 `docs/business-policy.md`、元数据和代表性样本。业务条件、单位、粒度和时间归属从这些来源取得，不把示例口径当所有数据源的固定规则。查不到支持时记录限制。

仅解释概念时，以语义及证据回答，不创建没有原生数据执行的 completed 任务。

## 登记真实任务

数据分析需通过 `prepare_ontology_workload` 登记用户本次问题。传入 `questions` 和 `include_history:false`；从返回结果选出匹配问题的真实 ID，不假定排序、不覆盖已登记问题或配置。默认保留用户来源；生成的探索问题需有 `evidence_refs` 并保留 generated 来源。

调用 `start_ontology_task(question_id,version)`，把当前版本固定到任务，并保存返回的 `task_id`。使用 `resolve_ontology_task` 记录本任务实际采用的语义。为减少重复读取，可先创建任务再做绑定解析；不要求固定的 browse/resolve/登记先后顺序。若无适当语义对象，记录缺口后只读探索，不虚构知识支持。

## 查询与证据

根据映射和约束编写本次查询。表字段未知时先查结构。SQLite 使用 `execute_ontology_query(task_id,query,event_id)`，它在注册数据源上有界只读执行并自动记录。其他源通过宿主原生只读工具查询，随后用 `record_ontology_task_event` 保存实际输入输出。不得用固定脚本答案、旧页面或无执行的 SQL 代替真实结果。

核对问题对应的日期范围、金额单位、状态和过滤、退款归属、关联粒度及比率分母；具体值从当前证据取得。多笔退款和明细不能放大订单级金额。空数据不等于零收入，分母为零时比率无定义。

查询最多返回100行；聚合或分页，明确截断范围。事件 ID 在任务内唯一，相同观察重试才复用。保留真实错误，修正后继续；不改写已记录结果。不记录私有推理链。

## 完成与输出

取得原生结果后调用 `finish_ontology_task` 保存结论及必要口径。`completed` 表示执行完成，不代表独立验证正确；失败和中断分别记录 `failed`、`interrupted`。任务记录失败时明确说明。

回答给出结论、所需表格、期间、单位、主要口径、数据来源属性、本体版本及真实任务 ID。按需生成 `outputs/` 文件。用户未要求时不输出完整工具日志、不打开浏览器、不运行进化。

本流程是 Workspace 的业务接入技能。Build、Explore、Evolve 的方法和版本生命周期仍由官方插件技能负责，不在此复制实现。官方依据见 `docs/agent-definition.md`。
