#!/usr/bin/env python3
"""Local synthetic sales fixture, read-only checks and result presentation."""
import argparse
import hashlib
import html
import json
import sqlite3
from decimal import Decimal
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


class DemoHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        self.serve_public(super().do_GET)

    def do_HEAD(self):
        self.serve_public(super().do_HEAD)

    def serve_public(self, serve):
        route = unquote(urlsplit(self.path).path)
        allowed = {"/", "/index.html", "/artifacts/checks.json", "/docs/business-policy.md",
                   "/.evoontology/visualizations/ontology-layer-explorer.html"}
        if route not in allowed:
            self.send_error(404)
            return
        serve()

ROOT = Path(__file__).resolve().parent
DB = ROOT / "data" / "sales.sqlite"
START = "2026-07-01"
END = "2026-10-01"

ORDERS = [
    ("O01", "C01", "web", "2026-07-01", "2026-07-01", "paid", 0, 10000),
    ("O02", "C02", "store", "2026-07-15", "2026-07-15", "partially_refunded", 0, 20000),
    ("O03", "C01", "web", "2026-08-05", "2026-08-05", "paid", 0, 15000),
    ("O04", "C03", "ads", "2026-08-20", "2026-08-20", "refunded", 0, 8000),
    ("O05", "C04", "store", "2026-09-30", "2026-09-30", "paid", 0, 12000),
    ("O06", "C05", "web", "2026-09-15", "2026-09-15", "paid", 0, 5000),
    ("O07", "C06", "web", "2026-08-01", None, "cancelled", 0, 9000),
    ("O08", "C07", "ads", "2026-09-01", None, "pending", 0, 7000),
    ("O09", "TEST", "web", "2026-09-02", "2026-09-02", "paid", 1, 50000),
    ("O10", "C06", "web", "2026-06-30", "2026-07-01", "paid", 0, 6000),
    ("O11", "C07", "ads", "2026-09-30", "2026-10-01", "paid", 0, 11000),
    ("O12", "C08", "store", "2026-06-15", "2026-06-15", "paid", 0, 4000),
]
REFUNDS = [
    ("R01", "O02", "2026-08-01", "succeeded", 4000),
    ("R02", "O02", "2026-09-01", "succeeded", 1000),
    ("R03", "O03", "2026-09-10", "pending", 3000),
    ("R04", "O03", "2026-10-02", "succeeded", 2000),
    ("R05", "O04", "2026-09-05", "succeeded", 8000),
    ("R06", "O12", "2026-07-10", "succeeded", 1000),
]
COHORT = """WITH cohort AS (
 SELECT * FROM orders
 WHERE paid_at >= '2026-07-01' AND paid_at < '2026-10-01'
 AND is_test = 0 AND status IN ('paid','partially_refunded','refunded')
), refund_totals AS (
 SELECT order_id, SUM(amount_cents) AS refund_cents FROM refunds
 WHERE status = 'succeeded' AND refunded_at < '2026-10-01'
 GROUP BY order_id
) """
QUERIES = {
    "totals": COHORT + """SELECT SUM(o.amount_cents) AS gross_cents,
 SUM(COALESCE(r.refund_cents,0)) AS refund_cents,
 SUM(o.amount_cents - COALESCE(r.refund_cents,0)) AS net_cents,
 COUNT(*) AS paid_orders, COUNT(DISTINCT o.customer_id) AS buyers
 FROM cohort o LEFT JOIN refund_totals r ON o.order_id = r.order_id""",
    "channels": COHORT + """SELECT o.channel, SUM(o.amount_cents) AS gross_cents,
 SUM(COALESCE(r.refund_cents,0)) AS refund_cents,
 SUM(o.amount_cents - COALESCE(r.refund_cents,0)) AS net_cents,
 COUNT(*) AS paid_orders FROM cohort o
 LEFT JOIN refund_totals r ON o.order_id = r.order_id GROUP BY o.channel ORDER BY o.channel""",
    "months": COHORT + """SELECT substr(paid_at,1,7) AS month,
 SUM(amount_cents) AS gross_cents, COUNT(*) AS paid_orders
 FROM cohort GROUP BY month ORDER BY month""",
    "naive": """SELECT SUM(amount_cents) AS created_order_cents FROM orders
 WHERE created_at >= '2026-07-01' AND created_at < '2026-10-01'""",
    "fanout": COHORT + """SELECT SUM(o.amount_cents) AS duplicated_gross_cents
 FROM cohort o LEFT JOIN refunds r ON o.order_id=r.order_id""",
    "units": "SELECT DISTINCT typeof(amount_cents) AS storage_type FROM orders",
}


