# Workspace 智能体定义与官方依据

本目录定义一个销售分析智能体，运行载体是 Claude Code 主会话。Workspace 保存角色指令、按需工作流、业务数据、本体和任务历史。默认能力是根据当前数据源回答销售问题，并留下可追溯的真实观察。

这份定义采用 EvoOntology 的官方方法，将本体知识与 Agent 执行分开。它不训练模型，不提供多租户沙箱，也不把网页当智能体运行入口。

## 组件归属

| 责任 | 所在位置 | 原因 |
| --- | --- | --- |
| 主角色、请求路由、边界与回答约定 | `CLAUDE.md` | Claude Code 每会话加载，保留适用于本智能体的短规则 |
| 分析流程 | `.claude/skills/sales-analysis/SKILL.md` | 按业务问题加载，连接主会话与官方任务工具 |
| 插件依赖、工具放行、启动事件 | `.claude/settings.json` | 原生 Claude Code 项目配置，模型与凭据由平台继承 |
| 当前状态检查 | `.claude/hooks/session-start.py` | 确定性读取状态并提示；不启动分析或重写配置 |
| 业务定义、映射、约束与证据 | `.evoontology/versions/` 与业务来源文档 | 通过 MCP 按需导航，不将完整知识复制进角色提示 |
| 数据查询和任务记录 | workspace-analytics查询DuckDB，官方evo-semantic记录任务；SQLite用官方内置工具 | 保存真实输入输出，完成任务不代表独立验证正确 |
| 默认数据源和独立本体选择 | config/analytics.json | 默认百万订单DuckDB及.evoontology/analytics，原SQLite本体保留 |
| 有界查询入口 | .mcp.json与scripts/analytics-server.py | 固定数据源、禁止外部访问和写入，限制执行时间与返回量 |
| Build、Explore、Evolve | 官方 EvoOntology 插件技能 | 复用官方算法与生命周期，不在项目复制另一套 |

`.claude/agents/` 用于独立上下文中的子智能体。当前 Workspace 本身是主智能体，无需重复定义一个同名子智能体。未来确有独立审查或专门领域任务时才增加子智能体。

## 请求和生命周期

| 当前状态或请求 | 行为 |
| --- | --- |
| 未配置项目、未发布本体 | 说明当前状态；用户要求接入或初始化后走官方 Build |
| 已有 active 本体，用户问数据 | 按需解析语义，固定任务版本，真实查询，保存轨迹并回答 |
| 用户问概念 | 查询语义和证据，不制造已执行数据任务 |
| 用户要求查看知识或历史 | 官方 Explore 渲染只读浏览器 |
| 用户要求改进本体 | 官方 Evolve；有运行中 run 则恢复，先具备可信runner和evaluator |
| 达到30条新轨迹或7天 | 官方 SessionStart hook 提醒，不自动开始进化 |
| 缺失数据、MCP或评估 | 报告具体限制，不造数、不假通过、不推进checkpoint |

浏览语义和解析语义是按需导航，不强制每个问题先 browse 再 resolve。业务规则从当前映射、约束、证据和明确业务文档取得。SQL及最终任务答案保留在任务轨迹，不把答案或操作策略塞进语义对象。

## 构建、应用和进化边界

Build 以用户问题、同数据源项目历史和有证据的探索问题形成 workload，生成五类记录。首次发布按 `save_version`、`annotate_ontology_version`、`publish_ontology_build` 完成。当前已有 `ontology_v0`，不重建覆盖。

普通分析通过任务工具记录真实观察，不保存私有推理链。合成探索问题、用户问题与历史来源必须保留。公开构建回放不是独立验证数据。

Evolve 复用项目上下文和已授权来源，冻结批次和轮次预算。Candidate 与 Parent 以独立版本参评，不在比较时切换 active。通过 gate 才发布新正式版本和推进checkpoint；Reject继续同一个run，Incomplete保留Parent。当前项目未配置正式评估器，维持该限制，不虚构改进。

## 平台职责

平台为每个智能体设置独立 cwd，安装所需官方插件，加载项目指令和项目配置。交互终端首次接受工作目录信任；无交互宿主审核后显式加载settings或提供自己的受控权限配置。项目文件不保存凭据，不指定平台模型。

项目允许工具只能按工具名控制，不能保证工具参数始终指向本Workspace。多租户隔离需要平台的进程、文件系统、工具参数授权与凭据边界。CLAUDE.md是模型指令，不能当访问控制。

启动钩子仅提示注册状态，兼容未初始化、配置后未发布、数据缺失和现有版本。它不验证MCP连通性，也不自动修正迁移后的绝对路径。换机器时明确更新官方项目配置并校验数据映射。

## 本次与官方对照后的调整

- 缩短主角色定义，删除文件清单和重复操作细节；详细方法放按需技能和本文件。
- 去掉分析技能的强制browse顺序和重复的样例业务常量。
- 去掉钩子对固定数据库文件名的要求，从已保存项目上下文读取数据源，并报告分阶段状态。
- 保留官方进化提醒，不再实现第二套触发器或后台自进化。
- 验证关注真实语义使用、只读执行和轨迹，不把browse次数当效果。

## 官方来源

EvoOntology以本机安装1.1.1及仓库提交c94389b的内容核对。Claude Code最佳实践文档于2026-10-17读取。项目定制分析技能是本Workspace的集成选择，不宣称官方提供了同名销售智能体模板。

- [EvoOntology产品化使用指南](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/USAGE.zh-CN.md)，工作区初始化、官方技能与生命周期。
- [EvoOntology语义交互协议](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/build-ontology/references/ontology-interaction-protocol.md)，按需导航及真实数据证据。
- [EvoOntology workload与可观察任务](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/build-ontology/references/workload-experience.md)，来源和真实任务记录。
- [EvoOntology Evolve skill](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/evolve-ontology/SKILL.md)，评估准备、预算和验证隔离。
- [Claude Code最佳实践](https://code.claude.com/docs/en/best-practices)，简洁CLAUDE.md、按需技能、事件钩子与真实验证。
- [Claude Code权限与工作区信任](https://code.claude.com/docs/en/permissions#project-allow-rules-and-workspace-trust)，项目allow规则及headless授权边界。
