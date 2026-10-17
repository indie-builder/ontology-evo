# 实现逻辑与持续迭代

这份指南面向要复现、接入平台或继续开发的人。当前可运行系统是Claude Code Workspace、官方EvoOntology插件和本项目DuckDB查询工具，36表复杂企业模型仍为下一阶段设计。

## 从用户问题看实现

用户问“第三季度各渠道净收入是多少”。模型需要确定期间、订单范围、退款截止和单位，再读取数据。系统分工如下。

1. Claude Code在项目cwd启动，加载根CLAUDE.md、项目settings和技能元数据。SessionStart脚本只报告路径和初始化状态，不代表已连接数据库或MCP。
2. 普通销售问题触发sales-analysis。技能不另起LLM循环，而是在主会话中指导工具使用。
3. analytics_status返回config/analytics.json绑定的数据库、业务文档、本体目录和schema首页。需要更多结构时调用schema并跟随next_cursor，不能将截断首页当完整目录。
4. 主会话从所选本体project.json、active.json读取数据源和版本。browse用于发现未知概念；已知概念可直接resolve。定义、字段、grain和约束来自官方本体及证据，不从表名猜业务。
5. prepare_ontology_workload登记问题，start_ontology_task固定版本。resolve_ontology_task把实际语义使用加入轨迹。
6. query工具执行本次SQL，模型收到真实结果后立即调用record_ontology_task_event。最终finish_ontology_task保存答案和限制，主会话向用户回答。

执行顺序可以按需求调整，但数据源不能混用，结果不能伪造，任务完成不能代替业务正确性证明。解释概念不必创建已执行数据任务。

## 为什么使用两个MCP

官方evo-semantic提供语义导航、版本、任务、构建和进化会话。它的execute_ontology_query只支持SQLite。项目不复制或修改其运行时，而是在.mcp.json声明workspace-analytics，负责DuckDB读取。

数据工具返回观察，官方任务工具保存观察。因此DuckDB数据源可以接入官方轨迹，不需要自造新的本体字段或改SQLite执行器。将来平台接远端数仓时，也是替换数据查询实现，保留语义与记录边界。

## 数据、知识和结果分别保存

