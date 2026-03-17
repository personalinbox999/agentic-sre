"""
main.py — Agentic SRE Poller
Polls the Airflow REST API for real failed DAG runs, fetches their task logs,
and feeds them to the AI agent for analysis.
"""
import os
import time
import json
import datetime
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from agent_graph import agent_app as app
from api_server import start_control_server
from db import init_db, read_state, write_state, patch_state, append_event

load_dotenv()

# Airflow REST API
AIRFLOW_URL   = os.getenv("AIRFLOW_URL", "http://localhost:8080")
AIRFLOW_USER  = os.getenv("AIRFLOW_USER", "airflow")
AIRFLOW_PASS  = os.getenv("AIRFLOW_PASS", "airflow")
AIRFLOW_AUTH  = HTTPBasicAuth(AIRFLOW_USER, AIRFLOW_PASS)
AIRFLOW_HEADS = {"Content-Type": "application/json", "Accept": "application/json"}

# Poll interval when idle (seconds)
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

# ─────────────────────────────── UI state helpers ────────────────────────────

def ts():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# State operations mapped to PostgreSQL via db.py

# ─────────────────────────────── Airflow API ─────────────────────────────────

def get_all_dags() -> list[str]:
    """Returns list of dag_ids from all active DAGs."""
    try:
        r = requests.get(f"{AIRFLOW_URL}/api/v1/dags?only_active=true",
                         auth=AIRFLOW_AUTH, headers=AIRFLOW_HEADS, timeout=10)
        if r.ok:
            return [d["dag_id"] for d in r.json().get("dags", [])]
    except Exception as e:
        print(f"[Airflow] Error listing DAGs: {e}")
    return []

def get_failed_runs(dag_id: str, limit: int = 5) -> list[dict]:
    """Returns recent failed DAG runs for a given dag_id."""
    try:
        r = requests.get(
            f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns",
            auth=AIRFLOW_AUTH, headers=AIRFLOW_HEADS, timeout=10,
            params={"state": "failed", "limit": limit, "order_by": "-start_date"}
        )
        if r.ok:
            return r.json().get("dag_runs", [])
    except Exception as e:
        print(f"[Airflow] Error fetching runs for {dag_id}: {e}")
    return []

def get_task_logs(dag_id: str, dag_run_id: str) -> tuple[str, int, str]:
    """Fetches logs from the first failed task instance in a run, its try number, and the task_id."""
    try:
        # Get task instances
        r = requests.get(
            f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances",
            auth=AIRFLOW_AUTH, headers=AIRFLOW_HEADS, timeout=10
        )
        if not r.ok:
            return ""
        task_instances = r.json().get("task_instances", [])
        failed_tasks = [t for t in task_instances if t.get("state") == "failed"]
        if not failed_tasks:
            failed_tasks = task_instances  # fallback: grab all

        max_attempt = 1
        first_failed_task_id = "unknown_task"
        logs_combined = []
        for task in failed_tasks[:2]:   # cap at 2 tasks
            task_id = task["task_id"]
            if first_failed_task_id == "unknown_task":
                first_failed_task_id = task_id
            attempt = task.get("try_number", 1)
            max_attempt = max(max_attempt, attempt)
            log_r = requests.get(
                f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}/logs/{attempt}",
                auth=AIRFLOW_AUTH,
                headers={"Accept": "text/plain"},
                timeout=15
            )
            # Actually, `log_text` is often a string containing the Errno 3 message if Airflow webserver itself couldn't reach the worker.
            # If so, let's try reading the file directly from the mounted volume if nothing else works.
            content = log_r.text
            try:
                log_data = log_r.json()
                if "content" in log_data:
                    content = log_data["content"]
            except Exception:
                pass

            if isinstance(content, list):
                content = "\\n".join(content)

            # Strip out Airflow's giant HTTP wrapper if it's there but we got the Docker log instead
            if "*** Found logs served from host" in content:
                 # Standardize to only keep stuff after the hostname warning
                 parts = content.split(".log\\n", 1)
                 if len(parts) > 1:
                     content = parts[1]

            logs_combined.append(f"[task: {task_id}]\\n{content.strip()}")

        return "\\n...\\n".join(logs_combined)[:1500], max_attempt, first_failed_task_id

    except Exception as e:
        return f"Error fetching logs: {e}", 1, "error"

