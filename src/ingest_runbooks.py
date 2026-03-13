from openai import OpenAI
import oracledb
import array
import os
from dotenv import load_dotenv
from confluence import get_page_by_title, get_folder_child_pages

load_dotenv()

# --- Configuration ---
# Oracle DB Config
DB_HOST = os.getenv("ORACLE_HOST", "localhost")
# Connect as the PDB admin (PDBADMIN or similar created via FREEPDB1 default env) or explicitly use the USERS tablespace. System tablespace does not support vectors well.
DB_USER = os.getenv("ORACLE_USER", "system")
DB_PASS = os.getenv("ORACLE_PASSWORD", "AdminPassword123")
DB_PORT = os.getenv("ORACLE_PORT", "1521")
DB_SERVICE = os.getenv("ORACLE_SERVICE", "FREEPDB1")
COLLECTION_NAME = "etl_runbooks"

# We use OpenRouter's Qwen model for Dense Embeddings
EMBEDDING_MODEL = "qwen/qwen3-embedding-8b"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY is missing from environment")

openai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

def get_oracle_connection():
    dsn = f"{DB_HOST}:{DB_PORT}/{DB_SERVICE}"
    return oracledb.connect(user=DB_USER, password=DB_PASS, dsn=dsn)

def recreate_collection():
    conn = get_oracle_connection()
    try:
        with conn.cursor() as cur:
            # Drop table if exists
            try:
                cur.execute(f"DROP TABLE {COLLECTION_NAME}")
                print(f"Dropped existing table '{COLLECTION_NAME}'.")
            except oracledb.DatabaseError as e:
                pass # Table might not exist, that's fine
                
            print(f"Creating table '{COLLECTION_NAME}'...")
            # Oracle SYSTEM tablespace doesn't support ASSM which vectors need. 
            # So we create the table forcing it onto the USERS tablespace if running as SYSTEM.
            cur.execute(f"""
                CREATE TABLE {COLLECTION_NAME} (
                    id VARCHAR2(36) PRIMARY KEY,
                    filename VARCHAR2(255),
                    content CLOB,
                    embedding VECTOR(4096, FLOAT32)
                ) TABLESPACE USERS
            """)
        conn.commit()
    finally:
        conn.close()

def generate_dense_embedding(text: str) -> list[float]:
    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )
    return response.data[0].embedding

def ingest_runbooks():
    recreate_collection()
    
    # We will use the explicit Workspace Folder ID provided by the user: 1769473
    folder_id = "1769473"
    print(f"Fetching children of Confluence folder ID: {folder_id}...")
    pages = get_folder_child_pages(folder_id, limit=100)
    
    if not pages:
        print(f"No runbooks found under folder {folder_id}.")
        return
        
    print(f"Found {len(pages)} runbooks. Processing...")
    
    points = []
    
    for page in pages:
        content = page["title"] + "\n\n" + page["body"]
        filename = page["title"] # Using title as filename equivalent
        
        print(f"Embedding {filename}...")
        
        # We process standard dense embeddings because FastEmbed segfaults on this Python 3.14 build
        dense_vec = generate_dense_embedding(content)
        
        # Oracle expects vectors as array objects
        vec_array = array.array("f", dense_vec)
        
        points.append({
            "id": page["id"], # Use Confluence ID as the primary key
            "content": content,
            "filename": filename,
            "embedding": vec_array
        })
        
    if points:
        print(f"Inserting {len(points)} documents to Oracle...")
        conn = get_oracle_connection()
        try:
            with conn.cursor() as cur:
                # Use executemany for fast batch inserts
                cur.setinputsizes(content=oracledb.DB_TYPE_CLOB)
                cur.executemany(f"""
                    INSERT INTO {COLLECTION_NAME} (id, filename, content, embedding)
                    VALUES (:id, :filename, :content, :embedding)
                """, points)
            conn.commit()
        finally:
            conn.close()
        print("Ingestion complete.")

if __name__ == "__main__":
    if os.path.basename(os.getcwd()) != "syf_agentic":
        print("WARNING: Please run from the syf_agentic root directory")
    ingest_runbooks()
