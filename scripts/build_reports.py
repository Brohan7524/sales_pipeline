"""
REPORTS LAYER — Creates report_customers and report_products in MySQL gold.
Run with: python build_reports.py
"""

import pandas as pd
from sqlalchemy import create_engine, text
import sys
from datetime import date

DB_USER     = "root"
DB_PASSWORD = "admin"
DB_HOST     = "localhost"
DB_PORT     = "3306"
GOLD_DB     = "gold"

def make_engine():
    try:
        engine = create_engine(
            f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{GOLD_DB}"
        )
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print(f"    ✅ Connected to '{GOLD_DB}'.")
        return engine
    except Exception as e:
        print(f"    ❌ Cannot connect: {e}")
        sys.exit(1)

def write_table(df, engine, table_name):
    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"    ✅ Written '{table_name}': {len(df):,} rows.")
        return True
    except Exception as e:
        print(f"    ❌ Failed to write '{table_name}': {e}")
        return False

def clean_int_key(series):
    """Convert keys like '29483.0', 29483.0, nan → '29483'. Drops nulls."""
    return (
        pd.to_numeric(series, errors="coerce")
        .dropna()
        .astype(int)
        .astype(str)
        .str.strip()
    )

def months_between(d1, d2):
    d1 = pd.to_datetime(d1)
    d2 = pd.to_datetime(d2)
    return ((d1.dt.year - d2.dt.year) * 12 + (d1.dt.month - d2.dt.month)).clip(lower=0)

# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  REPORTS LAYER — Building report tables...")
print("="*60)

engine     = make_engine()
today      = date.today()
all_success = True

# ═══════════════════════════════════════════════════════════
# 10 — report_customers
# ═══════════════════════════════════════════════════════════
print(f"\n[1/2] Building report_customers...")
try:
    fact      = pd.read_sql("SELECT * FROM fact_sales",    engine)
    customers = pd.read_sql("SELECT * FROM dim_customers", engine)
    print(f"      → fact_sales: {len(fact):,} | dim_customers: {len(customers):,}")

    # ── Fix customer ID keys ───────────────────────────────
    # fact: int64 → str  e.g. 21768 → '21768'
    fact["_cust_key"] = fact["sls_cust_id"].astype(str).str.strip()

    # dim_customers: '29483.0' / nan → '29483'
    customers["_cust_key"] = clean_int_key(customers["cst_id"])
    customers = customers.dropna(subset=["_cust_key"])

    print(f"      → Sample fact keys:     {fact['_cust_key'].head(3).tolist()}")
    print(f"      → Sample customer keys: {customers['_cust_key'].head(3).tolist()}")
    matched = len(set(fact["_cust_key"]) & set(customers["_cust_key"]))
    print(f"      → Matching IDs: {matched}")

    # Parse dates
    fact["sls_order_dt"] = pd.to_datetime(fact["sls_order_dt"], errors="coerce")
    customers["bdate"]   = pd.to_datetime(customers["bdate"],   errors="coerce")

    # Merge on cleaned keys
    base = fact.merge(customers, on="_cust_key", how="inner")
    base = base[base["sls_order_dt"].notna()].copy()
    print(f"      → Rows after join: {len(base):,}")

    # Age
    base["age"] = (
        (pd.Timestamp(today) - base["bdate"]).dt.days / 365.25
    ).where(base["bdate"].notna()).round(0).astype("Int64")

    # Aggregate
    agg = base.groupby(["_cust_key", "cst_firstname", "cst_lastname"]).agg(
        total_orders    =("sls_ord_num",  "nunique"),
        total_sales     =("sales_amount", "sum"),
        total_quantity  =("sls_quantity", "sum"),
        total_products  =("sls_prd_key",  "nunique"),
        last_order_date =("sls_order_dt", "max"),
        first_order_date=("sls_order_dt", "min"),
        age             =("age",          "first"),
        cst_gndr        =("cst_gndr",     "first"),
        cntry           =("cntry",        "first"),
    ).reset_index().rename(columns={"_cust_key": "cst_id"})

    # Lifespan & recency
    agg["last_order_date"]  = pd.to_datetime(agg["last_order_date"])
    agg["first_order_date"] = pd.to_datetime(agg["first_order_date"])
    agg["lifespan"]         = months_between(agg["last_order_date"], agg["first_order_date"])
    agg["recency_months"]   = (
        (today.year  - agg["last_order_date"].dt.year) * 12
      + (today.month - agg["last_order_date"].dt.month)
    )

    # Age group
    agg["age"] = agg["age"].astype(float)
    agg["age_group"] = pd.cut(
        agg["age"],
        bins=[0, 19, 29, 39, 49, 999],
        labels=["Under 20", "20-29", "30-39", "40-49", "50 and above"]
    ).astype(str)

    # Segment
    agg["customer_segment"] = "New"
    agg.loc[(agg["lifespan"] >= 12) & (agg["total_sales"] <= 5000), "customer_segment"] = "Regular"
    agg.loc[(agg["lifespan"] >= 12) & (agg["total_sales"] >  5000), "customer_segment"] = "VIP"

    # KPIs — cast to float to avoid pd.NA round() error
    agg["lifespan"]          = agg["lifespan"].astype(float)
    agg["avg_order_value"]   = (agg["total_sales"].astype(float) / agg["total_orders"].astype(float).replace(0, float("nan"))).round(2).fillna(0)
    agg["avg_monthly_spend"] = (agg["total_sales"].astype(float) / agg["lifespan"].replace(0, float("nan"))).round(2).fillna(agg["total_sales"].astype(float))

    report_customers = agg.drop(columns=["first_order_date"])
    print(f"      → Segments: {report_customers['customer_segment'].value_counts().to_dict()}")
    ok = write_table(report_customers, engine, "report_customers")
    if not ok: all_success = False

