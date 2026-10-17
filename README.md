# 销售分析智能体 Workspace

这个目录就是一个以 Claude Code 为运行底座的智能体。将 Claude Code 的工作目录设到这里，直接提出销售分析问题。会话自动读取 `CLAUDE.md`，使用项目技能查询 EvoOntology，再只读查询数据并记录真实任务。

角色、能力、初始化与进化阶段的完整定义，以及逐项官方依据，见 [智能体定义](docs/agent-definition.md)。本项目是按官方机制集成的销售智能体，不是官方发布的销售智能体模板。

## 直接启动和提问

```bash
gh repo clone indie-builder/ontology-evo
cd ontology-evo
claude plugin marketplace add ruc-datalab/EvoOntology
claude plugin install evoontology@evoontology
claude
```

第一次克隆后，在 Claude Code 中运行 `/setup-workspace`。它通过官方 MCP 将公开样例本体导入当前目录，使用当前机器的数据绝对路径初始化，不复制作者的会话或任务。已有本体时该命令不覆盖。

也可以不导入样例，要求 Claude 使用官方 `/evoontology:build-ontology`，从 `data/sales.sqlite`、业务说明和分析目标构建。

在对话里输入：

```text
2026年第三季度各渠道净收入是多少？
```

也可以问：

- 第三季度支付客单价是多少？
- 六月创建、七月支付的订单应该计入哪个季度？
- 退款为什么不能直接和订单连接后累计金额？

无需先启动网页、运行 demo.py 或手工指定 MCP 工具。需要显式选择分析流程时可用 `/sales-analysis <问题>`。

当前数据是合成销售样本。口径来自 [业务定义](docs/business-policy.md)，数字必须来自本次真实查询。静态演示页面和旧答案不是数据分析入口。

## Workspace 文件组织

```text
ontology-evo/
├── CLAUDE.md                       # 主智能体角色、默认路由和边界
├── .claude/
│   ├── settings.json               # 项目插件、分析工具权限、启动钩子
│   ├── hooks/session-start.py      # 检查数据与本体，注入当前绝对路径
│   └── skills/sales-analysis/
│       └── SKILL.md                # 语义解析、只读查询、任务记录流程
├── .evoontology/                   # 当前智能体的知识、版本和任务轨迹
├── data/sales.sqlite               # 当前合成数据源
├── docs/business-policy.md         # 业务规则来源
├── docs/workspace-verification.md  # 实际启动与问答验证记录
├── outputs/                        # 按需生成的分析交付文件
├── artifacts/                      # 开发验证证据
├── scripts/                        # 开发验证脚本
└── demo.py                         # 样本构造和辅助展示工具
```

`outputs/` 在用户首次要求导出时创建。`.loopx/` 和 `.audit/` 保存开发协作记录，不参与日常业务问答。

这里的主智能体由根目录 `CLAUDE.md` 定义。`.claude/agents/` 用于另行定义子智能体，本项目无需再创建同名子智能体。项目技能在当前主会话中执行。

## 默认执行流程

收到实际数据问题后，主智能体加载 `sales-analysis`，执行以下步骤。

1. 读取当前工作区的项目数据源与 active 本体版本。
2. 通过 `browse_semantics` 和语义解析获取口径、字段、约束和证据。
3. 登记用户问题，创建或恢复任务，固定使用的本体版本。
4. 使用官方 MCP 的只读 SQLite 查询工具执行真实 SQL，自动记录结果。
5. 结束任务，在回答中给出结论、期间、单位、口径和真实任务 ID。

只解释概念时查询本体，不创建没有数据执行的 completed 任务。查询失败或 MCP 不可用时明确报告，不生成虚构答案或轨迹。

本体构建、查看和进化分别通过官方插件技能触发。日常分析不会自动覆盖版本或开启进化。当前未配置独立进化评估器，公开样例检查不作为正式进化验证。

## 平台如何运行这个 Workspace

将每个智能体目录作为单独的工作目录。启动当前智能体时，把进程 `cwd` 设为本目录。保留 Claude Code 的默认系统指令和项目发现能力，不要使用会跳过项目指令的 `--bare` 或 `--safe-mode`。

交互启动时，首次接受这个工作目录的信任对话框，Claude Code 才会使用项目的权限放行规则。

无交互的平台由宿主审核并显式加载配置。本机验证使用以下命令，不跳过权限检查：

```bash
claude -p '2026年第三季度各渠道净收入是多少？' \
  --settings .claude/settings.json --output-format json
```

未信任的目录直接运行 `claude -p` 会忽略项目级权限放行，可能导致 MCP 工具被拒绝。平台只对自己审核、托管的 Workspace 显式加载配置，不应将任意上传的配置作为可信宿主配置。

如果平台使用 Claude Agent SDK，需在宿主按 SDK 的设置加载机制启用项目配置和项目指令，并配置工具授权。仅设置 cwd 不能替代宿主正确加载项目配置。项目目录不包含 API key，不覆盖平台选择的模型。

宿主需安装 Claude Code、Python 3.10 以上以及 `evoontology@evoontology`。`.claude/settings.json` 声明所需 marketplace 和插件，但声明不等于完成所有机器上的安装。新宿主准备：

```bash
claude plugin marketplace add ruc-datalab/EvoOntology
claude plugin install evoontology@evoontology
```

安装后用 `/mcp` 检查 `evo-semantic`。当前长会话如需刷新新插件工具，运行 `/reload-plugins --force`；全新会话直接加载。项目不重复定义 `.mcp.json`，避免加载两份相同 MCP。

## 复制成另一个智能体

复制角色、项目技能、项目配置以及所需业务文档，换成该智能体的数据源和目标。不要照搬此实例的旧轨迹作为新数据源的历史。

本体的 `project.json` 当前包含本机数据绝对路径。迁移目录或换机器后，明确重新配置数据源并验证本体映射；启动钩子报告注册文件缺失或项目未初始化，不静默修改。钩子不再限制数据库的文件名，也不证明仍可访问的旧路径属于新Workspace。换用全新业务数据时通过官方构建流程建立新工作区的本体。

项目 permissions 和 CLAUDE.md 指令不构成多租户文件隔离。平台仍需为各 Workspace 提供独立的进程权限、凭据和数据访问范围。

## 开发检查和辅助展示

```bash
python3 demo.py check
python3 demo.py verify-tasks
python3 demo.py serve
```

前两项检查公开合成数据和初始示例轨迹，第三项启动可选静态展示。

已实际启动新的 Claude Code 会话验证普通问题会自动使用本体并创建新轨迹，步骤见 [Workspace 验证记录](docs/workspace-verification.md)。原始会话、本机验证摘要和 `.evoontology/` 运行状态不提交到公开仓库。公开样例本体保存在 `examples/ontology_v0/`，数据库和算术探查证据可直接复跑。

`verify-tasks` 检查作者构建阶段的四个示例任务，仅在本地存在对应轨迹时可用。新克隆应实际提问后，使用 `scripts/verify-workspace.py` 检查自己的会话，不期待仓库携带作者历史。

初始化后可通过 `/evoontology:explore-ontology` 生成 `.evoontology/visualizations/ontology-layer-explorer.html`。已有 `ontology_v0` 时不要重复覆盖；重要版本先备份。当前插件存在同名版本写入保护不完整的已知问题。
