import subprocess
import os
import oracledb
from dotenv import load_dotenv

load_dotenv()

def run_cmd(cmd):
    print(f"Executing: {cmd}")
    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Command failed: {e}")

def reset_oracle():
    print("\n--- Phase 1: Resetting Oracle 23ai State ---")
    try:
        dsn = f"{os.getenv('ORACLE_HOST', 'localhost')}:{os.getenv('ORACLE_PORT', '1521')}/{os.getenv('ORACLE_SERVICE', 'FREEPDB1')}"
        conn = oracledb.connect(
            user=os.getenv("ORACLE_USER", "system"),
            password=os.getenv("ORACLE_PASSWORD", "AdminPassword123"),
            dsn=dsn
        )
        cur = conn.cursor()
        
        tables = ["agent_state_kv", "agent_events", "etl_runbooks"]
        for table in tables:
            print(f"Truncating {table}...")
            try:
                cur.execute(f"TRUNCATE TABLE {table}")
            except Exception as e:
                print(f"  Note: {table} might not exist yet: {e}")
        
        conn.commit()
        cur.close()
        conn.close()
        print("Oracle DB state wiped successfully.")
    except Exception as e:
        print(f"Error resetting Oracle: {e}")

def reset_airflow():
    print("\n--- Phase 2: Resetting Airflow Database ---")
    # Stop scheduler to avoid locks
    run_cmd("docker compose stop airflow-scheduler")
    
    # Force DB reset
    run_cmd("docker compose exec airflow-webserver airflow db reset -y")
    
    # Re-create admin user
    run_cmd("docker compose exec airflow-webserver airflow users create -u airflow -p airflow -f Air -l Flow -r Admin -e admin@example.com")
    
    # Restart scheduler
    run_cmd("docker compose start airflow-scheduler")
    print("Airflow reset successfully.")

if __name__ == "__main__":
    print("========================================")
    print("      SRE DASHBOARD MASTER RESET")
    print("========================================")
    
    reset_oracle()
    reset_airflow()
    
    print("\n========================================")
    print("   RESET COMPLETE - SYSTEM READY")
    print("========================================")