def read_connection(path):
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def seed(path):
    if path.exists():
        with read_connection(path) as connection:
            found = connection.execute("SELECT value FROM metadata WHERE key='fixture'").fetchone()
            if found is None or found[0] != "evo-sales-v1":
                raise ValueError("Existing database is not this fixture; refusing to replace it")
        print(f"Existing fixture retained: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE orders (
          order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, channel TEXT NOT NULL,
          created_at TEXT NOT NULL, paid_at TEXT, status TEXT NOT NULL,
          is_test INTEGER NOT NULL CHECK(is_test IN (0,1)),
          amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0));
        CREATE TABLE order_items (
          item_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(order_id),
          product TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents >= 0));
        CREATE TABLE refunds (
          refund_id TEXT PRIMARY KEY, order_id TEXT NOT NULL REFERENCES orders(order_id),
          refunded_at TEXT NOT NULL, status TEXT NOT NULL,
          amount_cents INTEGER NOT NULL CHECK(amount_cents > 0));
        """)
        connection.execute("INSERT INTO metadata VALUES ('fixture','evo-sales-v1')")
        connection.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?,?)", ORDERS)
        for order in ORDERS:
            half = order[7] // 2
            connection.executemany("INSERT INTO order_items VALUES (?,?,?,?)", [
                (order[0] + "-1", order[0], "茶杯", half),
                (order[0] + "-2", order[0], "咖啡豆", order[7] - half),
            ])
        connection.executemany("INSERT INTO refunds VALUES (?,?,?,?,?)", REFUNDS)
    print(f"Created synthetic fixture: {path}")


def inspect(path):
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with read_connection(path) as connection:
        results = {name: [dict(row) for row in connection.execute(query)]
                   for name, query in QUERIES.items()}
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 12
        assert connection.execute("""SELECT COUNT(*) FROM (
         SELECT o.order_id FROM orders o JOIN order_items i USING(order_id)
         GROUP BY o.order_id HAVING SUM(i.amount_cents) != o.amount_cents)""").fetchone()[0] == 0
        try:
            connection.execute("UPDATE orders SET amount_cents = 0")
        except sqlite3.OperationalError as error:
            assert "readonly" in str(error).lower() or "read-only" in str(error).lower()
        else:
            raise AssertionError("Read-only connection accepted a write")
    # These public fixture checks demonstrate arithmetic, not held-out Agent accuracy.
    assert results["totals"] == [{"gross_cents": 76000, "refund_cents": 13000,
                                    "net_cents": 63000, "paid_orders": 7, "buyers": 6}], results
    assert results["channels"] == [
        {"channel": "ads", "gross_cents": 8000, "refund_cents": 8000, "net_cents": 0, "paid_orders": 1},
        {"channel": "store", "gross_cents": 32000, "refund_cents": 5000, "net_cents": 27000, "paid_orders": 2},
        {"channel": "web", "gross_cents": 36000, "refund_cents": 0, "net_cents": 36000, "paid_orders": 4},
    ]
    assert results["months"] == [
        {"month": "2026-07", "gross_cents": 36000, "paid_orders": 3},
        {"month": "2026-08", "gross_cents": 23000, "paid_orders": 2},
        {"month": "2026-09", "gross_cents": 17000, "paid_orders": 2},
    ]
    assert results["naive"][0]["created_order_cents"] == 147000
    assert results["fanout"][0]["duplicated_gross_cents"] == 111000
    assert results["units"] == [{"storage_type": "integer"}]
    assert before == hashlib.sha256(path.read_bytes()).hexdigest(), "Database changed during checks"
    return {"fixture": "evo-sales-v1", "synthetic": True, "period": [START, END],
            "database_sha256": before, "read_only_verified": True,
            "results": results, "queries": QUERIES,
            "interpretation": "公开合成案例的确定性查询验证；不是独立评测，也不证明模型准确率提升。"}


def money(cents):
    return f"¥{Decimal(cents) / 100:,.2f}"


def report(path):
    result = inspect(path)
    output = ROOT / "artifacts"
    output.mkdir(exist_ok=True)
    (output / "checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    totals = result["results"]["totals"][0]
    channel_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in
          (row["channel"], money(row["gross_cents"]), money(row["refund_cents"]), money(row["net_cents"]), row["paid_orders"])) + "</tr>"
        for row in result["results"]["channels"])
    query_blocks = "".join(f"<details><summary>{html.escape(name)} · 查看实际 SQL</summary><pre>{html.escape(query)}</pre></details>"
                           for name, query in QUERIES.items())
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>销售口径实验室 · EvoOntology</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,sans-serif;line-height:1.65;background:#f6f7f9;color:#18212f}
*{box-sizing:border-box}body{margin:0}main{max-width:980px;margin:auto;padding:40px 24px 80px}h1{font-size:clamp(28px,5vw,44px);line-height:1.2}h2{font-size:22px;margin-top:36px}p{max-width:76ch}a{color:#1556a3}a:focus-visible,summary:focus-visible{outline:3px solid #c46500;outline-offset:4px}.tag{font-size:14px;color:#43536a}section{background:#fff;border:1px solid #d8dfe8;border-radius:12px;padding:22px;margin:20px 0}.table{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left}th,td{padding:10px;border-bottom:1px solid #d8dfe8;white-space:nowrap}pre{overflow:auto;background:#edf1f6;padding:16px;font-size:13px}summary{cursor:pointer;padding:12px 0}code{overflow-wrap:anywhere}nav{display:flex;gap:16px;flex-wrap:wrap}.note{border-left:4px solid #b76600;padding-left:14px}@media(max-width:480px){main{padding:24px 16px}section{padding:16px}}@media(prefers-color-scheme:dark){:root{background:#111722;color:#e2e8f0}section{background:#1b2433;border-color:#43536a}a{color:#95c7ff}.tag{color:#bac8dc}pre{background:#111722}th,td{border-color:#43536a}}
</style><main><p class="tag">EvoOntology 实例 / 公开合成数据 / 2026 Q3</p>
<h1>同一批订单，口径决定答案。</h1><p>先看真实 SQLite 查询结果，再打开官方本体浏览器，检查这些口径如何记录、引用证据并用于任务。</p>
<nav><a href=".evoontology/visualizations/ontology-layer-explorer.html">打开官方本体浏览器</a><a href="artifacts/checks.json">查询与校验 JSON</a><a href="docs/business-policy.md">演示业务口径</a></nav>
<section><h2>第三季度支付订单的净收入</h2><p>有效支付金额 <strong>GROSS</strong>，减去截至季末已成功的退款 <strong>REFUND</strong>，得到净收入 <strong>NET</strong>。包含 ORDERS 笔有效支付订单，BUYERS 位客户。</p>
<p class="note">这是一份按支付订单归属季度的净额报表，不是财务收入确认或当期现金流水。所有金额在数据库中以整数分保存，页面以元展示。</p></section>
<h2>按渠道核对</h2><div class="table" tabindex="0" role="region" aria-label="渠道金额明细，可横向滚动"><table><thead><tr><th>渠道</th><th>支付金额</th><th>成功退款</th><th>净收入</th><th>订单数</th></tr></thead><tbody>CHANNELS</tbody></table></div>
<h2>故意展示的错误写法</h2><p>按创建日期直接累加所有订单会得到 <strong>¥1,470.00</strong>。它混入测试单、未支付单和下季度支付订单，还漏掉跨季度创建的支付订单。</p><p>直接把订单连接到多条退款再累加订单金额，会把支付金额算成 <strong>¥1,110.00</strong>。一笔订单出现多条退款时，订单金额会重复出现。</p>
<p>这些是指定错误 SQL 的对照，便于观察规则作用。它们不是无本体 Agent 的实测表现。</p>
<h2>实际查询与复跑</h2><p>在项目目录执行 <code>python3 demo.py check</code> 重新验证。执行 <code>python3 demo.py report</code> 重新生成此页和校验结果。</p>QUERIES
<h2>接着体验本体</h2><ol><li>打开官方浏览器，在 Results &amp; questions 查看已执行任务和答案。</li><li>在 Content 查看净收入、成功退款和金额单位的约束及证据。</li><li>回到 Claude Code，要求先解析本体，再查询各渠道净收入，并记录真实任务轨迹。</li></ol>
<p class="tag">不使用生产数据。当前展示的是初版本体和公开任务演示；未运行正式进化或独立模型评测。</p></main></html>"""
    for key, value in {"GROSS": money(totals["gross_cents"]), "REFUND": money(totals["refund_cents"]),
                       "NET": money(totals["net_cents"]), "ORDERS": str(totals["paid_orders"]),
                       "BUYERS": str(totals["buyers"]), "CHANNELS": channel_rows, "QUERIES": query_blocks}.items():
        page = page.replace(key, value)
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def verify_tasks():
    workspace = ROOT / ".evoontology"
    active = json.loads((workspace / "active.json").read_text())["active_version"]
    paths = sorted((workspace / "trajectories").glob("*.json"))
    assert len(paths) >= 4, "Missing recorded MCP tasks"
    checked = []
    expected_questions = {"demo_net", "demo_channels", "demo_months", "demo_aov"}
    with read_connection(DB) as connection:
        for path in paths:
            task = json.loads(path.read_text())
            if task["question_id"] not in expected_questions:
                continue
            assert task["task_status"] == "completed"
            assert task["ontology_version"] == active
            assert task["origin"] == "generated", "Synthetic provenance lost"
            assert task["semantic_calls"], "Missing semantic resolution record"
            calls = [event for event in task["native_tool_calls"] if event["tool"] == "sqlite_query"]
            assert calls, "Missing real SQLite result"
            for event in calls:
                assert not event["error"] and not event["result_truncated"]
                cursor = connection.execute(event["input"]["query"])
                rows = [list(row) for row in cursor]
                assert rows == event["result"]["rows"], path.name
                assert [column[0] for column in cursor.description] == event["result"]["columns"]
            checked.append({"question_id": task["question_id"], "queries_replayed": len(calls)})
    assert {task["question_id"] for task in checked} == expected_questions
    result = {"active_version": active, "tasks": checked, "all_recorded_sql_replayed": True,
              "independent_evaluation": False}
    (ROOT / "artifacts" / "mcp-replay.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["seed", "check", "report", "verify-tasks", "serve"])
    parser.add_argument("--database", type=Path, default=DB)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.command == "seed":
        seed(args.database)
    elif args.command == "check":
        print(json.dumps(inspect(args.database), ensure_ascii=False, indent=2))
    elif args.command == "report":
        report(args.database)
    elif args.command == "verify-tasks":
        verify_tasks()
    else:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(DemoHandler, directory=str(ROOT)))
        print(f"Open http://127.0.0.1:{args.port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == "__main__":
    main()
