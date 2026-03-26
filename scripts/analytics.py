"""
ANALYTICS LAYER — Converts SQL Server analysis scripts 01-09 to Python/MySQL.
Runs all exploratory and analytical queries against the gold layer.
Prints results neatly to console.

Run with: python analytics.py
"""

import pandas as pd
from sqlalchemy import create_engine, text
import sys

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
DB_USER     = "root"
DB_PASSWORD = "admin"
DB_HOST     = "localhost"
DB_PORT     = "3306"
GOLD_DB     = "gold"

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
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

def run_query(engine, title, sql):
    print(f"\n{'─'*60}")
    print(f"  📊 {title}")
    print(f"{'─'*60}")
    try:
        df = pd.read_sql(sql, engine)
        if df.empty:
            print("  (no results)")
        else:
            print(df.to_string(index=False))
        return df
    except Exception as e:
        print(f"  ❌ Query failed: {e}")
        return None

# ─────────────────────────────────────────────
print("\n" + "="*60)
print("  ANALYTICS LAYER — Starting...")
print("="*60)

engine = make_engine()

# ═══════════════════════════════════════════════════════════
# 01 — DATABASE EXPLORATION
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  01 — DATABASE EXPLORATION")
print("█"*60)

run_query(engine, "All tables in gold database","""
    SELECT TABLE_NAME, TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'gold'
""")

run_query(engine, "Columns in dim_customers", """
    SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'gold' AND TABLE_NAME = 'dim_customers'
""")

# ═══════════════════════════════════════════════════════════
# 02 — DATA EXPLORATION
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  02 — DATA EXPLORATION")
print("█"*60)

run_query(engine, "Distinct countries of customers", """
    SELECT DISTINCT cntry AS country
    FROM dim_customers
    ORDER BY country
""")

run_query(engine, "Product categories, subcategories and names", """
    SELECT DISTINCT cat AS category, subcat AS subcategory, prd_nm AS product_name
    FROM dim_products
    ORDER BY category, subcategory, product_name
""")

run_query(engine, "First order, last order, duration in months", """
    SELECT
        MIN(sls_order_dt)                                          AS first_order_date,
        MAX(sls_order_dt)                                          AS last_order_date,
        TIMESTAMPDIFF(MONTH, MIN(sls_order_dt), MAX(sls_order_dt)) AS duration_months
    FROM fact_sales
    WHERE sls_order_dt IS NOT NULL
""")

run_query(engine, "Youngest and oldest customer ages", """
    SELECT
        MAX(bdate)                                        AS youngest_birthdate,
        TIMESTAMPDIFF(YEAR, MAX(bdate), CURDATE())        AS youngest_age,
        MIN(bdate)                                        AS oldest_birthdate,
        TIMESTAMPDIFF(YEAR, MIN(bdate), CURDATE())        AS oldest_age
    FROM dim_customers
    WHERE bdate IS NOT NULL
""")

run_query(engine, "Key business metrics summary", """
    SELECT 'Total Sales'        AS measure_name, SUM(sales_amount)            AS measure_value FROM fact_sales
    UNION ALL
    SELECT 'Total Quantity',                      SUM(sls_quantity)            FROM fact_sales
    UNION ALL
    SELECT 'Average Price',                       ROUND(AVG(sls_price), 2)    FROM fact_sales
    UNION ALL
    SELECT 'Total Orders',                        COUNT(DISTINCT sls_ord_num)  FROM fact_sales
    UNION ALL
    SELECT 'Total Products',                      COUNT(DISTINCT prd_key)      FROM dim_products
    UNION ALL
    SELECT 'Total Customers',                     COUNT(DISTINCT cst_id)       FROM dim_customers
""")

# ═══════════════════════════════════════════════════════════
# 03 — MAGNITUDE ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  03 — MAGNITUDE ANALYSIS")
print("█"*60)

run_query(engine, "Total customers by country", """
    SELECT cntry AS country, COUNT(cst_id) AS total_customers
    FROM dim_customers
    GROUP BY cntry
    ORDER BY total_customers DESC
""")

run_query(engine, "Total customers by gender", """
    SELECT cst_gndr AS gender, COUNT(cst_id) AS total_customers
    FROM dim_customers
    GROUP BY cst_gndr
    ORDER BY total_customers DESC
""")

