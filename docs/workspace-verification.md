# Workspace 智能体验证

验证目标是在当前目录启动全新 Claude Code 会话，只输入普通业务问题，检查项目指令、项目技能、MCP、真实查询和轨迹是否接通。

验收问题：2026年第三季度各渠道净收入是多少？

验收条件：

- 自动发现项目的 sales-analysis 技能。
- 实际调用 EvoOntology 语义解析。
- 使用当前注册 SQLite 数据源执行只读查询。
- 通过官方工具完成任务并留下新轨迹。
- 回复净收入和统计口径，不要求用户运行演示页面。

首次验证自动发现并调用了 sales-analysis，项目启动钩子执行成功，MCP 连接成功。但 ontology_workflow_status 被拒绝，未执行 SQL，未生成轨迹。第二次试验不同工具名称规则仍被拒绝，已经删除无效的替代规则。

根因是 `~/.claude.json` 中这个工作目录的 `hasTrustDialogAccepted` 为 false。Claude Code 2.1.302 在 `-p` 中不弹信任对话框，且不应用未受信任目录的项目级 allow 规则。官方依据是 https://code.claude.com/docs/en/permissions#project-allow-rules-and-workspace-trust 。没有修改全局信任记录。

修正测试方式由宿主显式提供 `--settings .claude/settings.json`，维持默认权限模式，仅授权项目列出的分析 MCP 工具。正式平台需审核所加载的配置。

## 通过的实际会话

2026-10-17 在项目根目录执行：

```bash
claude -p '2026年第三季度各渠道净收入是多少？' \
  --settings .claude/settings.json \
  --output-format stream-json --verbose --no-session-persistence \
  --permission-mode default --permission-prompts none \
  > artifacts/agent-session-host.jsonl
```

会话没有注入额外业务系统提示、没有指定技能，也没有跳过权限。当前宿主模型继承为 `codex/gpt-6.1-sol`，项目配置没有固定模型。

实际观察：

- SessionStart 项目钩子执行并注入工作区路径。
- 项目 `sales-analysis` 技能被自动调用。
- `plugin:evoontology:evo-semantic` 连接成功。
- 实际调用 browse、workload prepare、start task、resolve task、execute query、finish task。
- 保存新任务 `task_32e4e32493524ef7a48c080b39b40e05`，问题来源为 user。
- 执行两条真实 SQL，最终得到 web 360元、store 270元、ads 0元，合计630元。
- 未发生权限拒绝，源数据库哈希未变。

使用下面的检查重放会话中的已记录 SQL，逐项比较真实轨迹结果：

```bash
python3 scripts/verify-workspace.py artifacts/agent-session-host.jsonl
```

检查已通过，摘要保存在 `artifacts/workspace-verification.json`。检查曾针对第一次未完成会话正确报缺少实际工具调用；后续按官方按需导航协议移除了强制 browse 要求，仍要求真实语义解析、查询和完成记录。不能仅因 Claude 退出码为0就算完成分析。

## 对照官方实践后的复验

简化角色和按需导航流程、移除固定数据库文件名后，用相同自然语言问题启动新的会话，日志保存到 `artifacts/agent-session-practices.jsonl`。

`scripts/verify-workspace.py` 已验证该会话，自动加载技能和启动钩子、MCP连接、真实任务记录均通过；任务为 `task_3dc571f31ae1473ca2d0acbc6d90394a`，执行3条SQL，回放结果一致，无权限拒绝，数据库哈希不变。

`python3 -I tests/test_workspace_context.py` 的3项测试通过，覆盖未初始化、已配置未发布、自定义SQLite文件名、缺失数据与非法版本路径。调用顺序不是验收依据，验收真实语义使用与执行结果。

## DuckDB默认数据源复验

新增受控workspace-analytics MCP后，使用百万订单库和独立 `.evoontology/analytics` 执行全新会话：

```bash
claude -p '2026年第三季度各渠道净收入是多少？使用当前默认的扩展销售数据。' \
  --settings .claude/settings.json --mcp-config .mcp.json \
  --output-format stream-json --verbose --no-session-persistence \
  --permission-mode default --permission-prompts none \
  > artifacts/agent-session-duckdb.jsonl

uv run --no-project --with duckdb==1.5.6 python -I scripts/verify-workspace.py \
  artifacts/agent-session-duckdb.jsonl --workspace .evoontology/analytics
```

会话自动选择新数据源、读取本体、执行两条DuckDB SQL并将实际工具结果记录进官方轨迹；复跑一致、无权限拒绝、数据库哈希不变。任务 `task_8ea96907b36b4c029eec622fa89074d0` 得到第三季度净收入53,778,981.48元，属于合成业务结果。公开验证摘要在 `artifacts/duckdb-integration.json`。

查询边界测试覆盖写入、多语句、外部文件、网络读取、扩展安装、结果行数与字节限制、路径逃逸和超时错误分支。它们不是生产多租户或高并发压测。

交互终端首次启动仍需用户接受目录和项目MCP信任；平台headless通过宿主显式加载配置和工具授权。没有测试用户原平台SDK、远端环境或其他模型。
