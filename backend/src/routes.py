import httpx
import asyncio
from fastapi import APIRouter, HTTPException
from models import ParseRequest, EvaluateRequest, EvaluateJudgeRequest, ResourceRequest
from utils import get_exact_domain, load_domains, calculate_token_level_eval
from database import get_db_connection
from parser_logic import perform_parse
from llm_judge import evaluate_with_llm

router = APIRouter()

@router.get("/domains")
async def get_domains():
    return {"domains": load_domains()}

@router.get("/gold_standard_urls")
async def get_gs_urls(domain: str):
    clean_d = domain[4:] if domain.startswith("www.") else domain
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT url FROM web_resources WHERE domain=?", (clean_d,))
    urls = [r[0] for r in cur.fetchall()]
    conn.close()
    return {"gold_standard_urls": urls}

@router.get("/gold_standard")
async def get_gs(url: str):
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT w.*, g.gold_text FROM web_resources w JOIN gold_standard g ON w.url=g.url WHERE w.url=?", (url,))
    res = cur.fetchone()
    conn.close()
    if not res: raise HTTPException(status_code=404, detail="URL non presente nel Gold Standard")
    return res

@router.post("/parse")
async def api_parse(req: ParseRequest):
    # La fusione dei due campi per il grader del prof!
    html_finale = req.html or req.html_text or ""
    return await perform_parse(req.url, req.local, html_finale)

@router.post("/evaluate")
async def api_eval(req: EvaluateRequest):
    return {"token_level_eval": calculate_token_level_eval(req.parsed_text, req.gold_text)}

@router.post("/evaluate_judge")
async def api_judge(req: EvaluateJudgeRequest):
    try:
        async with httpx.AsyncClient() as client:
            tags_res = await client.get("http://ollama:11434/api/tags", timeout=5.0)
            if tags_res.status_code == 200:
                models = [m["name"] for m in tags_res.json().get("models", [])]
                if not any("llama3.2" in m for m in models):
                    raise HTTPException(status_code=503, detail="Modello Llama non pronto.")
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Server Ollama offline.")

    f1_score = calculate_token_level_eval(req.parsed_text, req.gold_text).get("f1", 0)
    res = await evaluate_with_llm(req.parsed_text, req.gold_text)
    
    conn = get_db_connection()
    if conn:
        cur = conn.cursor()
        cur.execute("REPLACE INTO evaluations (url, f1_score, judge_score, judge_feedback) VALUES (?, ?, ?, ?)", 
                              (req.url, f1_score, res.get("judge_score", 0), res.get("judge_feedback", "")))
        conn.commit()
        conn.close()
    return res

@router.get("/full_gs_eval")
async def full_eval(domain: str):
    clean_d = domain[4:] if domain.startswith("www.") else domain
    conn = get_db_connection()
    if not conn: return {"error": "DB off"}
    
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT w.url, g.gold_text FROM web_resources w JOIN gold_standard g ON w.url=g.url WHERE w.domain=?", (clean_d,))
    rows = cur.fetchall()
    
    if not rows: 
        conn.close()
        return {"token_level_eval": {"f1": 0}, "judge_score": 0}
    
    f1s, judges = [], []
    sem = asyncio.Semaphore(2)

    async def process_row(r):
        async with sem:
            try:
                p = await perform_parse(r['url'], local=True)
                f1_data = calculate_token_level_eval(p['parsed_text'], r['gold_text'])
                j_res = await evaluate_with_llm(p['parsed_text'], r['gold_text'])
                
                f1_score = f1_data.get('f1', 0)
                j_score = j_res.get('judge_score', 0)
                j_feed = j_res.get('judge_feedback', '')
                
                # Salviamo nel DB riga per riga!
                cur_in = conn.cursor()
                cur_in.execute("""
                    REPLACE INTO evaluations (url, f1_score, judge_score, judge_feedback) 
                    VALUES (?, ?, ?, ?)
                """, (r['url'], f1_score, j_score, j_feed))
                conn.commit()
                
                return f1_score, j_score
            except Exception as e:
                print(f"Errore su {r['url']}: {e}")
                return 0, 0 

    tasks = [process_row(r) for r in rows]
    results = await asyncio.gather(*tasks)
    conn.close()

    for f1, judge in results:
        f1s.append(f1)
        judges.append(judge)
    
    return {
        "token_level_eval": {"f1": round(sum(f1s)/len(f1s), 3) if f1s else 0},
        "judge_score": round(sum(judges)/len(judges), 2) if judges else 0
    }

@router.post("/add_web_resource")
async def add_res(req: ResourceRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO web_resources (url, domain, html_text) VALUES (?, ?, ?)", 
                (req.url, get_exact_domain(req.url), req.html_text))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.post("/add_gold_standard")
async def add_gs(req: ResourceRequest):
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO gold_standard (url, gold_text) VALUES (?, ?)", (req.url, req.gold_text))
        conn.commit()
        return {"status": "ok"}
    except: raise HTTPException(status_code=400, detail="URL non presente in web_resources")
    finally: conn.close()

@router.delete("/web_resource")
async def del_res(url: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM web_resources WHERE url=?", (url,))
    conn.commit()
    conn.close()
    return {"status": "ok"}

@router.get("/db_stats")
async def db_stats():
    conn = get_db_connection()
    if not conn:
        return {"error": "DB non raggiungibile"}
    
    cur = conn.cursor(dictionary=True)
    
    # 1. Conteggio Web Resources per dominio
    cur.execute("SELECT domain, COUNT(*) as count FROM web_resources GROUP BY domain")
    wr_counts = {r['domain']: r['count'] for r in cur.fetchall()}
    
    # 2. Conteggio Gold Standard per dominio
    cur.execute("""
        SELECT w.domain, COUNT(*) as count 
        FROM gold_standard g 
        JOIN web_resources w ON g.url = w.url 
        GROUP BY w.domain
    """)
    gs_counts = {r['domain']: r['count'] for r in cur.fetchall()}
    
    # 3. Medie ISTANTANEE dalla nuova tabella evaluations
    cur.execute("""
        SELECT 
            w.domain, 
            AVG(e.f1_score) as avg_f1, 
            AVG(e.judge_score) as avg_judge
        FROM web_resources w
        JOIN evaluations e ON w.url = e.url
        GROUP BY w.domain
    """)
    rows = cur.fetchall()
    
    avg_eval = {r['domain']: {"token_level_eval": {"f1": round(r['avg_f1'], 2) if r['avg_f1'] else 0}} for r in rows}
    avg_eval_judge = {r['domain']: {"judge_score": round(r['avg_judge'], 1) if r['avg_judge'] else 0} for r in rows}

    conn.close()
    
    return {
        "web_resources": wr_counts,
        "gold_standard": gs_counts,
        "avg_eval": avg_eval,
        "avg_eval_judge": avg_eval_judge
    }

@router.get("/db_schema")
async def db_schema():
    return {
        "web_resources": {"url": "varchar(500), PK", "domain": "varchar(255)", "html_text": "longtext"},
        "gold_standard": {"url": "varchar(500), PK, FK", "gold_text": "longtext"}
    }

@router.get("/status")
async def get_status():
    status = {"backend": "ok", "database": "error", "ollama": "error"}
    try:
        conn = get_db_connection()
        if conn: status["database"] = "ok"; conn.close()
    except: pass
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://ollama:11434/api/tags")
            if res.status_code == 200: status["ollama"] = "ok"
    except: pass
    return status