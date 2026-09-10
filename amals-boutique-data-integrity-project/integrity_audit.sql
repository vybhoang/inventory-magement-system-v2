-- integrity_audit.sql
-- ---------------------------------------------------------------------------
-- Data-integrity audit run against the three raw source tables (loaded as-is,
-- no cleaning applied yet) inside raw_sources.db. Each query below targets one
-- concrete class of integrity gap found across Amal's Boutique's three legacy
-- product data sources (in-store POS, supplier catalog feed, e-commerce
-- platform export) before they were centralized into a single master catalog.
--
-- Run with:  sqlite3 raw_sources.db < integrity_audit.sql
-- ---------------------------------------------------------------------------

-- 1. Missing / blank supplier reference in the POS export -------------------
SELECT COUNT(*) AS pos_missing_supplier
FROM legacy_pos
WHERE supplier_name IS NULL OR TRIM(supplier_name) = '';

-- 2. Supplier names in the POS export that don't match the canonical
--    4-supplier list (retired aliases, abbreviations, typos) ---------------
SELECT supplier_name, COUNT(*) AS occurrences
FROM legacy_pos
WHERE TRIM(supplier_name) != ''
  AND supplier_name NOT IN
      ('Fashion Hub Ltd', 'Textile World Co', 'Apparel Solutions', 'Atelier Nord')
GROUP BY supplier_name
ORDER BY occurrences DESC;

-- 3. Category codes that don't match the 6 canonical categories -------------
SELECT category_code, COUNT(*) AS occurrences
FROM legacy_pos
WHERE category_code NOT IN
      ('Tops','Bottoms','Dresses','Outerwear','Footwear','Accessories')
GROUP BY category_code
ORDER BY occurrences DESC;

-- 4. Prices stored as formatted text instead of numeric values --------------
SELECT COUNT(*) AS pos_non_numeric_price
FROM legacy_pos
WHERE unit_price LIKE '$%' OR unit_price LIKE '%,%';

-- 5. Negative or otherwise invalid stock counts (POS glitches) --------------
SELECT COUNT(*) AS pos_negative_stock
FROM legacy_pos
WHERE CAST(qty_on_hand AS INTEGER) < 0;

-- 6. Exact duplicate rows re-keyed into the POS system -----------------------
SELECT item_name, category_code, COUNT(*) AS times_entered
FROM legacy_pos
GROUP BY item_name, category_code, supplier_name
HAVING COUNT(*) > 1
ORDER BY times_entered DESC
LIMIT 20;

-- 7. Supplier feed rows missing a supplier ------------------------------------
SELECT COUNT(*) AS supplier_feed_missing_supplier
FROM supplier_feed
WHERE supplier IS NULL OR TRIM(supplier) = '';

-- 8. Supplier feed rows quoted in a foreign currency (unmarked in downstream
--    systems that assume USD -- a silent price-integrity risk) -------------
SELECT currency, COUNT(*) AS occurrences
FROM supplier_feed
GROUP BY currency;

-- 9. E-commerce listings with zero inventory that still look "live"
--    (duplicate/orphaned listings from a past platform migration) ----------
SELECT COUNT(*) AS ecom_orphaned_zero_stock_listings
FROM ecom_export
WHERE inventory_count = 0 AND title LIKE '%(copy)%';

-- 10. Summary row counts per source (the raw, uncentralized picture) --------
SELECT 'legacy_pos'     AS source, COUNT(*) AS row_count FROM legacy_pos
UNION ALL
SELECT 'supplier_feed'  AS source, COUNT(*) AS row_count FROM supplier_feed
UNION ALL
SELECT 'ecom_export'    AS source, COUNT(*) AS row_count FROM ecom_export;
