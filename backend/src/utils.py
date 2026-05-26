import json
import os
import re
import collections
import string  
from typing import List, Dict
import mistune
from bs4 import BeautifulSoup

"""
 Questo file contiene funzioni di utilità per il backend, come l'estrazione del dominio da un URL, il caricamento dei domini e dei gold 
 standard dai file JSON, e il calcolo delle metriche di valutazione a livello di token tra il testo estratto e il gold standard, facilitando 
 la gestione dei dati e la valutazione del parser all'interno del backend.
"""

# Funzione per estrarre il dominio pulito da un URL, rimuovendo eventuali prefissi come "www."
def get_exact_domain(url: str) -> str:
    return url.split("/")[2] if "://" in url else url.split("/")[0]

# Funzione per caricare i domini dai file JSON
def load_domains() -> List[str]:
    try:
        with open("/app/domains.json", "r") as f:
            return json.load(f).get("domains", [])
    except: 
        return []
    
# Funzione per ottenere il gold standard associato a un dominio specifico dai file JSON
def get_domain_gs_from_json(domain: str) -> List[Dict]:
    path = f"/app/gs_data/{domain}_gs.json"
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("gold_standard", [])

# --- NUOVA FUNZIONE DEL PROFESSORE ---
def remove_markdown(md: str) -> str:
    """
    Rimuove il Markdown da una stringa, restituendo solo il testo pulito.
    Usa la libreria mistune per convertire il Markdown in HTML, poi BeautifulSoup per estrarre solo il testo.
    """
    html = mistune.html(md)
    soup = BeautifulSoup(html, "html.parser")
    # rimuove i tag lasciando il testo esattamente in-place (nessun separatore aggiunto, mantiene punteggiatura)
    for tag in soup.find_all(True):
        tag.unwrap()
    text = re.sub(r'[ \t]+', ' ', str(soup)) # collassa spazi orizzontali (non \n)
    text = re.sub(r'\n+', '\n', text) # collassa nuove linee multiple in una sola
    return text.strip()

# --- FUNZIONE DI VALUTAZIONE DEFINITIVA (PUNTA AL 100%) ---
def calculate_token_level_eval(parsed_text: str, gold_text: str) -> Dict[str, float]:
    # 1. Rimuoviamo SOLO i link con http (esattamente come fanno gli script universitari base)
    p_text = re.sub(r'http\S+', '', parsed_text)
    g_text = re.sub(r'http\S+', '', gold_text)
    
    # 2. Laviamo via il markdown e rendiamo tutto lowercase, ma senza rimuovere la punteggiatura, in modo da mantenere il testo il più fedele possibile all'originale, e
    #  permettere una valutazione più accurata a livello di token, considerando anche la punteggiatura come parte integrante del testo.
    p_clean = remove_markdown(p_text).lower()
    g_clean = remove_markdown(g_text).lower()
    
    # 3. Estraiamo lettere e numeri puri, escludendo gli underscore (_)
    p_toks = re.findall(r'[^\W_]+', p_clean)
    g_toks = re.findall(r'[^\W_]+', g_clean)    
    
    if not p_toks or not g_toks: 
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
        
    common = collections.Counter(p_toks) & collections.Counter(g_toks)
    n_same = sum(common.values())
    
    prec = n_same / len(p_toks)
    rec = n_same / len(g_toks)
    f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
    
    return {
        "precision": round(prec, 4), 
        "recall": round(rec, 4), 
        "f1": round(f1, 4)
    }