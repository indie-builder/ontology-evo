#!/usr/bin/env python3
"""Compile the proposed schema and exercise public relational counterexamples."""
import json
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parent


def integrity_violations(connection):
    return connection.execute((ROOT / "quality-checks.sql").read_text()).fetchall()


def verify():
    with duckdb.connect() as connection:
        connection.execute((ROOT / "schema.sql").read_text())
        tables = connection.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_type='BASE TABLE' ORDER BY table_schema,table_name").fetchall()
        connection.execute("""
        INSERT INTO enterprise.commerce__sales_order VALUES
          ('t1','o1','oms','source-1','c1','le1','store1','web','2026-07-01T00:00:00Z','CNY',2,false,'b1');
        INSERT INTO enterprise.commerce__order_line VALUES
          ('t1','l1','o1','sku1',2,10000,0,0),
          ('t1','l2','o1','sku2',1,10000,0,0);
        INSERT INTO enterprise.payments__payment_event VALUES
          ('t1','p1','psp','psp1','payment1','capture','2026-07-01T00:00:00Z','2026-07-01T00:00:00Z','CNY',2,20000,'succeeded');
        INSERT INTO enterprise.payments__payment_line_allocation VALUES
          ('t1','pa1','p1','l1','v1','explicit',10000),
          ('t1','pa2','p1','l2','v1','explicit',10000);
        INSERT INTO enterprise.fulfillment__fulfillment_line VALUES
          ('t1','f1','l1','w1',1,'2026-07-02T00:00:00Z','2026-07-02T00:00:00Z'),
          ('t1','f2','l1','w2',1,'2026-07-03T00:00:00Z','2026-07-03T00:00:00Z'),
          ('t1','f3','l2','w1',1,'2026-07-02T00:00:00Z','2026-07-02T00:00:00Z');
        INSERT INTO enterprise.returns__refund_event VALUES
          ('t1','r1','psp','ref1','refund1','2026-08-01T00:00:00Z','2026-08-01T00:00:00Z','CNY',2,2000,'succeeded'),
          ('t1','r2','psp','ref2','refund2','2026-09-01T00:00:00Z','2026-10-05T00:00:00Z','CNY',2,1000,'succeeded');
        INSERT INTO enterprise.returns__refund_line_allocation VALUES
          ('t1','ra1','r1','l1',NULL,'v1','explicit',2000),
          ('t1','ra2','r2','l1',NULL,'v1','explicit',1000);
        INSERT INTO enterprise.returns__refund_payment_allocation VALUES
          ('t1','rp1','r1','p1',2000,'v1'),('t1','rp2','r2','p1',1000,'v1');
        """)
        naive = connection.execute("""SELECT SUM(p.amount_minor) FROM enterprise.payments__payment_line_allocation p
          JOIN enterprise.fulfillment__fulfillment_line f USING(tenant_id,order_line_id)
          LEFT JOIN enterprise.returns__refund_line_allocation r USING(tenant_id,order_line_id)""").fetchone()[0]
        paid = connection.execute("SELECT SUM(amount_minor) FROM enterprise.payments__payment_line_allocation").fetchone()[0]
        assert naive == 50000 and paid == 20000, (naive, paid)
        distinct_amount = connection.execute("SELECT SUM(DISTINCT amount_minor) FROM enterprise.payments__payment_line_allocation").fetchone()[0]
        assert distinct_amount == 10000 and distinct_amount != paid
        correct = connection.execute("""WITH paid AS (
          SELECT tenant_id,order_line_id,SUM(amount_minor) paid_minor
          FROM enterprise.payments__payment_line_allocation WHERE allocation_version='v1' GROUP BY ALL
        ), refunded AS (
          SELECT a.tenant_id,a.order_line_id,SUM(a.amount_minor) refund_minor
          FROM enterprise.returns__refund_line_allocation a JOIN enterprise.returns__refund_event e USING(tenant_id,refund_event_id)
          WHERE e.succeeded_at<'2026-10-01T00:00:00Z' AND e.known_at<'2026-10-01T00:00:00Z'
          AND a.allocation_version='v1' GROUP BY a.tenant_id,a.order_line_id
        ) SELECT SUM(paid_minor-COALESCE(refund_minor,0))
          FROM paid LEFT JOIN refunded USING(tenant_id,order_line_id)""").fetchone()[0]
        assert correct == 18000
        restated = connection.execute("SELECT SUM(amount_minor) FROM enterprise.returns__refund_event WHERE succeeded_at<'2026-10-01T00:00:00Z' AND known_at<'2026-10-10T00:00:00Z'").fetchone()[0]
        assert restated == 3000
        connection.execute("""INSERT INTO enterprise.identity__customer_version VALUES
          ('t1','cv1','c1','east','consumer','2026-01-01T00:00:00Z','2026-08-01T00:00:00Z','2026-01-01T00:00:00Z','9999-01-01T00:00:00Z'),
          ('t1','cv2','c1','south','consumer','2026-08-01T00:00:00Z','9999-01-01T00:00:00Z','2026-08-01T00:00:00Z','9999-01-01T00:00:00Z')""")
        regions = connection.execute("""SELECT region_id FROM enterprise.identity__customer_version
          WHERE tenant_id='t1' AND customer_id='c1' AND valid_from<='2026-07-01T00:00:00Z'
          AND valid_to>'2026-07-01T00:00:00Z' AND known_from<='2026-10-01T00:00:00Z' AND known_to>'2026-10-01T00:00:00Z'""").fetchall()
        assert regions == [('east',)]
        try:
            connection.execute("INSERT INTO enterprise.payments__payment_line_allocation VALUES ('t2','cross','p1','l1','v1','explicit',1)")
        except duckdb.ConstraintException:
            pass
        else:
            raise AssertionError("Cross-tenant relationship was accepted")
        totals = connection.execute("""SELECT e.payment_event_id,e.amount_minor,SUM(a.amount_minor)
          FROM enterprise.payments__payment_event e JOIN enterprise.payments__payment_line_allocation a USING(tenant_id,payment_event_id)
          WHERE a.allocation_version='v1' GROUP BY e.payment_event_id,e.amount_minor""").fetchall()
        assert totals == [('p1',20000,20000)]
        assert integrity_violations(connection) == [], integrity_violations(connection)
        schema = []
        for domain, name in tables:
            columns = connection.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=? AND table_name=? ORDER BY ordinal_position", [domain,name]).fetchall()
            schema.append({"table": domain+'.'+name,"columns":[{"name":n,"type":t} for n,t in columns]})
        return {"status":"design_checks_passed","runtime_implemented":False,
                "schema_table_count":len(tables),"tables":schema,
                "public_counterexamples":{"naive_fanout_minor":naive,"actual_paid_minor":paid,"sum_distinct_minor":distinct_amount,
                    "close_snapshot_net_minor":correct,"later_known_refund_minor":restated,
                    "historical_region":"east","cross_tenant_fk_rejected":True,
                    "payment_allocation_conserved":True},
                "limitations":["Public hand-built counterexamples, not held-out Agent evaluation.",
                    "No full enterprise generator, production adapters or official ontology build for this schema implemented."]}


if __name__ == '__main__':
    print(json.dumps(verify(),ensure_ascii=False,indent=2))
