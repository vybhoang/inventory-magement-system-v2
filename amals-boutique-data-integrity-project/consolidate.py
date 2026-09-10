"""
consolidate.py
---------------
The core of the case study: loads the three raw, disconnected product sources
into SQLite, runs SQL profiling queries against them to *quantify* integrity
gaps (this is the "queried ... in SQL" half of the work), then uses Python
(pandas + rule-based fuzzy matching) to reconcile, standardize and merge them
into ONE centralized master catalog (the "analyzed ... in Python, centralizing
sources into a single dataset" half) -- and finally re-measures the same
integrity checks against that master catalog to quantify the improvement.

Run with:  python3 consolidate.py
Requires:  raw_data/ populated by generate_sources.py
"""
import json
import re
import sqlite3
import unicodedata
from collections import defaultdict

import pandas as pd

RAW_DIR = "raw_data"
DB_PATH = "raw_sources.db"

CANONICAL_CATEGORIES = ["Tops", "Bottoms", "Dresses", "Outerwear", "Footwear", "Accessories"]
CANONICAL_SUPPLIERS = ["Fashion Hub Ltd", "Textile World Co", "Apparel Solutions", "Atelier Nord"]

CATEGORY_LOOKUP = {
    "tops": "Tops", "top": "Tops", "tshirts/tops": "Tops",
    "bottoms": "Bottoms", "bottom": "Bottoms", "pants/bottoms": "Bottoms", "btms": "Bottoms",
    "dresses": "Dresses", "dress": "Dresses", "drss": "Dresses",
    "outerwear": "Outerwear", "outer": "Outerwear", "jackets/outerwear": "Outerwear", "outr": "Outerwear",
    "footwear": "Footwear", "shoes": "Footwear", "shoes/footwear": "Footwear", "ftwr": "Footwear",
    "accessories": "Accessories", "acc": "Accessories", "accessory": "Accessories", "accs": "Accessories",
}
SUPPLIER_ALIAS_LOOKUP = {
    "fashion hub ltd": "Fashion Hub Ltd", "fashion hub": "Fashion Hub Ltd", "fh wholesale (old)": "Fashion Hub Ltd",
    "textile world co": "Textile World Co", "textile world": "Textile World Co", "tw co.": "Textile World Co",
    "apparel solutions": "Apparel Solutions", "apparel sol.": "Apparel Solutions", "apparelsolns": "Apparel Solutions",
    "atelier nord": "Atelier Nord", "atelier nord studio": "Atelier Nord", "a. nord": "Atelier Nord",
}
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]


# ---------------------------------------------------------------------------
# 1. LOAD raw sources exactly as received, into SQLite (no cleaning yet)
# ---------------------------------------------------------------------------
def load_raw_sources_to_sqlite():
    pos = pd.read_csv(f"{RAW_DIR}/legacy_pos_export.csv", dtype=str)
    sup = pd.read_csv(f"{RAW_DIR}/supplier_catalog_feed.csv", dtype=str)
    with open(f"{RAW_DIR}/ecommerce_platform_export.json") as f:
        ecom = pd.json_normalize(json.load(f))

    conn = sqlite3.connect(DB_PATH)
    pos.to_sql("legacy_pos", conn, if_exists="replace", index=False)
    sup.to_sql("supplier_feed", conn, if_exists="replace", index=False)
    ecom_sql = ecom.copy()
    ecom_sql["tags"] = ecom_sql["tags"].apply(lambda t: ",".join(t) if isinstance(t, list) else t)
    ecom_sql.to_sql("ecom_export", conn, if_exists="replace", index=False)
    conn.commit()
    return conn, pos, sup, ecom