run_query(engine, "Total products by category", """
    SELECT cat AS category, COUNT(prd_key) AS total_products
    FROM dim_products
    GROUP BY cat
    ORDER BY total_products DESC
""")

run_query(engine, "Average cost per category", """
    SELECT cat AS category, ROUND(AVG(prd_cost), 2) AS avg_cost
    FROM dim_products
    GROUP BY cat
    ORDER BY avg_cost DESC
""")

run_query(engine, "Total revenue by category", """
    SELECT p.cat AS category, SUM(s.sales_amount) AS total_revenue
    FROM fact_sales s
    LEFT JOIN dim_products p ON p.prd_key = s.sls_prd_key
    GROUP BY p.cat
    ORDER BY total_revenue DESC
""")

run_query(engine, "Total revenue by customer (top 20)", """
    SELECT
        c.cst_id        AS customer_id,
        c.cst_firstname AS first_name,
        c.cst_lastname  AS last_name,
        SUM(s.sales_amount) AS total_revenue
    FROM fact_sales s
    LEFT JOIN dim_customers c ON c.cst_id = s.sls_cust_id
    GROUP BY c.cst_id, c.cst_firstname, c.cst_lastname
    ORDER BY total_revenue DESC
    LIMIT 20
""")

run_query(engine, "Total items sold by country", """
    SELECT c.cntry AS country, SUM(s.sls_quantity) AS total_sold_items
    FROM fact_sales s
    LEFT JOIN dim_customers c ON c.cst_id = s.sls_cust_id
    GROUP BY c.cntry
    ORDER BY total_sold_items DESC
""")

# ═══════════════════════════════════════════════════════════
# 04 — RANKING ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  04 — RANKING ANALYSIS")
print("█"*60)

run_query(engine, "Top 5 products by revenue", """
    SELECT
        p.prd_nm AS product_name,
        SUM(s.sales_amount) AS total_revenue,
        RANK() OVER (ORDER BY SUM(s.sales_amount) DESC) AS product_rank
    FROM fact_sales s
    LEFT JOIN dim_products p ON p.prd_key = s.sls_prd_key
    GROUP BY p.prd_nm
    ORDER BY total_revenue DESC
    LIMIT 5
""")

run_query(engine, "Bottom 5 products by revenue", """
    SELECT
        p.prd_nm AS product_name,
        SUM(s.sales_amount) AS total_revenue
    FROM fact_sales s
    LEFT JOIN dim_products p ON p.prd_key = s.sls_prd_key
    GROUP BY p.prd_nm
    ORDER BY total_revenue ASC
    LIMIT 5
""")

run_query(engine, "Top 10 customers by revenue", """
    SELECT
        c.cst_id        AS customer_id,
        c.cst_firstname AS first_name,
        c.cst_lastname  AS last_name,
        SUM(s.sales_amount) AS total_revenue,
        ROW_NUMBER() OVER (ORDER BY SUM(s.sales_amount) DESC) AS customer_rank
    FROM fact_sales s
    LEFT JOIN dim_customers c ON c.cst_id = s.sls_cust_id
    GROUP BY c.cst_id, c.cst_firstname, c.cst_lastname
    ORDER BY total_revenue DESC
    LIMIT 10
""")

run_query(engine, "10 customers with fewest orders", """
    SELECT
        c.cst_id        AS customer_id,
        c.cst_firstname AS first_name,
        c.cst_lastname  AS last_name,
        COUNT(DISTINCT s.sls_ord_num) AS total_orders
    FROM fact_sales s
    LEFT JOIN dim_customers c ON c.cst_id = s.sls_cust_id
    GROUP BY c.cst_id, c.cst_firstname, c.cst_lastname
    ORDER BY total_orders ASC
    LIMIT 10
""")

# ═══════════════════════════════════════════════════════════
# 05 — TIME-SERIES ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  05 — TIME-SERIES ANALYSIS")
print("█"*60)

