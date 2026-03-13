# Runbook: Out of Memory (OOM) Error

## Error Signature
`MemoryError`, `java.lang.OutOfMemoryError: Java heap space`, or `Container killed by YARN for exceeding memory limits`.

## Description
The container running the Python data transformation job exhausted its available RAM. This happens when attempting to load an entire massive dataset into a Pandas DataFrame in memory without chunking or moving to Spark.

## Validation Steps
Check the Kubernetes/Docker or YARN resource graphs for the worker node to confirm the memory spike precisely at the time of failure.

## Remediation Action
This requires two interventions: an immediate temporary fix and a permanent code architecture change.

**Quick Temporary Fix:**
Restart the job with a larger instance class.

**Permanent Code Fix (Requires CR):**
The pipeline script must physically be rewritten to use chunks rather than reading the entire CSV into memory at once.

```python
# Change needed in extraction script
import pandas as pd

# INSTEAD OF: df = pd.read_csv("massive_file.csv")
# USE CHUNKS:
chunk_size = 50000
for chunk in pd.read_csv("massive_file.csv", chunksize=chunk_size):
    process_chunk(chunk)
```

REQUIRED: Set `REQUIRES_INCIDENT: True` so engineering can implement chunking.
REASONING for AI Extraction: The task failed with an OutOfMemoryError because it tried to load an entire massive dataset into RAM at once. To fix this permanently, the Python pandas code must be refactored to use the `chunksize=50000` argument, which streams the file in smaller, memory-safe batches.
