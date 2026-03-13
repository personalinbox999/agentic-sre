from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta

def simulate_api_rate_limit(**context):
    try_number = context['ti'].try_number
    
    print("Starting API data extraction from External Vendor...")
    print(f"Current Try Number: {try_number}")
    print("Fetching page 1/100... Success.")
    print("Fetching page 2/100... Success.")
    
    if try_number > 1:
        print("AI Remediation Applied: Backoff strategy enabled.")
        print("Fetching page 3/100... Success.")
        print("Fetching page 4/100... Success.")
        print("All pages fetched successfully!")
        return "Success"
        
    print("Fetching page 3/100... Success.")
    print("Fetching page 4/100...")
    
    # Simulate API Rate Limit
    raise Exception("HTTP 429 Too Many Requests: Rate limit exceeded. Allowed: 3 requests per second.")

with DAG(
    'failing_api_ingestion',
    default_args={
        'owner': 'data_engineering',
        'depends_on_past': False,
        'retries': 0,
    },
    description='A DAG that intentionally fails due to API Rate Limiting',
    schedule_interval=timedelta(minutes=10),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=['etl', 'failing', 'api'],
) as dag:

    fetch_api_data = PythonOperator(
        task_id='fetch_api_data',
        python_callable=simulate_api_rate_limit,
    )

    fetch_api_data
