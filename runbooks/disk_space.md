# Runbook: Out of Disk Space during Transformation

## Error Signature
`[Errno 28] No space left on device`, usually referencing `/tmp/spark-local` or `/tmp`

## Description
The Airflow worker node practically ran out of local disk space while shuffling large Parquet files during a Heavy Pandas/Spark transformation job. This is an infrastructure capacity issue, not a codebase application bug.

## Validation Steps
SSH into the Airflow worker node and execute these bash commands to verify the disk usage:

```bash
# Check the root partition and /tmp mount space
df -h

# Find the largest directories under /tmp
sudo du -ah /tmp | sort -n -r | head -n 10
```

## Remediation Action
The immediate fix requires an Operations engineer to perform cleanup. Code changes to the ETL pipeline are not immediately required to fix the outage.

**Infrastructure Fix (Ops Action):**
1. Clear the `/tmp` directory on the worker node to free up space manually.
```bash
sudo rm -rf /tmp/spark-local/*
```
2. Manually restart the Airflow task.
3. Long term, expand the EBS volume of the Airflow worker instances or configure the ETL script to use Amazon S3 for intermediate shuffle data.

REQUIRED: Set `REQUIRES_INCIDENT: True`. This requires an Infrastructure Incident/Ops Ticket so DevOps can clear space.
REASONING for AI Extraction: The Airflow worker has 0% free disk space left, preventing it from writing any temporary files. Operations must run `docker system prune` or clear `/tmp` to free up space, after which the DAG can safely be retried.
