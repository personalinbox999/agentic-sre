import oracledb
import os

print("Wiping Agent Oracle database...")
try:
    # Airflow history is still in Postgres, but our App history is in Oracle
    dsn = f"localhost:1521/FREEPDB1"
    conn = oracledb.connect(user="system", password=os.getenv("ORACLE_PASSWORD", "AdminPassword123"), dsn=dsn)
    cur = conn.cursor()
    
    # Wipe Agent
    try:
        cur.execute("TRUNCATE TABLE agent_state_kv")
        cur.execute("TRUNCATE TABLE agent_events")
        print("Agent tables wiped in Oracle.")
    except Exception as e:
        print(f"Warning wiping agent tables: {e}")
        
    try:
        cur.execute("TRUNCATE TABLE etl_runbooks")
        print("Vector embeddings wiped in Oracle.")
    except Exception as e:
        print(f"Warning wiping etl_runbooks table: {e}")
    
    conn.close()
    
    # Airflow is completely separate now, so we don't wipe it here
    print("Wipe operation complete!")
except Exception as e:
    print(f"Error wiping DB: {e}")