| 内容 | 位置与来源 | 更新方式 |
| --- | --- | --- |
| 主智能体行为 | CLAUDE.md和项目技能 | 工程修改、测试、PR |
| 数据工具及授权 | .mcp.json、settings、analytics-server.py | 平台审核配置和代码 |
| 数据源选择 | config/analytics.json | 显式选择，同步检查本体数据源 |
| 原始业务数据 | data/generated/或平台数仓 | 数据流程，不由LLM任意改写 |
| 业务来源文档 | docs/analytics-policy.md等 | 明确业务变更，保留审阅 |
| 本体知识 | .evoontology/analytics/versions | 官方Build和Evolve工具发布 |
| 问题及执行轨迹 | 所选.evoontology下workload、tasks、trajectories | 官方工具记录真实执行 |
| 样例本体 | examples/analytics_ontology_v0 | 已知合成数据的便携种子，导入不等于自主发现 |
| 本地原始会话 | artifacts/agent-session*.jsonl | headless运行生成，不提交Git |
| 可公开检查摘要 | artifacts/*.json | 验证脚本生成，不能当实时查询答案 |

配置中的相对路径解决项目复制，官方project中的数据库路径按工具约定为绝对路径。迁移机器需要明确重新配置，不能静默沿用作者路径。两个数据源的ontology_v0名称相同并不表示同一份知识，任务必须携带准确workspace和版本。

## 查询边界怎么实现

analytics-server.py使用官方MCP SDK的stdio服务，每次query启动独立Python工作进程。服务端解析DuckDB语句类型，仅接受单条SELECT或WITH。数据库read_only打开，外部访问和自动扩展关闭，连接配置锁定。

工作进程有15秒外层期限，查询约10秒触发引擎interrupt。DuckDB配置512MB内存、256MB临时空间，结果最多100行和64KB。超限明确截断，非有限数值保留为文本。schema分页独立于数据结果大小。

这些机制限制当前工具行为，不是多租户沙箱。memory_limit不是进程RSS硬限制；用户若能调用任意Shell或修改配置，仍需要平台权限控制。生产不能靠“模型会写tenant_id条件”隔离数据。

## 开发者怎么从零搭建

第一步先确认运行环境和依赖。安装Claude Code、uv和Python3.10以上，完成Claude Code登录或平台认证，不把凭据写入项目。

```bash
gh repo clone indie-builder/ontology-evo
cd ontology-evo
claude plugin marketplace add ruc-datalab/EvoOntology
claude plugin install evoontology@evoontology
```

第二步生成默认配套数据。该命令无需调用模型，但会下载依赖并写本机数据库、Parquet和manifest。

```bash
uv run --no-project --with duckdb==1.5.6 python -I scripts/generate-analytics.py \
  --orders 1000000 --output data/generated/million-orders
```

输出目录须为空，失败时检查原因或使用新空目录，不删除未知数据。如果改用别的目录，同时显式更新config绑定；本体已经存在时还需核对其数据源。

第三步验证数据工具。

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/analytics-server.py --query 'SELECT COUNT(*) AS orders FROM orders'
```

应返回1000000。未生成数据应报缺失，不应偷偷回退到12单样例。

第四步启动Claude Code，接受工作目录与项目MCP信任，用/mcp检查两个服务。运行/setup-workspace导入配套本体，或要求官方build-ontology基于同一数据源和分析目标构建。默认生成数据步骤已完成时setup复用，不应覆盖。

setup本身是一份由Claude执行的技能，不是确定性一键安装程序；其效果依赖宿主权限和插件状态。已有本体时停止覆盖。官方发布必须走save_version、annotate_ontology_version、publish_ontology_build，不自行复制active.json。

第五步直接问业务问题，确认回答带来源限制及真实任务ID，再运行本地回归与会话验收。安装成功、MCP connected和模型退出码0都不足以证明业务任务完成。

## 平台嵌入

平台为每个智能体设置cwd，并加载主指令、项目配置、技能和所需MCP。项目不强制模型，平台选择模型及认证方式。

```bash
claude -p '2026年第三季度各渠道净收入是多少？' \
  --settings .claude/settings.json --mcp-config .mcp.json \
  --output-format stream-json --verbose --no-session-persistence \
  > artifacts/agent-session-local.jsonl
```

先确保artifacts目录存在。无交互模式不会展示目录信任窗口，项目allow可能被忽略；宿主只能对自己审核过的配置显式授权。不能把用户上传的任意settings当宿主可信政策。Agent SDK另需按其设置加载机制启用项目指令和工具，本仓库没有提供可直接粘贴的SDK宿主实现。

生产数据建议集中存储。查询服务负责只读账号、tenant/行列授权、数据快照、查询取消、排队、并发、扫描及资源配额；Workspace保存知识与结果引用。DuckDB适合本地实验和受控数据子集，不要求给每个Workspace复制生产全量数据。

## 持续迭代分成四条路径

| 改动类型 | 例子 | 应改哪里 | 验证 |
| --- | --- | --- | --- |
| 智能体行为 | 未知口径先查证、错误后重试 | CLAUDE.md、sales-analysis | 新会话真实问题与任务证据 |
| 查询和数据访问 | 分页、超时、新后端 | analytics-server.py、配置和平台工具 | 先复现、回归边界、实际MCP |
| 业务数据模型 | 新退款行分摊或客户历史 | 生成器、来源文档、schema | 外键、时间、金额/数量守恒与负例 |
| 本体知识 | 映射遗漏、grain错误、概念范围不足 | 官方Build/Evolve | 真实轨迹、独立验证、版本门控 |

不要把代码改动和本体更新混为一次“自学习”。工程PR审查代码是否正确；EvoOntology评估候选本体是否真正改善分析。两者可以关联，但不能相互替代。

每轮工程迭代遵循：选择一个实际失败或明确需求，复现；修根因；跑相关测试；跑全套适用检查；用新会话确认行为；审查公开边界；PR独立审查后合并。仅文档改动检查链接、命令与实现一致即可，不需要无意义重跑付费模型。

## 本体怎样持续改进

日常任务通过官方start、record、finish积累轨迹，不靠聊天自动学习。达到官方阈值时提醒，人决定是否进化。

用户要求改进时调用官方evolve-ontology。恢复已有run，确定目标、预算及数据来源。将设计轨迹和独立验证分开；同一业务case的近似问法不要跨集合。Candidate验证一个主要机制，通过评估后官方accept发布，再finalize展示。

没有可靠runner、evaluator或足够隔离数据时保留Parent并报告缺失。当前项目只有公开构建检查，尚未配置正式进化评估器，不能用同一公开题反复修补后声称准确率提升。

本体仅保存官方五类记录。SQL模板、执行指令和本次标准答案不塞入Term或Constraint。若发现表达能力不足，按官方Content/Tool/Schema诊断，不能在Build时暗中增加对象族。

## 复杂模型下一步怎么落地

36表设计保留支付分配、履约、退货退款、历史归属、币种与财务对账的难点。下一步按可验证批次实施：

1. 生成小而可人工核账的多对多支付、拆仓履约和退款案例，运行现有关系检查。
2. 准备公开问题和覆盖图，让官方Build比较候选grounding并提交证据，不预制逐题答案。
3. 验证扇出、时点、缺联合分摊时的拒绝行为，形成真实轨迹。
4. 接入结算、收入确认、成本及总账，再验证跨币种与对账差异。
5. 具备独立验证后才评估本体进化；关系正确后再增加数据量和并发。

使用新数据集和新本体目录，满足数据检查、代表性问答和旧样例回归后才切换默认源。当前不能仅修改config指向DDL空库，就认为复杂智能体已完成。

## 如何判断一次迭代真的完成

本地自动检查：

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/validate-all.py
```

真实会话证据检查：

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/validate-all.py --session artifacts/agent-session-local.jsonl
```

默认验收所选analytics本体，其他本体传--workspace。原始会话当前需位于项目目录内；不要把包含敏感信息的会话提交Git。验收会核对技能、实际宿主响应、任务结果和有界SQL回放，但它不是独立业务oracle，也不证明生产安全或性能。

保存失败前证据和通过后证据，标出未实现内容。历史报告是一次快照，运行validate-all会重新生成artifacts/full-validation.json；无需把耗时变化当成性能提升。

## 常见问题

| 现象 | 排查方向 |
| --- | --- |
| MCP连接前数据库不存在 | 先生成配置中的数据，别改用其他库 |
| 工具显示connected但调用被拒绝 | 目录信任、项目allow及宿主权限，不能靠伪造工具结果跳过 |
| 缺schema或只看见一部分 | schema分页和next_cursor，按表缩小范围 |
| 问题登记成功但无轨迹 | start后必须真实执行并finish；中断任务先恢复 |
| 回答有数字但无实际工具响应 | 验收不通过，不拿旧页面或固定答案充数 |
| 品类净收入无法计算 | 检查是否缺退款明细或已授权分摊政策，不能硬平均 |
| 换机器后本体仍指旧路径 | 显式重新配置，旧轨迹不当新源历史 |
| 查询被截断或超时 | 下推聚合、缩小范围、说明限制，不擅自放开资源 |

更多依据见README中的官方来源、[智能体定义](agent-definition.md)、[复杂业务设计](enterprise-analytics-design.md)和[验证修复记录](validation-and-fixes.md)。
