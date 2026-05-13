import os
import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any, Optional # <--- FIX: Aggiunto Optional qui

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Carica l'URL del backend dall'ambiente o usa il default
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8003")

# Client asincrono per comunicare con il backend
async def call_backend(method: str, endpoint: str, params=None, json_data=None):
    # Il timeout è stato aumentato a 120 secondi per gestire operazioni più lunghe come il parsing di pagine complesse o la valutazione con LLM
    async with httpx.AsyncClient(timeout=120.0) as client: 
        url = f"{BACKEND_URL}{endpoint}"
        if method == "GET":
            return await client.get(url, params=params)
        elif method == "POST":
            return await client.post(url, json=json_data)
        elif method == "DELETE":
            return await client.delete(url, params=params)

# --- UTILITIES ---
# Funzione per estrarre il dominio pulito da un URL, rimuovendo eventuali prefissi "www." e restituendo solo la parte principale del dominio, per garantire coerenza nella gestione dei domini all'interno del database e nelle operazioni di parsing e valutazione.
def get_exact_domain(url: str) -> str:
    """Estrae il dominio pulito da un URL (es. https://www.amazon.it/page -> amazon.it)"""
    domain = url.split("/")[2] if "://" in url else url.split("/")[0]
    return domain[4:] if domain.startswith("www.") else domain

# --- PAGINA 1: HOME ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    status = {"backend": "ok", "database": "error", "ollama": "error"}
    domains = []
    try:
        status_res = await call_backend("GET", "/status")
        if status_res.status_code == 200: status = status_res.json()
        
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200: domains = dom_res.json().get("domains", [])
    except: pass
    
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "status": status, 
        "domains": domains,
        "matricole": ["Lorenzo Bordi 2066423", "Claudio Frontoni 2089078", "Lorenzo Labella 2135570"] 
    })

# --- PAGINA 2: PARSER & EVALUATION ---
@app.get("/parser", response_class=HTMLResponse)
async def parser_view(request: Request):
    gs_urls = []
    try:
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200:
            for d in dom_res.json().get("domains", []):
                urls_res = await call_backend("GET", "/gold_standard_urls", params={"domain": d})
                if urls_res.status_code == 200:
                    gs_urls.extend(urls_res.json().get("gold_standard_urls", []))
    except: pass
    return templates.TemplateResponse("parser.html", {"request": request, "gs_urls": gs_urls})

@app.post("/parser", response_class=HTMLResponse)
async def parser_action(request: Request, url: str = Form(...), mode: str = Form("live")):
    local = True if mode == "local" else False
    error_msg = None
    parsed_data, gold_data, eval_metrics, judge_data = None, None, None, None
    gs_urls = []
    
    try:
        # Recupera URL per il menu a tendina
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200:
            for d in dom_res.json().get("domains", []):
                urls_res = await call_backend("GET", "/gold_standard_urls", params={"domain": d})
                if urls_res.status_code == 200:
                    gs_urls.extend(urls_res.json().get("gold_standard_urls", []))
                    
        # 1. Chiamata al Parser
        p_res = await call_backend("POST", "/parse", json_data={"url": url, "local": local})
        
        # CONTROLLO ERRORI DAL BACKEND
        if p_res.status_code != 200:
            error_msg = p_res.json().get("detail", "Errore sconosciuto dal backend.")
        else:
            parsed_data = p_res.json()
            
            # 2. Recupero Gold Standard
            gs_res = await call_backend("GET", "/gold_standard", params={"url": url})
            if gs_res.status_code == 200:
                gold_data = gs_res.json()
                
                # 3. Metriche
                e_res = await call_backend("POST", "/evaluate", json_data={
                    "parsed_text": parsed_data["parsed_text"], "gold_text": gold_data["gold_text"]
                })
                if e_res.status_code == 200: eval_metrics = e_res.json().get("token_level_eval")
                
                # 4. Valutazione LLM Judge
                j_res = await call_backend("POST", "/evaluate_judge", json_data={
                    "url": url, 
                    "parsed_text": parsed_data["parsed_text"], 
                    "gold_text": gold_data["gold_text"]
                })
                
                if j_res.status_code == 200: 
                    judge_data = j_res.json()
                else:
                    error_msg = j_res.json().get("detail", "Errore durante la valutazione LLM.")

    except Exception as e:
        error_msg = f"Impossibile comunicare con il server: {str(e)}"

    return templates.TemplateResponse("parser.html", {
        "request": request, "url": url, "gs_urls": gs_urls, "parsed_data": parsed_data,
        "gold_data": gold_data, "eval_metrics": eval_metrics, "judge": judge_data,
        "error": error_msg  # <--- PASSIAMO L'ERRORE AL TEMPLATE
    })

