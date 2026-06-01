import os
import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any, Optional 

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Configurazione URL del backend (con fallback per ambiente di sviluppo locale)
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8003")

# =====================================================================
# UTILITIES & COMMUNICATION
# =====================================================================

async def call_backend(method: str, endpoint: str, params=None, json_data=None):
    """
    Gestisce le comunicazioni asincrone con il container backend.
    Il timeout è impostato a 120 secondi per accomodare le richieste 
    all'LLM Judge (Ollama) che possono richiedere tempi di elaborazione lunghi.
    """
    async with httpx.AsyncClient(timeout=120.0) as client: 
        url = f"{BACKEND_URL}{endpoint}"
        if method == "GET":
            return await client.get(url, params=params)
        elif method == "POST":
            return await client.post(url, json=json_data)
        elif method == "DELETE":
            return await client.delete(url, params=params)

def get_exact_domain(url: str) -> str:
    """
    Estrae il dominio pulito da un URL (rimuovendo protocolli e prefissi 'www.').
    Garantisce coerenza nella gestione delle risorse tra frontend e backend.
    """
    domain = url.split("/")[2] if "://" in url else url.split("/")[0]
    return domain[4:] if domain.startswith("www.") else domain

# =====================================================================
# PAGINA 1: DASHBOARD / HOME
# =====================================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """
    Renderizza la pagina principale. Effettua un controllo di base sullo 
    stato dei servizi (Health Check) e recupera i domini supportati.
    Applica una logica di tolleranza ai guasti: se il backend è offline, 
    l'interfaccia viene caricata ugualmente mostrando gli alert di errore.
    """
    status = {"backend": "ok", "database": "error", "ollama": "error"}
    domains = []
    
    try:
        status_res = await call_backend("GET", "/status")
        if status_res.status_code == 200: 
            status = status_res.json()
        
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200: 
            domains = dom_res.json().get("domains", [])
    except: 
        pass # Ignoriamo gli errori di connessione per permettere il rendering della pagina
        
    return templates.TemplateResponse("index.html", {
        "request": request, 
        "status": status, 
        "domains": domains,
        "matricole": ["Lorenzo Bordi 2066423", "Claudio Frontoni 2089078", "Lorenzo Labella 2135570"] 
    })

# =====================================================================
# PAGINA 2: PARSER & EVALUATION (CORE PIPELINE)
# =====================================================================

@app.get("/parser", response_class=HTMLResponse)
async def parser_view(request: Request):
    """
    Carica l'interfaccia utente per il parsing e la valutazione.
    Popola il menu a tendina con gli URL del Gold Standard presenti nel database.
    """
    gs_urls = []
    try:
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200:
            for d in dom_res.json().get("domains", []):
                urls_res = await call_backend("GET", "/gold_standard_urls", params={"domain": d})
                if urls_res.status_code == 200:
                    gs_urls.extend(urls_res.json().get("gold_standard_urls", []))
    except: 
        pass
        
    return templates.TemplateResponse("parser.html", {"request": request, "gs_urls": gs_urls})

@app.post("/parser", response_class=HTMLResponse)
async def parser_action(request: Request, url: str = Form(...), mode: str = Form("live")):
    """
    Gestisce l'intera pipeline di elaborazione quando un utente sottomette un URL:
    1. Parsing della pagina web (Live o Locale).
    2. Recupero del Gold Standard associato.
    3. Valutazione Token-Level (Precision, Recall, F1).
    4. Valutazione qualitativa LLM Judge tramite Ollama.
    """
    local = True if mode == "local" else False
    error_msg = None
    parsed_data, gold_data, eval_metrics, judge_data = None, None, None, None
    gs_urls = []
    
    try:
        # Recupero liste URL per mantenere popolata la select nell'interfaccia
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200:
            for d in dom_res.json().get("domains", []):
                urls_res = await call_backend("GET", "/gold_standard_urls", params={"domain": d})
                if urls_res.status_code == 200:
                    gs_urls.extend(urls_res.json().get("gold_standard_urls", []))
                    
        # Step 1: Esecuzione del Parsing
        p_res = await call_backend("POST", "/parse", json_data={"url": url, "local": local})
        
        if p_res.status_code != 200:
            error_msg = p_res.json().get("detail", "Errore sconosciuto dal backend.")
        else: 
            parsed_data = p_res.json()
            
            # Step 2: Recupero Gold Standard
            gs_res = await call_backend("GET", "/gold_standard", params={"url": url})
            
            if gs_res.status_code == 200:
                gold_data = gs_res.json()
                
                # Step 3: Metriche Token-Level
                e_res = await call_backend("POST", "/evaluate", json_data={
                    "parsed_text": parsed_data["parsed_text"], "gold_text": gold_data["gold_text"]
                })
                if e_res.status_code == 200: 
                    eval_metrics = e_res.json().get("token_level_eval")
                
                # Step 4: Valutazione LLM
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
        "error": error_msg 
    })

# =====================================================================
# PAGINA 3: GOLD STANDARD BUILDER (CRUD)
# =====================================================================

@app.get("/builder", response_class=HTMLResponse)
async def builder_view(request: Request, domain: Optional[str] = None):
    """
    Mostra l'interfaccia per la creazione e gestione manuale del Gold Standard.
    """
    domains, urls = [], []
    try:
        d_res = await call_backend("GET", "/domains")
        if d_res.status_code == 200: 
            domains = d_res.json().get("domains", [])
            
        if domain:
            u_res = await call_backend("GET", "/gold_standard_urls", params={"domain": domain})
            if u_res.status_code == 200: 
                urls = u_res.json().get("gold_standard_urls", [])
    except: 
        pass
        
    return templates.TemplateResponse("builder.html", {
        "request": request, "domains": domains, "current_domain": domain, "urls": urls
    })

@app.post("/builder/preview", response_class=HTMLResponse)
async def builder_preview(request: Request, url: str = Form(...), domain: Optional[str] = Form(None)):
    """
    Scarica il codice HTML di una risorsa e lo mostra in anteprima all'utente 
    prima che questi proceda alla creazione del Gold Standard definitivo.
    """
    domains, urls, preview_html, error_msg = [], [], "", None
    try:
        d_res = await call_backend("GET", "/domains")
        if d_res.status_code == 200: 
            domains = d_res.json().get("domains", [])
            
        if domain:
            u_res = await call_backend("GET", "/gold_standard_urls", params={"domain": domain})
            if u_res.status_code == 200: 
                urls = u_res.json().get("gold_standard_urls", [])
        
        p_res = await call_backend("POST", "/parse", json_data={"url": url, "local": False})
        
        if p_res.status_code != 200:
            error_msg = p_res.json().get("detail", "Impossibile scaricare la risorsa.")
        else:
            preview_html = p_res.json().get("html_text", "")
            
    except Exception as e:
        error_msg = f"Errore di rete: {str(e)}"
        
    return templates.TemplateResponse("builder.html", {
        "request": request, "domains": domains, "current_domain": domain, "urls": urls,
        "preview_url": url, "preview_html": preview_html,
        "error": error_msg 
    })

@app.post("/builder/add", response_class=RedirectResponse)
async def builder_add(url: str = Form(...), html_text: str = Form(...), gold_text: str = Form(...)):
    """
    Invia la risorsa web (HTML) e il testo di riferimento (Gold Standard) 
    al backend per il salvataggio persistente nel database.
    """
    domain = get_exact_domain(url)
    await call_backend("POST", "/add_web_resource", json_data={"url": url, "html_text": html_text})
    await call_backend("POST", "/add_gold_standard", json_data={"url": url, "gold_text": gold_text})
    return RedirectResponse(url=f"/builder?domain={domain}", status_code=303)

@app.get("/builder/delete", response_class=RedirectResponse)
async def builder_delete(url: str, domain: str):
    """
    Richiede al backend l'eliminazione completa di una risorsa web 
    (che a cascata eliminerà anche il relativo Gold Standard).
    """
    await call_backend("DELETE", "/web_resource", params={"url": url})
    return RedirectResponse(url=f"/builder?domain={domain}", status_code=303)

# =====================================================================
# PAGINA 4: STATISTICHE AGGREGATE
# =====================================================================

@app.get("/stats", response_class=HTMLResponse)
async def stats_view(request: Request):
    """
    Interroga il backend per ottenere le statistiche di sistema aggiornate
    (conteggio risorse, medie F1, medie giudizi LLM) e le renderizza a schermo.
    """
    stats = {}
    error_msg = None
    
    try:
        s_res = await call_backend("GET", "/db_stats")
        if s_res.status_code == 200: 
            data = s_res.json()
            if "error" not in data:
                stats = data
            else:
                error_msg = data.get("error")
        else:
            error_msg = f"Errore backend: {s_res.status_code}"
    except Exception as e: 
        error_msg = f"Errore di connessione: {str(e)}"
    
    return templates.TemplateResponse("stats.html", {
        "request": request, 
        "stats": stats,
        "error": error_msg
    })