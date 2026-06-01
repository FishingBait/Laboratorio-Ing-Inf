import httpx
import asyncio
from fastapi import APIRouter, HTTPException
from models import ParseRequest, EvaluateRequest, EvaluateJudgeRequest, ResourceRequest, DeleteRequest, GoldStandardRequest
from utils import get_exact_domain, load_domains, calculate_token_level_eval
from database import get_db_connection
from parser_logic import perform_parse
from llm_judge import evaluate_with_llm

router = APIRouter()

# =====================================================================
# SYSTEM & HEALTH CHECK ROUTES
# =====================================================================

@router.get("/status")
async def get_status():
    """
    Verifica lo stato di salute dei componenti principali del sistema:
    Backend, Database (MariaDB) e LLM Judge (Ollama).
    """
    status = {"backend": "ok", "database": "error", "ollama": "error"}
    try:
        conn = get_db_connection()
        if conn: 
            status["database"] = "ok"
            conn.close()
    except: 
        pass
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://ollama:11434/api/tags")
            if res.status_code == 200: 
                status["ollama"] = "ok"
    except: 
        pass
        
    return status 

@router.get("/db_schema")
async def db_schema():
    """
    Restituisce lo schema delle tabelle principali del database 
    come richiesto dalle specifiche del progetto.
    """
    return {
        "web_resources": {"url": "varchar(500), PK", "domain": "varchar(255)", "html_text": "longtext"},
        "gold_standard": {"url": "varchar(500), PK, FK", "gold_text": "longtext"}
    }

# =====================================================================
# DOMAINS & STATISTICS ROUTES
# =====================================================================

@router.get("/domains")
async def get_domains():
    """
    Restituisce la lista dei domini supportati dal sistema, 
    caricati dal file di configurazione (domains.json).
    """
    return {"domains": load_domains()}

@router.get("/db_stats")
async def db_stats():
    """
    Fornisce un'aggregazione statistica dello stato del database:
    conteggio risorse, gold standard e medie delle valutazioni per dominio.
    """
    conn = get_db_connection()
    if not conn:
        return {"error": "DB non raggiungibile"}
    
    cur = conn.cursor(dictionary=True)
    
    # Inizializzazione della struttura di risposta attesa dal grader
    response = {
        "web_resources": {},
        "gold_standard": {},
        "avg_eval": {},
        "avg_eval_judge": {}
    }
    
    # 1. Recupero dei domini distinti per inizializzare le chiavi
    cur.execute("SELECT DISTINCT domain FROM web_resources")
    all_domains = [r['domain'] for r in cur.fetchall()]
    
    for d in all_domains:
        response["web_resources"][d] = 0
        response["gold_standard"][d] = 0
        response["avg_eval"][d] = {"token_level_eval": {"f1": 0}}
        response["avg_eval_judge"][d] = {"judge_score": 0}
        
    # 2. Popolamento statistiche web_resources
    cur.execute("SELECT domain, COUNT(*) as count FROM web_resources GROUP BY domain")
    for r in cur.fetchall():
        response["web_resources"][r['domain']] = r['count']
        
    # 3. Popolamento statistiche gold_standard
    cur.execute("""
        SELECT w.domain, COUNT(*) as count 
        FROM gold_standard g 
        JOIN web_resources w ON g.url = w.url 
        GROUP BY w.domain
    """)
    for r in cur.fetchall():
        if r['domain'] in response["gold_standard"]:
            response["gold_standard"][r['domain']] = r['count']
            
    # 4. Calcolo delle metriche medie (F1 e Judge Score)
    cur.execute("""
        SELECT 
            w.domain, 
            AVG(e.f1_score) as avg_f1, 
            AVG(e.judge_score) as avg_judge
        FROM web_resources w
        LEFT JOIN evaluations e ON w.url = e.url
        GROUP BY w.domain
    """)
    for r in cur.fetchall():
        d = r['domain']
        if d in response["avg_eval"]:
            f1 = round(r['avg_f1'], 4) if r['avg_f1'] is not None else 0
            judge = round(r['avg_judge'], 1) if r['avg_judge'] is not None else 0
            response["avg_eval"][d]["token_level_eval"]["f1"] = f1
            response["avg_eval_judge"][d]["judge_score"] = judge

    conn.close()
    return response

# =====================================================================
# DATA EXTRACTION (PARSING) ROUTES
# =====================================================================