def airflow_is_up() -> bool:
    try:
        r = requests.get(f"{AIRFLOW_URL}/health", timeout=5)
        return r.ok
    except Exception:
        return False

# ─────────────────────────────── Analysis ────────────────────────────────────

def process_run(dag_id: str, run: dict, cycle: int):
    run_id       = run["dag_run_id"]
    run_state    = run.get("state", "failed")
    start_date   = run.get("start_date", "")[:19].replace("T", " ")

    print(f"\n{'='*52}")
    print(f"  CYCLE {cycle} | {dag_id} | run={run_id[:40]}")
    print(f"{'='*52}")

    # Fetch real task logs from Airflow
    patch_state({
        "status": "analyzing", "cycle": cycle,
        "execution_logs": ["Starting analysis cycle...", f"Connected to Airflow for DAG {dag_id}"],
        "current": {
            "dag_id": dag_id, "run_id": run_id,
            "state": run_state, "start": start_date,
            "logs": "Fetching logs from Airflow…"
        }
    })

    logs, try_num, failed_task_id = get_task_logs(dag_id, run_id)
    logs_snippet = logs[:400]
    print(f"[Logs] {logs_snippet[:80]}…")

    patch_state({"current": {"dag_id": dag_id, "run_id": run_id,
                              "state": run_state, "start": start_date,
                              "logs": logs_snippet}})

    initial_state = {
        "messages": [],
        "dag_id": dag_id,
        "task_id": failed_task_id,
        "task_try_number": try_num,
        "logs": logs,
        "scenario": run_state,
        "analysis_result": "",
        "confidence_score": 0.0,
        "is_transient": False,
        "requires_incident": False,
        "remediation_action": "",
        "incident_number": "",
        "incident_link": "",
        "runbook_source": "",
        "remediation_reasoning": "",
        "execution_logs": ["Logs fetched. Starting RAG retrieval..."],
    }

    final_analyze = {}
    final_remediate = {}

    for step in app.stream(initial_state, config={}):
        print(step)
        if "analyze" in step:
            final_analyze = step["analyze"]
        if "remediate" in step:
            final_remediate = step["remediate"]
        
        # Stream live logs to UI
        all_logs = []
        if "analyze" in step and "execution_logs" in step["analyze"]:
            all_logs = step["analyze"]["execution_logs"]
        elif "remediate" in step and "execution_logs" in step["remediate"]:
            all_logs = step["remediate"]["execution_logs"]
        elif "retrieve" in step and "execution_logs" in step["retrieve"]:
            all_logs = step["retrieve"]["execution_logs"]
            
        if all_logs:
            patch_state({"execution_logs": all_logs})

    event = {
        "timestamp":          ts(),
        "cycle":              cycle,
        "dag_id":             dag_id,
        "task_id":            failed_task_id,
        "run_id":             run_id,
        "state":              run_state,
        "logs_snippet":       logs_snippet,
        "analysis":           final_analyze.get("analysis_result", ""),
        "confidence":         final_analyze.get("confidence_score", 0.0),
        "is_transient":       final_analyze.get("is_transient", False),
        "requires_incident":  final_analyze.get("requires_incident", False),
        "remediation_action": final_analyze.get("remediation_action", ""),
        "runbook_hit":        bool(final_analyze.get("runbook_source", "") and final_analyze.get("runbook_source") != "AI-Generated"),
        "remediation_source": final_analyze.get("runbook_source", ""),
        "remediation_reasoning": final_analyze.get("remediation_reasoning", ""),
        "incident_number":    final_remediate.get("incident_number", ""),
        "incident_link":      final_remediate.get("incident_link", ""),
        "dag_paused":         final_remediate.get("dag_paused", False),
        "execution_logs":     final_remediate.get("execution_logs", final_analyze.get("execution_logs", [])),
    }

    append_event(event)
    patch_state({
        "status":        "finished",
        "confidence":    event["confidence"],
        "needsIncident": event["requires_incident"],
        "isTransient":   event["is_transient"],
        "runbook_hit":   event["runbook_hit"],
    })

    return event

