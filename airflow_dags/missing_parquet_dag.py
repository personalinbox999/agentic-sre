from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

# A DAG that runs every 5 minutes and simulates a missing parquet file from a vendor

def simulate_missing_parquet(**context):
    try_number = context['ti'].try_number
    
    print("Starting data load from S3 bucket: s3://vendor-drops/daily/")
    print(f"Current Try Number: {try_number}")
    print("Checking for expected partition: daily_extract_2026.parquet")
    
    if try_number > 1:
        print("AI Remediation Applied: Waiting for vendor SLA / checking fallback bucket.")
        print("Fallback location checked. File is still missing. Escalating...")
        
    # Simulate Missing File Error (Transient but unresolved)
    raise FileNotFoundError("FileNotFoundError: Expected daily_extract_2026.parquet not found in S3 bucket. Vendor may be delayed.")

with DAG(
    'missing_parquet_etl',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 0,
    },
    description='A DAG that intentionally fails due to a missing upstream vendor file',
    schedule_interval=timedelta(minutes=5),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'failing', 's3'],
) as dag:

    load_from_s3 = PythonOperator(
        task_id='load_from_s3',
        python_callable=simulate_missing_parquet,
    )

    load_from_s3