except Exception as e:
    print(f"    ❌ Error building report_customers: {e}")
    import traceback; traceback.print_exc()
    all_success = False

# ═══════════════════════════════════════════════════════════
# 11 — report_products
# ═══════════════════════════════════════════════════════════
print(f"\n[2/2] Building report_products...")
try:
    fact     = pd.read_sql("SELECT * FROM fact_sales",   engine)
    products = pd.read_sql("SELECT * FROM dim_products", engine)
    print(f"      → fact_sales: {len(fact):,} | dim_products: {len(products):,}")

    # ── Fix product keys ───────────────────────────────────
    # fact has short keys: 'BK-R93R-62'
    # dim_products has long keys: 'CO-RF-FR-R92B-58'
    # The prd_key in dim_products was built from prd_key in silver (full key)
    # but fact uses sls_prd_key which is the short version
    # We need to match on the SHORT key portion of dim_products.prd_key
    # Short key = last 3 segments e.g. 'CO-RF-FR-R92B-58' → 'FR-R92B-58'? No.
    # Actually prd_key format: CO-RF-FR-R92B-58 → the sls_prd_key is BK-R93R-62
    # These are DIFFERENT products — we need to read from silver prd_info directly
    # to find the correct key that matches sls_prd_key

    # Read silver prd_info which has the original prd_key matching sls_prd_key
    silver_engine = create_engine(
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/silver"
    )
    prd_silver = pd.read_sql("SELECT * FROM clean_prd_info", silver_engine)
    print(f"      → silver clean_prd_info columns: {list(prd_silver.columns)}")
    print(f"      → silver prd_key sample: {prd_silver['prd_key'].head(5).tolist()}")

    # Find which column in silver matches fact's sls_prd_key
    fact_keys = set(fact["sls_prd_key"].astype(str).str.strip())
    for col in prd_silver.columns:
        sample_vals = set(prd_silver[col].astype(str).str.strip())
        overlap = len(fact_keys & sample_vals)
        if overlap > 0:
            print(f"      → Column '{col}' matches {overlap} fact product keys ✅")

    # The silver prd_key contains the long key — extract short key from it
    # Format: 'CO-RF-FR-R92B-58' — the fact key 'BK-R93R-62' matches last parts
    # Try extracting last 2 segments as short key
    prd_silver["short_key"] = prd_silver["prd_key"].astype(str).apply(
        lambda k: "-".join(k.split("-")[-2:]) if "-" in str(k) else k
    )
    overlap_short = len(fact_keys & set(prd_silver["short_key"]))
    print(f"      → short_key (last 2 segments) matches: {overlap_short}")

    # Try last 3 segments
    prd_silver["short_key3"] = prd_silver["prd_key"].astype(str).apply(
        lambda k: "-".join(k.split("-")[-3:]) if "-" in str(k) else k
    )
    overlap_short3 = len(fact_keys & set(prd_silver["short_key3"]))
    print(f"      → short_key (last 3 segments) matches: {overlap_short3}")

    # Pick whichever matches more
    if overlap_short3 >= overlap_short and overlap_short3 > 0:
        join_col = "short_key3"
    elif overlap_short > 0:
        join_col = "short_key"
    else:
        join_col = None

    if join_col:
        print(f"      → Using '{join_col}' to join with fact sls_prd_key")
        prd_silver["_prd_join_key"] = prd_silver[join_col]
    else:
        # Fallback: use prd_key as-is from silver (already active/deduped)
        print(f"      ⚠️  No key match found — using prd_key as-is")
        prd_silver["_prd_join_key"] = prd_silver["prd_key"]

    # Keep only active products (prd_end_dt null)
    if "prd_end_dt" in prd_silver.columns:
        prd_silver["prd_end_dt"] = pd.to_datetime(prd_silver["prd_end_dt"], errors="coerce")
        prd_silver = prd_silver[prd_silver["prd_end_dt"].isna()].copy()

    prd_silver["_prd_join_key"] = prd_silver["_prd_join_key"].astype(str).str.strip()
    prd_silver = prd_silver.drop_duplicates(subset="_prd_join_key", keep="first")

    # Parse dates
    fact["sls_order_dt"]  = pd.to_datetime(fact["sls_order_dt"], errors="coerce")
    fact["_prd_join_key"] = fact["sls_prd_key"].astype(str).str.strip()

    # Merge
    base = fact.merge(prd_silver, on="_prd_join_key", how="inner")
    base = base[base["sls_order_dt"].notna()].copy()
    print(f"      → Rows after join: {len(base):,}")

    if len(base) == 0:
        print("      ❌ Still no matches — check column printout above and report it")
        all_success = False
    else:
        # Determine correct column names from silver
        name_col = next((c for c in prd_silver.columns if c in ["prd_nm","prd_name","product_name"]), None)
        cat_col  = next((c for c in prd_silver.columns if c in ["cat","category"]), None)
        sub_col  = next((c for c in prd_silver.columns if c in ["subcat","subcategory"]), None)
        cost_col = next((c for c in prd_silver.columns if c in ["prd_cost","cost"]), None)

        group_cols = ["_prd_join_key"]
        if name_col: group_cols.append(name_col)
        if cat_col:  group_cols.append(cat_col)
        if sub_col:  group_cols.append(sub_col)
        if cost_col: group_cols.append(cost_col)

        agg_dict = {
            "total_orders":    ("sls_ord_num",  "nunique"),
            "total_customers": ("sls_cust_id",  "nunique"),
            "total_sales":     ("sales_amount", "sum"),
            "total_quantity":  ("sls_quantity", "sum"),
            "last_sale_date":  ("sls_order_dt", "max"),
            "first_sale_date": ("sls_order_dt", "min"),
        }

        agg = base.groupby(group_cols).agg(**agg_dict).reset_index()
        agg = agg.rename(columns={"_prd_join_key": "prd_key"})

        agg["last_sale_date"]  = pd.to_datetime(agg["last_sale_date"])
        agg["first_sale_date"] = pd.to_datetime(agg["first_sale_date"])
        agg["lifespan"]        = months_between(agg["last_sale_date"], agg["first_sale_date"])
        agg["recency_months"]  = (
            (today.year  - agg["last_sale_date"].dt.year) * 12
          + (today.month - agg["last_sale_date"].dt.month)
        )

        agg["product_segment"] = "Low-Performer"
        agg.loc[agg["total_sales"] >= 10000, "product_segment"] = "Mid-Range"
        agg.loc[agg["total_sales"] >  50000, "product_segment"] = "High-Performer"

        agg["avg_selling_price"]  = (agg["total_sales"] / agg["total_quantity"].replace(0, pd.NA)).round(1).fillna(0)
        agg["avg_order_revenue"]  = (agg["total_sales"] / agg["total_orders"].replace(0, pd.NA)).round(2).fillna(0)
        agg["avg_monthly_revenue"] = (agg["total_sales"] / agg["lifespan"].replace(0, pd.NA)).round(2).fillna(agg["total_sales"])

        report_products = agg.drop(columns=["first_sale_date"])
        print(f"      → Segments: {report_products['product_segment'].value_counts().to_dict()}")
        ok = write_table(report_products, engine, "report_products")
        if not ok: all_success = False

except Exception as e:
    print(f"    ❌ Error building report_products: {e}")
    import traceback; traceback.print_exc()
    all_success = False

# ─────────────────────────────────────────────
print("\n" + "="*60)
if all_success:
    print("  ✅ REPORTS COMPLETE — Two report tables ready in 'gold'.")
    print("\n  In Power BI → load from gold:")
    print("    fact_sales, report_customers, report_products, dim_date")
    print("    Connect: report_customers.cst_id → fact_sales.sls_cust_id")
    print("    Connect: report_products.prd_key  → fact_sales.sls_prd_key")
else:
    print("  ❌ REPORTS FAILED — Check errors above.")
    sys.exit(1)
print("="*60 + "\n")