# ---------------------------------------------------------------------------
# 2. SQL-based integrity audit on the RAW sources (the "before" picture)
# ---------------------------------------------------------------------------
def run_sql_audit(conn):
    q = {}
    q["pos_missing_supplier"] = conn.execute(
        "SELECT COUNT(*) FROM legacy_pos WHERE supplier_name IS NULL OR TRIM(supplier_name)=''"
    ).fetchone()[0]
    q["pos_unrecognized_supplier"] = conn.execute(f"""
        SELECT COUNT(*) FROM legacy_pos
        WHERE TRIM(supplier_name) != ''
          AND supplier_name NOT IN ({','.join('?'*len(CANONICAL_SUPPLIERS))})
    """, CANONICAL_SUPPLIERS).fetchone()[0]
    q["pos_invalid_category"] = conn.execute(f"""
        SELECT COUNT(*) FROM legacy_pos
        WHERE category_code NOT IN ({','.join('?'*len(CANONICAL_CATEGORIES))})
    """, CANONICAL_CATEGORIES).fetchone()[0]
    q["pos_nonnumeric_price"] = conn.execute(
        "SELECT COUNT(*) FROM legacy_pos WHERE unit_price LIKE '$%' OR unit_price LIKE '%,%'"
    ).fetchone()[0]
    q["pos_negative_stock"] = conn.execute(
        "SELECT COUNT(*) FROM legacy_pos WHERE CAST(qty_on_hand AS INTEGER) < 0"
    ).fetchone()[0]
    q["pos_exact_duplicates"] = conn.execute("""
        SELECT COALESCE(SUM(c-1),0) FROM (
            SELECT COUNT(*) c FROM legacy_pos
            GROUP BY item_name, category_code, supplier_name HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    q["supplier_feed_missing_supplier"] = conn.execute(
        "SELECT COUNT(*) FROM supplier_feed WHERE supplier IS NULL OR TRIM(supplier)=''"
    ).fetchone()[0]
    q["supplier_feed_foreign_currency"] = conn.execute(
        "SELECT COUNT(*) FROM supplier_feed WHERE currency != 'USD'"
    ).fetchone()[0]
    q["ecom_orphaned_copies"] = conn.execute(
        "SELECT COUNT(*) FROM ecom_export WHERE title LIKE '%(copy)%'"
    ).fetchone()[0]
    return q


# ---------------------------------------------------------------------------
# 3. Normalization helpers used to fuzzy-match the SAME product across
#    three sources that each format it differently and use unrelated SKUs.
# ---------------------------------------------------------------------------
def norm_text(s):
    if not isinstance(s, str):
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = s.lower().strip()
    s = re.sub(r"\(copy\)", "", s)
    s = re.sub(r"\(case pack\)|- case pack", "", s)
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_size(text):
    for size in sorted(SIZES, key=len, reverse=True):
        if re.search(rf"\b{size.lower()}\b", norm_text(text)):
            return size
    return None


def base_name_from_pos(item_name):
    t = item_name
    for size in SIZES:
        t = re.sub(rf"\s*-\s*{size}\s*$", "", t, flags=re.IGNORECASE)
    return norm_text(t)


def base_name_from_supplier(product_title):
    t = re.sub(r"\s*\([^)]*\)\s*$", "", product_title)  # strip trailing "(M)" or "(M) - Case Pack" handled below
    t = re.sub(r"\s*-\s*case pack\s*$", "", t, flags=re.IGNORECASE)
    return norm_text(t)


def base_name_from_ecom(title):
    t = re.sub(r"\s*\(copy\)\s*$", "", title, flags=re.IGNORECASE)
    parts = t.split(" - ")
    if len(parts) >= 3:
        # "<Color Noun> - <Color> - <Size>" -> keep just "<Color Noun>"
        return norm_text(parts[0])
    return norm_text(t)


def resolve_category(raw):
    return CATEGORY_LOOKUP.get(str(raw).strip().lower())


def resolve_supplier(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    return SUPPLIER_ALIAS_LOOKUP.get(raw.strip().lower())


def clean_price(raw, currency="USD"):
    if raw is None:
        return None
    s = str(raw).replace("$", "").replace(",", "").strip()
    try:
        val = float(s)
    except ValueError:
        return None
    if currency == "CAD":
        val = round(val * 0.73, 2)  # convert to USD
    return round(val, 2)


# ---------------------------------------------------------------------------
# 4. Build a normalized record set per source, then merge on
#    (base_name, size, supplier) -- the best available match key once
#    formatting noise is stripped out.
# ---------------------------------------------------------------------------
def normalize_pos(pos):
    recs = []
    for _, r in pos.iterrows():
        recs.append({
            "source": "pos",
            "base_name": base_name_from_pos(r["item_name"]),
            "size": extract_size(r["item_name"]) or "",
            "category": resolve_category(r["category_code"]),
            "supplier": resolve_supplier(r["supplier_name"]),
            "price": clean_price(r["unit_price"]),
            "stock": int(r["qty_on_hand"]) if pd.notna(r["qty_on_hand"]) else None,
        })
    return recs


def normalize_supplier(sup):
    recs = []
    for _, r in sup.iterrows():
        if "case pack" in str(r["product_title"]).lower():
            continue  # bulk-pack duplicate listing, not a distinct product
        recs.append({
            "source": "supplier",
            "base_name": base_name_from_supplier(r["product_title"]),
            "size": extract_size(r["product_title"]) or "",
            "category": None,
            "supplier": resolve_supplier(r["supplier"]),
            "price": clean_price(r["list_price"], currency=r["currency"]),
            "stock": None,
        })
    return recs


def normalize_ecom(ecom):
    recs = []
    for _, r in ecom.iterrows():
        if "(copy)" in str(r["title"]).lower():
            continue  # orphaned duplicate listing
        tags = r["tags"] if isinstance(r["tags"], list) else []
        cat = None
        for tag in tags:
            cat = resolve_category(tag)
            if cat:
                break
        recs.append({
            "source": "ecom",
            "base_name": base_name_from_ecom(r["title"]),
            "size": extract_size(r["title"]) or "",
            "category": cat,
            "supplier": resolve_supplier(r["vendor"]) if isinstance(r.get("vendor"), str) else None,
            "price": clean_price(r["price"]),
            "stock": int(r["inventory_count"]) if pd.notna(r["inventory_count"]) else None,
        })
    return recs


def merge_records(all_records):
    """Group by (base_name, size) -- the one match key every source can
    reliably produce -- then reconcile conflicting fields per group."""
    # Match key = normalized name + size + supplier. Supplier is included
    # because "Ivory Ankle Boot, size M" legitimately exists as distinct
    # products from different suppliers -- name+size alone collapses those.
    # Records with an unresolved supplier fall into their own per-name bucket
    # instead of silently merging into a resolved one.
    groups = defaultdict(list)
    for rec in all_records:
        key = (rec["base_name"], rec["size"], rec["supplier"] or "__UNRESOLVED__")
        groups[key].append(rec)

    master_rows = []
    price_conflicts = 0
    stock_conflicts = 0
    category_conflicts = 0
    supplier_conflicts = 0
    unresolved = 0

    for (base_name, size, _supplier_key), recs in groups.items():
        if not base_name:
            continue

        # Category: prefer a value found in >=1 record; flag if sources disagree.
        cats = {r["category"] for r in recs if r["category"]}
        category = sorted(cats)[0] if cats else None
        if len(cats) > 1:
            category_conflicts += 1

        suppliers = {r["supplier"] for r in recs if r["supplier"]}
        supplier = sorted(suppliers)[0] if suppliers else None
        if len(suppliers) > 1:
            supplier_conflicts += 1

        prices = [r["price"] for r in recs if r["price"] is not None]
        price = None
        if prices:
            price = round(sum(prices) / len(prices), 2)  # reconcile via mean of cleaned prices
            if max(prices) - min(prices) > 0.05 * price:
                price_conflicts += 1

        # Stock: prefer POS (most operationally current), else ecom, floor at 0.
        stock = None
        for pref in ("pos", "ecom"):
            for r in recs:
                if r["source"] == pref and r["stock"] is not None:
                    stock = max(0, r["stock"])
                    break
            if stock is not None:
                break
        stocks = [max(0, r["stock"]) for r in recs if r["stock"] is not None]
        if len(set(stocks)) > 1:
            stock_conflicts += 1

        if category is None or supplier is None or price is None or stock is None:
            unresolved += 1

        master_rows.append({
            "product_name": base_name.title(),
            "size": size,
            "category": category,
            "supplier": supplier,
            "price": price,
            "stock": stock,
            "source_count": len(set(r["source"] for r in recs)),
        })

    master = pd.DataFrame(master_rows)
    conflict_stats = {
        "groups_total": len(master_rows),
        "price_conflicts_resolved": price_conflicts,
        "stock_conflicts_resolved": stock_conflicts,
        "category_conflicts_resolved": category_conflicts,
        "supplier_conflicts_resolved": supplier_conflicts,
        "still_unresolved_after_merge": unresolved,
    }
    return master, conflict_stats


# ---------------------------------------------------------------------------
# 5. Re-run the SAME class of integrity checks against the MASTER catalog
#    (the "after" picture).
# ---------------------------------------------------------------------------
def audit_master(master):
    issues = pd.Series(False, index=master.index)
    issues |= master["category"].isna()
    issues |= master["supplier"].isna()
    issues |= master["price"].isna()
    issues |= master["stock"].isna()
    issues |= master["stock"].fillna(0) < 0
    dup_mask = master.duplicated(subset=["product_name", "size", "supplier"], keep=False) & master["supplier"].notna()
    issues |= dup_mask
    return {
        "master_rows": len(master),
        "master_missing_category": int(master["category"].isna().sum()),
        "master_missing_supplier": int(master["supplier"].isna().sum()),
        "master_missing_price": int(master["price"].isna().sum()),
        "master_missing_stock": int(master["stock"].isna().sum()),
        "master_duplicate_keys": int(dup_mask.sum()),
        "master_records_with_any_issue": int(issues.sum()),
    }


def main():
    conn, pos, sup, ecom = load_raw_sources_to_sqlite()

    print("=" * 70)
    print("STEP 1 -- SQL integrity audit on raw sources (BEFORE)")
    print("=" * 70)
    before = run_sql_audit(conn)
    for k, v in before.items():
        print(f"  {k:35s} {v:>8,}")
    total_raw_records = len(pos) + len(sup) + len(ecom)
    before_flagged_total = (
        before["pos_missing_supplier"] + before["pos_unrecognized_supplier"] +
        before["pos_invalid_category"] + before["pos_nonnumeric_price"] +
        before["pos_negative_stock"] + before["pos_exact_duplicates"] +
        before["supplier_feed_missing_supplier"] + before["supplier_feed_foreign_currency"] +
        before["ecom_orphaned_copies"]
    )
    print(f"\n  TOTAL RAW RECORDS ACROSS 3 SOURCES: {total_raw_records:,}")
    print(f"  TOTAL FLAGGED DATA-INTEGRITY ISSUES (before): {before_flagged_total:,}")

    print("\n" + "=" * 70)
    print("STEP 2 -- Python: normalize, fuzzy-match & centralize into one dataset")
    print("=" * 70)
    all_records = normalize_pos(pos) + normalize_supplier(sup) + normalize_ecom(ecom)
    master, conflict_stats = merge_records(all_records)
    for k, v in conflict_stats.items():
        print(f"  {k:35s} {v:>8,}")
    master.to_csv("master_catalog.csv", index=False)
    print(f"\n  Centralized master catalog written: master_catalog.csv ({len(master):,} rows)")

    print("\n" + "=" * 70)
    print("STEP 3 -- Re-audit the centralized master catalog (AFTER)")
    print("=" * 70)
    after = audit_master(master)
    for k, v in after.items():
        print(f"  {k:35s} {v:>8,}")

    reduction = 100 * (1 - after["master_records_with_any_issue"] / before_flagged_total)
    print("\n" + "=" * 70)
    print("RESULT")
    print("=" * 70)
    print(f"  Records queried & analyzed (Python + SQL):  {total_raw_records:,}")
    print(f"  Data-integrity issues found before cleanup: {before_flagged_total:,}")
    print(f"  Data-integrity issues remaining after merge: {after['master_records_with_any_issue']:,}")
    print(f"  Discrepancy reduction:                       {reduction:.1f}%")

    summary = {
        "total_raw_records": total_raw_records,
        "records_per_source": {"legacy_pos": len(pos), "supplier_feed": len(sup), "ecom_export": len(ecom)},
        "before_audit": before,
        "before_flagged_total": before_flagged_total,
        "merge_conflict_stats": conflict_stats,
        "after_audit": after,
        "discrepancy_reduction_pct": round(reduction, 1),
        "master_catalog_rows": len(master),
    }
    with open("metrics_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print("\n  Full metrics written to metrics_summary.json")


if __name__ == "__main__":
    main()
