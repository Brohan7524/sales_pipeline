"""
PIPELINE ORCHESTRATOR - Runs Bronze -> Silver -> Gold in sequence.
Stops immediately if any layer fails (won't run Silver on empty Bronze, etc.)

Reports and analytics are optional, flagged steps since not everyone needs
them on every run:
    python run_pipeline.py                # Bronze -> Silver -> Gold
    python run_pipeline.py --with-reports  # ...+ report_customers/report_products
    python run_pipeline.py --with-analytics  # ...+ console analytics (implies
                                              #    --with-reports, since its
                                              #    customer-segment query reads
                                              #    report_customers)
    python run_pipeline.py --full          # everything
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

RUN_ANALYTICS = "--with-analytics" in sys.argv or "--full" in sys.argv
RUN_REPORTS   = "--with-reports" in sys.argv or "--full" in sys.argv or RUN_ANALYTICS

if RUN_REPORTS:
    STEPS.append(("REPORTS", "build_reports.py", "Build report_customers/report_products (incl. customer segmentation)"))
if RUN_ANALYTICS:
    STEPS.append(("ANALYTICS", "analytics.py", "Run console analytics queries against the gold layer"))

def run_step(label, script, description):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), script)

    print(f"\n{'='*50}")
    print(f"  Running {label} layer: {script}")
    print(f"     {description}")
    print(f"{'='*50}")

    if not os.path.exists(script_path):
        print(f"\n  Script not found: {script_path}")
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
        print(f"\n  {label} layer finished in {elapsed:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        elapsed = time.time() - start
        print(f"\n  {label} layer FAILED after {elapsed:.1f}s (exit code {e.returncode})")
        return False
    except Exception as e:
        print(f"\n  Unexpected error running {label}: {e}")
        return False

print("\n" + "="*50)
print("  SALES DWH PIPELINE - Starting Full Run")
print("="*50)
pipeline_start = time.time()

for label, script, description in STEPS:
    success = run_step(label, script, description)
    if not success:
        print(f"\n{'='*50}")
        print(f"  PIPELINE STOPPED at {label} layer.")
        print(f"     Fix the errors above, then re-run:")
        print(f"       python run_pipeline.py")
        print("="*50 + "\n")
        sys.exit(1)

total_time = time.time() - pipeline_start

print("\n" + "="*50)
print(f"  PIPELINE COMPLETE in {total_time:.1f}s")
print()
print("  Layers:")
print("    Bronze - 6 raw tables in MySQL (bronze)")
print("    Silver - 6 clean tables in MySQL (silver)")
print("    Gold   - star schema in MySQL (gold)")
if RUN_REPORTS:
    print("    Reports   - report_customers/report_products in MySQL (gold)")
if RUN_ANALYTICS:
    print("    Analytics - console queries run against MySQL (gold)")
print()
print("  Next, open Power BI Desktop:")
print("    1. Get Data -> MySQL Database")
print("    2. Server: localhost   Database: gold")
print("    3. Load: fact_sales, dim_customers, dim_products, dim_date")
print("    4. Model view -> create relationships")
print("="*50 + "\n")
