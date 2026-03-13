from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import random

# A DAG that runs every 5 minutes and simulates a failure

def simulate_etl_db_connection(**context):
    try_number = context['ti'].try_number
    
    # Simulate some initial work
    print("Starting Extract phase from Salesforce...")
    print(f"Current Try Number: {try_number}")
    print("Export successful. 500,000 rows extracted.")
    
    print("Attempting to connect to PostgreSQL Data Warehouse...")
    print("Connecting to 10.0.0.5:5432...")
    
    if try_number > 1:
        print("AI Remediation Applied: Using alternate DB connection string / timeout adjusted.")
        print("Connection Established.")
        print("Data Load complete: 500,000 rows inserted.")
        return "Success"
    
    # We force an exception to simulate the database timeout
    raise ConnectionError("Exception: Connection refused to database at 10.0.0.5. Timeout waiting for lock.")

with DAG(
    'failing_snowflake_etl',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'email_on_failure': False,
        'email_on_retry': False,
        'retries': 0,
    },
    description='A DAG that intentionally fails to test the AI Remediation Agent',
    schedule_interval=timedelta(minutes=5),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'failing'],
) as dag:

    extract_to_s3 = PythonOperator(
        task_id='extract_to_s3',
        python_callable=simulate_etl_db_connection,
    )

    extract_to_s3
