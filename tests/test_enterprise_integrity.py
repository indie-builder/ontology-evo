import importlib.util
import unittest
from pathlib import Path
import duckdb

ROOT = Path(__file__).resolve().parents[1] / "design/enterprise"
spec = importlib.util.spec_from_file_location("enterprise_design", ROOT / "verify-design.py")
design = importlib.util.module_from_spec(spec)
spec.loader.exec_module(design)


class EnterpriseIntegrityTest(unittest.TestCase):
    def test_conflicting_temporal_versions_are_observable(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            connection.execute("""INSERT INTO enterprise.identity__customer_version VALUES
              ('t1','a','c1','east','consumer','2026-01-01','2027-01-01','2026-01-01','9999-01-01'),
              ('t1','b','c1','south','consumer','2026-02-01','2027-01-01','2026-02-01','9999-01-01')""")
            violations = design.integrity_violations(connection)
            self.assertIn("customer_temporal_overlap", {row[0] for row in violations})

    def test_missing_category_references_are_rejected(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            with self.assertRaises(duckdb.ConstraintException):
                connection.execute("INSERT INTO enterprise.catalog__sku_category_allocation VALUES ('t1','a','missing-sku','missing-category','sales','v1',1)")

    def test_unmapped_identity_does_not_require_invented_customer(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            connection.execute("INSERT INTO enterprise.identity__customer_identity VALUES ('t1','unmapped','crm','source1',NULL,'2026-01-01','2027-01-01','2026-01-01','9999-01-01','unmapped')")
            with self.assertRaises(duckdb.ConstraintException):
                connection.execute("INSERT INTO enterprise.identity__customer_identity VALUES ('t1','bad','crm','source2',NULL,'2026-01-01','2027-01-01','2026-01-01','9999-01-01','confirmed')")

    def test_invalid_weights_and_unbalanced_journal_are_reported(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            connection.execute("""INSERT INTO enterprise.catalog__sku_version VALUES
              ('t1','sku-v1','sku1','erp','s1','brand','2026-01-01','2027-01-01','2026-01-01','9999-01-01');
              INSERT INTO enterprise.catalog__category_version VALUES
              ('t1','cat-v1','cat1',NULL,'category','2026-01-01','2027-01-01','2026-01-01','9999-01-01');
              INSERT INTO enterprise.catalog__sku_category_allocation VALUES ('t1','weight','sku-v1','cat-v1','sales','v1',0.7);
              INSERT INTO enterprise.finance__journal_line VALUES
              ('t1','j1','journal','entity','account','2026-07-01','2026-07-01','CNY',2,100,0)""")
            checks = {row[0] for row in design.integrity_violations(connection)}
            self.assertIn("category_weight_total", checks)
            self.assertIn("journal_unbalanced", checks)

    def test_hierarchy_cycles_require_overlapping_business_and_known_time(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            connection.execute("""INSERT INTO enterprise.identity__org_version VALUES
              ('t1','oa','a','b','le1','2026-01-01','2027-01-01','2026-01-01','9999-01-01'),
              ('t1','ob','b','a','le1','2026-01-01','2027-01-01','2026-01-01','9999-01-01');
              INSERT INTO enterprise.catalog__category_version VALUES
              ('t1','ca','a','b','A','2026-01-01','2027-01-01','2026-01-01','9999-01-01'),
              ('t1','cb','b','a','B','2026-01-01','2027-01-01','2026-01-01','9999-01-01')""")
            checks = {row[0] for row in design.integrity_violations(connection)}
            self.assertIn("org_hierarchy_cycle", checks)
            self.assertIn("category_hierarchy_cycle", checks)
            connection.execute("UPDATE enterprise.identity__org_version SET valid_from='2027-01-01',valid_to='2028-01-01' WHERE org_id='b'")
            connection.execute("UPDATE enterprise.catalog__category_version SET known_from='2027-01-01',known_to='9999-01-01' WHERE category_id='b'")
            connection.execute("UPDATE enterprise.catalog__category_version SET known_to='2027-01-01' WHERE category_id='a'")
            checks = {row[0] for row in design.integrity_violations(connection)}
            self.assertNotIn("org_hierarchy_cycle", checks)
            self.assertNotIn("category_hierarchy_cycle", checks)

    def test_finance_allocations_reject_currency_and_exponent_mismatch(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            connection.execute("""
              INSERT INTO enterprise.commerce__sales_order VALUES
                ('t1','o1','oms','source1','c1','le1','store1','web','2026-07-01','CNY',2,false,'b1');
              INSERT INTO enterprise.commerce__order_line VALUES ('t1','l1','o1','sku1',1,10000,0,0);
              INSERT INTO enterprise.payments__payment_event VALUES
                ('t1','p1','psp','e1','pay1','capture','2026-07-01','2026-07-01','CNY',2,10000,'succeeded');
              INSERT INTO enterprise.payments__payment_line_allocation VALUES ('t1','pa','p1','l1','v1','explicit',10000);
              INSERT INTO enterprise.finance__settlement_line VALUES
                ('t1','s1','stmt','le1','2026-07-01','2026-07-01','USD',2,10000,0,10000);
              INSERT INTO enterprise.finance__settlement_payment_allocation VALUES ('t1','sa','s1','p1','v1',10000,0);
              INSERT INTO enterprise.finance__invoice_line VALUES
                ('t1','i1','le1','invoice','2026-07-01','2026-07-01','CNY',0,10000,0);
              INSERT INTO enterprise.finance__invoice_order_allocation VALUES ('t1','ia','i1','l1','v1',10000);
              INSERT INTO enterprise.finance__recognition_event VALUES
                ('t1','r1','le1','2026-07-01','2026-07-01','USD',2,10000,NULL);
              INSERT INTO enterprise.finance__recognition_allocation VALUES ('t1','ra','r1','l1',NULL,'v1',10000);
            """)
            checks = {row[0] for row in design.integrity_violations(connection)}
            self.assertTrue({'settlement_currency_mismatch','invoice_currency_mismatch','recognition_currency_mismatch'}.issubset(checks), checks)
            connection.execute("UPDATE enterprise.finance__settlement_line SET currency='CNY'")
            connection.execute("UPDATE enterprise.finance__invoice_line SET currency_exponent=2")
            connection.execute("UPDATE enterprise.finance__recognition_event SET currency='CNY'")
            self.assertEqual(design.integrity_violations(connection), [])

    def test_cost_and_journal_bridges_check_currency_and_exponent(self):
        for currency, exponent in [('USD',2),('CNY',0),('CNY',2)]:
            with self.subTest(currency=currency, exponent=exponent), duckdb.connect() as connection:
                connection.execute((ROOT / "schema.sql").read_text())
                connection.execute("""
                  INSERT INTO enterprise.commerce__sales_order VALUES ('t1','o1','oms','s1','c1','le1','store','web','2026-07-01','CNY',2,false,'b1');
                  INSERT INTO enterprise.commerce__order_line VALUES ('t1','l1','o1','sku1',1,10000,0,0);
                  INSERT INTO enterprise.fulfillment__fulfillment_line VALUES ('t1','f1','l1','w1',1,'2026-07-01','2026-07-01');
                  INSERT INTO enterprise.finance__recognition_event VALUES ('t1','r1','le1','2026-07-01','2026-07-01','CNY',2,10000,NULL);
                  INSERT INTO enterprise.finance__recognition_allocation VALUES ('t1','ra','r1','l1','f1','v1',10000);
                """)
                connection.execute("INSERT INTO enterprise.fulfillment__inventory_cost_event VALUES ('t1','c1','sku1','w1','lot','2026-07-01','2026-07-01',?,?,5000)",[currency,exponent])
                connection.execute("INSERT INTO enterprise.fulfillment__cost_allocation VALUES ('t1','ca','f1','c1','v1',5000)")
                for key,debit,credit in [('j1',10000,0),('j2',0,10000)]:
                    connection.execute("INSERT INTO enterprise.finance__journal_line VALUES (? ,?,'journal','le1','account','2026-07-01','2026-07-01',?,?,?,?)",['t1',key,currency,exponent,debit,credit])
                connection.execute("INSERT INTO enterprise.finance__journal_recognition_allocation VALUES ('t1','ja','j1','r1','v1',10000)")
                checks = {row[0] for row in design.integrity_violations(connection)}
                if (currency,exponent)==('CNY',2):
                    self.assertEqual(checks,set())
                else:
                    self.assertTrue({'journal_recognition_currency_mismatch','cost_currency_mismatch'}.issubset(checks), checks)

    def test_weights_and_allocations_cannot_silently_pass(self):
        with duckdb.connect() as connection:
            connection.execute((ROOT / "schema.sql").read_text())
            connection.execute("""INSERT INTO enterprise.payments__payment_event VALUES
              ('t1','p1','psp','e1','pay1','capture','2026-07-01','2026-07-01','CNY',2,10000,'succeeded')""")
            self.assertIn("payment_allocation_total", {row[0] for row in design.integrity_violations(connection)})


if __name__ == '__main__':
    unittest.main()
