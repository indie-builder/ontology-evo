# EvoOntology 销售分析智能体 Workspace

一个目录就是一个以 Claude Code 为底座的智能体。进入这个目录后，直接用自然语言提问，主会话按需查询业务本体、执行只读数据分析，并记录可追溯的真实任务。

本项目参考并集成 **[ruc-datalab/EvoOntology](https://github.com/ruc-datalab/EvoOntology)**。知识构建、语义导航、任务轨迹与本体进化沿用其官方方法。本项目增加销售业务场景、DuckDB查询工具、合成数据和回归验证，不是EvoOntology官方销售模板，也不修改其核心实现。

## 项目状态

| 能力 | 当前状态 |
| --- | --- |
| Claude Code主会话、项目技能、启动上下文 | 已实现，已用全新会话验证 |
| 百万订单六表DuckDB及Parquet样例 | 已生成并验证，生成文件不提交Git |
| 受控DuckDB查询、元数据分页、真实轨迹 | 已实现，含错误恢复和不支持口径的回答验证 |
| 36表复杂企业关系模型 | 设计DDL及公开关系反例可执行，完整业务运行时尚未实现 |
| 正式本体进化 | 复用官方流程；本项目未配置独立评估器，不宣称进化效果 |
| 生产多租户与并发 | 由平台提供隔离、凭据和调度，本样例未完成生产验收 |

## 与官方项目的关系

EvoOntology维护业务语义，数据引擎提供查询，Claude Code负责根据问题探索与分析。

```text
用户业务问题
  → Claude Code读取CLAUDE.md并加载sales-analysis
  → 官方browse/resolve按需取得概念、映射、约束和证据
  → workspace-analytics只读查询DuckDB
  → 官方任务工具记录实际调用、结果和最终答案
```

遵循以下官方实践：

- 从workload与数据证据构建知识，不把表结构机械转换成术语。
- 保持Term、Mapping、Relation、Constraint、Evidence五类记录，不另造指标DSL或语义规划器。
- 本体保存业务含义及证据，SQL和本次任务答案留在执行轨迹。
- 语义结果用于定位和约束，最终数字来自真实数据查询。
- Build、Explore、Evolve使用官方技能与MCP发布生命周期；进化提醒不自动触发更新。
- Candidate与Parent按官方数据边界评估，公开构建回放不冒充独立验证。

主要参考资料：

- [EvoOntology中文介绍](https://github.com/ruc-datalab/EvoOntology/blob/master/README.zh-CN.md)
- [产品化使用指南](https://github.com/ruc-datalab/EvoOntology/blob/master/USAGE.zh-CN.md)
- [官方Build技能](https://github.com/ruc-datalab/EvoOntology/blob/master/plugins/claude-code/skills/build-ontology/SKILL.md)
- [语义结构与交互协议](https://github.com/ruc-datalab/EvoOntology/tree/master/plugins/claude-code/skills/build-ontology/references)
- [官方Evolve技能](https://github.com/ruc-datalab/EvoOntology/blob/master/plugins/claude-code/skills/evolve-ontology/SKILL.md)

本机验证使用EvoOntology插件1.1.1。设计依据核对仓库提交 `c94389b764394379086ff25e50d0e0f4396167b4`；固定版本的来源链接和职责对应见[智能体定义](docs/agent-definition.md)。

## 快速开始

需要Claude Code、Python3.10以上和[uv](https://docs.astral.sh/uv/getting-started/installation/)。查询工具固定使用DuckDB1.5.6与MCP SDK2.3.0，由uv隔离加载；首次启动需下载依赖。本地实测使用Python3.14。

```bash
gh repo clone indie-builder/ontology-evo
cd ontology-evo
claude plugin marketplace add ruc-datalab/EvoOntology
claude plugin install evoontology@evoontology
claude
```

首次接受工作目录和 `workspace-analytics` 项目MCP配置。在Claude Code中运行：

```text
/setup-workspace
```

该技能生成百万订单DuckDB与Parquet，检查样例后通过官方MCP将配套本体发布到 `.evoontology/analytics`。它是已知样例导入，不宣称自主发现；已有版本不覆盖，不复制作者会话或轨迹。全新克隆的完整setup技能仍需按宿主权限完成，数据生成、官方发布和初始化后的真实分析已分别实测。

若希望观察从数据探索知识，使用官方 `/evoontology:build-ontology`，明确针对 `config/analytics.json` 的数据源、分析目标和 `docs/analytics-policy.md` 构建，而不导入样例本体。

初始化后直接问：

```text
2026年第三季度各渠道净收入是多少？
```

也可以问客户地区、支付客单价或退款口径。请求不具备数据依据的品类退款分摊时，智能体应报告缺口，不猜分摊规则。无需打开网页或手工指定工具；可用 `/sales-analysis <问题>` 显式选择流程。

当前均为合成数据，金额不能代表真实经营结果。

## 数据与存储选择

| 数据层级 | 用途 |
| --- | --- |
| `data/sales.sqlite`，12笔订单 | 人工核对日期、单位、状态及关联重复的微样例 |
| 六表扩展样例，默认百万订单 | 客户、商品、订单、明细、退款、投放分析；输出DuckDB和分区Parquet |
| `design/enterprise/`，36表 | 多对多支付分摊、拆单履约、退货退款、双时间历史及财务对账的下一版设计 |

可独立生成其他规模，不覆盖已有目录：

```bash
uv run --no-project --with duckdb==1.5.6 python -I scripts/generate-analytics.py \
  --orders 100000 --output data/generated/analytics
```

10万和100万订单版本已实际生成并验证。默认数据绑定仍由 `config/analytics.json` 决定，生成新目录不会自动切换本体。用户明确选择原12单SQLite时使用独立根 `.evoontology`，不混用扩展库映射。

生产建议是共享数仓或数据湖保留全量数据，Workspace保存角色、语义、工具绑定和任务引用。DuckDB用于受控本地分析或Parquet子集查询，不因数据量大就默认替代生产分析平台。详见[数据样本与存储选型](docs/data-and-storage.md)。

## 查询与任务边界

EvoOntology1.1.1的内置 `execute_ontology_query` 只执行SQLite。本项目通过独立的 `workspace-analytics` MCP查询DuckDB，再用官方 `record_ontology_task_event` 和 `finish_ontology_task` 保存实际观察；不重复加载EvoOntology MCP。

查询服务固定配置中的数据库，不接受任意路径；拒绝写入、多语句、外部文件与网络访问和扩展安装。单次最多100行、64KB结果，工作进程期限15秒，DuckDB内存512MB、临时磁盘256MB。元数据按schema和table分页。非有限数值明确返回文本，不能当正常指标值。

这些限制不等于完整沙箱，DuckDB内存设置也不是进程RSS硬限制。租户权限、文件系统隔离、凭据、并发及容器配额仍由宿主平台负责。

## Workspace目录

```text
CLAUDE.md                         主智能体角色与请求路由
.claude/settings.json             插件、分析工具权限与启动事件
.claude/skills/                   分析与初始化技能
.mcp.json                         DuckDB查询MCP
config/analytics.json             数据源、本体和业务文档绑定
data/sales.sqlite                 原始微样例
data/generated/                   本机生成数据，不提交Git
examples/                         可导入的五类本体记录
.evoontology/                     本机知识版本、任务与轨迹，不提交Git
design/enterprise/                36表设计和关系质量检查
docs/                            业务口径、设计、验证及修复说明
scripts/                         生成、查询及验证入口
tests/                           本地回归检查
artifacts/                       可公开的验证摘要
```

`.claude/agents/`用于独立子智能体，当前Workspace自身由主会话承担，无需重复定义子智能体。`outputs/`在请求导出时创建。原始会话、凭据、生成数据和LoopX内部状态不提交。

## 平台无交互运行

设置进程cwd到Workspace，保留项目指令发现；不要使用会跳过它们的 `--bare` 或 `--safe-mode`。审核项目配置后可显式加载：

```bash
claude -p '2026年第三季度各渠道净收入是多少？' \
  --settings .claude/settings.json --mcp-config .mcp.json --output-format json
```

未受信任目录的 `claude -p` 不应用项目级allow规则。平台不能把任意上传配置自动当可信宿主配置。使用Agent SDK时，宿主还需启用项目设置、指令与工具授权。项目不保存API key，也不覆盖平台模型。

换机器或数据源时明确重新配置本体中的数据绝对路径和映射，不能只复制旧轨迹。启动钩子只报告文件状态，不证明MCP已连接。使用 `/mcp` 检查语义与数据工具。

## 验证与修复

```bash
uv run --no-project --with duckdb==1.5.6 --with mcp==2.3.0 \
  python -I scripts/validate-all.py
```

当前21项回归测试、36表DDL与公开关系反例、SQLite算术检查通过。上面命令不调用LLM。已有本地会话时可追加 `--session <会话.jsonl>`，验证实际工具响应、轨迹和有界SQL复跑；原始会话不随仓库分发。

实际会话已验证：渠道净收入、缺乏退款分摊时拒绝品类净收入，以及先发生Binder Error再修正查询的任务恢复。详见[验证与修复记录](docs/validation-and-fixes.md)、[Workspace实测](docs/workspace-verification.md)和[完整检查摘要](artifacts/full-validation.json)。这些不是生产性能或独立模型准确率评测。

## 复杂业务设计与后续边界

[企业复杂分析设计](docs/enterprise-analytics-design.md)包含36表粒度、键、多对多桥、双时间、币种、指标范围、验证和迁移方案，并逐项对应EvoOntology官方方法。

DDL和公开反例已运行，包括200元支付被错误多事实JOIN算成500元、SUM DISTINCT误算成100元、历史归属、迟到退款、跨租户引用和分摊检查。完整36表数据生成与官方Build问答尚未实现，当前默认仍是六表扩展样例。

进化继续使用官方 `/evoontology:evolve-ontology`。当前没有独立评估器，不能用公开构建题宣称进化成功；旧版本不直接覆盖。可用 `/evoontology:explore-ontology` 查看当前知识和任务。

## 来源与致谢

- [EvoOntology](https://github.com/ruc-datalab/EvoOntology)：本项目主要参考与集成对象，提供官方插件、语义结构、Build/Evolve/Explore方法和确定性核心。
- [Claude Code最佳实践](https://code.claude.com/docs/en/best-practices)：主会话、CLAUDE.md、按需技能、钩子和验证组织。
- [DuckDB文档](https://duckdb.org/docs/current/)与[MCP Python SDK](https://py.sdk.modelcontextprotocol.io/)：本地分析引擎和独立数据工具接入。

第三方边界见[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
