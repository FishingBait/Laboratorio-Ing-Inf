import os
import httpx
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Any, Optional 

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Carica l'URL del backend dall'ambiente o usa il default
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8003")

# Client asincrono per comunicare con il backend
async def call_backend(method: str, endpoint: str, params=None, json_data=None):
    # Il timeout è stato aumentato a 120 secondi per gestire operazioni più lunghe
    async with httpx.AsyncClient(timeout=120.0) as client: 
        url = f"{BACKEND_URL}{endpoint}"
        if method == "GET":
            return await client.get(url, params=params)
        elif method == "POST":
            return await client.post(url, json=json_data)
        elif method == "DELETE":
            return await client.delete(url, params=params)

# --- UTILITIES --- 
# Queste funzioni di utilità sono utilizzate per estrarre il dominio da un URL, e sono condivise tra il frontend e il backend per 
# garantire coerenza nella gestione dei domini, facilitando la costruzione del gold standard e la gestione delle risorse web all'interno del nostro progetto.
def get_exact_domain(url: str) -> str:
    """Estrae il dominio pulito da un URL"""
    domain = url.split("/")[2] if "://" in url else url.split("/")[0]
    return domain[4:] if domain.startswith("www.") else domain

# --- PAGINA 1: HOME ---
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    status = {"backend": "ok", "database": "error", "ollama": "error"} # Inizializziamo con errori, poi aggiorniamo se va tutto bene
    domains = []
    # Proviamo a contattare il backend per ottenere lo status e i domini, ma se fallisce mostriamo comunque la pagina con errori evidenti
    try:
        status_res = await call_backend("GET", "/status")
        if status_res.status_code == 200: status = status_res.json()
        
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200: domains = dom_res.json().get("domains", [])
    except: pass
    # Renderizziamo la pagina home con lo status e i domini, evidenziando eventuali errori di connessione o di servizio, 
    # ma senza bloccare l'accesso alla pagina stessa, in modo che l'utente possa comunque vedere le informazioni disponibili e 
    # capire se ci sono problemi con il backend o i servizi associati.
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
    # Proviamo a caricare le URL del gold standard per mostrarle nella select, ma se fallisce mostriamo comunque la pagina vuota, 
    # in modo che l'utente possa comunque inserire un URL manualmente e provare
    try:
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200:
            for d in dom_res.json().get("domains", []):
                urls_res = await call_backend("GET", "/gold_standard_urls", params={"domain": d})
                if urls_res.status_code == 200:
                    gs_urls.extend(urls_res.json().get("gold_standard_urls", []))
    except: pass
    return templates.TemplateResponse("parser.html", {"request": request, "gs_urls": gs_urls})


# Questa rotta gestisce la logica di parsing, valutazione e giudizio qualitativo quando l'utente invia un URL da testare,
@app.post("/parser", response_class=HTMLResponse)
async def parser_action(request: Request, url: str = Form(...), mode: str = Form("live")):
    local = True if mode == "local" else False
    error_msg = None
    parsed_data, gold_data, eval_metrics, judge_data = None, None, None, None
    gs_urls = []
    # Proviamo a caricare le URL del gold standard per mostrarle nella select, ma se fallisce mostriamo comunque la pagina con i risultati del parsing,
    # in modo che l'utente possa comunque vedere i risultati del parsing e capire se ci
    try:
        dom_res = await call_backend("GET", "/domains")
        if dom_res.status_code == 200:
            for d in dom_res.json().get("domains", []):
                urls_res = await call_backend("GET", "/gold_standard_urls", params={"domain": d})
                if urls_res.status_code == 200:
                    gs_urls.extend(urls_res.json().get("gold_standard_urls", []))
                    
        p_res = await call_backend("POST", "/parse", json_data={"url": url, "local": local})
        # Se il parsing fallisce, mostriamo comunque la pagina con l'errore, ma se va a buon fine procediamo con la valutazione e il giudizio qualitativo,
        # in modo che l'utente possa vedere i risultati del parsing e capire se ci sono
        if p_res.status_code != 200:
            error_msg = p_res.json().get("detail", "Errore sconosciuto dal backend.")
        else: # Se il parsing ha successo, procediamo a caricare il gold standard e fare la valutazione, ma se qualcosa fallisce in questi passaggi mostriamo comunque i risultati del parsing,
            parsed_data = p_res.json()
            gs_res = await call_backend("GET", "/gold_standard", params={"url": url})
            
            if gs_res.status_code == 200:
                gold_data = gs_res.json()
                e_res = await call_backend("POST", "/evaluate", json_data={
                    "parsed_text": parsed_data["parsed_text"], "gold_text": gold_data["gold_text"]
                })
                if e_res.status_code == 200: eval_metrics = e_res.json().get("token_level_eval")
                
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
    # Renderizziamo la pagina del parser con tutti i dati disponibili, evidenziando eventuali errori di connessione o di servizio, ma senza bloccare la visualizzazione dei risultati ottenuti,
    # in modo che l'utente possa comunque vedere i risultati del parsing e capire se ci sono problemi con il backend o i servizi associati, e possa comunque interagire con la pagina per testare altre URL o visualizzare i gold standard disponibili.     
    return templates.TemplateResponse("parser.html", {
        "request": request, "url": url, "gs_urls": gs_urls, "parsed_data": parsed_data,
        "gold_data": gold_data, "eval_metrics": eval_metrics, "judge": judge_data,
        "error": error_msg 
    })

