"""
SILVER LAYER - Clean and standardize all 6 bronze tables.
CRM: cust_info, prd_info, sales_details
ERP: CUST_AZ12, LOC_A101, PX_CAT_G1V2
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
import mysql.connector
import sys
from dotenv import load_dotenv

# Config - loaded from .env (see .env.example)
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "3306")
BRONZE_DB   = "bronze"
SILVER_DB   = "silver"

# Helpers
def make_engine(db_name):
    try:
        engine = create_engine(
            f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{db_name}"
        )
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        print(f"    Connected to '{db_name}'.")
        return engine
    except Exception as e:
        print(f"    Cannot connect to '{db_name}': {e}")
        return None

def read_table(engine, table_name, db_name):
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name}", engine)
        print(f"    Read '{table_name}' from '{db_name}': {len(df):,} rows.")
        return df
    except Exception as e:
        print(f"    Failed to read '{table_name}' from '{db_name}': {e}")
        return None

def write_table(df, engine, table_name, db_name):
    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"    Written '{table_name}' -> '{db_name}': {len(df):,} rows.")
        return True
    except Exception as e:
        print(f"    Failed to write '{table_name}' to '{db_name}': {e}")
        return False

print("\n" + "="*50)
print("  SILVER LAYER - Starting...")
print("="*50)

# Step 1 - Create silver database
print(f"\n[1/8] Creating '{SILVER_DB}' database if it doesn't exist...")
try:
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, port=int(DB_PORT)
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {SILVER_DB};")
    conn.commit()
    cursor.close()
    conn.close()
    print(f"    Database '{SILVER_DB}' is ready.")
except Exception as e:
    print(f"    Could not create '{SILVER_DB}' database: {e}")
    sys.exit(1)

# Step 2 - Connect
print(f"\n[2/8] Connecting to bronze and silver...")
bronze_engine = make_engine(BRONZE_DB)
silver_engine = make_engine(SILVER_DB)
if bronze_engine is None or silver_engine is None:
    print("    Cannot proceed. Exiting.")
    sys.exit(1)

all_success = True

# Step 3 - Clean CRM: cust_info
print(f"\n[3/8] Cleaning CRM -> cust_info...")
df = read_table(bronze_engine, "raw_cust_info", BRONZE_DB)
if df is not None:
    try:
        before = len(df)
        df.columns = df.columns.str.lower().str.strip()
        df.drop_duplicates(inplace=True)

        # Standardize gender values if column exists
        if "gender" in df.columns:
            df["gender"] = df["gender"].str.upper().str.strip()
            df["gender"] = df["gender"].replace({"M": "Male", "F": "Female", "N/A": None, "NAS": None})

        # Fix marital status if column exists
        if "marital_status" in df.columns:
            df["marital_status"] = df["marital_status"].str.upper().str.strip()
            df["marital_status"] = df["marital_status"].replace({"S": "Single", "M": "Married"})

        # cst_id arrives as a float-safe numeric (e.g. "11000.0" after any coercion) -
        # cast to a clean nullable int here so it matches fact_sales.sls_cust_id downstream
        if "cst_id" in df.columns:
            df["cst_id"] = pd.to_numeric(df["cst_id"], errors="coerce").astype("Int64")

        print(f"      Removed {before - len(df)} duplicate rows.")
        ok = write_table(df, silver_engine, "clean_cust_info", SILVER_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    Error cleaning cust_info: {e}")
        all_success = False
else:
    all_success = False

# Step 4 - Clean CRM: prd_info
print(f"\n[4/8] Cleaning CRM -> prd_info...")
df = read_table(bronze_engine, "raw_prd_info", BRONZE_DB)
if df is not None:
    try:
        before = len(df)
        df.columns = df.columns.str.lower().str.strip()
        df.drop_duplicates(inplace=True)

        # Fix cost column if present
        for col in ["prd_cost", "cost", "price"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Extract category key if product number column exists (e.g. prd_key like CO-RF-FR-R92B-58)
        if "prd_key" in df.columns:
            df["cat_id"] = df["prd_key"].str.split("-").str[1:3].str.join("-")

            # prd_key is a compound key: 2-segment category prefix + the real product key
            # (e.g. "CO-RF-FR-R92B-58" -> prefix "CO-RF" + real key "FR-R92B-58").
            # fact_sales.sls_prd_key only ever has the real key, so strip the prefix here
            # instead of guess-matching it back downstream.
            df["prd_key"] = df["prd_key"].str.split("-").str[2:].str.join("-")

        # Parse product end date if present
        for col in ["prd_end_dt", "end_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")

        print(f"      Removed {before - len(df)} duplicate rows.")
        ok = write_table(df, silver_engine, "clean_prd_info", SILVER_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    Error cleaning prd_info: {e}")
        all_success = False
else:
    all_success = False

# Step 5 - Clean CRM: sales_details
print(f"\n[5/8] Cleaning CRM -> sales_details...")
df = read_table(bronze_engine, "raw_sales_details", BRONZE_DB)
if df is not None:
    try:
        before = len(df)
        df.columns = df.columns.str.lower().str.strip()
        df.drop_duplicates(inplace=True)

        # Fix date columns
        for col in ["order_date", "ship_date", "due_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col].astype(str), format="%Y%m%d", errors="coerce")

        # Fix numeric columns
        for col in ["sls_quantity", "sls_price", "sls_sales"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # Derived column: sales amount - computed once here; gold_model.py reads it as-is
        if "sls_quantity" in df.columns and "sls_price" in df.columns:
            df["sales_amount"] = df["sls_quantity"] * df["sls_price"]

        # Drop rows missing critical keys
        key_cols = [c for c in ["order_number", "product_key", "customer_id"] if c in df.columns]
        if key_cols:
            dropped = df[key_cols].isna().any(axis=1).sum()
            df.dropna(subset=key_cols, inplace=True)
            if dropped > 0:
                print(f"      Dropped {dropped} rows with null key fields.")

        print(f"      Removed {before - len(df)} duplicate/null rows.")
        ok = write_table(df, silver_engine, "clean_sales_details", SILVER_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    Error cleaning sales_details: {e}")
        all_success = False
else:
    all_success = False

# Step 6 - Clean ERP: CUST_AZ12
print(f"\n[6/8] Cleaning ERP -> CUST_AZ12...")
df = read_table(bronze_engine, "raw_cust_az12", BRONZE_DB)
if df is not None:
    try:
        before = len(df)
        df.columns = df.columns.str.lower().str.strip()
        df.drop_duplicates(inplace=True)

        # Fix birthdate
        for col in ["bdate", "birthdate", "birth_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
                # Flag future birthdates as invalid
                future_mask = df[col] > pd.Timestamp.today()
                if future_mask.sum() > 0:
                    print(f"      {future_mask.sum()} future birthdates found - setting to null.")
                    df.loc[future_mask, col] = None

        # Standardize gender
        if "gen" in df.columns:
            df["gen"] = df["gen"].str.upper().str.strip()
            df["gen"] = df["gen"].replace({"M": "Male", "F": "Female", "N/A": None})

        print(f"      Removed {before - len(df)} duplicate rows.")
        ok = write_table(df, silver_engine, "clean_cust_az12", SILVER_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    Error cleaning CUST_AZ12: {e}")
        all_success = False
else:
    all_success = False

# Step 7 - Clean ERP: LOC_A101
print(f"\n[7/8] Cleaning ERP -> LOC_A101...")
df = read_table(bronze_engine, "raw_loc_a101", BRONZE_DB)
if df is not None:
    try:
        before = len(df)
        df.columns = df.columns.str.lower().str.strip()
        df.drop_duplicates(inplace=True)

        # Clean up country codes or names
        for col in ["cntry", "country"]:
            if col in df.columns:
                df[col] = df[col].str.strip()
                df[col] = df[col].replace({
                    "DE": "Germany", "US": "United States", "USA": "United States",
                    "GB": "United Kingdom", "UK": "United Kingdom",
                    "FR": "France", "AU": "Australia", "CA": "Canada"
                })
                df[col] = df[col].fillna("Unknown")

        print(f"      Removed {before - len(df)} duplicate rows.")
        ok = write_table(df, silver_engine, "clean_loc_a101", SILVER_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    Error cleaning LOC_A101: {e}")
        all_success = False
else:
    all_success = False

# Step 8 - Clean ERP: PX_CAT_G1V2
print(f"\n[8/8] Cleaning ERP -> PX_CAT_G1V2...")
df = read_table(bronze_engine, "raw_px_cat_g1v2", BRONZE_DB)
if df is not None:
    try:
        before = len(df)
        df.columns = df.columns.str.lower().str.strip()
        df.drop_duplicates(inplace=True)

        # Fill missing category/subcategory
        for col in ["cat", "subcat", "category", "subcategory", "maintenance"]:
            if col in df.columns:
                df[col] = df[col].fillna("Unknown")
                df[col] = df[col].str.strip()

        print(f"      Removed {before - len(df)} duplicate rows.")
        ok = write_table(df, silver_engine, "clean_px_cat_g1v2", SILVER_DB)
        if not ok: all_success = False
    except Exception as e:
        print(f"    Error cleaning PX_CAT_G1V2: {e}")
        all_success = False
else:
    all_success = False

print("\n" + "="*50)
if all_success:
    print("  SILVER LAYER COMPLETE - All 6 tables cleaned.")
    print("\n  Tables in 'silver':")
    print("    - clean_cust_info      (CRM customers)")
    print("    - clean_prd_info       (CRM products)")
    print("    - clean_sales_details  (CRM sales)")
    print("    - clean_cust_az12      (ERP customers)")
    print("    - clean_loc_a101       (ERP locations)")
    print("    - clean_px_cat_g1v2    (ERP categories)")
else:
    print("  SILVER LAYER FAILED - Fix errors above then re-run.")
    sys.exit(1)
print("="*50 + "\n")
