"""
REPORTS LAYER - Creates report_customers and report_products in MySQL gold.
Run with: python build_reports.py
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import sys
from datetime import date

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "3306")
GOLD_DB     = "gold"

def make_engine():
    try:
        engine = create_engine(
            f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{GOLD_DB}"
        )
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print(f"    Connected to '{GOLD_DB}'.")
        return engine
    except Exception as e:
        print(f"    Cannot connect: {e}")
        sys.exit(1)

def write_table(df, engine, table_name):
    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"    Written '{table_name}': {len(df):,} rows.")
        return True
    except Exception as e:
        print(f"    Failed to write '{table_name}': {e}")
        return False

def months_between(d1, d2):
    d1 = pd.to_datetime(d1)
    d2 = pd.to_datetime(d2)
    return ((d1.dt.year - d2.dt.year) * 12 + (d1.dt.month - d2.dt.month)).clip(lower=0)

print("\n" + "="*60)
print("  REPORTS LAYER - Building report tables...")
print("="*60)

engine     = make_engine()
today      = date.today()
all_success = True

# 1 - report_customers
print(f"\n[1/2] Building report_customers...")
try:
    fact      = pd.read_sql("SELECT * FROM fact_sales",    engine)
    customers = pd.read_sql("SELECT * FROM dim_customers", engine)
    print(f"      fact_sales: {len(fact):,} | dim_customers: {len(customers):,}")

    # dim_customers.cst_id and fact_sales.sls_cust_id are both clean ints
    # (fixed at ingestion in silver_transform.py) - join directly, no key cleanup needed.
    fact["sls_order_dt"] = pd.to_datetime(fact["sls_order_dt"], errors="coerce")
    customers["bdate"]   = pd.to_datetime(customers["bdate"],   errors="coerce")

    base = fact.merge(customers, left_on="sls_cust_id", right_on="cst_id", how="inner")
    base = base[base["sls_order_dt"].notna()].copy()
    print(f"      Rows after join: {len(base):,}")

    # Age
    base["age"] = (
        (pd.Timestamp(today) - base["bdate"]).dt.days / 365.25
    ).where(base["bdate"].notna()).round(0).astype("Int64")

    # Aggregate
    agg = base.groupby(["cst_id", "cst_firstname", "cst_lastname"]).agg(
        total_orders    =("sls_ord_num",  "nunique"),
        total_sales     =("sales_amount", "sum"),
        total_quantity  =("sls_quantity", "sum"),
        total_products  =("sls_prd_key",  "nunique"),
        last_order_date =("sls_order_dt", "max"),
        first_order_date=("sls_order_dt", "min"),
        age             =("age",          "first"),
        cst_gndr        =("cst_gndr",     "first"),
        cntry           =("cntry",        "first"),
    ).reset_index()

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

    # Segment - this is the single definition of customer segmentation.
    # analytics.py reads the result back from gold.report_customers instead of
    # recomputing this logic in SQL.
    agg["customer_segment"] = "New"
    agg.loc[(agg["lifespan"] >= 12) & (agg["total_sales"] <= 5000), "customer_segment"] = "Regular"
    agg.loc[(agg["lifespan"] >= 12) & (agg["total_sales"] >  5000), "customer_segment"] = "VIP"

    # KPIs - cast to float to avoid pd.NA round() error
    agg["lifespan"]          = agg["lifespan"].astype(float)
    agg["avg_order_value"]   = (agg["total_sales"].astype(float) / agg["total_orders"].astype(float).replace(0, float("nan"))).round(2).fillna(0)
    agg["avg_monthly_spend"] = (agg["total_sales"].astype(float) / agg["lifespan"].replace(0, float("nan"))).round(2).fillna(agg["total_sales"].astype(float))

    report_customers = agg.drop(columns=["first_order_date"])
    print(f"      Segments: {report_customers['customer_segment'].value_counts().to_dict()}")
    ok = write_table(report_customers, engine, "report_customers")
    if not ok: all_success = False

except Exception as e:
    print(f"    Error building report_customers: {e}")
    import traceback; traceback.print_exc()
    all_success = False

# 2 - report_products
print(f"\n[2/2] Building report_products...")
try:
    fact     = pd.read_sql("SELECT * FROM fact_sales",   engine)
    products = pd.read_sql("SELECT * FROM dim_products", engine)
    print(f"      fact_sales: {len(fact):,} | dim_products: {len(products):,}")

    # dim_products.prd_key is now the short form (fixed at ingestion in
    # silver_transform.py) so it joins directly against fact_sales.sls_prd_key.
    fact["sls_order_dt"] = pd.to_datetime(fact["sls_order_dt"], errors="coerce")

    base = fact.merge(products, left_on="sls_prd_key", right_on="prd_key", how="inner")
    base = base[base["sls_order_dt"].notna()].copy()
    print(f"      Rows after join: {len(base):,}")

    if len(base) == 0:
        print("      No matches after join - check dim_products.prd_key vs fact_sales.sls_prd_key")
        all_success = False
    else:
        group_cols = [c for c in ["prd_key", "prd_nm", "cat", "subcat", "prd_cost"] if c in base.columns]

        agg = base.groupby(group_cols).agg(
            total_orders    =("sls_ord_num",  "nunique"),
            total_customers =("sls_cust_id",  "nunique"),
            total_sales     =("sales_amount", "sum"),
            total_quantity  =("sls_quantity", "sum"),
            last_sale_date  =("sls_order_dt", "max"),
            first_sale_date =("sls_order_dt", "min"),
        ).reset_index()

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

        agg["avg_selling_price"]   = (agg["total_sales"] / agg["total_quantity"].replace(0, pd.NA)).round(1).fillna(0)
        agg["avg_order_revenue"]   = (agg["total_sales"] / agg["total_orders"].replace(0, pd.NA)).round(2).fillna(0)
        agg["avg_monthly_revenue"] = (agg["total_sales"] / agg["lifespan"].replace(0, pd.NA)).round(2).fillna(agg["total_sales"])

        report_products = agg.drop(columns=["first_sale_date"])
        print(f"      Segments: {report_products['product_segment'].value_counts().to_dict()}")
        ok = write_table(report_products, engine, "report_products")
        if not ok: all_success = False

except Exception as e:
    print(f"    Error building report_products: {e}")
    import traceback; traceback.print_exc()
    all_success = False

print("\n" + "="*60)
if all_success:
    print("  REPORTS COMPLETE - Two report tables ready in 'gold'.")
    print("\n  In Power BI, load from gold:")
    print("    fact_sales, report_customers, report_products, dim_date")
    print("    Connect: report_customers.cst_id -> fact_sales.sls_cust_id")
    print("    Connect: report_products.prd_key  -> fact_sales.sls_prd_key")
else:
    print("  REPORTS FAILED - Check errors above.")
    sys.exit(1)
print("="*60 + "\n")