# --- PAGINA 3: GOLD STANDARD BUILDER ---
@app.get("/builder", response_class=HTMLResponse)
async def builder_view(request: Request, domain: Optional[str] = None):
    domains, urls = [], []
    try:
        d_res = await call_backend("GET", "/domains")
        if d_res.status_code == 200: domains = d_res.json().get("domains", [])
        if domain:
            u_res = await call_backend("GET", "/gold_standard_urls", params={"domain": domain})
            if u_res.status_code == 200: urls = u_res.json().get("gold_standard_urls", [])
    except: pass
    return templates.TemplateResponse("builder.html", {
        "request": request, "domains": domains, "current_domain": domain, "urls": urls
    })

# Rotta per il download dell'HTML (STEP 1)
@app.post("/builder/preview", response_class=HTMLResponse)
async def builder_preview(request: Request, url: str = Form(...), domain: Optional[str] = Form(None)):
    domains, urls, preview_html, error_msg = [], [], "", None
    try:
        d_res = await call_backend("GET", "/domains")
        if d_res.status_code == 200: domains = d_res.json().get("domains", [])
        if domain:
            u_res = await call_backend("GET", "/gold_standard_urls", params={"domain": domain})
            if u_res.status_code == 200: urls = u_res.json().get("gold_standard_urls", [])
        
        # Chiamata di scaricamento
        p_res = await call_backend("POST", "/parse", json_data={"url": url, "local": False})
        
        # CONTROLLO ERRORI DAL BACKEND
        if p_res.status_code != 200:
            error_msg = p_res.json().get("detail", "Impossibile scaricare la risorsa.")
        else:
            preview_html = p_res.json().get("html_text", "")
            
    except Exception as e:
        error_msg = f"Errore di rete: {str(e)}"
        
    return templates.TemplateResponse("builder.html", {
        "request": request, "domains": domains, "current_domain": domain, "urls": urls,
        "preview_url": url, "preview_html": preview_html,
        "error": error_msg # <--- PASSIAMO L'ERRORE AL TEMPLATE
    })

# Rotta per il salvataggio nel Database (STEP 2)
@app.post("/builder/add", response_class=RedirectResponse)
async def builder_add(url: str = Form(...), html_text: str = Form(...), gold_text: str = Form(...)):
    domain = get_exact_domain(url)
    # 1. Salva la risorsa web
    await call_backend("POST", "/add_web_resource", json_data={"url": url, "html_text": html_text})
    # 2. Salva il testo pulito
    await call_backend("POST", "/add_gold_standard", json_data={"url": url, "gold_text": gold_text})
    
    return RedirectResponse(url=f"/builder?domain={domain}", status_code=303)

# Rotta per l'eliminazione a cascata
@app.get("/builder/delete", response_class=RedirectResponse)
async def builder_delete(url: str, domain: str):
    await call_backend("DELETE", "/web_resource", params={"url": url})
    return RedirectResponse(url=f"/builder?domain={domain}", status_code=303)

# --- PAGINA 4: STATS ---
@app.get("/stats", response_class=HTMLResponse)
async def stats_view(request: Request):
    stats = {}
    try:
        # Recupera le statistiche aggregate dal DB (Obiettivo 6)
        s_res = await call_backend("GET", "/db_stats")
        if s_res.status_code == 200: 
            stats = s_res.json()
    except: pass
    return templates.TemplateResponse("stats.html", {"request": request, "stats": stats})