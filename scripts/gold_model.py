"""
GOLD LAYER — Build Star Schema from silver tables.
Merges CRM + ERP sources into clean dim/fact tables for Power BI.

Star Schema:
  fact_sales
    ├── dim_customers  (merged CRM cust_info + ERP CUST_AZ12 + ERP LOC_A101)
    ├── dim_products   (merged CRM prd_info + ERP PX_CAT_G1V2)
    └── dim_date       (generated from sales order dates)
"""

import pandas as pd
from sqlalchemy import create_engine, text
import mysql.connector
import sys

# ─────────────────────────────────────────────
# CONFIG — Only change DB_PASSWORD
# ─────────────────────────────────────────────
DB_USER     = "root"
DB_PASSWORD = "admin"
DB_HOST     = "localhost"
DB_PORT     = "3306"
SILVER_DB   = "silver"
GOLD_DB     = "gold"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def make_engine(db_name):
    try:
        engine = create_engine(
            f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{db_name}"
        )
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print(f"    ✅ Connected to '{db_name}'.")
        return engine
    except Exception as e:
        print(f"    ❌ Cannot connect to '{db_name}': {e}")
        return None

def read_table(engine, table_name, db_name):
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
        print(f"    📄 Read '{table_name}' from '{db_name}': {len(df):,} rows.")
        return df
    except Exception as e:
        print(f"    ❌ Failed to read '{table_name}' from '{db_name}': {e}")
        return None

def write_table(df, engine, table_name, db_name):
    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"    ✅ Written '{table_name}' → '{db_name}': {len(df):,} rows.")
        return True
    except Exception as e:
        print(f"    ❌ Failed to write '{table_name}' to '{db_name}': {e}")
        return False

# ─────────────────────────────────────────────
print("\n" + "="*50)
print("  GOLD LAYER — Starting...")
print("="*50)

# STEP 1 — Create gold database
print(f"\n[1/6] Creating '{GOLD_DB}' database if it doesn't exist...")
try:
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, port=int(DB_PORT)
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {GOLD_DB};")
    conn.commit()
    cursor.close()
    conn.close()
    print(f"    ✅ Database '{GOLD_DB}' is ready.")
except Exception as e:
    print(f"    ❌ Could not create '{GOLD_DB}' database: {e}")
    sys.exit(1)

# STEP 2 — Connect
print(f"\n[2/6] Connecting to silver and gold...")
silver_engine = make_engine(SILVER_DB)
gold_engine   = make_engine(GOLD_DB)
if silver_engine is None or gold_engine is None:
    print("    ❌ Cannot proceed. Exiting.")
    sys.exit(1)

all_success = True

# ─────────────────────────────────────────────
# STEP 3 — dim_customers
# ─────────────────────────────────────────────
print(f"\n[3/6] Building dim_customers...")
crm_cust = read_table(silver_engine, "clean_cust_info",  SILVER_DB)
erp_cust = read_table(silver_engine, "clean_cust_az12",  SILVER_DB)
erp_loc  = read_table(silver_engine, "clean_loc_a101",   SILVER_DB)

