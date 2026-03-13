# Runbook: Vendor API Rate Limit Exceeded

## Error Signature
`HTTP 429 Too Many Requests` or `Rate limit exceeded`

## Description
The data extraction pipeline is pulling data too aggressively from the external vendor API. The vendor allows a maximum of 3 requests per second. Airflow is hitting the API too fast and getting blocked.

## Validation Steps
Run a simple `curl` test from the Airflow worker to see what headers the API is returning:

```bash
curl -I -X GET "https://api.externalvendor.com/v1/data" \
     -H "Authorization: Bearer $API_TOKEN"
```
Look for the `Retry-After: X` header in the response, which tells you how long the vendor wants you to wait.

## Remediation Action
The extraction script requires an immediate code change. We must implement a backoff strategy between paginated requests in the PythonOperator that fetches the data.

**Code Fix:**
Add a sleep timer or an exponential backoff decorator to the extraction loop.

```python
import time

def fetch_api_data():
    for page in range(100):
        response = requests.get(f"https://api.externalvendor.com/v1/data?page={page}")
        if response.status_code == 429:
            # We hit the rate limit! Wait 2 seconds before retry
            print("Rate limit hit. Sleeping for 2 seconds...")
            time.sleep(2)
            # Retry logic...
        elif response.status_code == 200:
            # Process success
            # Ensure we don't naturally exceed 3 req/sec even on success
            time.sleep(0.35) 
```

REQUIRED: Set `REQUIRES_INCIDENT: True` so the engineering team can implement the sleep timer.
REASONING for AI Extraction: Implementing a 2-second sleep allows the vendor's tokens to replenish, ensuring our request rate stays strictly below 3 req/sec and avoiding 429 blockades.
