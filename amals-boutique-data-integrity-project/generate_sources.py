"""
generate_sources.py
--------------------
Builds a "ground truth" boutique product catalog and then simulates how that
catalog would actually look after years of being tracked across THREE
disconnected systems that a growing multi-location boutique retailer
(Amal's Boutique) realistically accumulates:

  1. legacy_pos_export.csv      - exports from the in-store point-of-sale system
  2. supplier_catalog_feed.csv  - vendor-provided spreadsheets (4 suppliers)
  3. ecommerce_platform_export.json - the online storefront platform's product export

Each system independently drifts from the truth: stale prices, async stock
counts, inconsistent category labels, duplicate/garbled entries, missing or
orphaned supplier references, mixed currency, etc. That's the raw material
for the integrity audit + consolidation pipeline in the other two scripts.

Deterministic (seeded) so the whole project is reproducible.
"""
import csv
import json
import random
from datetime import datetime, timedelta

random.seed(42)

OUT_DIR = "raw_data"

CATEGORIES = ["Tops", "Bottoms", "Dresses", "Outerwear", "Footwear", "Accessories"]
# Realistic messy variants of the same 6 categories, as they'd actually be typed
# across three different systems over several years.
CATEGORY_VARIANTS = {
    "Tops": ["Tops", "TOPS", "top", "Tshirts/Tops", "TOP"],
    "Bottoms": ["Bottoms", "BOTTOM", "bottoms", "Pants/Bottoms", "Btms"],
    "Dresses": ["Dresses", "DRESS", "dress", "Dresses ", "Drss"],
    "Outerwear": ["Outerwear", "OUTER", "outerwear", "Jackets/Outerwear", "Outr"],
    "Footwear": ["Footwear", "SHOES", "footwear", "Shoes/Footwear", "Ftwr"],
    "Accessories": ["Accessories", "ACC", "accessories", "Accessory", "Accs"],
}
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]
COLORS = ["Black", "White", "Ivory", "Charcoal", "Camel", "Blush", "Indigo",
          "Emerald", "Cognac", "Beige", "Tan", "Burgundy"]
BRAND_BY_SUPPLIER = {
    "Fashion Hub Ltd": "Fashion Hub Ltd",
    "Textile World Co": "Textile World Co",
    "Apparel Solutions": "Apparel Solutions",
    "Atelier Nord": "Atelier Nord",
}
SUPPLIERS = list(BRAND_BY_SUPPLIER.keys())
# A supplier name that exists in the supplier feed but was later renamed/retired
# in the POS system without the change propagating -- a realistic orphaned
# reference source.
RETIRED_SUPPLIER_ALIASES = {
    "Fashion Hub Ltd": ["Fashion Hub", "FH Wholesale (old)"],
    "Textile World Co": ["Textile World", "TW Co."],
    "Apparel Solutions": ["Apparel Sol.", "ApparelSolns"],
    "Atelier Nord": ["Atelier Nord Studio", "A. Nord"],
}

PRODUCT_NOUNS = {
    "Tops": ["Crewneck Tee", "V-Neck Sweater", "Silk Blouse", "Turtleneck",
             "Button-Up Shirt", "Tank Top", "Cardigan", "Henley"],
    "Bottoms": ["Skinny Jean", "Wide-Leg Trouser", "Pleated Skirt", "Chino Pant",
                "Denim Short", "Linen Pant", "Midi Skirt"],
    "Dresses": ["Wrap Dress", "Midi Dress", "Shift Dress", "Maxi Dress",
                "Slip Dress", "Shirt Dress"],
    "Outerwear": ["Moto Jacket", "Trench Coat", "Wool Peacoat", "Denim Jacket",
                  "Puffer Vest", "Blazer"],
    "Footwear": ["Ankle Boot", "Low-Top Sneaker", "Ballet Flat", "Heeled Mule",
                 "Loafer", "Espadrille"],
    "Accessories": ["Twill Scarf", "Leather Tote", "Woven Belt", "Crossbody Bag",
                     "Wide-Brim Hat", "Statement Earrings"],
}


def make_true_catalog(n_true=7500):
    """The real, correct product catalog -- what a perfect single source of truth
    would contain. This never gets written out directly; it's the answer key
    used to score how well the consolidation pipeline reconstructs it."""
    catalog = []
    used_names = set()
    for i in range(n_true):
        category = random.choice(CATEGORIES)
        noun = random.choice(PRODUCT_NOUNS[category])
        color = random.choice(COLORS)
        size = random.choice(SIZES)
        supplier = random.choice(SUPPLIERS)
        name = f"{color} {noun}"
        sku = f"AB-{category[:3].upper()}-{i:05d}-{size}"
        base_price = round(random.uniform(18, 320), 2)
        base_stock = random.randint(0, 140)
        catalog.append({
            "true_sku": sku,
            "name": name,
            "category": category,
            "size": size,
            "color": color,
            "brand": supplier,
            "supplier": supplier,
            "price": base_price,
            "stock": base_stock,
            "last_true_update": datetime(2024, 1, 1) + timedelta(days=random.randint(0, 900)),
        })
    return catalog


def maybe_typo_category(category):
    return random.choice(CATEGORY_VARIANTS[category])


def drift_price(price, days_stale, currency_flip=False):
    """Simulate a stale/rounded/possibly-foreign-currency price."""
    drift = 1 + random.uniform(-0.02, 0.02) * (days_stale / 30.0)
    p = price * drift
    if currency_flip:
        # Vendor feed sometimes still in CAD, ~0.73 USD conversion, un-marked.
        p = p / 0.73
    return round(p, 2)


