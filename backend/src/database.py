import mariadb
import time

DB_CONFIG = {
    "user": "user",
    "password": "sapienza",
    "host": "mariadb", 
    "port": 3306,
    "database": "mio_database"
}

def get_db_connection():
    retries = 15
    while retries > 0:
        try:
            return mariadb.connect(**DB_CONFIG)
        except mariadb.Error as e:
            time.sleep(3)
            retries -= 1
    return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    try:
        cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS web_resources (url VARCHAR(500) PRIMARY KEY, domain VARCHAR(255), title VARCHAR(500), html_text LONGTEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS gold_standard (url VARCHAR(500) PRIMARY KEY, gold_text LONGTEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (url) REFERENCES web_resources(url) ON DELETE CASCADE)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS evaluations (url VARCHAR(500) PRIMARY KEY, f1_score FLOAT, judge_score INT, judge_feedback TEXT, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP, FOREIGN KEY (url) REFERENCES gold_standard(url) ON DELETE CASCADE)""")
        conn.commit()
    finally:
        conn.close()