# ─────────────────────────────── Main loop ───────────────────────────────────

def start_poller():
    print("=" * 52)
    print("   AGENTIC AI POLLER — REAL AIRFLOW MODE")
    print("   soul.md loaded as system prompt")
    print("=" * 52)

    init_db()
    start_control_server(port=8766)

    # Init UI state
    existing = read_state()
    write_state({
        "status":       "watching",
        "cycle":        existing.get("cycle", 0),
        "last_updated": ts(),
        "current":      existing.get("current", {}),
        "events":       existing.get("events", []),
        "confidence":   0,
        "needsIncident": False,
        "isTransient":  False,
        "runbook_hit":  False,
        "execution_logs": [],
        "next_event_in": POLL_INTERVAL,
    })

    cycle = int(existing.get("cycle", 0))
    # Track which runs we've already processed so we don't repeat
    seen_runs: set[str] = set(existing.get("seen_runs", []))

    print(f"[Poller] Polling Airflow at {AIRFLOW_URL} every {POLL_INTERVAL}s")

    while True:
        if not airflow_is_up():
            print("[Poller] Airflow not reachable — waiting 30s…")
            patch_state({"status": "watching", "next_event_in": 30})
            time.sleep(30)
            continue

        patch_state({"status": "polling", "next_event_in": 0})
        dag_ids = get_all_dags()
        if not dag_ids:
            print("[Poller] No active DAGs found.")

        found_new = False
        for dag_id in dag_ids:
            failed_runs = get_failed_runs(dag_id, limit=3)
            for run in failed_runs:
                run_id = run["dag_run_id"]
                if run_id in seen_runs:
                    continue
                seen_runs.add(run_id)
                patch_state({"seen_runs": list(seen_runs)})
                found_new = True
                cycle += 1
                try:
                    process_run(dag_id, run, cycle)
                except Exception as e:
                    print(f"CRITICAL ERROR processing {run_id}: {e}")

        # Check for successes on previously seen failed runs
        resolved_runs = []
        for run_id in list(seen_runs):
            # Try to figure out dag_id by guessing from run_id or existing state
            # A cleaner way is to just look up the latest event for this run_id
            curr_state = read_state()
            run_events = [e for e in curr_state.get("events", []) if e.get("run_id") == run_id]
            if not run_events:
                continue
            
            latest_event = run_events[0]
            if latest_event.get("state") == "success" or latest_event.get("dag_paused") is True:
                continue # Already marked terminal
                
            dag_id = latest_event.get("dag_id")
            
            try:
                r = requests.get(
                    f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/dagRuns/{run_id}",
                    auth=AIRFLOW_AUTH, headers=AIRFLOW_HEADS, timeout=10
                )
                if r.ok:
                    run_data = r.json()
                    if run_data.get("state") == "success":
                        print(f"[Poller] Run {run_id} has SUCCEEDED after AI retry!")
                        cycle += 1
                        success_event = {
                            "timestamp":          ts(),
                            "cycle":              cycle,
                            "dag_id":             dag_id,
                            "task_id":            latest_event.get("task_id", "-"),
                            "run_id":             run_id,
                            "state":              "success",
                            "logs_snippet":       "All tasks completed successfully.",
                            "analysis":           "DAG Run Recovered.",
                            "confidence":         1.0,
                            "is_transient":       True,
                            "requires_incident":  False,
                            "remediation_action": "Validation Successful: The Airflow DAG Run completed successfully after AI-triggered retry.",
                            "runbook_hit":        False,
                            "remediation_source": "Airflow Verification",
                            "remediation_reasoning": "The DAG run state changed to 'success'.",
                            "incident_number":    "",
                            "incident_link":      "",
                            "dag_paused":         False,
                            "execution_logs":     ["Validation Successful: Run state is now 'success'."]
                        }
                        append_event(success_event)
                        found_new = True
            except Exception as e:
                pass

        if not found_new:
            print(f"[Poller] No new failures. Sleeping {POLL_INTERVAL}s…")

        patch_state({"status": "watching", "next_event_in": POLL_INTERVAL})
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    start_poller()
