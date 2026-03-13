import oracledb
import os
from dotenv import load_dotenv

load_dotenv()

def clear_database():
    print("Connecting to Oracle to clear agent state...")
    try:
        dsn = f"{os.getenv('ORACLE_HOST', 'localhost')}:{os.getenv('ORACLE_PORT', '1521')}/{os.getenv('ORACLE_SERVICE', 'FREEPDB1')}"
        conn = oracledb.connect(
            user=os.getenv("ORACLE_USER", "system"),
            password=os.getenv("ORACLE_PASSWORD", "AdminPassword123"),
            dsn=dsn
        )
        cur = conn.cursor()
        
        print("Truncating tables agent_state_kv and agent_events...")
        try:
            cur.execute("TRUNCATE TABLE agent_state_kv")
            cur.execute("TRUNCATE TABLE agent_events")
        except oracledb.DatabaseError as e:
            print(f"Tables might not exist yet: {e}")
        
        cur.close()
        conn.close()
        print("Database cleared successfully. The UI will now start fresh!")
    except Exception as e:
        print(f"Error clearing database: {e}")

if __name__ == "__main__":
    clear_database()
