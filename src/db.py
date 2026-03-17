import os
import datetime
import oracledb
import json

DB_HOST = os.getenv("ORACLE_HOST", "localhost")
DB_USER = os.getenv("ORACLE_USER", "system")
DB_PASS = os.getenv("ORACLE_PASSWORD", "AdminPassword123")
DB_PORT = os.getenv("ORACLE_PORT", "1521")
DB_SERVICE = os.getenv("ORACLE_SERVICE", "FREEPDB1")

def get_connection():
    # Make sure Oracle responses map natively to dicts if preferred, but standard tuples work fine too
    dsn = f"{DB_HOST}:{DB_PORT}/{DB_SERVICE}"
    return oracledb.connect(
        user=DB_USER,
        password=DB_PASS,
        dsn=dsn
    )

def init_db():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Oracle 23ai JSON column syntax
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_state_kv (
                    key VARCHAR2(100) PRIMARY KEY,
                    value JSON
                ) TABLESPACE USERS
            """)
            # Oracle 23ai Identity syntax
            cur.execute("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    event_data JSON
                ) TABLESPACE USERS
            """)
        conn.commit()
    except Exception as e:
        print(f"[DB API] Failed to initialize DB: {e}")
    finally:
        conn.close()

def read_state() -> dict:
    state = {}
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Need to use Oracle lob/json conversions explicitly if string is expected
                cur.execute("SELECT key, json_serialize(value RETURNING CLOB) FROM agent_state_kv")
                for row in cur.fetchall():
                    val = row[1].read() if hasattr(row[1], 'read') else row[1]
                    state[row[0]] = json.loads(val) if isinstance(val, str) else val
                
                cur.execute("SELECT json_serialize(event_data RETURNING CLOB) FROM agent_events ORDER BY id DESC")
                events = []
                for row in cur.fetchall():
                    val = row[0].read() if hasattr(row[0], 'read') else row[0]
                    events.append(json.loads(val) if isinstance(val, str) else val)
                state["events"] = events
                
                # Dynamically fetch the list of runbook embeddings
                try:
                    cur.execute("SELECT filename FROM etl_runbooks")
                    # Fetchall returns a list of tuples, e.g. [('file1.pdf',), ('file2.pdf',)]
                    filenames = [row[0] for row in cur.fetchall()]
                    # Deduplicate in case multiple chunks of the same file exist
                    unique_filenames = list(set(filenames))
                    state["indexed_runbooks_list"] = unique_filenames
                    state["indexed_runbooks"] = len(unique_filenames)
                except oracledb.DatabaseError as e:
                    if 'ORA-00942' in str(e):
                        state["indexed_runbooks_list"] = []
                        state["indexed_runbooks"] = 0 # Table not created yet
                    else:
                        raise e
        finally:
            conn.close()
    except Exception as e:
        print(f"[DB API] Error reading state: {e}")
    return state

def write_state(state: dict):
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for k, v in state.items():
                    if k == "events":
                        continue
                    # Oracle Merge (Upsert) syntax instead of ON CONFLICT
                    cur.execute("""
                        MERGE INTO agent_state_kv dst
                        USING (SELECT :key as key, :val as value FROM dual) src
                        ON (dst.key = src.key)
                        WHEN MATCHED THEN
                            UPDATE SET dst.value = src.value
                        WHEN NOT MATCHED THEN
                            INSERT (key, value) VALUES (src.key, src.value)
                    """, key=k, val=json.dumps(v))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[DB API] Error writing state: {e}")

def patch_state(patch: dict):
    state = read_state()
    state.update(patch)
    state["last_updated"] = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    write_state(state)

def append_event(event: dict):
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Using bind variables
                cur.execute("INSERT INTO agent_events (event_data) VALUES (:val)", val=json.dumps(event))
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"[DB API] Error appending event: {e}")
    
    write_state({"last_updated": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})

def get_recent_events(limit: int = 15) -> list[dict]:
    """Retrieves the most recent events for Chat Context."""
    events = []
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # Using Oracle FETCH FIRST instead of Postgres LIMIT
                cur.execute("SELECT json_serialize(event_data RETURNING CLOB) FROM agent_events ORDER BY id DESC FETCH FIRST :lim ROWS ONLY", lim=limit)
                for row in cur.fetchall():
                    val = row[0].read() if hasattr(row[0], 'read') else row[0]
                    events.append(json.loads(val) if isinstance(val, str) else val)
        finally:
            conn.close()
    except Exception as e:
        print(f"[DB API] Error fetching recent events: {e}")
    return events
