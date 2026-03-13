"""
api_server.py — Lightweight control HTTP server for the UI to call.
Runs on port 8765 in a daemon thread alongside main.py.

Endpoints:
  POST /api/ingest   — Re-ingest runbooks from Confluence + local files into Qdrant
  GET  /api/status   — Returns current ingest status
"""

import os
import sys
import json
import threading
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from db import read_state, get_recent_events
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Shared state for ingest status
_status = {"running": False, "last_run": None, "last_result": None}
_lock = threading.Lock()

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
PYTHON = sys.executable


import datetime

INGEST_LOG_PATH = "/tmp/ingest_trace.log"

def _run_ingestion():
    """Executes ingest_runbooks.py and writes output to a file for the UI to poll."""
    global _status
    with _lock:
        _status["running"] = True
        _status["last_result"] = None
    
    # Clear previous logs
    with open(INGEST_LOG_PATH, "w") as f:
        f.write(f"--- Ingestion started at {datetime.datetime.now()} ---\n")

    try:
        script = os.path.join(PROJECT_ROOT, "src", "ingest_runbooks.py")
        # We run with unbuffered output or manual piping
        process = subprocess.Popen(
            [PYTHON, "-u", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=PROJECT_ROOT,
            text=True
        )
        
        for line in process.stdout:
            with open(INGEST_LOG_PATH, "a") as f:
                f.write(line)
        
        process.wait()
        success = process.returncode == 0
        
        with _lock:
            _status["last_run"] = datetime.datetime.now().strftime("%H:%M:%S")
            _status["last_result"] = "success" if success else "error"
    except Exception as e:
        with open(INGEST_LOG_PATH, "a") as f:
            f.write(f"\n[ERROR] {e}\n")
        with _lock:
            _status["last_result"] = f"error: {e}"
    finally:
        with _lock:
            _status["running"] = False


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/api/status"):
            body = json.dumps(_status).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path.startswith("/api/state"):
            content = read_state()
            body = json.dumps(content).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # Client closed the connection before we could finish writing, ignore.
                pass
        elif self.path.startswith("/api/logs"):
            content = ""
            if os.path.exists(INGEST_LOG_PATH):
                with open(INGEST_LOG_PATH, "r") as f:
                    content = f.read()
            body = json.dumps({"logs": content}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        if self.path == "/api/ingest":
            with _lock:
                already_running = _status["running"]

            if already_running:
                body = json.dumps({"ok": False, "message": "Ingestion already running"}).encode()
                self.send_response(409)
            else:
                t = threading.Thread(target=_run_ingestion, daemon=True)
                t.start()
                body = json.dumps({"ok": True, "message": "Ingestion started"}).encode()
                self.send_response(202)

            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path == "/api/chat":
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            
            try:
                data = json.loads(post_data.decode('utf-8'))
                user_msg = data.get("message", "")
                
                # Fetch recent DB events for context (limit to 10 for better history)
                recent_events = get_recent_events(limit=10)
                
                # Trim the size of the injected context so Minimax doesn't choke on 50k tokens
                trimmed_events = []
                for e in recent_events:
                    safe_e = {
                        "dag_id": e.get("dag_id"),
                        "status": e.get("scenario"),
                        "analysis": e.get("analysis_result"),
                        "remediation": e.get("remediation_action"),
                        "source": e.get("runbook_source"),
                        "incident": e.get("incident_number")
                    }
                    trimmed_events.append(safe_e)
                
                context_str = json.dumps(trimmed_events, indent=2)
                
                # Use ChatOpenAI
                llm = ChatOpenAI(
                    api_key=os.getenv("OPENROUTER_API_KEY"),
                    base_url="https://openrouter.ai/api/v1",
                    model="minimax/minimax-m2.5",
                )
                
                sys_prompt = (
                    "You are the Synchrony SRE Assistant. Respond in a professional, technical, and helpful manner.\n\n"
                    "FORMATTING RULES:\n"
                    "1. ALWAYS use Markdown tables when listing multiple incidents, jobs, or metrics. This is mandatory for readability.\n"
                    "2. Use bold text for technical terms (e.g. **OOM**, **DAG**, **Runbook**).\n"
                    "3. If a task was successful after retry, mention it clearly.\n"
                    "4. Be concise but ensure all technical details from the context are preserved.\n\n"
                    f"RECENT EVENTS CONTEXT (Airflow/ServiceNow JSON log):\n{context_str}"
                )
                
                response = llm.invoke([
                    SystemMessage(content=sys_prompt),
                    HumanMessage(content=user_msg)
                ])
                
                body = json.dumps({"response": response.content}).encode()
                self.send_response(200)
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
                self.send_response(500)
                
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            
        else:
            self.send_response(404)
            self._cors()
            self.end_headers()
            self.wfile.write(b"404 Not Found")


def start_control_server(port: int = 8766):
    server = HTTPServer(("0.0.0.0", port), ControlHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[Control API] Listening on http://localhost:{port}")
    return server
