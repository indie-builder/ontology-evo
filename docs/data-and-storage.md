# 数据样本与生产分析存储

当前Workspace保留12笔订单的SQLite口径样例，另外提供可扩大规模的DuckDB和Parquet分析样例。两者是独立数据源。不要直接将原本体切到扩展库；新数据源应单独配置工作区并通过官方Build建立映射。

## 扩展样例

使用可选依赖DuckDB 1.5.6，不改变原有Python标准库示例。命令在项目根执行：

```bash
uv run --no-project --with duckdb==1.5.6 python -I scripts/generate-analytics.py \
  --orders 100000 --output data/generated/analytics
```

没有uv时，可在独立虚拟环境安装 `duckdb==1.5.6`，再运行同一脚本。运行时固定线程数4、memory_limit为1GB，溢写目录位于输出目录。输出目录必须为空，脚本不覆盖已有数据。失败后的目录保留，重试使用新的空目录。

生成以下六张表。

| 表 | 默认行数 | 粒度与分析用途 |
| --- | ---: | --- |
| customers | 20,000 | 客户、地区、客户类型、注册日期 |
| products | 200 | 商品、品类 |
| orders | 100,000 | 支付、创建时间、四渠道、订单状态、测试标记、整数分金额 |
| order_items | 200,000 | 每单两条商品行，演示一对多连接 |
| refunds | 22,759 | 全退、部分退、多笔退款、待处理和跨期退款 |
| channel_spend | 2,920 | 两年逐日逐渠道投放金额 |

创建日期覆盖2025和2026年，支付可能跨日及跨年。金额统一为人民币分，渠道与订单状态采用独立生成维度；脚本检查所有渠道都覆盖五种状态。数据人工生成，不代表真实生产分布。

产物包括 `sales.duckdb`、`parquet/orders/created_month=YYYY-MM/*.parquet`、其他表的Parquet和 `manifest.json`。订单按创建月份分区；按支付日期过滤不保证能裁剪创建月份分区，生产分区应根据主要过滤条件和迟到数据策略决定。

manifest记录生成版本、行数、季度查询SQL及真实结果。生成时检查明细金额合计、客户引用、成功退款不超过原支付、DuckDB与Parquet金额一致，以及只读连接拒绝删除。它们是公开算术检查，不是模型准确率或性能评测。

可尝试100万订单：

```bash
uv run --no-project --with duckdb==1.5.6 python -I scripts/generate-analytics.py \
  --orders 1000000 --output data/generated/million-orders
```

规模参数不是机器容量保证。大规模运行前估算数据库、Parquet副本和临时溢写所需磁盘。脚本默认创建两种存储表示以便比较，不建议生产无条件保留两份。

建议分析问题包括季度净收入及同比、地区与客户类型拆分、支付客单价、退款时延、渠道投放与回报。产品级退款尚无退款商品分摊，净收入不是财务确认收入。投放成本与收入相关不代表因果归因。当前生成器是样例工具，不支持生产CDC、事件去重或完整状态历史。

## DuckDB是否适合海量生产数据

DuckDB是嵌入式分析引擎，适合列扫描、聚合、连接和直接查询Parquet。它可以处理部分超内存工作负载并溢写磁盘；复杂阻塞操作组合和部分聚合仍可能耗尽内存。不要用“数据大”推导为无限单机扩展能力。

| 工作负载 | 推荐方向 |
| --- | --- |
| 小型可审计口径样例、零依赖演示 | SQLite |
| 单Workspace分析文件、Parquet子集、离线批量分析 | DuckDB |
| 生产订单更新、高并发事务、多行一致性 | PostgreSQL、MySQL等事务数据库 |
| 多Workspace高并发分析、集中权限、持续入库 | ClickHouse、云数仓或现有分析平台，按实际负载选择 |
| 对象存储上的大规模历史数据和共享查询 | Parquet/Iceberg等数据湖，配Trino、Spark或云查询引擎；DuckDB可分析受控子集 |

这些是部署方向，不是按GB、TB机械划线。需要知道总存量、单次扫描量、增长速度、同时查询数、时延目标、写入方式、更新删除需求和治理要求，才能确定生产方案。

多个进程可以只读打开本地DuckDB文件，但读写模式不能简单视为任意多进程共享写入数据库。多线程、单进程的读写与多进程写入是不同的部署方式。官方另有远程及catalog方案，采用前应核实当前版本和成熟度。

## 对Workspace平台的建议

生产数据保存在共享数仓或数据湖。每个Workspace只保存角色、业务知识、工具绑定、任务和结果引用。模型通过受控只读查询服务获取schema、样本或聚合结果；不要把生产全量数据复制到每个Workspace，更不要传入模型上下文。

DuckDB适合作为每个Workspace按需使用的本地分析能力、受限缓存或Parquet查询引擎。平台需要设置CPU、内存、临时磁盘、查询时间、扫描与结果量限制，以及租户凭据和行列权限。直接暴露任意DuckDB SQL并不能自然获得安全边界，它还能读取文件和外部源；生产应由平台限制路径、扩展和网络能力。

EvoOntology的本体JSON是语义层，不需要换成DuckDB。需要选择的是底层数据查询引擎，语义对象仍通过官方MCP持久化。

## 当前接入限制

EvoOntology 1.1.1的 `execute_ontology_query` 实现调用Python sqlite3，只支持SQLite。把文件名改成duckdb或修改data_source类型不会获得DuckDB支持。

本项目已用 `.mcp.json` 接入独立的workspace-analytics MCP。config/analytics.json选择默认数据库、业务说明和独立本体目录。查询工具没有数据库路径参数，仅允许一个SELECT语句，数据库以read_only打开，禁用外部访问、自动扩展和配置修改。每次查询独立工作进程，限制15秒、512MB DuckDB内存、256MB临时空间、100行和64KB结果。DuckDB memory_limit不是进程RSS的硬上限，生产还需容器或OS配额。当前工具不提供直接Parquet任意路径查询，Parquet作为数据湖样例保留。

主会话收到真实结果后调用record_ontology_task_event，再finish_ontology_task。本次已用全新Claude Code会话对百万订单完成实际分析及轨迹复跑。默认分析本体是 `.evoontology/analytics`；原根SQLite本体保留，不混用轨迹。新数据源和正式评估仍需独立配置。

依赖固定DuckDB1.5.6和MCP SDK2.3.0，由uv在本机隔离环境加载。首次启动需要依赖下载，后续运行使用缓存。主进程每次查询启动独立Python进程，适用于本例受控验证，不代表高并发生产查询服务；生产应由平台提供数据库服务和调度。

## 官方依据

- [DuckDB工作负载与超内存处理](https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads.html)
- [DuckDB并发模型](https://duckdb.org/docs/current/connect/concurrency.html)
- [DuckDB Parquet查询与下推](https://duckdb.org/docs/current/data/parquet/overview.html)
- [EvoOntology可观察任务接入](https://github.com/ruc-datalab/EvoOntology/blob/master/plugins/claude-code/skills/build-ontology/references/workload-experience.md)
