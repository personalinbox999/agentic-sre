from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

def simulate_disk_space_error(**context):
    try_number = context['ti'].try_number
    
    print("Starting data transformation job...")
    print(f"Current Try Number: {try_number}")
    print("Reading 50GB Parquet file into PyArrow...")
    
    if try_number > 1:
        print("AI Remediation Applied: Clearing /tmp/spark-local before run.")
        print("Writing temporary shuffle files to /tmp/spark-local...")
        print("Job completed successfully!")
        return "Success"
        
    print("Writing temporary shuffle files to /tmp/spark-local...")
    
    # Simulate Disk Space Error
    raise OSError("[Errno 28] No space left on device: '/tmp/spark-local/shuffle_1_2.parquet'")

with DAG(
    'failing_disk_space_job',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'retries': 0,
    },
    description='A DAG that intentionally fails due to disk space issues',
    schedule_interval=timedelta(minutes=15),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'failing', 'infrastructure'],
) as dag:

    transform_data = PythonOperator(
        task_id='transform_data',
        python_callable=simulate_disk_space_error,
    )

    transform_data
