#!/bin/bash
set -e

echo "========================================================"
echo "    STARTING SYNCHRONY BANK AGENTIC AI INFRASTRUCTURE   "
echo "========================================================"

echo "[1/6] Stopping any dangling containers..."
docker compose down

echo "[2/6] Building and spinning up core infrastructure..."
echo "      (PostgreSQL, Qdrant Vector DB, Airflow, React UI)"
docker compose up -d --build

echo "[3/6] Setting up Python Virtual Environment..."

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "      Virtual environment created."
fi
source .venv/bin/activate
pip install -r requirements.txt --quiet
echo "      Python dependencies installed."

echo "[4/6] Waiting for Qdrant Vector DB to become ready (5s)..."
sleep 5

echo "========================================================"
echo " INFRASTRUCTURE READY! "
echo " "
echo " -------------------------------------------------------------------"
echo " 🌐  Control Dashboard           -> http://localhost:5173"
echo " 🏗  Airflow UI (SRE Jobs)       -> http://localhost:8080"
echo " 🔎  Qdrant Search Dashboard    -> http://localhost:6333/dashboard"
echo " "
echo "========================================================"
echo "[6/6] Launching the simulated Airflow Webhook Poller..."
echo "      (This will begin the simulation and trigger the agent)"
echo ""
sleep 2

python3 src/main.py
