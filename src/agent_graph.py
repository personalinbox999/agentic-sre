import os
import json
import time
import logging
from typing import Any, TypedDict
import oracledb
import array

# Configure basic logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("agent")
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from dotenv import load_dotenv

load_dotenv()

from snow import create_incident
from db import patch_state

# --- Load Soul (System Prompt) from soul.md ---
SOUL_FILE = os.path.join(os.path.dirname(__file__), "..", "soul.md")

def load_soul() -> str:
    """Reads the system prompt from soul.md, stripping comment lines."""
    try:
        with open(SOUL_FILE, "r") as f:
            lines = f.readlines()
        # Strip lines starting with # (comments/headings used for human editing)
        content = "".join(
            line for line in lines if not line.strip().startswith("#")
        ).strip()
        return content
    except Exception as e:
        print(f"Warning: Could not load soul.md, using default prompt: {e}")
        return (
            "You are an SRE AI. Analyze the Airflow failure and respond ONLY in JSON: "
            "You are an SRE AI. Analyze the Airflow failure and respond ONLY in JSON: "
            '{"analysis": str, "confidence": float, "is_transient": bool, "requires_incident": bool, "remediation_action": str, "remediation_source": str, "remediation_reasoning": str}'
        )

# --- Types ---
class AgentState(TypedDict):
    # Input from main.py
    dag_id: str
    task_id: str
    task_try_number: int
    logs: str
    scenario: str

    # Intermediate
    retrieved_runbooks: str

    # Output from analyze node
    analysis_result: str
    confidence_score: float
    is_transient: bool
    requires_incident: bool
    remediation_action: str
    runbook_source: str
    remediation_reasoning: str

    # Output from incident node
    incident_number: str
    incident_link: str

    # Execution Trace
    execution_logs: list[str]

    # Legacy fields (unused but kept for graph compat)
    messages: list

# --- Configuration ---
# Oracle DB Config
DB_HOST = os.getenv("ORACLE_HOST", "localhost")
DB_USER = os.getenv("ORACLE_USER", "system")
DB_PASS = os.getenv("ORACLE_PASSWORD", "AdminPassword123")
DB_PORT = os.getenv("ORACLE_PORT", "1521")
DB_SERVICE = os.getenv("ORACLE_SERVICE", "FREEPDB1")
COLLECTION_NAME = "etl_runbooks"

EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY is missing from environment")

openai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# --- Helpers ---
def get_oracle_connection():
    dsn = f"{DB_HOST}:{DB_PORT}/{DB_SERVICE}"
    return oracledb.connect(user=DB_USER, password=DB_PASS, dsn=dsn)

def get_openrouter_embedding(text: str) -> list:
    embedding_response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        encoding_format="float"
    )
    return embedding_response.data[0].embedding

def get_llm():
    return ChatOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        model="minimax/minimax-m2.5",
    )

def update_ui_field(key: str, value: Any):
    """Modifies the live UI state JSON so the React dashboard updates."""
    try:
        patch_state({key: value})
    except Exception as e:
        print(f"Failed to update UI state: {e}")

import datetime

def add_log(state: AgentState, message: str):
    """Utility to log robustly and append to execution logs."""
    logger.info(message)
    if state.get("execution_logs") is None:
        state["execution_logs"] = []
    
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
    formatted_msg = f"{ts} [INFO] {message}"
    state["execution_logs"].append(formatted_msg)
    # Sync to UI state immediately for "live" feel
    update_ui_field("execution_logs", state["execution_logs"])

# --- Nodes ---
def retrieve_runbook(state: AgentState):
    add_log(state, f"Starting runbook retrieval for DAG: {state.get('dag_id')}")
    
    dag_id = state.get('dag_id', 'unknown')
    logs   = state.get('logs', '')
    query_text = f"DAG: {dag_id} STATUS: {state.get('scenario', 'UNKNOWN')} LOGS: {logs[:500]}"
    
    add_log(state, "Generating vector embedding for retrieval query...")
    t_start = time.time()
    try:
        dense_vec = get_openrouter_embedding(query_text)
        t_emb = time.time() - t_start
        add_log(state, f"Vector embedding generated in {t_emb:.2f}s (Dimensions: {len(dense_vec)})")
    except Exception as e:
        add_log(state, f"Failed to generate vector embedding from OpenRouter API: {e}")
        add_log(state, "Proceeding with Zero-Shot analysis (no runbook context available).")
        update_ui_field("runbookHit", False)
        return {"retrieved_runbooks": "", "execution_logs": state["execution_logs"]}

    add_log(state, "Searching Oracle 23ai native vector database for matching runbooks...")
    t_search = time.time()
    vec_array = array.array("f", dense_vec)
    
    docs = []
    scores = []
    
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cur:
            # Query Oracle using native VECTOR_DISTANCE, finding the closest matches
            cur.execute(f"""
                SELECT content, VECTOR_DISTANCE(embedding, :vec, COSINE) as sim_score 
                FROM {COLLECTION_NAME} 
                ORDER BY sim_score ASC 
                FETCH FIRST 2 ROWS ONLY
            """, vec=vec_array)
            
            for row in cur.fetchall():
                # Oracle LOB reading
                docs.append(row[0].read() if hasattr(row[0], 'read') else row[0])
                scores.append(f"{row[1]:.3f}")
    except oracledb.DatabaseError as e:
        add_log(state, f"Database error during vector search: {e}")
    finally:
        conn.close()
        
    t_match = time.time() - t_search

    combined_docs = "\n".join(docs)

    if docs:
        scores_str = ", ".join(scores)
        add_log(state, f"Found {len(docs)} relevant runbook(s) in {t_match:.2f}s. Cosine distances (lower is better): [{scores_str}]")
    else:
        add_log(state, "No relevant runbooks found in vector DB.")

    update_ui_field("runbookHit", len(docs) > 0)

    return {"retrieved_runbooks": combined_docs, "execution_logs": state["execution_logs"]}

