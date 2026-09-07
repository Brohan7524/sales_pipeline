"""
BRONZE LAYER - Raw data ingestion from CSV into MySQL
Sources: source_crm/ and source_erp/ folders inside datasets/
No transformations. Just load as-is.
"""

import pandas as pd
from sqlalchemy import create_engine, text
import mysql.connector
import os
import sys
from dotenv import load_dotenv

# Config - loaded from .env (see .env.example)
ROOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
load_dotenv(os.path.join(ROOT_DIR, ".env"))

DB_USER     = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = os.getenv("DB_PORT", "3306")
DB_NAME     = "bronze"

# Automatically resolve path: scripts/ -> datasets/
BASE_DIR = os.path.join(ROOT_DIR, "datasets")

# Map: MySQL table name -> CSV file path
CSV_FILES = {
    "raw_cust_info":     os.path.join(BASE_DIR, "source_crm", "cust_info.csv"),
    "raw_prd_info":      os.path.join(BASE_DIR, "source_crm", "prd_info.csv"),
    "raw_sales_details": os.path.join(BASE_DIR, "source_crm", "sales_details.csv"),
    "raw_cust_az12":     os.path.join(BASE_DIR, "source_erp", "CUST_AZ12.csv"),
    "raw_loc_a101":      os.path.join(BASE_DIR, "source_erp", "LOC_A101.csv"),
    "raw_px_cat_g1v2":   os.path.join(BASE_DIR, "source_erp", "PX_CAT_G1V2.csv"),
}

print("\n" + "="*50)
print("  BRONZE LAYER - Starting...")
print("="*50)

# Step 1 - Create bronze database
print(f"\n[1/3] Connecting to MySQL and creating '{DB_NAME}' database...")
try:
    conn = mysql.connector.connect(
        host=DB_HOST, user=DB_USER,
        password=DB_PASSWORD, port=int(DB_PORT)
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME};")
    conn.commit()
    cursor.close()
    conn.close()
    print(f"    Database '{DB_NAME}' is ready.")
except mysql.connector.Error as e:
    print(f"    Failed to connect to MySQL: {e}")
    print("      Check DB_USER, DB_PASSWORD, DB_HOST, DB_PORT.")
    sys.exit(1)

# Step 2 - Create SQLAlchemy engine
print(f"\n[2/3] Creating database engine for '{DB_NAME}'...")
try:
    engine = create_engine(
        f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )
    with engine.connect() as c:
        c.execute(text("SELECT 1"))
    print(f"    Engine connected to '{DB_NAME}' successfully.")
except Exception as e:
    print(f"    Failed to create engine: {e}")
    sys.exit(1)

# Step 3 - Load each CSV into its bronze table
print(f"\n[3/3] Loading CSV files into '{DB_NAME}'...")

all_success = True
for table_name, file_path in CSV_FILES.items():
    csv_name = os.path.basename(file_path)
    print(f"\n    Loading '{csv_name}' -> table '{table_name}'...")

    # Check file exists
    if not os.path.exists(file_path):
        print(f"      File not found: {os.path.normpath(file_path)}")
        all_success = False
        continue

    # Read CSV
    try:
        df = pd.read_csv(file_path)
        print(f"      {len(df):,} rows x {len(df.columns)} columns read.")
    except Exception as e:
        print(f"      Failed to read '{csv_name}': {e}")
        all_success = False
        continue

    # Write to MySQL
    try:
        df.to_sql(table_name, engine, if_exists="replace", index=False)
        print(f"      '{table_name}' loaded - {len(df):,} rows.")
    except Exception as e:
        print(f"      Failed to write table '{table_name}': {e}")
        all_success = False

print("\n" + "="*50)
if all_success:
    print("  BRONZE LAYER COMPLETE - All 6 tables loaded.")
else:
    print("  BRONZE LAYER FAILED - Fix errors above then re-run.")
    sys.exit(1)
print("="*50 + "\n")
