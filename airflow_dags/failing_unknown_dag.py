from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

def simulate_unsupported_error(**context):
    try_number = context['ti'].try_number
    
    print("Starting custom data transformation...")
    print(f"Current Try Number: {try_number}")
    print("Loading data map...")
    
    if try_number > 1:
        print("AI Remediation Applied: Applying zero-shot structural fix.")
        print("Zero-shot fix failed. Unexpected binary format found.")

    # Introduce an error that has no corresponding runbook
    # We will raise a very specific, weird custom ValueError that the runbooks definitely won't match.
    raise ValueError("TransformationFailed: Unable to parse binary proto file from unknown mainframe schema v0.9 (MAGIC_NUMBER missing).")

with DAG(
    'failing_unknown_error_etl',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 0,
    },
    description='A DAG that intentionally fails with an unknown error to test AI generated fixes',
    schedule_interval=timedelta(minutes=15),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'failing', 'unknown'],
) as dag:

    transform_data = PythonOperator(
        task_id='transform_data',
        python_callable=simulate_unsupported_error,
    )

    transform_data
