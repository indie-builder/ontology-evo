# 完整验证与修复记录

2026-10-17使用LoopX在已有Workspace执行验证。范围为当前六表百万订单DuckDB智能体、原SQLite样例、36表设计DDL与公开关系反例。36表生产运行时尚未实现，不将设计检查当作完整业务Agent验收。

## 发现并修复

| 问题 | 复现 | 修复与验证 |
| --- | --- | --- |
| 64KB预算未包含最后添加的limits元数据 | 返回65460字符的数据行触发误导性metadata超限错误 | 先加入完整元数据再决定截断，边界测试通过 |
| schema只读取main且最多100列 | enterprise schema中的120列无法通过原status完整发现 | 增加schema(schema,table,cursor)，status给首页游标，120列两页无重复无遗漏 |
| SKU类目桥缺少引用外键 | 插入不存在的SKU与类目仍成功 | 添加tenant复合外键；缺引用负例拒绝 |
| 退款和收入确认的可选引用无约束 | return_line_id、fulfillment_line_id存在非空孤儿风险 | 添加可空复合外键，跨行检查验证引用对象与订单行一致 |
| 未映射客户被强制要求规范客户ID | customer_id NOT NULL与unmapped状态矛盾 | unmapped允许且要求空ID，confirmed必须非空，测试通过 |
| 正常微样本不足以证明复杂关系质量 | 缺分摊和历史区间重叠不会被现有脚本报告 | 新增quality-checks.sql，检查时间重叠、分摊、金额和数量、币种、借贷平衡；负例测试通过 |
| 轨迹验收只比对写入的结果和SQL | 未要求结果确实来自宿主实际MCP响应 | 从host transcript提取对应tool_use/tool_result，逐项匹配记录及结果列，再复跑SQL |

数据质量SQL针对完整快照，可报告迟到和部分批次的未覆盖，不自动修复账务金额，也不替代官方语义方法。本轮追加修复了组织/类目环检查，保持双时间交集以避免历史误报；完整lineage、跨版本政策选择和独立oracle仍不在已实现范围。

## 实际端到端问答

使用一个全新Claude Code会话同时提出渠道净收入和品类净收入问题，未提供SQL或本体对象ID。

- 自动使用sales-analysis、独立analytics本体和workspace-analytics MCP。
- 渠道净收入结果53,778,981.48元，实际查询且有独立汇总核对。
- 品类净收入因缺少商品退款关联及分摊规则明确无法可靠计算，只输出未扣退款的品类支付金额。
- 两个任务共5条SQL，实际MCP响应、轨迹内容、结果列与数据库复跑一致，未出现权限拒绝。
- 数据库哈希保持不变。原SQLite公开口径检查仍通过。
- 对真实巨大交叉积查询执行超时检查，DuckDB返回 `INTERRUPT Error: Interrupted!`，工作进程正常结束；证据在artifacts/query-timeout-check.json。

这些是合成数据功能检查，不代表生产准确率、海量并发性能或正式进化改进。问题来源、真实结果和限制由官方任务工具持久化；不保存私有推理链。

## 执行问题追加修复

- 组织和类目中实际共存的循环关系原来未被检查。新增递归检查，沿路径交集业务有效时间与系统已知时间，实际共存的环会报告，跨时期合法变更不误报。
- DuckDB查询错误原来被宿主证据提取丢弃，验收又要求每条查询成功，导致已正确恢复的任务不能通过。现在保留真实error响应，检查轨迹error标记一致，完成任务至少有一条成功数据查询。
- 验收复跑原来直接连接DuckDB，绕过受控查询的外部访问、结果和进程超时限制。现在固定到配置中的同一数据源，使用bounded_query复跑，不执行无界结果提取。
- 非有限浮点结果NaN和Infinity原来输出为非标准JSON数字。现在保留为明确文本，严格JSON序列化检查通过，不把它们变成零。

补充真实Claude Code错误恢复会话，任务中先保留缺列Binder Error，再成功查询1,000,000单。宿主工具响应、两条轨迹记录和有界复跑验收通过，成功查询1条、真实错误1条，数据未修改。

当前全套19项测试通过。当前机器可运行：

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/validate-all.py --session artifacts/agent-session-error-recovery.jsonl
```

## 合并前独立审查修复

独立Opus审查在隔离checkout复现：CNY支付可以关联同数字的USD结算，质量检查却返回空结果。新增结算、发票和收入确认分摊的币种及小数位检查；跨币种需要显式换汇桥，当前设计没有该桥时报告不匹配。新增测试先复现空检查集，再验证三类异常被识别且同币种修正后无异常。第二轮审查又发现总账到收入确认桥的同类缺陷，已连同成本到履约桥补齐币种与小数位检查，分别覆盖异币种、同币不同小数位和正常匹配。全套现为21项测试通过。

## 复跑

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/validate-all.py
```

当前机器还可用本地会话证据复跑端到端验收：

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/validate-all.py \
  --session artifacts/agent-session-full-validation.jsonl
```

原始会话与运行本体不提交公开仓库。其他机器需先setup并执行自己的会话，再传入其路径。无session参数只执行本地测试、36表结构与关系检查、SQLite数据检查，不宣称重新执行过LLM。

最终报告是 `artifacts/full-validation.json`。本轮16项测试通过。LoopX任务为full-validation-repair。当前goal禁止子Agent，因此没有独立审查结果；没有执行Git提交或远端推送。