run_query(engine, "Sales seasonality by month", """
    SELECT
        MONTH(sls_order_dt)                    AS order_month,
        SUM(sales_amount)                       AS total_sales,
        COUNT(DISTINCT sls_cust_id)             AS total_customers,
        SUM(sls_quantity)                       AS total_quantity
    FROM fact_sales
    WHERE sls_order_dt IS NOT NULL
    GROUP BY MONTH(sls_order_dt)
    ORDER BY total_sales DESC
""")

run_query(engine, "Monthly sales performance over time", """
    SELECT
        DATE_FORMAT(sls_order_dt, '%Y-%b')      AS order_month,
        SUM(sales_amount)                        AS total_sales,
        COUNT(DISTINCT sls_cust_id)              AS total_customers,
        SUM(sls_quantity)                        AS total_quantity
    FROM fact_sales
    WHERE sls_order_dt IS NOT NULL
    GROUP BY DATE_FORMAT(sls_order_dt, '%Y-%b'), DATE_FORMAT(sls_order_dt, '%Y-%m')
    ORDER BY DATE_FORMAT(sls_order_dt, '%Y-%m')
""")

# ═══════════════════════════════════════════════════════════
# 06 — CUMULATIVE ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  06 — CUMULATIVE ANALYSIS")
print("█"*60)

run_query(engine, "Running total sales and average price by year", """
    SELECT
        order_year,
        total_sales,
        SUM(total_sales) OVER (ORDER BY order_year)        AS running_total_sales,
        ROUND(avg_price, 2)                                AS avg_price,
        ROUND(AVG(avg_price) OVER (ORDER BY order_year), 2) AS running_avg_price
    FROM (
        SELECT
            YEAR(sls_order_dt)      AS order_year,
            SUM(sales_amount)       AS total_sales,
            AVG(sls_price)          AS avg_price
        FROM fact_sales
        WHERE sls_order_dt IS NOT NULL
        GROUP BY YEAR(sls_order_dt)
    ) t
    ORDER BY order_year
""")

run_query(engine, "Rolling 2-year total and average price", """
    SELECT
        order_year,
        total_sales,
        SUM(total_sales) OVER (ORDER BY order_year ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) AS rolling_total_sales,
        ROUND(avg_price, 2) AS avg_price,
        ROUND(AVG(avg_price) OVER (ORDER BY order_year ROWS BETWEEN 1 PRECEDING AND CURRENT ROW), 2) AS rolling_avg_price
    FROM (
        SELECT
            YEAR(sls_order_dt)  AS order_year,
            SUM(sales_amount)   AS total_sales,
            AVG(sls_price)      AS avg_price
        FROM fact_sales
        WHERE sls_order_dt IS NOT NULL
        GROUP BY YEAR(sls_order_dt)
    ) t
    ORDER BY order_year
""")

# ═══════════════════════════════════════════════════════════
# 07 — PERFORMANCE ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  07 — PERFORMANCE ANALYSIS")
print("█"*60)

run_query(engine, "Yearly sales vs average and prior year", """
    SELECT
        date_year,
        avg_sales_yearly,
        ROUND(avg_sales_overall, 2)   AS avg_sales_overall,
        previous_year_sales,
        CASE
            WHEN avg_sales_yearly > avg_sales_overall THEN 'Above Average'
            WHEN avg_sales_yearly < avg_sales_overall THEN 'Below Average'
            ELSE 'Average'
        END AS compare_to_avg,
        CASE
            WHEN avg_sales_yearly > previous_year_sales THEN 'Better Performance'
            WHEN avg_sales_yearly < previous_year_sales THEN 'Worse Performance'
            ELSE 'Same Performance'
        END AS compare_to_last_year
    FROM (
        SELECT
            date_year,
            avg_sales_yearly,
            AVG(avg_sales_yearly) OVER ()                          AS avg_sales_overall,
            LAG(avg_sales_yearly) OVER (ORDER BY date_year)        AS previous_year_sales
        FROM (
            SELECT
                YEAR(sls_order_dt)      AS date_year,
                AVG(sales_amount)       AS avg_sales_yearly
            FROM fact_sales
            WHERE sls_order_dt IS NOT NULL
            GROUP BY YEAR(sls_order_dt)
        ) t1
    ) t2
    ORDER BY date_year
""")

