#!/usr/bin/env python3
"""Generate a deterministic, synthetic DuckDB and partitioned Parquet sales sample."""
import argparse
import json
from pathlib import Path


def generate(output, orders):
    import duckdb

    if orders < 1000 or orders > 100_000_000:
        raise ValueError("Choose 1,000 to 100,000,000 orders; check disk and memory before large runs")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError("Output directory must be empty; existing data is never overwritten")
    database = output / "sales.duckdb"
    customers = max(100, orders // 5)
    with duckdb.connect(str(database)) as connection:
        connection.execute("SET threads=4")
        connection.execute("SET memory_limit='1GB'")
        connection.execute("SET preserve_insertion_order=false")
        connection.execute("SET temp_directory=?", [str(output / "spill")])
        connection.execute(f"""
        CREATE TABLE customers AS
        SELECT i::BIGINT customer_id,
          (['华东','华南','华北','西南'])[1+i%4] region,
          (['consumer','business'])[1+i%2] segment,
          DATE '2024-01-01'+(i%365)::INTEGER registered_date
        FROM range(1,{customers + 1}) t(i);
        CREATE TABLE products AS
        SELECT i::INTEGER product_id,
          (['茶饮','咖啡','器具','食品'])[1+i%4] category,
          ('product-'||i) product_name
        FROM range(1,201) t(i);
        CREATE TABLE orders AS
        SELECT i::BIGINT order_id, (1+hash('customer-'||i)%{customers})::BIGINT customer_id,
          (['web','store','ads','marketplace'])[(1+hash('channel-'||i)%4)::BIGINT] channel,
          DATE '2025-01-01'+((i*37)%730)::INTEGER created_date,
          CASE WHEN i%20 IN (0,1) THEN NULL
            ELSE DATE '2025-01-01'+((i*37)%730)::INTEGER+(i%4)::INTEGER END paid_date,
          CASE WHEN i%20=0 THEN 'cancelled' WHEN i%20=1 THEN 'pending'
            WHEN i%20=2 THEN 'refunded' WHEN i%20=3 THEN 'partially_refunded'
            ELSE 'paid' END status,
          (i%97=0) is_test, (1000+(i*7919)%99000)::BIGINT amount_cents
        FROM range(1,{orders + 1}) t(i);
        CREATE TABLE order_items AS
        SELECT o.order_id*10+j item_id, o.order_id,
          (1+(o.order_id*7+j)%200)::INTEGER product_id,
          CASE WHEN j=1 THEN o.amount_cents//2 ELSE o.amount_cents-o.amount_cents//2 END amount_cents
        FROM orders o CROSS JOIN range(1,3) t(j);
        CREATE TABLE refunds AS
        SELECT order_id*10+j refund_id,order_id,
          paid_date+(CASE WHEN j=1 THEN 2 ELSE 35 END)::INTEGER refunded_date,
          CASE WHEN status='paid' THEN 'pending' ELSE 'succeeded' END status,
          CASE WHEN status='refunded' THEN
            CASE WHEN j=1 THEN amount_cents//2 ELSE amount_cents-amount_cents//2 END
            ELSE amount_cents//10 END::BIGINT amount_cents
        FROM orders CROSS JOIN range(1,3) t(j)
        WHERE orders.status IN ('refunded','partially_refunded')
          OR (orders.status='paid' AND order_id%29=0 AND j=1);
        CREATE TABLE channel_spend AS
        SELECT d::DATE spend_date, channel,
          (2000+date_diff('day',DATE '2025-01-01',d)*13+length(channel)*100)::BIGINT spend_cents
        FROM generate_series(DATE '2025-01-01',DATE '2026-12-31',INTERVAL 1 DAY) t(d)
        CROSS JOIN (VALUES ('web'),('store'),('ads'),('marketplace')) c(channel);
        """)
        counts = {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                  for table in ["customers", "products", "orders", "order_items", "refunds", "channel_spend"]}
        assert counts["orders"] == orders and counts["order_items"] == 2 * orders
        assert connection.execute("SELECT COUNT(*) FROM (SELECT channel,status FROM orders GROUP BY channel,status)").fetchone()[0] == 20
        assert connection.execute("""SELECT COUNT(*) FROM (
          SELECT o.order_id FROM orders o JOIN order_items i USING(order_id)
          GROUP BY o.order_id,o.amount_cents HAVING SUM(i.amount_cents)<>o.amount_cents)""").fetchone()[0] == 0
        assert connection.execute("""SELECT COUNT(*) FROM orders o LEFT JOIN customers c USING(customer_id)
          WHERE c.customer_id IS NULL""").fetchone()[0] == 0
        assert connection.execute("""SELECT COUNT(*) FROM (
          SELECT r.order_id FROM refunds r JOIN orders o USING(order_id)
          WHERE r.status='succeeded' GROUP BY r.order_id,o.amount_cents
          HAVING SUM(r.amount_cents)>o.amount_cents)""").fetchone()[0] == 0
        query = """WITH cohort AS (
          SELECT * FROM orders WHERE paid_date>=DATE '2026-07-01'
          AND paid_date<DATE '2026-10-01' AND NOT is_test
          AND status IN ('paid','partially_refunded','refunded')
        ), refunds_by_order AS (
          SELECT order_id,SUM(amount_cents) refund_cents FROM refunds
          WHERE status='succeeded' AND refunded_date<DATE '2026-10-01' GROUP BY order_id
        ) SELECT channel,COUNT(*) paid_orders,SUM(o.amount_cents)::BIGINT gross_cents,
          SUM(COALESCE(r.refund_cents,0))::BIGINT refund_cents,
          SUM(o.amount_cents-COALESCE(r.refund_cents,0))::BIGINT net_cents
        FROM cohort o LEFT JOIN refunds_by_order r USING(order_id) GROUP BY channel ORDER BY channel"""
        cursor = connection.execute(query)
        columns = [column[0] for column in cursor.description]
        result = [dict(zip(columns, row)) for row in cursor.fetchall()]
        assert result and all(row["gross_cents"]-row["refund_cents"] == row["net_cents"] for row in result)
        parquet = output / "parquet"
        parquet.mkdir()
        for table in counts:
            destination = str(parquet / ("orders" if table == "orders" else table + ".parquet")).replace("'", "''")
            if table == "orders":
                connection.execute(f"""COPY (SELECT *,strftime(created_date,'%Y-%m') created_month FROM orders)
                  TO '{destination}' (FORMAT PARQUET,PARTITION_BY(created_month),COMPRESSION ZSTD)""")
            else:
                connection.execute(f"COPY {table} TO '{destination}' (FORMAT PARQUET,COMPRESSION ZSTD)")
        pattern = str(parquet / "orders/**/*.parquet")
        from_files = connection.execute("SELECT COUNT(*),SUM(amount_cents)::BIGINT FROM read_parquet(?,hive_partitioning=true)", [pattern]).fetchone()
        from_table = connection.execute("SELECT COUNT(*),SUM(amount_cents)::BIGINT FROM orders").fetchone()
        assert from_files == from_table, "Partitioned Parquet and DuckDB ledger differ"
        for table in counts:
            if table == "orders":
                continue
            assert connection.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(parquet / (table + ".parquet"))]).fetchone()[0] == counts[table]
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == orders
        try:
            connection.execute("DELETE FROM orders")
        except duckdb.InvalidInputException:
            pass
        else:
            raise AssertionError("Read-only database allowed DELETE")
    manifest = {"schema_version": 1, "fixture": "synthetic-analytics-v1", "synthetic": True,
                "duckdb_version": duckdb.__version__, "counts": counts,
                "created_period": ["2025-01-01", "2027-01-01"],
                "money_unit": "CNY integer cents", "orders_partition": "created_month",
                "quarter_query": query, "quarter_result": result,
                "checks": {"item_totals": True, "customer_references": True,
                           "refund_bound": True, "parquet_totals": True, "read_only": True},
                "files": {str(p.relative_to(output)): p.stat().st_size for p in output.rglob("*") if p.is_file()},
                "limitations": ["Synthetic arithmetic checks, not production scale or a performance benchmark.",
                                "Independent from the default SQLite ontology; requires a separate ontology workspace."]}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/generated/analytics"))
    parser.add_argument("--orders", type=int, default=100_000)
    args = parser.parse_args()
    print(json.dumps(generate(args.output,args.orders), ensure_ascii=False, indent=2))
