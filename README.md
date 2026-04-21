# Sales Pipeline Analytics

A comprehensive data pipeline project that implements a medallion architecture (Bronze → Silver → Gold) for transforming raw CRM and ERP data into analytics-ready datasets for Power BI reporting.

## Project Overview

This project demonstrates a production-grade data engineering approach using:
- **Bronze Layer**: Raw data ingestion from CSV files (CRM and ERP sources)
- **Silver Layer**: Data cleaning, standardization, and enrichment
- **Gold Layer**: Star schema dimensional modeling optimized for analytics and reporting

## Architecture

```
Raw Data (CSV)
    ↓
Bronze (Raw ingestion)
    ↓
Silver (Cleaning & transformation)
    ↓
Gold (Star schema for analytics)
    ↓
Power BI Reports
```

## Project Structure

```
sales_pipeline/
├── scripts/                          # Python ETL scripts
│   ├── initialise.py               # Initialize MySQL databases
│   ├── bronze_load.py              # Load raw data into Bronze layer
│   ├── silver_transform.py         # Transform Bronze → Silver
│   ├── gold_model.py               # Build Star schema (Gold layer)
│   ├── analytics.py                # Analytics utilities
│   ├── build_reports.py            # Generate reporting data
│   └── run_pipeline.py             # Main orchestrator script
├── datasets/                         # Data storage
│   ├── source_crm/                 # CRM source data
│   ├── source_erp/                 # ERP source data
│   ├── analytics_ready/            # Gold layer outputs
│   └── reporting_ready/            # Report-ready datasets
├── dwh_sales_analytics.pbix        # Power BI dashboard
├── data_architecture.png           # Architecture diagram
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variable template
├── LICENSE                         # MIT License
└── README.md                       # This file
```

## Prerequisites

- Python 3.8+
- MySQL Server 8.0+
- Git

## Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/sales_pipeline.git
   cd sales_pipeline
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your MySQL credentials
   ```

5. **Initialize databases**
   ```bash
   python scripts/initialise.py
   ```

## Usage

### Run Complete Pipeline

Execute the full Bronze → Silver → Gold pipeline:

```bash
python scripts/run_pipeline.py
```

This orchestrator will:
- Load raw data into Bronze layer
- Transform and clean data in Silver layer
- Build star schema in Gold layer
- Stop immediately if any layer fails

### Run Individual Layers

```bash
# Load raw data
python scripts/bronze_load.py

# Transform data
python scripts/silver_transform.py

# Build analytics model
python scripts/gold_model.py
```

### Build Reports
```bash
python scripts/build_reports.py
```

## Data Sources

### CRM (Customer Relationship Management)
- `cust_info.csv` - Customer master data
- `prd_info.csv` - Product information
- `sales_details.csv` - Transaction details

### ERP (Enterprise Resource Planning)
- `CUST_AZ12.csv` - Customer account master
- `LOC_A101.csv` - Location/warehouse data
- `PX_CAT_G1V2.csv` - Product category mapping

## Configuration

All database configuration is managed through `.env` file:

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
```

## Database Schema

### Bronze Layer (Raw)
- Tables: `raw_cust_info`, `raw_prd_info`, `raw_sales_details`, etc.
- No transformations, exact copy of source data

### Silver Layer (Cleaned)
- Tables: `cust_silver`, `prd_silver`, `sales_silver`, etc.
- Data cleaned, null values handled, duplicates removed
- Data types standardized

### Gold Layer (Analytics)
- Fact tables: `fact_sales`
- Dimension tables: `dim_customers`, `dim_products`, `dim_dates`
- Optimized for analytics queries and Power BI

## Power BI Integration

Open `dwh_sales_analytics.pbix` in Power BI Desktop to connect to the Gold layer and create interactive dashboards.

## Troubleshooting

### Connection Error
- Verify MySQL is running: `mysql -u root -p`
- Check `.env` credentials
- Ensure databases exist: `python scripts/initialise.py`

### Missing Data
- Verify CSV files exist in `datasets/source_*` folders
- Check file paths and column names
- Review script output for specific errors

### Pipeline Failure
- Run individual scripts to isolate the failing layer
- Check database connections with `initialise.py`
- Review error messages in console output

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## Author

Rohan Singh

## Support

For issues, questions, or suggestions, please open an issue on GitHub.

---

**Last Updated**: April 2026
