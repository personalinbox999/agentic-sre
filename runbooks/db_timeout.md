# Runbook: Database Connection Timeout Remediation

## Error Signature
`Connection refused`, `Timeout waiting for lock`, or `SQLAlchemy Timeout`

## Description
The ETL pipeline failed to connect to the target PostgreSQL Data Warehouse. This usually happens when the data warehouse is under heavy load, blocking connections and causing Airflow tasks to hit their standard connection timeout limit.

## Validation Steps
Run the following commands on the database server to check the connection status and load:

```sql
-- Check active connections
SELECT count(*) FROM pg_stat_activity;

-- Identify long-running queries blocking the lock
SELECT pid, now() - pg_stat_activity.query_start AS duration, query, state
FROM pg_stat_activity
WHERE (now() - pg_stat_activity.query_start) > interval '5 minutes';
```

## Remediation Action
Do not immediately restart the job, as that may worsen the load. 

**Code Fix:**
If the database load is confirmed to be a normal peak load, increase the connection timeout in the Airflow DAG configuration to prevent premature failures.

```python
# Change needed in DAG
# Add connect_timeout=120 to the connection string parameters
"postgresql+psycopg2://user:pass@host:5432/db?connect_timeout=120"
```

**Infrastructure Fix:**
If the database is legitimately overloaded and down, restart the instance and scale the connection pooler (e.g., PgBouncer).

REQUIRED: Set `REQUIRES_INCIDENT: True` so engineering can apply the backoff/timeout fix.
REASONING for AI Extraction: Setting `statement_timeout` forces deadlocked queries to abort immediately rather than hanging indefinitely. Catching `OperationalError` and retrying with exponential backoff allows transient locks to clear before the next attempt, ensuring eventual success without crashing the whole DAG.
