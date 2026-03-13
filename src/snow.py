import os
import requests

def create_incident(analysis_summary: str, remediation_plan: str, confidence: float, source: str, reasoning: str):
    """
    Calls the ServiceNow Personal Developer Instance API to generate an Incident.
    """
    sn_url = os.getenv("SERVICENOW_INSTANCE_URL")
    user = os.getenv("SERVICENOW_USERNAME")
    password = os.getenv("SERVICENOW_PASSWORD")

    if not all([sn_url, user, password]):
        print("WARNING: ServiceNow credentials missing. Simulating Incident creation locally.")
        print(f"--- SIMULATED INCIDENT ---\nAnalysis: {analysis_summary}\nSource: {source}\nReasoning: {reasoning}\nPlan: {remediation_plan}\nConfidence: {confidence}\n--------------------")
        return {"result": {"number": "INC000DEFAULT", "sys_id": "dummy-sys-id"}}

    # The standard ServiceNow Table API endpoint for Incidents
    endpoint = f"{sn_url.rstrip('/')}/api/now/table/incident"

    try:
        conf_val = float(confidence)
    except (ValueError, TypeError):
        conf_val = 0.0

    payload = {
        "short_description": f"AI Automated Incident (Confidence: {conf_val:.2f})",
        "description": f"Analysis:\n{analysis_summary}\n\nRemediation Source ({source}):\n{reasoning}\n\nProposed Remediation:\n{remediation_plan}",
        "category": "software",
        "impact": "2",
        "urgency": "2"
    }

    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    print(f"Sending Incident Request to {endpoint}...")
    try:
        response = requests.post(endpoint, auth=(user, password), headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"Successfully created ServiceNow Incident: {data.get('result', {}).get('number')}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"Failed to create Incident in ServiceNow: {e}")
        return None