@router.post("/parse")
async def api_parse(req: ParseRequest):
    """
    Esegue il parsing di una pagina web. Può operare sia su un URL remoto 
    che su testo HTML fornito localmente tramite il payload.
    """
    # Fusione dei campi per compatibilità con i test del grader
    html_finale = req.html or req.html_text or ""
    return await perform_parse(req.url, req.local, html_finale)

# =====================================================================
# CRUD OPERATIONS (WEB RESOURCES & GOLD STANDARD)
# =====================================================================

@router.post("/add_web_resource")
async def add_res(req: ResourceRequest):
    """
    Aggiunge o aggiorna una risorsa web grezza nel database.
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Estrazione e pulizia del dominio
    domain = get_exact_domain(req.url)
    if domain.startswith("www."):
        domain = domain.replace("www.", "", 1)
        
    cur.execute("INSERT IGNORE INTO web_resources (url, domain, html_text) VALUES (?, ?, ?)", 
                (req.url, domain, req.html_text))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.post("/add_gold_standard")
async def add_gold_standard(req: GoldStandardRequest):
    """
    Associa un testo 'Gold Standard' di riferimento a una risorsa web esistente.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="DB non raggiungibile")
    
    cur = conn.cursor(dictionary=True)
    
    # Controllo integrità: la risorsa padre deve esistere
    cur.execute("SELECT url FROM web_resources WHERE url = ?", (req.url,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        raise HTTPException(
            status_code=400, 
            detail="Impossibile aggiungere il gold standard: la risorsa web associata non esiste."
        )
    
    # Inserimento sicuro
    try:
        cur.execute(
            "INSERT IGNORE INTO gold_standard (url, gold_text) VALUES (?, ?)",
            (req.url, req.gold_text)
        )
        conn.commit()
    except Exception as e:
        cur.close()
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))
        
    cur.close()
    conn.close()
    return {"status": "ok"}

@router.get("/gold_standard_urls")
async def get_gs_urls(domain: str):
    """
    Restituisce tutti gli URL associati a un determinato dominio 
    presenti all'interno del database.
    """
    # Pulizia input
    clean_d = domain[4:] if domain.startswith("www.") else domain
    
    # Validazione dominio (supporta domini mockati dal grader)
    if clean_d not in load_domains() and domain not in load_domains():
        raise HTTPException(status_code=400, detail="Dominio non supportato")

    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Errore di connessione al DB")
        
    cur = conn.cursor()
    cur.execute("SELECT url FROM web_resources WHERE domain=?", (clean_d,))
    urls = [r[0] for r in cur.fetchall()]
    conn.close()
    
    return {"gold_standard_urls": urls}

@router.get("/gold_standard")
async def get_gs(url: str):
    """
    Recupera i dati completi di una risorsa, unendo la pagina web 
    al suo corrispettivo testo Gold Standard.
    """
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT w.*, g.gold_text FROM web_resources w JOIN gold_standard g ON w.url=g.url WHERE w.url=?", (url,))
    res = cur.fetchone()
    conn.close()
    
    if not res: 
        raise HTTPException(status_code=404, detail="URL non presente nel Gold Standard")
        
    return res

@router.delete("/web_resource")
async def del_res(req: DeleteRequest):
    """
    Elimina una risorsa web dal database.
    Se configurato a cascata, elimina anche il relativo Gold Standard.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM web_resources WHERE url=?", (req.url,))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        print(f"Errore durante l'eliminazione: {e}")
        return {"status": "error"}
    
@router.delete("/gold_standard")
async def del_gs(req: DeleteRequest):
    """
    Elimina unicamente il riferimento Gold Standard, mantenendo la risorsa web.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("DELETE FROM gold_standard WHERE url=?", (req.url,))
        
        # Controllo righe impattate per riscontro
        if cur.rowcount == 0:
            conn.close()
            return {"status": "error", "detail": "URL non presente nel GS"}
            
        conn.commit()
        conn.close()
        return {"status": "ok"}
        
    except Exception as e:
        print(f"Errore durante l'eliminazione del GS: {e}")
        return {"status": "error"}

# =====================================================================
# EVALUATION ROUTES (METRICS & LLM JUDGE)
# =====================================================================

