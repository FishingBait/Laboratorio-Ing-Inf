import mariadb
import time

# Configurazione della connessione al database MariaDB, con parametri specifici per l'utente, password, host, porta e nome del database. 
# Questi parametri devono essere configurati correttamente per garantire la connessione al database e il funzionamento del backend.
DB_CONFIG = {
    "user": "user",
    "password": "sapienza",
    "host": "mariadb", 
    "port": 3306,
    "database": "mio_database"
}

# Funzione per ottenere una connessione al database, con un meccanismo di retry che tenta di connettersi più volte in caso di errori di connessione, 
# ad esempio se il database non è ancora pronto all'avvio del server, restituendo None se non riesce a stabilire una connessione dopo un numero definito di tentativi.
def get_db_connection():
    retries = 15
    while retries > 0:
        try:
            return mariadb.connect(**DB_CONFIG)
        except mariadb.Error as e:
            time.sleep(3)
            retries -= 1
    return None

# Funzione per inizializzare il database, creando le tabelle necessarie per memorizzare le risorse web, i gold standard e le valutazioni, 
# con gestione delle eccezioni e chiusura della connessione al database per garantire che il database sia pronto all'uso quando il server inizia ad accettare richieste.
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