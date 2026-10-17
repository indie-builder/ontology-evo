WITH RECURSIVE hierarchy_edges AS (
 SELECT 'org' hierarchy,tenant_id,org_version_id version_id,org_id node_id,parent_org_id parent_id,
 valid_from,valid_to,known_from,known_to FROM enterprise.identity__org_version
 UNION ALL
 SELECT 'category',tenant_id,category_version_id,category_id,parent_category_id,
 valid_from,valid_to,known_from,known_to FROM enterprise.catalog__category_version
), hierarchy_paths AS (
 SELECT hierarchy,tenant_id,version_id,node_id start_id,parent_id next_id,[node_id] visited,
 valid_from,valid_to,known_from,known_to,(parent_id=node_id) cyclic
 FROM hierarchy_edges WHERE parent_id IS NOT NULL
 UNION ALL
 SELECT p.hierarchy,p.tenant_id,p.version_id,p.start_id,e.parent_id,list_append(p.visited,e.node_id),
 greatest(p.valid_from,e.valid_from),least(p.valid_to,e.valid_to),
 greatest(p.known_from,e.known_from),least(p.known_to,e.known_to),
 list_contains(p.visited,e.node_id)
 FROM hierarchy_paths p JOIN hierarchy_edges e
 ON e.hierarchy=p.hierarchy AND e.tenant_id=p.tenant_id AND e.node_id=p.next_id
 AND p.valid_from<e.valid_to AND e.valid_from<p.valid_to
 AND p.known_from<e.known_to AND e.known_from<p.known_to
 WHERE NOT p.cyclic
), violations AS (
 SELECT hierarchy||'_hierarchy_cycle' check_id,tenant_id,version_id object_id
 FROM hierarchy_paths WHERE cyclic
 UNION ALL
 SELECT 'customer_temporal_overlap' check_id,a.tenant_id,a.customer_version_id object_id
 FROM enterprise.identity__customer_version a JOIN enterprise.identity__customer_version b
 ON a.tenant_id=b.tenant_id AND a.customer_id=b.customer_id AND a.customer_version_id<b.customer_version_id
 AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to AND a.known_from<b.known_to AND b.known_from<a.known_to
 UNION ALL
 SELECT 'identity_temporal_overlap',a.tenant_id,a.identity_version_id
 FROM enterprise.identity__customer_identity a JOIN enterprise.identity__customer_identity b
 ON a.tenant_id=b.tenant_id AND a.source_system=b.source_system AND a.source_customer_id=b.source_customer_id
 AND a.identity_version_id<b.identity_version_id AND a.mapping_status='confirmed' AND b.mapping_status='confirmed'
 AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to AND a.known_from<b.known_to AND b.known_from<a.known_to
 UNION ALL
 SELECT 'org_temporal_overlap',a.tenant_id,a.org_version_id
 FROM enterprise.identity__org_version a JOIN enterprise.identity__org_version b
 ON a.tenant_id=b.tenant_id AND a.org_id=b.org_id AND a.org_version_id<b.org_version_id
 AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to AND a.known_from<b.known_to AND b.known_from<a.known_to
 UNION ALL
 SELECT 'sku_temporal_overlap',a.tenant_id,a.sku_version_id
 FROM enterprise.catalog__sku_version a JOIN enterprise.catalog__sku_version b
 ON a.tenant_id=b.tenant_id AND a.source_system=b.source_system AND a.source_sku_id=b.source_sku_id
 AND a.sku_version_id<b.sku_version_id AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to
 AND a.known_from<b.known_to AND b.known_from<a.known_to
 UNION ALL
 SELECT 'category_temporal_overlap',a.tenant_id,a.category_version_id
 FROM enterprise.catalog__category_version a JOIN enterprise.catalog__category_version b
 ON a.tenant_id=b.tenant_id AND a.category_id=b.category_id AND a.category_version_id<b.category_version_id
 AND a.valid_from<b.valid_to AND b.valid_from<a.valid_to AND a.known_from<b.known_to AND b.known_from<a.known_to
 UNION ALL
 SELECT 'category_weight_total',tenant_id,sku_version_id||':'||taxonomy||':'||allocation_version
 FROM enterprise.catalog__sku_category_allocation GROUP BY tenant_id,sku_version_id,taxonomy,allocation_version
 HAVING SUM(weight)<>1
 UNION ALL
 SELECT 'attribution_weight_total',tenant_id,order_line_id||':'||model_version
 FROM enterprise.marketing__attribution_allocation GROUP BY tenant_id,order_line_id,model_version HAVING SUM(weight)<>1
 UNION ALL
 SELECT 'payment_allocation_total',p.tenant_id,p.payment_event_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.payments__payment_event p LEFT JOIN enterprise.payments__payment_line_allocation a USING(tenant_id,payment_event_id)
 WHERE p.event_kind='capture' AND p.outcome='succeeded'
 GROUP BY p.tenant_id,p.payment_event_id,p.amount_minor,a.allocation_version HAVING COALESCE(SUM(a.amount_minor),0)<>p.amount_minor
 UNION ALL
 SELECT 'refund_line_total',r.tenant_id,r.refund_event_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.returns__refund_event r LEFT JOIN enterprise.returns__refund_line_allocation a USING(tenant_id,refund_event_id)
 WHERE r.outcome='succeeded' GROUP BY r.tenant_id,r.refund_event_id,r.amount_minor,a.allocation_version
 HAVING COALESCE(SUM(a.amount_minor),0)<>r.amount_minor
 UNION ALL
 SELECT 'refund_payment_total',r.tenant_id,r.refund_event_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.returns__refund_event r LEFT JOIN enterprise.returns__refund_payment_allocation a USING(tenant_id,refund_event_id)
 WHERE r.outcome='succeeded' GROUP BY r.tenant_id,r.refund_event_id,r.amount_minor,a.allocation_version
 HAVING COALESCE(SUM(a.amount_minor),0)<>r.amount_minor
 UNION ALL
 SELECT 'payment_currency_mismatch',a.tenant_id,a.allocation_id
 FROM enterprise.payments__payment_line_allocation a JOIN enterprise.payments__payment_event p USING(tenant_id,payment_event_id)
 JOIN enterprise.commerce__order_line l USING(tenant_id,order_line_id)
 JOIN enterprise.commerce__sales_order o ON o.tenant_id=l.tenant_id AND o.order_id=l.order_id
 WHERE p.currency<>o.currency OR p.currency_exponent<>o.currency_exponent
 UNION ALL
 SELECT 'refund_line_currency_mismatch',a.tenant_id,a.allocation_id
 FROM enterprise.returns__refund_line_allocation a JOIN enterprise.returns__refund_event r USING(tenant_id,refund_event_id)
 JOIN enterprise.commerce__order_line l USING(tenant_id,order_line_id)
 JOIN enterprise.commerce__sales_order o ON o.tenant_id=l.tenant_id AND o.order_id=l.order_id
 WHERE r.currency<>o.currency OR r.currency_exponent<>o.currency_exponent
 UNION ALL
 SELECT 'refund_payment_mismatch',a.tenant_id,a.allocation_id
 FROM enterprise.returns__refund_payment_allocation a JOIN enterprise.returns__refund_event r USING(tenant_id,refund_event_id)
 JOIN enterprise.payments__payment_event p USING(tenant_id,payment_event_id)
 WHERE r.currency<>p.currency OR r.currency_exponent<>p.currency_exponent OR p.event_kind<>'capture' OR p.outcome<>'succeeded'
 UNION ALL
 SELECT 'return_line_mismatch',a.tenant_id,a.allocation_id
 FROM enterprise.returns__refund_line_allocation a JOIN enterprise.returns__return_line r USING(tenant_id,return_line_id)
 WHERE a.order_line_id<>r.order_line_id
 UNION ALL
 SELECT 'return_fulfillment_mismatch',a.tenant_id,a.allocation_id
 FROM enterprise.returns__return_fulfillment_allocation a JOIN enterprise.returns__return_line r USING(tenant_id,return_line_id)
 JOIN enterprise.fulfillment__fulfillment_line f USING(tenant_id,fulfillment_line_id)
 WHERE r.order_line_id<>f.order_line_id
 UNION ALL
 SELECT 'over_fulfillment',l.tenant_id,l.order_line_id
 FROM enterprise.commerce__order_line l JOIN enterprise.fulfillment__fulfillment_line f USING(tenant_id,order_line_id)
 GROUP BY l.tenant_id,l.order_line_id,l.quantity HAVING SUM(f.quantity)>l.quantity
 UNION ALL
 SELECT 'over_return',l.tenant_id,l.order_line_id
 FROM enterprise.commerce__order_line l JOIN enterprise.returns__return_line r USING(tenant_id,order_line_id)
 GROUP BY l.tenant_id,l.order_line_id,l.quantity HAVING SUM(r.quantity)>l.quantity
 UNION ALL
 SELECT 'over_shipment',f.tenant_id,f.fulfillment_line_id
 FROM enterprise.fulfillment__fulfillment_line f JOIN enterprise.fulfillment__shipment_allocation a USING(tenant_id,fulfillment_line_id)
 GROUP BY f.tenant_id,f.fulfillment_line_id,f.quantity HAVING SUM(a.quantity)>f.quantity
 UNION ALL
 SELECT 'return_allocation_total',r.tenant_id,r.return_line_id
 FROM enterprise.returns__return_line r LEFT JOIN enterprise.returns__return_fulfillment_allocation a USING(tenant_id,return_line_id)
 WHERE r.received_at IS NOT NULL GROUP BY r.tenant_id,r.return_line_id,r.quantity
 HAVING COALESCE(SUM(a.quantity),0)<>r.quantity
 UNION ALL
 SELECT 'over_return_fulfillment',f.tenant_id,f.fulfillment_line_id
 FROM enterprise.fulfillment__fulfillment_line f JOIN enterprise.returns__return_fulfillment_allocation a USING(tenant_id,fulfillment_line_id)
 GROUP BY f.tenant_id,f.fulfillment_line_id,f.quantity HAVING SUM(a.quantity)>f.quantity
 UNION ALL
 SELECT 'recognition_total',r.tenant_id,r.recognition_event_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.finance__recognition_event r LEFT JOIN enterprise.finance__recognition_allocation a USING(tenant_id,recognition_event_id)
 GROUP BY r.tenant_id,r.recognition_event_id,r.net_minor,a.allocation_version HAVING COALESCE(SUM(a.net_minor),0)<>r.net_minor
 UNION ALL
 SELECT 'recognition_fulfillment_mismatch',a.tenant_id,a.allocation_id
 FROM enterprise.finance__recognition_allocation a JOIN enterprise.fulfillment__fulfillment_line f USING(tenant_id,fulfillment_line_id)
 WHERE a.order_line_id<>f.order_line_id
 UNION ALL
 SELECT 'invoice_allocation_total',i.tenant_id,i.invoice_line_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.finance__invoice_line i LEFT JOIN enterprise.finance__invoice_order_allocation a USING(tenant_id,invoice_line_id)
 GROUP BY i.tenant_id,i.invoice_line_id,i.net_minor,a.allocation_version HAVING COALESCE(SUM(a.net_minor),0)<>i.net_minor
 UNION ALL
 SELECT 'settlement_allocation_total',s.tenant_id,s.settlement_line_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.finance__settlement_line s LEFT JOIN enterprise.finance__settlement_payment_allocation a USING(tenant_id,settlement_line_id)
 GROUP BY s.tenant_id,s.settlement_line_id,s.gross_minor,s.fee_minor,a.allocation_version
 HAVING COALESCE(SUM(a.gross_minor),0)<>s.gross_minor OR COALESCE(SUM(a.fee_minor),0)<>s.fee_minor
 UNION ALL
 SELECT 'cost_allocation_total',c.tenant_id,c.cost_event_id||':'||COALESCE(a.allocation_version,'missing')
 FROM enterprise.fulfillment__inventory_cost_event c LEFT JOIN enterprise.fulfillment__cost_allocation a USING(tenant_id,cost_event_id)
 GROUP BY c.tenant_id,c.cost_event_id,c.amount_minor,a.allocation_version HAVING COALESCE(SUM(a.amount_minor),0)<>c.amount_minor
 UNION ALL
 SELECT 'journal_unbalanced',tenant_id,journal_id||':'||legal_entity_id||':'||currency
 FROM enterprise.finance__journal_line GROUP BY tenant_id,journal_id,legal_entity_id,currency,currency_exponent
 HAVING SUM(debit_minor)<>SUM(credit_minor)
)
SELECT DISTINCT check_id,tenant_id,object_id FROM violations ORDER BY check_id,tenant_id,object_id