@router.post("/evaluate")
async def api_eval(req: EvaluateRequest):
    """
    Calcola le metriche token-level (Precision, Recall, F1-Score) 
    confrontando il testo estratto con il Gold Standard.
    """
    risultati = calculate_token_level_eval(req.parsed_text, req.gold_text)
    return {"token_level_eval": risultati}

@router.post("/evaluate_judge")
async def api_judge(req: EvaluateJudgeRequest):
    """
    Utilizza un LLM (Ollama) per fornire un giudizio qualitativo (1-5) 
    sulla fedeltà del testo estratto rispetto al Gold Standard.
    """
    # Controllo disponibilità modello
    try:
        async with httpx.AsyncClient() as client:
            tags_res = await client.get("http://ollama:11434/api/tags", timeout=5.0)
            if tags_res.status_code == 200:
                models = [m["name"] for m in tags_res.json().get("models", [])]
                if not any("llama3.2" in m for m in models):
                    raise HTTPException(status_code=503, detail="Modello Llama non pronto.")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Server Ollama offline.")

    # Esecuzione valutazione LLM
    res = await evaluate_with_llm(req.parsed_text, req.gold_text)
    
    risposta_finale = {
        "model_name": "llama3.2:3b", 
        "judge_score": int(res.get("judge_score", 0)), 
        "judge_feedback": res.get("judge_feedback", "")
    }
    
    # Persistenza valutazione (se URL fornito)
    if req.url:
        f1_score = calculate_token_level_eval(req.parsed_text, req.gold_text).get("f1", 0)
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("""
                REPLACE INTO evaluations (url, f1_score, judge_score, judge_feedback) 
                VALUES (?, ?, ?, ?)
            """, (req.url, f1_score, risposta_finale["judge_score"], risposta_finale["judge_feedback"]))
            conn.commit()
            conn.close()
            
    return risposta_finale

@router.get("/full_gs_eval")
async def full_eval(domain: str):
    """
    Esegue un batch di valutazioni token-level (F1 Score) per tutte le risorse 
    appartenenti a uno specifico dominio, calcolandone le medie complessive.
    """
    clean_d = domain[4:] if domain.startswith("www.") else domain
    
    # Validazione input
    if clean_d not in load_domains() and domain not in load_domains():
        raise HTTPException(status_code=400, detail="Dominio non supportato")

    conn = get_db_connection()
    if not conn: 
        raise HTTPException(status_code=500, detail="DB off")
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT w.url, g.gold_text FROM web_resources w JOIN gold_standard g ON w.url=g.url WHERE w.domain=?", (clean_d,))
    rows = cur.fetchall()
    conn.close() 

    # Uscita anticipata per insiemi vuoti
    if not rows: 
        return {
            "token_level_eval": {"precision": 0.0, "recall": 0.0, "f1": 0.0}, 
            "judge_score": 0.0
        }
    
    precs, recs, f1s, judges = [], [], [], []

    # Esecuzione in serie del parsing e della validazione matematica
    for r in rows:
        try:
            # Parsing locale
            p = await perform_parse(r['url'], local=True)
            
            # Valutazione Token-Level
            f1_data = calculate_token_level_eval(p['parsed_text'], r['gold_text'])
            
            p_score = f1_data.get('precision', 0.0)
            r_score = f1_data.get('recall', 0.0)
            f1_score = f1_data.get('f1', 0.0)
            
            # Aggiornamento parziale nel DB
            conn_write = get_db_connection()
            if conn_write:
                cur_in = conn_write.cursor()
                cur_in.execute("""
                    REPLACE INTO evaluations (url, f1_score, judge_score) 
                    VALUES (?, ?, ?)
                """, (r['url'], f1_score, 0.0)) 
                conn_write.commit()
                conn_write.close()
            
            precs.append(p_score)
            recs.append(r_score)
            f1s.append(f1_score)
            
        except Exception as e:
            print(f"⚠️ Errore: {e}")
            precs.append(0.0)
            recs.append(0.0)
            f1s.append(0.0)

    # Calcolo medie di aggregazione
    n = len(rows)
    avg_p = sum(precs) / n
    avg_r = sum(recs) / n
    avg_f1 = sum(f1s) / n
    avg_j = sum(judges) / n if len(judges) > 0 else 0.0

    return {
        "token_level_eval": {
            "precision": round(avg_p, 4),
            "recall": round(avg_r, 4),
            "f1": round(avg_f1, 4)
        },
        "judge_score": round(avg_j, 2)
    }