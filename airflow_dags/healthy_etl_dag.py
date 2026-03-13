from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

def simulate_successful_etl():
    print("Starting daily batch ETL...")
    print("Extracting 1,000,000 records from Salesforce... Success.")
    print("Transforming records to Parquet format... Success.")
    print("Loading records into Snowflake Data Warehouse... Success.")
    print("ETL Job Completed successfully.")

with DAG(
    'healthy_daily_etl',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'retries': 0,
    },
    description='A healthy DAG that runs successfully every time.',
    schedule_interval=timedelta(hours=24),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'healthy'],
) as dag:

    run_etl = PythonOperator(
        task_id='run_etl',
        python_callable=simulate_successful_etl,
    )

    run_etl