run_query(engine, "Product yearly performance vs avg and prior year", """
    SELECT
        order_year,
        product_name,
        current_sales,
        ROUND(avg_sales, 2)        AS avg_sales,
        current_sales - avg_sales  AS diff_avg,
        CASE
            WHEN current_sales > avg_sales THEN 'Above Avg'
            WHEN current_sales < avg_sales THEN 'Below Avg'
            ELSE 'Avg'
        END AS avg_change,
        prev_year_sales,
        current_sales - prev_year_sales AS diff_prev_year,
        CASE
            WHEN current_sales > prev_year_sales THEN 'Increase'
            WHEN current_sales < prev_year_sales THEN 'Decrease'
            WHEN current_sales = prev_year_sales THEN 'No Change'
            ELSE NULL
        END AS prev_year_change
    FROM (
        SELECT
            order_year,
            product_name,
            current_sales,
            AVG(current_sales) OVER (PARTITION BY product_name)                             AS avg_sales,
            LAG(current_sales) OVER (PARTITION BY product_name ORDER BY order_year)         AS prev_year_sales
        FROM (
            SELECT
                YEAR(f.sls_order_dt)  AS order_year,
                p.prd_nm              AS product_name,
                SUM(f.sales_amount)   AS current_sales
            FROM fact_sales f
            LEFT JOIN dim_products p ON f.sls_prd_key = p.prd_key
            WHERE f.sls_order_dt IS NOT NULL
            GROUP BY YEAR(f.sls_order_dt), p.prd_nm
        ) base
    ) ranked
    ORDER BY product_name, order_year
""")

# ═══════════════════════════════════════════════════════════
# 08 — PART-TO-WHOLE ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  08 — PART-TO-WHOLE ANALYSIS")
print("█"*60)

run_query(engine, "Category contribution to overall sales (%)", """
    SELECT
        category,
        total_sales,
        overall_sales,
        CONCAT(ROUND((total_sales / overall_sales) * 100, 2), '%') AS percentage_of_total
    FROM (
        SELECT
            p.cat                      AS category,
            SUM(f.sales_amount)        AS total_sales,
            SUM(SUM(f.sales_amount)) OVER () AS overall_sales
        FROM fact_sales f
        LEFT JOIN dim_products p ON p.prd_key = f.sls_prd_key
        GROUP BY p.cat
    ) t
    ORDER BY total_sales DESC
""")

# ═══════════════════════════════════════════════════════════
# 09 — SEGMENTATION ANALYSIS
# ═══════════════════════════════════════════════════════════
print("\n\n" + "█"*60)
print("  09 — SEGMENTATION ANALYSIS")
print("█"*60)

run_query(engine, "Products by cost range segment", """
    SELECT
        cost_range,
        COUNT(prd_key) AS total_products
    FROM (
        SELECT
            prd_key,
            prd_nm,
            prd_cost,
            CASE
                WHEN prd_cost < 100             THEN 'Below 100'
                WHEN prd_cost BETWEEN 100 AND 500  THEN '100-500'
                WHEN prd_cost BETWEEN 500 AND 1000 THEN '500-1000'
                ELSE 'Above 1000'
            END AS cost_range
        FROM dim_products
    ) t
    GROUP BY cost_range
    ORDER BY total_products DESC
""")

run_query(engine, "Customer segments: VIP / Regular / New", """
    SELECT
        customer_segment,
        COUNT(sls_cust_id) AS total_customers
    FROM (
        SELECT
            sls_cust_id,
            CASE
                WHEN lifespan >= 12 AND total_spending > 5000 THEN 'VIP'
                WHEN lifespan >= 12 AND total_spending <= 5000 THEN 'Regular'
                ELSE 'New'
            END AS customer_segment
        FROM (
            SELECT
                sls_cust_id,
                SUM(sales_amount)                                                          AS total_spending,
                TIMESTAMPDIFF(MONTH, MIN(sls_order_dt), MAX(sls_order_dt))                AS lifespan
            FROM fact_sales
            GROUP BY sls_cust_id
        ) spending
    ) segmented
    GROUP BY customer_segment
    ORDER BY total_customers DESC
""")

# ─────────────────────────────────────────────
print("\n\n" + "="*60)
print("  ✅ ANALYTICS COMPLETE — All 9 analysis sections run.")
print("="*60 + "\n")
