"""
PIPELINE ORCHESTRATOR — Runs Bronze → Silver → Gold in sequence.
Stops immediately if any layer fails (won't run Silver on empty Bronze, etc.)
Run with: python run_pipeline.py
"""

import subprocess
import sys
import time
import os

STEPS = [
    ("BRONZE", "bronze_load.py",       "Raw CSV data loaded into MySQL"),
    ("SILVER", "silver_transform.py",  "Data cleaned and standardized"),
    ("GOLD",   "gold_model.py",        "Star schema built for Power BI"),
]

def run_step(label, script, description):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)

    print(f"\n{'='*50}")
    print(f"  ▶  Running {label} layer: {script}")
    print(f"     {description}")
    print(f"{'='*50}")

    if not os.path.exists(script_path):
        print(f"\n  ❌ Script not found: {script_path}")
        print(f"     Make sure all scripts are in the same folder.")
        return False

    start = time.time()
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            check=True,
            capture_output=False
        )
        elapsed = time.time() - start
        print(f"\n  ✅ {label} layer finished in {elapsed:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        print(f"\n  ❌ {label} layer FAILED after {elapsed:.1f}s (exit code {e.returncode})")
        return False
    except Exception as e:
        print(f"\n  ❌ Unexpected error running {label}: {e}")
        return False

# ─────────────────────────────────────────────
print("\n" + "█"*50)
print("  SALES DWH PIPELINE — Starting Full Run")
print("█"*50)
pipeline_start = time.time()

for label, script, description in STEPS:
    success = run_step(label, script, description)
    if not success:
        print(f"\n{'█'*50}")
        print(f"  ❌ PIPELINE STOPPED at {label} layer.")
        print(f"     Fix the errors above, then re-run:")
        print(f"       python run_pipeline.py")
        print("█"*50 + "\n")
        sys.exit(1)

total_time = time.time() - pipeline_start

# ─────────────────────────────────────────────
print("\n" + "█"*50)
print(f"  ✅ PIPELINE COMPLETE in {total_time:.1f}s")
print()
print("  Layers:")
print("    ✅ Bronze — 6 raw tables in MySQL (bronze)")
print("    ✅ Silver — 6 clean tables in MySQL (silver)")
print("    ✅ Gold   — star schema in MySQL (gold)")
print()
print("  Next → Open Power BI Desktop:")
print("    1. Get Data → MySQL Database")
print("    2. Server: localhost   Database: gold")
print("    3. Load: fact_sales, dim_customers, dim_products, dim_date")
print("    4. Model view → create relationships")
print("█"*50 + "\n")
