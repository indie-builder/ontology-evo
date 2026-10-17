CREATE SCHEMA enterprise;
-- Proposed relational contract, not a production migration or populated warehouse.

CREATE TABLE enterprise.audit__source_batch (
 tenant_id VARCHAR, batch_id VARCHAR, source_system VARCHAR NOT NULL,
 source_watermark VARCHAR, extracted_at TIMESTAMPTZ NOT NULL,
 snapshot_id VARCHAR NOT NULL, PRIMARY KEY(tenant_id,batch_id)
);
CREATE TABLE enterprise.audit__source_record (
 tenant_id VARCHAR, source_system VARCHAR, event_id VARCHAR, source_version BIGINT,
 batch_id VARCHAR NOT NULL, business_at TIMESTAMPTZ NOT NULL,
 received_at TIMESTAMPTZ NOT NULL, operation VARCHAR NOT NULL,
 payload JSON NOT NULL, PRIMARY KEY(tenant_id,source_system,event_id,source_version)
);
CREATE TABLE enterprise.identity__customer_identity (
 tenant_id VARCHAR, identity_version_id VARCHAR, source_system VARCHAR NOT NULL,
 source_customer_id VARCHAR NOT NULL, customer_id VARCHAR,
 valid_from TIMESTAMPTZ NOT NULL, valid_to TIMESTAMPTZ NOT NULL,
 known_from TIMESTAMPTZ NOT NULL, known_to TIMESTAMPTZ NOT NULL,
 mapping_status VARCHAR NOT NULL CHECK(mapping_status IN ('confirmed','ambiguous','unmapped')),
 PRIMARY KEY(tenant_id,identity_version_id),
 CHECK(mapping_status<>'confirmed' OR customer_id IS NOT NULL),
 CHECK(mapping_status<>'unmapped' OR customer_id IS NULL),
 CHECK(valid_from<valid_to), CHECK(known_from<known_to)
);
CREATE TABLE enterprise.identity__customer_version (
 tenant_id VARCHAR, customer_version_id VARCHAR, customer_id VARCHAR NOT NULL,
 region_id VARCHAR NOT NULL, segment VARCHAR NOT NULL,
 valid_from TIMESTAMPTZ NOT NULL, valid_to TIMESTAMPTZ NOT NULL,
 known_from TIMESTAMPTZ NOT NULL, known_to TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,customer_version_id),
 CHECK(valid_from<valid_to), CHECK(known_from<known_to)
);
CREATE TABLE enterprise.identity__org_version (
 tenant_id VARCHAR, org_version_id VARCHAR, org_id VARCHAR NOT NULL,
 parent_org_id VARCHAR, legal_entity_id VARCHAR NOT NULL,
 valid_from TIMESTAMPTZ NOT NULL, valid_to TIMESTAMPTZ NOT NULL,
 known_from TIMESTAMPTZ NOT NULL, known_to TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,org_version_id), CHECK(valid_from<valid_to), CHECK(known_from<known_to)
);
CREATE TABLE enterprise.catalog__sku_version (
 tenant_id VARCHAR, sku_version_id VARCHAR, sku_id VARCHAR NOT NULL,
 source_system VARCHAR NOT NULL, source_sku_id VARCHAR NOT NULL,
 brand_id VARCHAR NOT NULL, valid_from TIMESTAMPTZ NOT NULL,
 valid_to TIMESTAMPTZ NOT NULL, known_from TIMESTAMPTZ NOT NULL, known_to TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,sku_version_id), CHECK(valid_from<valid_to), CHECK(known_from<known_to)
);
CREATE TABLE enterprise.catalog__category_version (
 tenant_id VARCHAR, category_version_id VARCHAR, category_id VARCHAR NOT NULL,
 parent_category_id VARCHAR, category_name VARCHAR NOT NULL,
 valid_from TIMESTAMPTZ NOT NULL, valid_to TIMESTAMPTZ NOT NULL,
 known_from TIMESTAMPTZ NOT NULL, known_to TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,category_version_id), CHECK(valid_from<valid_to), CHECK(known_from<known_to)
);
CREATE TABLE enterprise.catalog__sku_category_allocation (
 tenant_id VARCHAR, sku_category_id VARCHAR, sku_version_id VARCHAR NOT NULL,
 category_version_id VARCHAR NOT NULL, taxonomy VARCHAR NOT NULL,
 allocation_version VARCHAR NOT NULL, weight DECIMAL(18,12) NOT NULL CHECK(weight>=0 AND weight<=1),
 PRIMARY KEY(tenant_id,sku_category_id),
 FOREIGN KEY(tenant_id,sku_version_id) REFERENCES enterprise.catalog__sku_version(tenant_id,sku_version_id),
 FOREIGN KEY(tenant_id,category_version_id) REFERENCES enterprise.catalog__category_version(tenant_id,category_version_id)
);
CREATE TABLE enterprise.commerce__sales_order (
 tenant_id VARCHAR, order_id VARCHAR, source_system VARCHAR NOT NULL,
 source_order_id VARCHAR NOT NULL, source_customer_id VARCHAR NOT NULL,
 legal_entity_id VARCHAR NOT NULL, store_org_id VARCHAR NOT NULL,
 channel_id VARCHAR NOT NULL, created_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL CHECK(currency_exponent<=4),
 is_test BOOLEAN NOT NULL, batch_id VARCHAR NOT NULL,
 PRIMARY KEY(tenant_id,order_id), UNIQUE(tenant_id,source_system,source_order_id)
);
CREATE TABLE enterprise.commerce__order_line (
 tenant_id VARCHAR, order_line_id VARCHAR, order_id VARCHAR NOT NULL,
 sku_id VARCHAR NOT NULL, quantity DECIMAL(18,6) NOT NULL CHECK(quantity>0),
 merchandise_minor BIGINT NOT NULL CHECK(merchandise_minor>=0),
 tax_minor BIGINT NOT NULL CHECK(tax_minor>=0), shipping_minor BIGINT NOT NULL CHECK(shipping_minor>=0),
 PRIMARY KEY(tenant_id,order_line_id),
 FOREIGN KEY(tenant_id,order_id) REFERENCES enterprise.commerce__sales_order(tenant_id,order_id)
);
CREATE TABLE enterprise.commerce__order_status_event (
 tenant_id VARCHAR, status_event_id VARCHAR, order_id VARCHAR NOT NULL,
 event_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 source_sequence BIGINT NOT NULL, status VARCHAR NOT NULL,
 PRIMARY KEY(tenant_id,status_event_id),
 FOREIGN KEY(tenant_id,order_id) REFERENCES enterprise.commerce__sales_order(tenant_id,order_id)
);
CREATE TABLE enterprise.commerce__discount_allocation (
 tenant_id VARCHAR, discount_allocation_id VARCHAR, promotion_id VARCHAR NOT NULL,
 order_line_id VARCHAR NOT NULL, funder VARCHAR NOT NULL,
 allocation_version VARCHAR NOT NULL, amount_minor BIGINT NOT NULL CHECK(amount_minor>=0),
 PRIMARY KEY(tenant_id,discount_allocation_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id)
);
CREATE TABLE enterprise.payments__payment_event (
 tenant_id VARCHAR, payment_event_id VARCHAR, source_system VARCHAR NOT NULL,
 source_event_id VARCHAR NOT NULL, payment_id VARCHAR NOT NULL,
 event_kind VARCHAR NOT NULL CHECK(event_kind IN ('authorization','capture','void','chargeback')),
 event_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 amount_minor BIGINT NOT NULL CHECK(amount_minor>=0), outcome VARCHAR NOT NULL,
 PRIMARY KEY(tenant_id,payment_event_id), UNIQUE(tenant_id,source_system,source_event_id)
);
CREATE TABLE enterprise.payments__payment_line_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, payment_event_id VARCHAR NOT NULL,
 order_line_id VARCHAR NOT NULL, allocation_version VARCHAR NOT NULL,
 allocation_method VARCHAR NOT NULL, amount_minor BIGINT NOT NULL CHECK(amount_minor>=0),
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,payment_event_id) REFERENCES enterprise.payments__payment_event(tenant_id,payment_event_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id)
);
CREATE TABLE enterprise.fulfillment__fulfillment_line (
 tenant_id VARCHAR, fulfillment_line_id VARCHAR, order_line_id VARCHAR NOT NULL,
 warehouse_id VARCHAR NOT NULL, quantity DECIMAL(18,6) NOT NULL CHECK(quantity>0),
 fulfilled_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,fulfillment_line_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id)
);
CREATE TABLE enterprise.fulfillment__shipment (
 tenant_id VARCHAR, shipment_id VARCHAR, carrier_id VARCHAR NOT NULL,
 shipped_at TIMESTAMPTZ NOT NULL, delivered_at TIMESTAMPTZ,
 PRIMARY KEY(tenant_id,shipment_id)
);
CREATE TABLE enterprise.fulfillment__shipment_allocation (
 tenant_id VARCHAR, shipment_allocation_id VARCHAR, fulfillment_line_id VARCHAR NOT NULL,
 shipment_id VARCHAR NOT NULL, quantity DECIMAL(18,6) NOT NULL CHECK(quantity>0),
 PRIMARY KEY(tenant_id,shipment_allocation_id),
 FOREIGN KEY(tenant_id,fulfillment_line_id) REFERENCES enterprise.fulfillment__fulfillment_line(tenant_id,fulfillment_line_id),
 FOREIGN KEY(tenant_id,shipment_id) REFERENCES enterprise.fulfillment__shipment(tenant_id,shipment_id)
);
CREATE TABLE enterprise.returns__return_line (
 tenant_id VARCHAR, return_line_id VARCHAR, order_line_id VARCHAR NOT NULL,
 quantity DECIMAL(18,6) NOT NULL CHECK(quantity>0), reason VARCHAR NOT NULL,
 requested_at TIMESTAMPTZ NOT NULL, received_at TIMESTAMPTZ, known_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,return_line_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id)
);
CREATE TABLE enterprise.returns__return_fulfillment_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, return_line_id VARCHAR NOT NULL,
 fulfillment_line_id VARCHAR NOT NULL, quantity DECIMAL(18,6) NOT NULL CHECK(quantity>0),
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,return_line_id) REFERENCES enterprise.returns__return_line(tenant_id,return_line_id),
 FOREIGN KEY(tenant_id,fulfillment_line_id) REFERENCES enterprise.fulfillment__fulfillment_line(tenant_id,fulfillment_line_id)
);
CREATE TABLE enterprise.returns__refund_event (
 tenant_id VARCHAR, refund_event_id VARCHAR, source_system VARCHAR NOT NULL,
 source_event_id VARCHAR NOT NULL, refund_id VARCHAR NOT NULL,
 succeeded_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 amount_minor BIGINT NOT NULL CHECK(amount_minor>=0), outcome VARCHAR NOT NULL,
 PRIMARY KEY(tenant_id,refund_event_id), UNIQUE(tenant_id,source_system,source_event_id)
);
CREATE TABLE enterprise.returns__refund_line_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, refund_event_id VARCHAR NOT NULL,
 order_line_id VARCHAR NOT NULL, return_line_id VARCHAR,
 allocation_version VARCHAR NOT NULL, allocation_method VARCHAR NOT NULL,
 amount_minor BIGINT NOT NULL CHECK(amount_minor>=0),
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,refund_event_id) REFERENCES enterprise.returns__refund_event(tenant_id,refund_event_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id),
 FOREIGN KEY(tenant_id,return_line_id) REFERENCES enterprise.returns__return_line(tenant_id,return_line_id)
);
CREATE TABLE enterprise.returns__refund_payment_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, refund_event_id VARCHAR NOT NULL,
 payment_event_id VARCHAR NOT NULL, amount_minor BIGINT NOT NULL CHECK(amount_minor>=0),
 allocation_version VARCHAR NOT NULL, PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,refund_event_id) REFERENCES enterprise.returns__refund_event(tenant_id,refund_event_id),
 FOREIGN KEY(tenant_id,payment_event_id) REFERENCES enterprise.payments__payment_event(tenant_id,payment_event_id)
);
CREATE TABLE enterprise.finance__fx_rate (
 tenant_id VARCHAR, rate_id VARCHAR, rate_date DATE NOT NULL,
 from_currency VARCHAR NOT NULL, to_currency VARCHAR NOT NULL,
 rate_type VARCHAR NOT NULL, rate DECIMAL(24,12) NOT NULL CHECK(rate>0),
 known_at TIMESTAMPTZ NOT NULL, PRIMARY KEY(tenant_id,rate_id),
 UNIQUE(tenant_id,rate_date,from_currency,to_currency,rate_type,known_at)
);
CREATE TABLE enterprise.finance__invoice_line (
 tenant_id VARCHAR, invoice_line_id VARCHAR, legal_entity_id VARCHAR NOT NULL,
 invoice_id VARCHAR NOT NULL, issued_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 net_minor BIGINT NOT NULL, tax_minor BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,invoice_line_id)
);
CREATE TABLE enterprise.finance__invoice_order_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, invoice_line_id VARCHAR NOT NULL,
 order_line_id VARCHAR NOT NULL, allocation_version VARCHAR NOT NULL, net_minor BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,invoice_line_id) REFERENCES enterprise.finance__invoice_line(tenant_id,invoice_line_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id)
);
CREATE TABLE enterprise.finance__recognition_event (
 tenant_id VARCHAR, recognition_event_id VARCHAR, legal_entity_id VARCHAR NOT NULL,
 recognized_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 net_minor BIGINT NOT NULL, reversal_of VARCHAR,
 PRIMARY KEY(tenant_id,recognition_event_id)
);
CREATE TABLE enterprise.finance__recognition_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, recognition_event_id VARCHAR NOT NULL,
 order_line_id VARCHAR NOT NULL, fulfillment_line_id VARCHAR,
 allocation_version VARCHAR NOT NULL, net_minor BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,recognition_event_id) REFERENCES enterprise.finance__recognition_event(tenant_id,recognition_event_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id),
 FOREIGN KEY(tenant_id,fulfillment_line_id) REFERENCES enterprise.fulfillment__fulfillment_line(tenant_id,fulfillment_line_id)
);
CREATE TABLE enterprise.finance__settlement_line (
 tenant_id VARCHAR, settlement_line_id VARCHAR, statement_id VARCHAR NOT NULL,
 legal_entity_id VARCHAR NOT NULL, settled_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 gross_minor BIGINT NOT NULL, fee_minor BIGINT NOT NULL, net_minor BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,settlement_line_id), CHECK(gross_minor-fee_minor=net_minor)
);
CREATE TABLE enterprise.finance__settlement_payment_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, settlement_line_id VARCHAR NOT NULL,
 payment_event_id VARCHAR NOT NULL, allocation_version VARCHAR NOT NULL,
 gross_minor BIGINT NOT NULL, fee_minor BIGINT NOT NULL,
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,settlement_line_id) REFERENCES enterprise.finance__settlement_line(tenant_id,settlement_line_id),
 FOREIGN KEY(tenant_id,payment_event_id) REFERENCES enterprise.payments__payment_event(tenant_id,payment_event_id)
);
CREATE TABLE enterprise.finance__journal_line (
 tenant_id VARCHAR, journal_line_id VARCHAR, journal_id VARCHAR NOT NULL,
 legal_entity_id VARCHAR NOT NULL, account_id VARCHAR NOT NULL,
 posted_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 debit_minor BIGINT NOT NULL CHECK(debit_minor>=0), credit_minor BIGINT NOT NULL CHECK(credit_minor>=0),
 PRIMARY KEY(tenant_id,journal_line_id), CHECK(debit_minor=0 OR credit_minor=0)
);
CREATE TABLE enterprise.finance__journal_recognition_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, journal_line_id VARCHAR NOT NULL,
 recognition_event_id VARCHAR NOT NULL, allocation_version VARCHAR NOT NULL,
 signed_minor BIGINT NOT NULL, PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,journal_line_id) REFERENCES enterprise.finance__journal_line(tenant_id,journal_line_id),
 FOREIGN KEY(tenant_id,recognition_event_id) REFERENCES enterprise.finance__recognition_event(tenant_id,recognition_event_id)
);
CREATE TABLE enterprise.fulfillment__inventory_cost_event (
 tenant_id VARCHAR, cost_event_id VARCHAR, sku_id VARCHAR NOT NULL,
 warehouse_id VARCHAR NOT NULL, inventory_lot_id VARCHAR NOT NULL,
 cost_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 amount_minor BIGINT NOT NULL, PRIMARY KEY(tenant_id,cost_event_id)
);
CREATE TABLE enterprise.fulfillment__cost_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, fulfillment_line_id VARCHAR NOT NULL,
 cost_event_id VARCHAR NOT NULL, allocation_version VARCHAR NOT NULL,
 amount_minor BIGINT NOT NULL, PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,fulfillment_line_id) REFERENCES enterprise.fulfillment__fulfillment_line(tenant_id,fulfillment_line_id),
 FOREIGN KEY(tenant_id,cost_event_id) REFERENCES enterprise.fulfillment__inventory_cost_event(tenant_id,cost_event_id)
);
CREATE TABLE enterprise.marketing__touch (
 tenant_id VARCHAR, touch_id VARCHAR, source_system VARCHAR NOT NULL,
 anonymous_id VARCHAR NOT NULL, source_customer_id VARCHAR,
 campaign_id VARCHAR NOT NULL, touched_at TIMESTAMPTZ NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(tenant_id,touch_id)
);
CREATE TABLE enterprise.marketing__attribution_allocation (
 tenant_id VARCHAR, allocation_id VARCHAR, order_line_id VARCHAR NOT NULL,
 touch_id VARCHAR NOT NULL, model_version VARCHAR NOT NULL,
 weight DECIMAL(18,12) NOT NULL CHECK(weight>=0 AND weight<=1),
 PRIMARY KEY(tenant_id,allocation_id),
 FOREIGN KEY(tenant_id,order_line_id) REFERENCES enterprise.commerce__order_line(tenant_id,order_line_id),
 FOREIGN KEY(tenant_id,touch_id) REFERENCES enterprise.marketing__touch(tenant_id,touch_id)
);
CREATE TABLE enterprise.marketing__spend (
 tenant_id VARCHAR, spend_id VARCHAR, campaign_id VARCHAR NOT NULL,
 legal_entity_id VARCHAR NOT NULL, spent_date DATE NOT NULL, known_at TIMESTAMPTZ NOT NULL,
 currency VARCHAR NOT NULL, currency_exponent UTINYINT NOT NULL,
 amount_minor BIGINT NOT NULL CHECK(amount_minor>=0), PRIMARY KEY(tenant_id,spend_id)
);
