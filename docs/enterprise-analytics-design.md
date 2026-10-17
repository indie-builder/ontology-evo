# 高关系复杂度的企业分析智能体设计

状态为设计草案，附可执行关系契约与反例检查。当前已运行的六表百万订单智能体仍保留，尚未迁移为本设计。业务背景假设为多租户、多法人、多渠道、跨境零售与履约结算，不代表用户生产规则。

## 官方方法是设计基线

本设计以 [ruc-datalab/EvoOntology](https://github.com/ruc-datalab/EvoOntology) 的Build、Evolve、Explore技能及共享references为方法依据，核对提交c94389b764394379086ff25e50d0e0f4396167b4，与当前master一致。复杂数据环境由本项目设计，知识获取和更新由官方方法驱动，不能将下面的表结构方案称为官方推荐行业模型。

实际构建顺序是用户分析需求、workload覆盖图、只读比较候选表与grain、验证语义证据、提交最小本体。不是先将36张表逐个变为Term，也不是先手写所有问题的SQL视图再让Agent复述。这里的36表仅定义需要被检验的数据环境，最终本体对象由实际问题与观测决定，未观测内容不得发布为知识。

## 用户实际要问的问题

“按成交时的客户区域、支付归属渠道、历史商品品类，比较第三季度支付净额、履约确认收入和毛利，并解释为什么与结算及总账不同。”

完整回答需要先确定金额定义、业务时间、观察截止时间、法人和币种，选择可解释的关系路径；不能把“销售额”自动解释成一个固定列。简单问题仍直接回答，只有会改变结论且无法从授权口径确定的歧义才追问。

其他验收问题包括：

1. 一笔合并支付覆盖两单，其中一单拆仓发货、跨月部分退货，季度渠道支付净额如何计算？
2. 客户八月改区、商品九月调整类目，七月成交按当时归属与当前归属各是多少？
3. 九月发生、十月才到数的退款，在九月关账视图和十月重述视图中差多少？
4. 支付成功但尚未结算、已结算但未开票、已开票但未确认收入分别有哪些差异原因？
5. 同一订单行的品类分摊与营销归因同时存在时，能否按品类和广告活动交叉汇总？缺少联合分摊时应如何回答？
6. 同一个外部客户编号在两个系统和两个租户出现，能否确认是同一个客户？
7. 季度汇总与逐月汇总为什么可能不同？独立客户数、期末库存不能直接逐月相加。
8. 数据源上游撤销重发、汇率缺失或映射有歧义时，答案应给出哪些未覆盖金额？

## 设计选择

| 结构方案 | 能隐藏的复杂性 | 暴露给Agent的问题 | 决定 |
| --- | --- | --- | --- |
| 原始业务表全部直接开放 | 少，保留所有源细节 | 每题重做去重、时间、分摊和多事实连接 | 仅受控诊断通道采用 |
| 一张全量宽表 | 常规维度读取简单 | 多个一对多相乘；历史和币种被压平，修正难追溯 | 拒绝作为统一底座 |
| 分域事件与事实、显式分摊桥、经检查的分析视图 | 数据平台集中管理事件去重、历史选择、金额守恒和已验证关系 | Agent仍需选择指标、时间、归因版本及合法维度 | 选为主体 |

逻辑域不等于必须使用不同数据库schema。DuckDB不支持跨schema外键，本地契约采用 `enterprise.<domain>__<table>`。逻辑关系仍按域组织。生产数据平台可采用原生约束和离线完整性检查，不能因测试引擎差异改变业务含义。

不新增通用语义引擎、指标DSL或规则规划器替代EvoOntology。底层提供真实表、键、元数据和只读工具；业务术语、映射、关系、约束及其证据归官方五类本体记录，分析与查询选择归Claude Code。构建用的workload覆盖图留在构建产物，不变成本体新对象族。

## 四层数据结构

1. 原始层保留源批次、版本、事件和观察时间，按 `(tenant,source,event,source_version)` 幂等入库。原始payload可审计，默认不让业务分析Agent读取敏感内容。
2. 标准层保留规范化标识、不可变业务事件、双时间历史和显式分摊桥。冲突记录进入质量隔离区，不用任意ROW_NUMBER静默消除歧义。
3. 数据环境可保留真实业务已经提供的事实视图，金额有来源事件、原币、最小货币单位及政策版本。测试环境同时开放标准明细表，不能为了简化任务预制逐题答案视图。Agent需按官方Build比较多种候选grounding并验证grain，视图和明细各自适用范围写入证据。
4. 语义层保留业务概念、映射、约束、证据；任务层保存当前问题、数据快照、指标版本、工具执行及结果。全量明细留在引擎，不进入模型上下文。

## 关系契约

所有稳定ID由租户范围限定。自然键带源系统，不能用裸order_id、customer_id跨系统连接。每个桥声明计量类型、方向、分摊方法及版本；货币分摊与数量分摊不能互换。

以下36张标准层表的可执行列定义在 `design/enterprise/schema.sql`。下表同时声明粒度和不能忽略的关系。

| 逻辑表 | 一行代表 | 关键关系与时间 |
| --- | --- | --- |
| audit.source_batch | 一个源提取批次 | 数据快照、水位、提取时间 |
| audit.source_record | 一个源事件的一个源版本 | 业务时间、收到时间、操作类型；保留重放和修正 |
| identity.customer_identity | 一段外部客户到规范客户映射版本 | 源系统+源客户号；业务有效与系统已知两个区间 |
| identity.customer_version | 一段客户属性历史 | customer_id；区间选择，地区和类型不能直接取当前行 |
| identity.org_version | 一段组织归属历史 | 父组织、法人；校验环与时间重叠 |
| catalog.sku_version | 一段外部SKU映射和品牌历史 | 源系统+SKU自然键；双时间 |
| catalog.category_version | 一段类目层级历史 | 分类树版本、父类目、双时间 |
| catalog.sku_category_allocation | SKU版本到类目版本的一份权重 | taxonomy及allocation_version；同分组权重守恒 |
| commerce.sales_order | 一笔规范订单 | 源订单唯一、法人、门店、外部客户、创建时间、币种 |
| commerce.order_line | 一条订单行 | 订单1:N行；商品金额、税、运费分开，数量允许小数 |
| commerce.order_status_event | 一个订单状态事件 | 事件时间、收到时间、源序号，不用当前状态抹掉历史 |
| commerce.discount_allocation | 一份促销优惠对订单行的分摊 | 行N:M促销，资助方、方法、版本和金额 |
| payments.payment_event | 一次授权、扣款、撤销或拒付事件 | 授权不是支付；只选指定类型和结果；源事件去重 |
| payments.payment_line_allocation | 支付事件对订单行的一份金额 | 支付N:M订单行；分期和合并支付在此表达 |
| fulfillment.fulfillment_line | 一份订单行的仓库履约数量 | 行1:N履约；履约与观察时间 |
| fulfillment.shipment | 一个包裹 | 发货、签收、承运人 |
| fulfillment.shipment_allocation | 履约数量对包裹的分配 | 履约N:M包裹；拆包与合包 |
| returns.return_line | 一份订单行退货请求 | 数量、原因、申请及收到时间 |
| returns.return_fulfillment_allocation | 退货数量对应原履约的份额 | 退货N:M履约，避免超退数量 |
| returns.refund_event | 一次资金退款事件 | 无货退款、退货未退款均可存在；成功及已知时间 |
| returns.refund_line_allocation | 退款事件对订单行的金额 | 退款N:M行，可关联退货但不强制存在 |
| returns.refund_payment_allocation | 退款对原支付事件的金额 | 跨支付拆退，支付渠道对账使用此桥 |
| finance.fx_rate | 一个日期、币对、类型、观察版本的汇率 | 缺汇率不默认为1；区分交易与报告折算 |
| finance.invoice_line | 一条发票行 | 法人、开票日、税额、原币；不直接等于确认收入 |
| finance.invoice_order_allocation | 发票行对订单行金额 | 合并开票、分次开票 |
| finance.recognition_event | 一次确认收入或冲销事件 | 确认日期、观察时间、有符号金额、冲销引用 |
| finance.recognition_allocation | 确认事件对订单/履约行金额 | 部分履约、分阶段确认 |
| finance.settlement_line | 渠道结算单一行 | 结算日、手续费、净额、原币 |
| finance.settlement_payment_allocation | 结算行对支付事件的分配 | 结算N:M支付；不能按订单数分摊手续费 |
| finance.journal_line | 一条总账分录行 | 会计日期、借贷、法人、币种 |
| finance.journal_recognition_allocation | 分录对确认收入事件的金额 | 关联已确认收入科目行，非整张凭证总额 |
| fulfillment.inventory_cost_event | 一次库存批次成本事件 | 库存批次、仓库、商品、成本时点 |
| fulfillment.cost_allocation | 成本事件对履约的分摊 | 成本N:M履约；方法和版本独立 |
| marketing.touch | 一个广告接触事件 | 匿名ID、可选外部客户ID、活动和观察时间 |
| marketing.attribution_allocation | 订单行对触点的一份归因权重 | 模型版本；不能把全部触点各算100% |
| marketing.spend | 活动、法人、日期、币种的一份成本 | 原始粒度独立于订单，不直接连接每笔订单累加 |

SCD区间不重叠、映射歧义、权重合计、金额守恒、组织无环不是普通外键能够保证的性质。数据构建必须运行跨行检查。外键只证明引用存在，不能证明关系口径正确。

可空引用例如refund_line_allocation.return_line_id，必须区分明确无退货与数据未到齐；后续质量状态表需保留原因。当前DDL是核心关系契约，不宣称已实现全部质量状态和源lineage字段。

## 时间与版本必须进入问题契约

业务发生时间valid/event决定事件归属，系统已知时间known决定当时可见的数据。两个维度分开选择。

每次分析固定：tenant授权范围、data_snapshot_id、业务期间、knowledge_cutoff、维度归属策略、metric_version、allocation_version、reporting_currency和fx_policy_version。

- 关账视图只使用截止时已知记录。
- 重述视图可纳入后来到达、但业务归属之前的修正。
- 客户或品类按成交时归属，选择业务时点有效且观察截止可见的唯一历史版本。
- “当前区域”是另一种合法分析，必须与“成交时区域”分别命名。
- 支付订单群组不能简单假设一个paid_at；分期场景默认使用capture事件期间。若要求首次支付归属整个订单，则使用独立metric_version，不能混为一个指标。
- 时间戳保存UTC，期间按所选法人业务时区转成UTC边界；禁止固定自然日字符串跨时区比较。

双时间按 `[from,to)` 选择，exactly-one或显式unknown。有效版本多于一条时阻止相关维度汇总，不随意选最新。

## 指标与合法计算路径

| 指标 | 基础事实/粒度 | 汇总与关系 | 主要限制 |
| --- | --- | --- | --- |
| 期间支付金额 | 成功capture的订单行分摊 | capture期间，按原币及法人先聚合 | 授权、撤销、测试排除；订单状态不能替代支付事件 |
| 支付群组净额 | capture分摊减与其关联的退款 | refund_payment桥限定原支付，再与行分摊按明确政策对齐 | 缺少支付与行联合退款分配时，不擅自推断交叉分摊 |
| 期间现金退款 | 成功refund事件 | 按退款日汇总，与支付发生季度无关 | 与支付群组净额不同 |
| 确认收入 | recognition_allocation | 按确认日、法人、报告币种和科目政策 | 与支付、发票、结算分开 |
| 履约成本 | cost_allocation | 履约或成本政策规定期间 | 成本调整和退货回冲需有符号事件 |
| 毛利 | 相同归属和币种的确认收入减匹配成本 | 各事实先达到统一分析粒度再组合 | 未匹配成本列coverage，不默认为0 |
| 结算净额 | settlement_line及payment桥 | 总额、手续费和净额守恒 | 不等于收入，跨币结算需要显式换汇桥 |
| 渠道对账差 | 支付、退款、结算各自聚合后全外连接 | 以已声明对账键与截至时点匹配 | 差异须分已解释、待到数、未映射 |
| 营销回报比 | 已选归因模型的收入分摊与spend | 活动、法人、日期及币种一致再比较 | 归因不等于因果；不能叫利润ROI |
| 购买客户数 | 规范客户标识集合 | 去重，跨时段重新计算 | 不可直接加月度去重数 |

支付群组净额是刻意保留的难例。退款到支付和退款到订单行是两个边际分配，不能默认相乘得到联合分配。可选政策是增加明确的 `(refund,payment,order_line)` 联合分摊事实，或只支持总额与已有可证明的切片；由业务授权后选定。当前设计选择先返回不支持的交叉范围及未分配金额，不用隐含独立假设填补。

同理，品类和营销活动都是多对多权重。如果没有共同分摊模型，不能把两个边际权重简单相乘。已验证的适用维度和缺失联合分摊由官方Constraint与Evidence描述；不支持组合应报告缺口，或拆成两个独立报表并解释。

不提供包罗所有事实的mega_join，也不让智能体只查预计算答案。通过原生只读工具探索多表，验证候选grounding、关系粒度和适用范围。选择失败、缺失关系及不能证明的口径作为coverage gap保留，不强行填满本体。

## 语义层与关系目录的分工

保持官方Term、Mapping、Relation、Constraint、Evidence五类记录，不扩展自造字段。

- Term定义支付、现金退款、确认收入、客户历史归属、分摊政策等概念，明确相近名称的区别。
- Mapping指向实际验证过的数据库、表或真实视图及字段，描述语义过滤、聚合和grain，派生指标明确不存在单独物理列。
- Relation表达派生、等价、层级等业务语义，不把物理JOIN图全部装成语义关系。
- Constraint说明非加性、时间选择、币种、支持维度组合、未映射状态及适用范围。
- Evidence指向文档、数据快照、结构检查、反例或可复现查询；不把标准答案或SQL模板塞进Term描述。

数据库元数据可暴露键、列类型和关系观测，作为Builder探索证据；不另写一套业务指标目录。已验证的时间条件、grain、分摊含义和适用范围应落在官方Mapping、Relation、Constraint、Evidence允许的字段，不附加join_path、SQL模板、规划步骤或隐藏执行策略。若复杂场景暴露表示能力不足，应在官方Evolve中以证据归因并验证，不在初始化时悄悄扩schema。

官方当前检索是词法匹配，复杂域下通过对象名称和别名、已知ID、分域发现控制上下文。需要多个文件或workspace隔离时，先保持一个tenant与snapshot的统一语义版本，避免跨本体版本组合出无法重现的结果。多本体联邦不是本轮默认设计。

## 智能体和查询服务接口

用户入口仍是Workspace主会话，不要求用户知道表名。项目分析技能按问题需要完成以下契约，不固定每题调用次数。

1. 定义指标、期间、观察时点、币种与归属，读取授权范围。
2. 按域检索语义，发现物理grain、可用视图和合法关系；有歧义就查证。
3. 明确基础事实与共同输出粒度，识别会产生扇出的边。
4. 请求验证关系与支持组合，再执行聚合下推，保留观察证据。
5. 核对守恒、coverage和未解释差，记录结果与限制。

数据工具保持最小能力。当前已有query负责受控只读执行；针对schema过大，只补元数据按域过滤及分页，不构建自定义语义校验器、指标计算引擎或四阶段查询规划协议。

```text
schema(domain?, table?, cursor?)
  -> 实际表、列、键及下一页；不返回预制任务答案
query(sql)
  -> 实际有界结果或错误；执行授权由平台控制
```

工具输出是证据，不替代Agent推理。语义调用仍用官方browse_semantics与resolve_semantics，任务固定版本并通过start/record/finish记录真实调用。DuckDB用原生查询MCP执行后立即record_ontology_task_event，不修改官方SQLite执行器冒充DuckDB支持。

analytics_status现在返回带next_cursor的目录首页；schema(schema?,table?,cursor?)可跨业务schema分页，已用120列测试确认无遗漏。翻页期间保持schema不变，不能把截断首页当全量目录。tenant、数据快照及凭据授权由平台绑定，不能信任模型写WHERE tenant_id。默认只提供授权只读数据集，原始敏感payload另行授权。

现有脚本每次启动Python子进程、512MB及15秒预算只适用于演示。新查询服务按工作负载类别配置并发、队列、扫描、超时、内存、spill、结果和取消；不自动把限制放宽到无限。DuckDB继续作为可复现实验引擎，生产后端可由平台统一接数仓或湖仓，接口契约不暴露凭据。

## 生成器与验证数据设计

生成顺序围绕业务过程，不再把每列独立随机填满。

- 生成组织与客户、SKU映射和历史变更，再生成订单。
- 生成可守恒的合并/分期支付分配、拆仓履约和包裹分配。
- 基于已履约数量生成退货，单独生成有货/无货退款及原支付分配。
- 生成确认、冲销、开票、结算、成本和会计事件，保留合法暂时差异。
- 生成营销触点和有版本归因，设置未归因桶。
- 最后注入重复、迟到、跨租户同号、缺映射及冲突，保留故障标签供独立检查，不当成Builder业务知识。

参数分开控制订单量、平均边度、分期比例、拆包比例、退款次数、历史变更率、迟到率、身份歧义率、币种数和tenant数。默认复杂微样本用于人工核账，中等规模关系样本用于Agent评估，大规模用于执行成本测试。增加行数不能替代关系覆盖。

公开微样本展示：一个capture分到两条同金额订单行，其中一行两次履约、两次退款。直接JOIN支付分配、履约和退款使200元支付变成500元。SUM(DISTINCT amount)又把两条各100元误算成100元；必须在声明grain上分别汇总。

验证分三类，不相互替代：

1. 数据不变量检查：事件去重、tenant复合键、分摊金额和数量守恒、历史区间唯一、币种匹配、借贷平衡、无环和覆盖率。包含故意破坏的负例，检查应失败于正确原因。
2. 任务正确性：公开微样本人工可核、oracle从独立账本守恒和指定政策计算。Parent/Candidate比较按官方数据边界隔离，关联问题按业务case分组，不能将同订单换问法拆进验证。
3. 运行能力：对真实查询计划测扫描、峰值内存、spill、并发、取消和结果大小。没有测量不报告性能提升。

必须覆盖的失败类别包括多事实扇出、SUM DISTINCT误去重、时点错配、迟到修正、币种混加、重复事件、tenant漏键、分摊不守恒、无联合分摊、成本未匹配、空数据与零值混淆、非加性指标相加、未知映射和源水位不齐。

## 演示中的具体反例

`design/enterprise/verify-design.py` 在内存DuckDB构建DDL并运行公开微案例，检查：

- 两条各100元订单行的支付分配守恒200元。
- 直接多事实连接得到500元，证明grain放大。
- 9月关账时已知退款20元，净额180元；后来才收到的另一笔10元退款在重述中可见。
- 七月业务记录使用七月有效的华东属性，而不是八月后的华南属性。
- 漏tenant跨租户引用被复合外键拒绝。

`design/enterprise/quality-checks.sql` 另外提供跨行检查，识别五类历史区间重叠、分摊权重和金额、数量上界、币种不一致、关联行错配、借贷不平衡。默认用于完整数据快照；迟到或部分批次会形成显式质量缺口，不能简单把所有差异当永久损坏。

负例测试覆盖客户历史重叠、缺失支付分摊、0.7类目权重、未平衡分录和不存在的类目引用。未映射客户ID允许为空，confirmed映射必须有ID。组织与类目环检测现已实现，递归路径同时保持业务有效区间与系统已知区间的公共交集；区间不重叠的历史关系不误判为环，负例和非重叠反例均通过。跨版本政策切换和完整源lineage仍待实现。

这些是设计可执行性检查，不代表36表已完成生产数据构造、指标视图或完整智能体评测。

## 落地文件与迁移

```text
现有Workspace角色与本体保持运行
  design/enterprise/schema.sql          核心关系DDL草案
  design/enterprise/verify-design.py    公开反例和结构检查
  docs/enterprise-analytics-design.md   本设计与验收约定
后续实现批次
  data builders                         业务过程、故障与快照生成
  metadata/read-only tools              实际表结构分页及受控查询
  workload coverage map                 构建阶段需求覆盖图，非本体新schema
  official ontology workspace           官方Build生成五类证据记录
  independent evaluator                 官方Evolve的隔离评估
```

第一批先将支付、订单行、履约、退款和客户历史落到可复跑复杂样本，准备公开业务问题，运行官方Build探索和提交证据；通过真实任务检验复杂JOIN与时点选择。第二批再接入结算、确认收入、成本和总账，闭合对账；第三批扩展商品多归属、身份歧义与归因，验证不支持组合时会明确拒绝。最后才增加行数与并发。

使用新数据源和 `.evoontology/enterprise`，由官方Build创建新本体，不覆盖旧版本。默认配置切换的门槛是关系不变量通过、代表性业务问题和错误拒绝通过、原样例仍可显式回归。设计完成不触发默认切换。

## 未决业务项与接受的代价

当前以零售结算为假设。实际企业可能是供应链、订阅、广告或工业设备，需要替换业务过程。收入确认规则、税费口径、汇率类型、匿名身份合并及退款联合分摊必须由业务授权，不能由技术选型决定。

接受更多分摊与历史表，以换取可证明的关系和重现性；不追求让Agent每次把36表全连起来。接受初期部分交叉维度报告不支持，以避免伪精确分摊。接受生产后端由平台提供，因为DuckDB本身不替代集中治理和多租户查询调度。

本轮没有独立设计评审，当前LoopX禁止子Agent；方案比较由同一会话完成。DDL和公开反例已实际执行，生产路径、完整oracle与运行时迁移仍待后续实现。

## 与EvoOntology官方实践的逐项对应

| 官方要求 | 本设计如何遵循 | 明确不做 |
| --- | --- | --- |
| workload-guided probing | 从业务问题形成覆盖图，再比较候选数据结构与grain | 将所有表机械映射成Term |
| evidence-grounded commitment | 每个对象连接需求与真实观测，无法验证保留缺口 | 手写猜测或把答案当证据 |
| 固定五类记录与受控关系类型 | Term/Mapping/Relation/Constraint/Evidence，relation_type保持官方枚举 | 自造join_path、metric DSL或额外对象族 |
| 元数据不等于答案 | 原生SQL提供结果，语义工具提供定义与定位 | 给每题预制结果视图让Agent复述 |
| 可观察真实任务 | 固定版本start任务，原生工具执行，立即record再finish | 伪造轨迹或保存私有推理链 |
| Diagnose→Attribute→Patch→Evaluate | 从复杂失败轨迹诊断，Candidate只验证一个主要机制 | 绕开官方会话手动切active或宣称更好 |
| 设计与评估隔离 | 业务case分组隔离，公开反例只用于构建演示 | 将本文件反例算成独立验证成功 |
| 发布与展示由官方工具完成 | save→annotate→publish；Evolve accept后finalize | 自写存储、复制版本JSON当发布 |

官方来源：

- [Build workflow](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/build-ontology/SKILL.md)
- [Ontology schema](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/build-ontology/references/ontology-schema.md)
- [Interaction protocol](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/build-ontology/references/ontology-interaction-protocol.md)
- [Workload and observable execution](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/build-ontology/references/workload-experience.md)
- [Evolve workflow](https://github.com/ruc-datalab/EvoOntology/blob/c94389b764394379086ff25e50d0e0f4396167b4/plugins/claude-code/skills/evolve-ontology/SKILL.md)
