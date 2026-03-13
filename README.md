# Agentic SRE Dashboard

An AI-powered SRE Dashboard for monitoring Airflow DAGs and automating incident remediation via ServiceNow.

## Features
- **Project Governance**: Automates incident creation and DAG management.
- **Hierarchical Story View**: Tracks the chronological "story" of a DAG failure from error to resolution.
- **AI Remediation**: Uses LLMs (Minimax-m2.5) to analyze logs and suggest/execute remediation steps.
- **Oracle 23ai Integration**: Native vector search for runbook retrieval.
- **ServiceNow Integration**: Automatic incident creation with deep-dive analysis.
- **Incident Storm Prevention**: Automatically pauses problematic DAGs to prevent alert fatigue.

## Tech Stack
- **Frontend**: React, Vite, TypeScript, Lucide-React.
- **Backend**: Python, LangGraph, Oracle 23ai (Native Vector Search).
- **Workflow**: Apache Airflow.
- **ITSM**: ServiceNow API.

## Setup
1. Clone the repository.
2. Initialize the backend:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Set and configure `.env` variables (refer to `.env.example` if available).
4. Start the system:
   ```bash
   ./start.sh
   ```

## Development
- Frontend source code is in `ui/`.
- Backend logic and AI graphs are in `src/`.
- Airflow DAGs reside in `airflow_dags/`.

---
*Built for the Agentic SRE Hackathon.*