if crm_cust is not None and erp_cust is not None and erp_loc is not None:
    try:
        print(f"      → crm_cust columns: {list(crm_cust.columns)}")
        print(f"      → erp_cust columns: {list(erp_cust.columns)}")
        print(f"      → erp_loc  columns: {list(erp_loc.columns)}")

        # ── Normalise CRM: keep latest record per cst_id ──────────
        crm_cust["cst_id"] = pd.to_numeric(crm_cust["cst_id"], errors="coerce")
        crm_cust = crm_cust.sort_values("cst_key", ascending=False)
        crm_cust = crm_cust.drop_duplicates(subset="cst_id", keep="first")
        crm_cust["cst_id"] = crm_cust["cst_id"].astype(str).str.strip()
        print(f"      → CRM unique customers after dedup: {len(crm_cust):,}")

        # ── Normalise ERP cid: strip 'NAS' prefix ─────────────────
        erp_cust["cid"] = erp_cust["cid"].astype(str).str.replace("NAS", "", regex=False).str.strip()
        erp_cust = erp_cust.drop_duplicates(subset="cid", keep="first")
        print(f"      → Sample CRM cst_id: {crm_cust['cst_id'].head(3).tolist()}")
        print(f"      → Sample ERP cid:    {erp_cust['cid'].head(3).tolist()}")

        # ── Normalise LOC key ──────────────────────────────────────
        loc_key = next((c for c in erp_loc.columns if "id" in c.lower()), erp_loc.columns[0])
        erp_loc[loc_key] = erp_loc[loc_key].astype(str).str.replace("NAS", "", regex=False).str.strip()
        erp_loc = erp_loc.drop_duplicates(subset=loc_key, keep="first")

        # ── Merge 1: CRM + ERP demographics ───────────────────────
        dim_customers = crm_cust.merge(erp_cust, left_on="cst_id", right_on="cid", how="left", suffixes=("", "_erp"))
        dim_customers.drop(columns=[c for c in dim_customers.columns if c.endswith("_erp")], inplace=True)
        matched = dim_customers["cid"].notna().sum()
        print(f"      → After CRM+ERP merge: {len(dim_customers):,} rows, {matched:,} matched")

        # ── Merge 2: + location ────────────────────────────────────
        dim_customers = dim_customers.merge(erp_loc, left_on="cst_id", right_on=loc_key, how="left", suffixes=("", "_loc"))
        dim_customers.drop(columns=[c for c in dim_customers.columns if c.endswith("_loc")], inplace=True)

        # ── Final dedup on cst_id (the PK for Power BI) ───────────
        before = len(dim_customers)
        dim_customers = dim_customers.drop_duplicates(subset="cst_id", keep="first")
        print(f"      → Removed {before - len(dim_customers)} duplicates → {len(dim_customers):,} unique customers")

        ok = write_table(dim_customers, gold_engine, "dim_customers", GOLD_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    ❌ Error building dim_customers: {e}")
        all_success = False
else:
    print("    ❌ Skipping dim_customers — one or more source tables missing.")
    all_success = False


# ─────────────────────────────────────────────
# STEP 4 — dim_products
# ─────────────────────────────────────────────
print(f"\n[4/6] Building dim_products...")
crm_prd  = read_table(silver_engine, "clean_prd_info",    SILVER_DB)
erp_cat  = read_table(silver_engine, "clean_px_cat_g1v2", SILVER_DB)

if crm_prd is not None and erp_cat is not None:
    try:
        print(f"      → crm_prd columns: {list(crm_prd.columns)}")
        print(f"      → erp_cat columns: {list(erp_cat.columns)}")

        # Keep only active products — prd_end_dt is null means currently active
        if "prd_end_dt" in crm_prd.columns:
            crm_prd["prd_end_dt"] = pd.to_datetime(crm_prd["prd_end_dt"], errors="coerce")
            before = len(crm_prd)
            crm_prd = crm_prd[crm_prd["prd_end_dt"].isna()].copy()
            print(f"      → Active products only: {before} → {len(crm_prd)}")

        # Dedup on prd_key
        before = len(crm_prd)
        crm_prd = crm_prd.drop_duplicates(subset="prd_key", keep="first")
        print(f"      → Removed {before - len(crm_prd)} duplicate prd_key rows → {len(crm_prd):,} unique")

        # Merge with ERP categories
        prd_cat_col = next((c for c in crm_prd.columns if "cat" in c.lower()), None)
        cat_id_col  = next((c for c in erp_cat.columns if "id" in c.lower() or "cat" in c.lower()), None)

        if prd_cat_col and cat_id_col:
            crm_prd[prd_cat_col] = crm_prd[prd_cat_col].astype(str).str.strip()
            erp_cat[cat_id_col]  = erp_cat[cat_id_col].astype(str).str.strip()
            dim_products = crm_prd.merge(erp_cat, left_on=prd_cat_col, right_on=cat_id_col, how="left", suffixes=("", "_cat"))
            dim_products.drop(columns=[c for c in dim_products.columns if c.endswith("_cat")], inplace=True)
            print(f"      → Merged with ERP categories: {len(dim_products):,} rows")
        else:
            dim_products = crm_prd.copy()

        # Final safety dedup
        dim_products = dim_products.drop_duplicates(subset="prd_key", keep="first")
        print(f"      → Final dim_products: {len(dim_products):,} unique products")

        ok = write_table(dim_products, gold_engine, "dim_products", GOLD_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    ❌ Error building dim_products: {e}")
        all_success = False
else:
    print("    ❌ Skipping dim_products — one or more source tables missing.")
    all_success = False

# STEP 5 — dim_date
print(f"\n[5/6] Building dim_date...")
sales = read_table(silver_engine, "clean_sales_details", SILVER_DB)

if sales is not None:
    try:
        print(f"      → Sales columns: {list(sales.columns)}")

        # ✅ FIX: match sls_order_dt and any _dt suffix
        date_col = next((c for c in sales.columns if "order_date" in c.lower()), None)
        if date_col is None:
            date_col = next((c for c in sales.columns if "order_dt" in c.lower()), None)
        if date_col is None:
            date_col = next((c for c in sales.columns if "date" in c.lower() or c.lower().endswith("_dt")), None)

        if date_col is None:
            print(f"    ❌ No date column found. Columns are: {list(sales.columns)}")
            all_success = False
        else:
            print(f"      → Using date column: '{date_col}'")
            sample = sales[date_col].dropna().iloc[0] if not sales[date_col].dropna().empty else None
            if sample is not None and str(sample).replace(".0","").isdigit() and len(str(int(float(sample)))) == 8:
                sales[date_col] = pd.to_datetime(sales[date_col].astype(str).str.replace(".0","", regex=False), format="%Y%m%d", errors="coerce")
            else:
                sales[date_col] = pd.to_datetime(sales[date_col], errors="coerce")

            unique_dates = sales[date_col].dropna().dt.normalize().unique()
            dim_date = pd.DataFrame({"date": sorted(unique_dates)})
            dim_date["year"]       = dim_date["date"].dt.year
            dim_date["quarter"]    = dim_date["date"].dt.quarter
            dim_date["month"]      = dim_date["date"].dt.month
            dim_date["month_name"] = dim_date["date"].dt.strftime("%B")
            dim_date["week"]       = dim_date["date"].dt.isocalendar().week.astype(int)
            dim_date["day"]        = dim_date["date"].dt.day
            dim_date["weekday"]    = dim_date["date"].dt.day_name()
            dim_date["is_weekend"] = dim_date["weekday"].isin(["Saturday", "Sunday"])

            print(f"      → Date range: {dim_date['date'].min().date()} → {dim_date['date'].max().date()}")
            ok = write_table(dim_date, gold_engine, "dim_date", GOLD_DB)
            if not ok: all_success = False
    except Exception as e:
        print(f"    ❌ Error building dim_date: {e}")
        all_success = False
else:
    all_success = False

# STEP 6 — fact_sales
print(f"\n[6/6] Building fact_sales...")
if sales is not None:
    try:
        fact_sales = sales.copy()

        qty_col   = next((c for c in fact_sales.columns if c in ["sales_quantity", "sls_quantity", "quantity"]), None)
        price_col = next((c for c in fact_sales.columns if c in ["unit_price", "sls_price", "price"]), None)
        cost_col  = next((c for c in fact_sales.columns if c in ["unit_cost", "sls_cost", "cost", "sls_sales"]), None)

        if qty_col:   fact_sales[qty_col]   = pd.to_numeric(fact_sales[qty_col],   errors="coerce").fillna(0)
        if price_col: fact_sales[price_col] = pd.to_numeric(fact_sales[price_col], errors="coerce").fillna(0)
        if cost_col:  fact_sales[cost_col]  = pd.to_numeric(fact_sales[cost_col],  errors="coerce").fillna(0)

        if qty_col and price_col:
            fact_sales["sales_amount"] = fact_sales[qty_col] * fact_sales[price_col]
            print(f"      → Calculated sales_amount = '{qty_col}' × '{price_col}'")

        if "sales_amount" in fact_sales.columns and cost_col and qty_col:
            fact_sales["profit"] = fact_sales["sales_amount"] - (fact_sales[cost_col] * fact_sales[qty_col])

        total_revenue = fact_sales["sales_amount"].sum() if "sales_amount" in fact_sales.columns else 0
        print(f"      → Total revenue: {total_revenue:,.2f}")
        print(f"      → Total orders:  {len(fact_sales):,}")

        ok = write_table(fact_sales, gold_engine, "fact_sales", GOLD_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    ❌ Error building fact_sales: {e}")
        all_success = False
else:
    all_success = False

# ─────────────────────────────────────────────
print("\n" + "="*50)
if all_success:
    print("  ✅ GOLD LAYER COMPLETE — Star schema ready for Power BI.")
    print("\n  Tables in 'gold':")
    print("    • dim_customers  ← CRM + ERP demographics + location")
    print("    • dim_products   ← CRM + ERP categories")
    print("    • dim_date       ← generated from order dates")
    print("    • fact_sales     ← sales with derived metrics")
    print("\n  Power BI Relationships:")
    print("    fact_sales.sls_cust_id  → dim_customers.cst_id")
    print("    fact_sales.sls_prd_key  → dim_products.prd_key")
    print("    fact_sales.sls_order_dt → dim_date.date")
else:
    print("  ❌ GOLD LAYER FAILED — Fix errors above then re-run.")
    sys.exit(1)
print("="*50 + "\n")