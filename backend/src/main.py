from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes import router
from database import init_db, get_db_connection
from utils import load_domains, get_domain_gs_from_json

# Inizializzazione del backend con sincronizzazione del database all'avvio, caricamento dei dati dai file JSON e setup delle rotte definite in routes.py. Utilizziamo un lifespan asincrono per eseguire operazioni di setup prima che il server inizi ad accettare richieste, 
# garantendo che il database sia popolato con i dati necessari per le operazioni di parsing e valutazione.
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Sincronizzazione DB in corso...")
    init_db()
    conn = get_db_connection()
    if conn:
        try:
            # Carichiamo i dati dai file JSON e li inseriamo nel database, assicurandoci di evitare duplicati con INSERT IGNORE e di gestire eventuali 
            # errori di parsing o formattazione dei dati, per garantire che il nostro database sia sempre aggiornato con le ultime risorse web e gold standard disponibili per la valutazione del parser.
            cur = conn.cursor()
            for d in load_domains():
                clean_d = d[4:] if d.startswith("www.") else d
                for item in get_domain_gs_from_json(d):
                    cur.execute("INSERT IGNORE INTO web_resources (url, domain, title, html_text) VALUES (?, ?, ?, ?)",
                                (item['url'], clean_d, item.get('title', ''), item.get('html_text', '')))
                    if 'gold_text' in item:
                        cur.execute("INSERT IGNORE INTO gold_standard (url, gold_text) VALUES (?, ?)", (item['url'], item['gold_text']))
            conn.commit()
            print("Database sincronizzato correttamente!")
        finally:
            conn.close()
    yield

# Creazione dell'istanza FastAPI con il lifespan definito per eseguire operazioni di setup all'avvio del server, come la sincronizzazione del database e il 
# caricamento dei dati dai file JSON, garantendo che tutte le rotte definite in routes.py abbiano accesso ai dati necessari per funzionare correttamente.
app = FastAPI(lifespan=lifespan)

# Colleghiamo tutte le rotte dal file routes.py
app.include_router(router)