from contextlib import asynccontextmanager
from fastapi import FastAPI
from routes import router
from database import init_db, get_db_connection
from utils import load_domains, get_domain_gs_from_json

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Sincronizzazione Minerva DB in corso...")
    init_db()
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            for d in load_domains():
                clean_d = d[4:] if d.startswith("www.") else d
                for item in get_domain_gs_from_json(d):
                    cur.execute("INSERT IGNORE INTO web_resources (url, domain, title, html_text) VALUES (?, ?, ?, ?)",
                                (item['url'], clean_d, item.get('title', ''), item.get('html_text', '')))
                    if 'gold_text' in item:
                        cur.execute("INSERT IGNORE INTO gold_standard (url, gold_text) VALUES (?, ?)", (item['url'], item['gold_text']))
            conn.commit()
            print("✅ Database sincronizzato correttamente.")
        finally:
            conn.close()
    yield

app = FastAPI(lifespan=lifespan)

# Colleghiamo tutte le rotte dal file routes.py
app.include_router(router)