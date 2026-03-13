from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

def simulate_oom_error(**context):
    try_number = context['ti'].try_number
    
    print("Starting huge Pandas data transformation...")
    print(f"Current Try Number: {try_number}")
    
    if try_number > 1:
        print("AI Remediation Applied: Switching to chunked processing (10,000 rows/batch).")
        print("Reading massive 10GB CSV file... Success.")
        print("Transformation complete.")
        return "Success"
        
    print("Reading massive 10GB CSV file directly into memory...")
    
    # Simulate Out Of Memory Error
    raise MemoryError("MemoryError: java.lang.OutOfMemoryError: Java heap space. Container killed by YARN for exceeding memory limits.")

with DAG(
    'failing_oom_job',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'retries': 0,
    },
    description='A DAG that intentionally fails due to Out Of Memory',
    schedule_interval=timedelta(hours=2),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'failing', 'compute'],
) as dag:

    oom_transform = PythonOperator(
        task_id='oom_transform',
        python_callable=simulate_oom_error,
    )

    oom_transform