def drift_stock(stock, volatility=0.35):
    if random.random() < volatility:
        delta = random.randint(-15, 15)
        return max(-3, stock + delta)  # occasional POS glitch: negative stock
    return stock


def build_pos_rows(catalog):
    rows = []
    for rec in catalog:
        if random.random() > 0.94:
            continue  # ~6% of the true catalog was never entered in the old POS
        row = {
            "pos_sku": rec["true_sku"],
            "item_name": rec["name"] + (f" - {rec['size']}" if random.random() < 0.3 else ""),
            "unit_price": f"${drift_price(rec['price'], random.randint(0, 200)):,.2f}"
                          if random.random() < 0.4 else drift_price(rec["price"], random.randint(0, 200)),
            "qty_on_hand": drift_stock(rec["stock"]),
            "category_code": maybe_typo_category(rec["category"]) if random.random() > 0.05
                             else random.choice(["MISC", "N/A", "9", ""]),
            "supplier_name": random.choice(
                [rec["supplier"]] + RETIRED_SUPPLIER_ALIASES[rec["supplier"]]
            ) if random.random() > 0.06 else "",  # ~6% missing supplier
            "last_updated": (rec["last_true_update"] - timedelta(days=random.randint(0, 240))).strftime("%m/%d/%Y"),
        }
        rows.append(row)
        # Human re-entry duplicates: ~4% of rows get keyed in twice with a typo'd name.
        if random.random() < 0.04:
            dup = dict(row)
            dup["item_name"] = dup["item_name"].replace("e", "e ", 1) if "e" in dup["item_name"] else dup["item_name"] + " "
            rows.append(dup)
    return rows


def build_supplier_rows(catalog):
    rows = []
    for rec in catalog:
        supplier_stocks_it = random.random() < 0.84
        if not supplier_stocks_it:
            continue
        currency_flip = rec["supplier"] == "Atelier Nord" and random.random() < 0.5
        price = drift_price(rec["price"], random.randint(0, 120), currency_flip=currency_flip)
        rows.append({
            "vendor_sku": rec["true_sku"].replace("AB-", "V-").lower(),  # different SKU scheme entirely
            "product_title": f"{rec['name']} ({rec['size']})",
            "list_price": price,
            "currency": "CAD" if currency_flip else "USD",
            "pack_size": random.choice([1, 1, 1, 6, 12]),
            "supplier": rec["supplier"] if random.random() > 0.03 else "",
        })
        # Vendor occasionally lists the same SKU twice under two pack sizes.
        if random.random() < 0.05:
            rows.append({
                "vendor_sku": rec["true_sku"].replace("AB-", "V-").lower(),
                "product_title": f"{rec['name']} ({rec['size']}) - Case Pack",
                "list_price": round(price * 11.5, 2),
                "currency": "CAD" if currency_flip else "USD",
                "pack_size": 12,
                "supplier": rec["supplier"],
            })
    return rows


def build_ecommerce_rows(catalog):
    rows = []
    next_id = 100000
    for rec in catalog:
        listed = random.random() < 0.92
        if not listed:
            continue
        title = f"{rec['name']} - {rec['color']} - {rec['size']}"
        rows.append({
            "id": next_id,
            "title": title,
            "price": drift_price(rec["price"], random.randint(0, 60)),
            "inventory_count": drift_stock(rec["stock"], volatility=0.25),
            "tags": ([rec["category"].lower()] if random.random() > 0.06 else []) +
                    [rec["color"].lower(), "new" if random.random() < 0.1 else ""],
            "vendor": rec["supplier"],
        })
        next_id += 1
        # Storefront glitch: abandoned duplicate listing from a platform migration.
        if random.random() < 0.06:
            rows.append({
                "id": next_id,
                "title": title + " (copy)",
                "price": rows[-1]["price"],
                "inventory_count": 0,
                "tags": [rec["category"].lower()],
                "vendor": rec["supplier"],
            })
            next_id += 1
    return rows


def main():
    import os
    os.makedirs(OUT_DIR, exist_ok=True)

    catalog = make_true_catalog(n_true=7700)

    pos_rows = build_pos_rows(catalog)
    supplier_rows = build_supplier_rows(catalog)
    ecom_rows = build_ecommerce_rows(catalog)

    with open(f"{OUT_DIR}/legacy_pos_export.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["pos_sku", "item_name", "unit_price", "qty_on_hand",
                                           "category_code", "supplier_name", "last_updated"])
        w.writeheader()
        w.writerows(pos_rows)

    with open(f"{OUT_DIR}/supplier_catalog_feed.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["vendor_sku", "product_title", "list_price",
                                           "currency", "pack_size", "supplier"])
        w.writeheader()
        w.writerows(supplier_rows)

    with open(f"{OUT_DIR}/ecommerce_platform_export.json", "w", encoding="utf-8") as f:
        json.dump(ecom_rows, f, indent=2)

    # Also persist the ground-truth catalog privately (not shipped as a "source" --
    # used only by the validation script to measure how close the pipeline gets).
    with open(f"{OUT_DIR}/_ground_truth.json", "w", encoding="utf-8") as f:
        json.dump([{**r, "last_true_update": r["last_true_update"].isoformat()} for r in catalog], f, indent=2)

    total = len(pos_rows) + len(supplier_rows) + len(ecom_rows)
    print(f"True catalog size:        {len(catalog):,}")
    print(f"legacy_pos_export.csv:    {len(pos_rows):,} rows")
    print(f"supplier_catalog_feed.csv:{len(supplier_rows):,} rows")
    print(f"ecommerce_platform_export.json: {len(ecom_rows):,} rows")
    print(f"TOTAL RAW RECORDS:        {total:,}")


if __name__ == "__main__":
    main()