# --- PAGINA 3: GOLD STANDARD BUILDER ---
@app.get("/builder", response_class=HTMLResponse)
async def builder_view(request: Request, domain: Optional[str] = None):
    domains, urls = [], []
    # Proviamo a caricare i domini e le URL del gold standard per mostrarle nella pagina, ma se fallisce mostriamo comunque la pagina vuota,
    # in modo che l'utente possa comunque inserire un URL manualmente e provare a costruire il gold standard, e capire se ci sono problemi con il backend o i servizi associati.
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
# Le rotte per aggiungere, visualizzare l'anteprima e cancellare le risorse web nel gold standard, gestiscono la logica di comunicazione con il backend per eseguire le operazioni richieste dall'utente, ma in caso di errori di comunicazione o di servizio mostrano comunque la pagina con i dati disponibili e un messaggio di errore, in modo che l'utente possa comunque interagire con la pagina e capire se ci sono problemi con il backend o i servizi associati.  
@app.post("/builder/preview", response_class=HTMLResponse)
async def builder_preview(request: Request, url: str = Form(...), domain: Optional[str] = Form(None)):
    domains, urls, preview_html, error_msg = [], [], "", None
    # Proviamo a contattare il backend per ottenere i domini, le URL del gold standard e l'anteprima del parsing, ma se fallisce mostriamo comunque la pagina con i dati disponibili e un messaggio di errore, in modo che l'utente possa comunque interagire con la pagina e capire se ci sono problemi con il backend o i servizi associati.
    try:
        d_res = await call_backend("GET", "/domains")
        if d_res.status_code == 200: domains = d_res.json().get("domains", [])
        if domain:
            u_res = await call_backend("GET", "/gold_standard_urls", params={"domain": domain})
            if u_res.status_code == 200: urls = u_res.json().get("gold_standard_urls", [])
        
        p_res = await call_backend("POST", "/parse", json_data={"url": url, "local": False})
        
        if p_res.status_code != 200:
            error_msg = p_res.json().get("detail", "Impossibile scaricare la risorsa.")
        else:
            preview_html = p_res.json().get("html_text", "")
            
    except Exception as e:
        error_msg = f"Errore di rete: {str(e)}"
    # Renderizziamo la pagina del builder con tutti i dati disponibili, evidenziando eventuali errori di connessione o di servizio, ma senza bloccare la visualizzazione dei dati ottenuti,
    return templates.TemplateResponse("builder.html", {
        "request": request, "domains": domains, "current_domain": domain, "urls": urls,
        "preview_url": url, "preview_html": preview_html,
        "error": error_msg 
    })

# Le rotte per aggiungere, visualizzare l'anteprima e cancellare le risorse web nel gold standard, gestiscono la logica di comunicazione con il backend per eseguire le operazioni richieste dall'utente, ma in caso di errori di comunicazione o di servizio mostrano comunque la pagina con i dati disponibili e un messaggio di errore, in modo che l'utente possa comunque interagire con la pagina e capire se ci sono problemi con il backend o i servizi associati.
@app.post("/builder/add", response_class=RedirectResponse)
async def builder_add(url: str = Form(...), html_text: str = Form(...), gold_text: str = Form(...)):
    domain = get_exact_domain(url)
    await call_backend("POST", "/add_web_resource", json_data={"url": url, "html_text": html_text})
    await call_backend("POST", "/add_gold_standard", json_data={"url": url, "gold_text": gold_text})
    return RedirectResponse(url=f"/builder?domain={domain}", status_code=303)

# Le rotte per aggiungere, visualizzare l'anteprima e cancellare le risorse web nel gold standard, gestiscono la logica di comunicazione con il backend per eseguire le operazioni richieste dall'utente, ma in caso di errori di comunicazione o di servizio mostrano comunque la pagina con i dati disponibili e un messaggio di errore, in modo che l'utente possa comunque interagire con la pagina e capire se ci sono problemi con il backend o i servizi associati.
@app.get("/builder/delete", response_class=RedirectResponse)
async def builder_delete(url: str, domain: str):
    await call_backend("DELETE", "/web_resource", params={"url": url})
    return RedirectResponse(url=f"/builder?domain={domain}", status_code=303)

# --- PAGINA 4: STATS ---
@app.get("/stats", response_class=HTMLResponse)
async def stats_view(request: Request):
    # Inizializziamo a vuoto, senza la struttura vecchia!
    stats = {}
    error_msg = None
    
    # Proviamo a contattare il backend per ottenere le statistiche, ma se fallisce mostriamo comunque la pagina con un messaggio di errore, in modo che l'utente possa comunque vedere la pagina e capire se ci sono problemi con il backend o i servizi associati.
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
    
    # Renderizziamo la pagina delle statistiche con i dati disponibili, evidenziando eventuali errori di connessione o di servizio, ma senza bloccare la visualizzazione della pagina stessa, in modo che l'utente possa comunque vedere le informazioni disponibili e capire se ci sono problemi con il backend o i servizi associati.
    return templates.TemplateResponse("stats.html", {
        "request": request, 
        "stats": stats,
        "error": error_msg
    })