# Runbook: Missing Parquet File

## Error Signature
`FileNotFoundError`, `KeyError in S3 bucket`, or `The specified key does not exist.`

## Description
The downstream data aggregation pipeline failed because it was looking for a specific Parquet file on Amazon S3 (e.g., `s3://data-lake-raw/sales/date=2026-03-11/data.parquet`), but the file wasn't there. This usually happens when the upstream "extract" job silently failed or was delayed.

## Validation Steps
Validate if the file actually exists using the AWS CLI:

```bash
aws s3 ls s3://data-lake-raw/sales/date=2026-03-11/
```

## Remediation Action
No code changes are required. The pipeline logic is sound, it just lacks the data.

**Quick Remediation Steps (Ops Action):**
1. Check the upstream Airflow DAG (e.g., `salesforce_extract_to_s3`) and run it manually for the missing date partition.
REQUIRED: Set `REQUIRES_INCIDENT: False` and `is_transient: True`. No Change Request or Incident is needed.
REASONING for AI Extraction: The downstream data aggregation pipeline failed because it was looking for a specific Parquet file on Amazon S3 that wasn't there yet. This happens when the upstream "extract" job is delayed. An automated rerun via Airflow clears the task so it can try again once the file arrives.
