import os
import pymysql

env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
env = {}
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()

conn = pymysql.connect(
    host=env.get("DB_HOST", "127.0.0.1"),
    port=int(env.get("DB_PORT", 3307)),
    user=env.get("DB_USER", "logpulse_user"),
    password=env.get("DB_PASSWORD", "logpulse_password"),
    database=env.get("DB_NAME", "logpulse"),
    cursorclass=pymysql.cursors.DictCursor
)
with conn.cursor() as cur:
    print("=== SELECT COUNT(*) FROM events ===")
    cur.execute("SELECT COUNT(*) AS total_count FROM events;")
    print(cur.fetchall())

    print("\n=== SHOW CREATE TABLE events ===")
    cur.execute("SHOW CREATE TABLE events;")
    res = cur.fetchone()
    print(res["Create Table"])

    print("\n=== information_schema.PARTITIONS ===")
    cur.execute("""
        SELECT PARTITION_NAME, TABLE_ROWS, PARTITION_DESCRIPTION, PARTITION_METHOD
        FROM information_schema.PARTITIONS
        WHERE TABLE_NAME = 'events' AND TABLE_SCHEMA = 'logpulse'
        ORDER BY PARTITION_ORDINAL_POSITION;
    """)
    for row in cur.fetchall():
        p_name = row['PARTITION_NAME']
        rows = row['TABLE_ROWS']
        desc = row['PARTITION_DESCRIPTION']
        print(f"{p_name:<15} | rows: {str(rows):<8} | values less than: {desc}")
conn.close()