def analyze_and_decide(state: AgentState):
    add_log(state, "Starting AI failure analysis via LLM (minimax-m2.5)...")

    # Load configurable system prompt from soul.md
    system_template = load_soul()

    prompt = PromptTemplate.from_template("""
        --- DAG INFO ---
        ID: {dag_id}
        Status: {status}

        --- LOGS ---
        {logs}

        --- RETRIEVED RUNBOOK CONTEXT ---
        {runbooks}
    """)

    formatted_prompt = prompt.format(
        dag_id=state.get('dag_id', 'unknown'),
        status=state.get('scenario', 'UNKNOWN'),
        logs=state.get('logs', 'No logs'),
        runbooks=state.get('retrieved_runbooks', 'No runbooks found')
    )

    add_log(state, f"Context assembled (~{len(formatted_prompt.split())} tokens). Sending request to OpenRouter API...")
    llm = get_llm()
    
    t_llm_start = time.time()
    
    endpoint = "https://openrouter.ai/api/v1"
    add_log(state, f"Context assembled (~{len(formatted_prompt.split())} tokens). Sending request to OpenRouter API (Endpoint: {endpoint})...")
    
    response = llm.invoke([
        SystemMessage(content=system_template),
        HumanMessage(content=formatted_prompt)
    ])
    t_llm = time.time() - t_llm_start

    add_log(state, f"Received API Response (HTTP 200 OK) in {t_llm:.2f}s. Payload size: {len(response.content)} bytes.")

    try:
        content = response.content
        
        # Super robust extraction for minimax which sometimes leaves text around json
        import re
        json_match = re.search(r'(\{.*\})', content.replace('\n', ''))
        if json_match:
            content = json_match.group(1)
        elif "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.replace("```", "").strip()

        add_log(state, f"Parsing JSON content from LLM...")
        
        # Safely try parsing
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            import ast
            result = ast.literal_eval(content) # Fallback to python literal eval 

        add_log(state, f"LLM analysis complete. Confidence: {result.get('confidence', 0.0)}")
        add_log(state, f"Requires Incident: {result.get('requires_incident', False)} | Is Transient: {result.get('is_transient', False)}")

        update_ui_field("confidence", result.get("confidence", 0.0))
        update_ui_field("needsIncident", result.get("requires_incident", False))
        update_ui_field("isTransient", result.get("is_transient", False))

        return {
            "analysis_result": result.get("analysis", "Error"),
            "confidence_score": result.get("confidence", 0.0),
            "is_transient": result.get("is_transient", False),
            "requires_incident": result.get("requires_incident", False),
            "remediation_action": result.get("remediation_action", "None"),
            "runbook_source": result.get("remediation_source", "AI-Generated"),
            "remediation_reasoning": result.get("remediation_reasoning", "No reasoning provided."),
            "execution_logs": state.get("execution_logs", [])
        }
    except Exception as e:
        add_log(state, f"CRITICAL: Failed to parse LLM Response: {e}")
        return {
            "analysis_result": f"Failed to parse LLM output. Raw: {response.content[-100:]}",
            "confidence_score": 0.0,
            "is_transient": False,
            "requires_incident": True,
            "remediation_action": "Manual intervention required.",
            "runbook_source": "Error",
            "remediation_reasoning": "Extraction failed.",
            "execution_logs": state["execution_logs"]
        }

import requests
from requests.auth import HTTPBasicAuth

def execute_remediation(state: AgentState):
    """Handles transient retries via Airflow or escalates to ServiceNow Incidents."""
    dag_id = state.get("dag_id")
    task_id = state.get("task_id", "see_logs") # The actual task ID is not explicitly passed yet, but we clear the whole DAG run for simplicity if transient.
    # In a real setup, we'd want the exact task_id. For now, Airflow clear DAG run is safe enough.
    
    if state.get("is_transient") and not state.get("requires_incident"):
        try_num = int(state.get("task_try_number") or 1)
        if try_num <= 1:
            add_log(state, f"Transient failure detected based on '{state.get('runbook_source')}'. Attempting automated Airflow rerun (Try {try_num})...")
            
            # Actually execute the Airflow REST API call to clear the task instances
            AIRFLOW_URL = os.getenv("AIRFLOW_URL", "http://localhost:8080")
            AIRFLOW_AUTH = HTTPBasicAuth(os.getenv("AIRFLOW_USER", "airflow"), os.getenv("AIRFLOW_PASS", "airflow"))
            
            try:
                # To retry a task effectively, we can clear the task instance state.
                payload = {
                    "dry_run": False,
                    "reset_dag_runs": True,
                    "only_failed": True,
                    "task_ids": [task_id]
                }
                clear_url = f"{AIRFLOW_URL}/api/v1/dags/{dag_id}/clearTaskInstances"
                add_log(state, f"Sending POST {clear_url} with {payload}")
                
                r = requests.post(clear_url, json=payload, auth=AIRFLOW_AUTH)
                if r.ok:
                    add_log(state, f"POST /api/v1/dags/{dag_id}/clearTaskInstances -> 200 OK")
                    add_log(state, "Airflow task cleared successfully. It will automatically retry on the next scheduler tick.")
                else:
                    add_log(state, f"Failed to clear Airflow task. HTTP {r.status_code}: {r.text}")
            except Exception as e:
                add_log(state, f"Error calling Airflow clear API: {e}")
            
            return {
                "incident_number": "N/A (Rerun)",
                "incident_link": "",
                "execution_logs": state["execution_logs"]
            }
        else:
            add_log(state, f"Transient runbook match, BUT task has already failed {try_num} times. Bypassing retry and escalating to Incident.")
            state["requires_incident"] = True # Force escalation

    if state.get("requires_incident"):
        sn_url = os.getenv("SERVICENOW_INSTANCE_URL", "https://dev281822.service-now.com")
        add_log(state, f"Persistent failure detected. Connecting to ServiceNow API (Endpoint: {sn_url})...")
        
        # Incident Storm Prevention: Pause the DAG in Airflow
        AIRFLOW_URL = os.getenv("AIRFLOW_URL", "http://localhost:8080")
        AIRFLOW_AUTH = HTTPBasicAuth(os.getenv("AIRFLOW_USER", "airflow"), os.getenv("AIRFLOW_PASS", "airflow"))
        dag_paused = False
        try:
            pause_url = f"{AIRFLOW_URL}/api/v1/dags/{dag_id}"
            add_log(state, f"Incident Storm Prevention: Pausing DAG {dag_id} to prevent alert storm...")
            r_pause = requests.patch(pause_url, json={"is_paused": True}, auth=AIRFLOW_AUTH)
            if r_pause.ok:
                add_log(state, f"Successfully paused DAG {dag_id}.")
                dag_paused = True
                state['remediation_action'] += "\n\n> **Note**: This DAG has been automatically paused by the SRE AI to prevent an incident storm."
            else:
                add_log(state, f"Failed to pause DAG {dag_id}. HTTP {r_pause.status_code}")
        except Exception as e:
            add_log(state, f"Error calling Airflow API to pause DAG: {e}")

        incident_resp = create_incident(
            analysis_summary=state['analysis_result'],
            remediation_plan=state['remediation_action'],
            confidence=state['confidence_score'],
            source=state['runbook_source'],
            reasoning=state['remediation_reasoning']
        )

        incident_result = incident_resp.get("result", {}) if incident_resp else {}
        inc_sys_id = incident_result.get("sys_id", "")
        inc_link = f"{sn_url.rstrip('/')}/nav_to.do?uri=incident.do?sys_id={inc_sys_id}" if inc_sys_id else "#"

        add_log(state, f"ServiceNow Incident created: {incident_result.get('number', 'SUCCESS')}")
        update_ui_field("incidentUrl", inc_link)

        return {
            "incident_number": incident_result.get("number", "Unknown"),
            "incident_link": inc_link,
            "dag_paused": dag_paused,
            "execution_logs": state["execution_logs"]
        }
    else:
        add_log(state, "Runbook policy: Local manual fix recommended. No Incident needed.")
        return {
            "incident_number": "N/A",
            "incident_link": "",
            "execution_logs": state["execution_logs"]
        }

# --- Graph Definition ---
workflow = StateGraph(AgentState)

workflow.add_node("retrieve", retrieve_runbook)
workflow.add_node("analyze", analyze_and_decide)
workflow.add_node("remediate", execute_remediation)

workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "analyze")
workflow.add_edge("analyze", "remediate")
workflow.add_edge("remediate", END)

agent_app = workflow.compile()
