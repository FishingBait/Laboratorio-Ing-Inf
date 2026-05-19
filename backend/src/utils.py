import json
import os
import re
import collections
from typing import List, Dict

"""
 Questo file contiene funzioni di utilità per il backend, come l'estrazione del dominio da un URL, il caricamento dei domini e dei gold 
 standard dai file JSON, e il calcolo delle metriche di valutazione a livello di token tra il testo estratto e il gold standard, facilitando 
 la gestione dei dati e la valutazione del parser all'interno del backend.
"""

#funzione per estrarre il dominio pulito da un URL, rimuovendo eventuali prefissi come "www." per garantire una gestione 
# uniforme dei domini all'interno del database e delle rotte del backend.
def get_exact_domain(url: str) -> str:
    return url.split("/")[2] if "://" in url else url.split("/")[0]

#funzione per caricare i domini dai file JSON, restituendo una lista di domini disponibili per il parsing e la valutazione,
def load_domains() -> List[str]:
    try:
        with open("/app/domains.json", "r") as f:
            return json.load(f).get("domains", [])
    except: return []
    
#funzione per ottenere il gold standard associato a un dominio specifico dai file JSON, restituendo una lista di risorse web e i loro gold standard associati, 
# utilizzata per popolare il database e fornire i dati necessari per la valutazione del parser.
def get_domain_gs_from_json(domain: str) -> List[Dict]:
    path = f"/app/gs_data/{domain}_gs.json"
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("gold_standard", [])
    
# funzione per calcolare le metriche di valutazione a livello di token tra il testo estratto e il gold standard, restituendo un dizionario con precisione, recall e F1 score,
# utilizzata per fornire una valutazione quantitativa della qualità del parsing, che può essere visualizzata nel frontend o utilizzata come parte del feedback fornito da Ollama 
# nella valutazione qualitativa. La funzione rimuove URL e link markdown, tokenizza i testi e calcola le metriche basate sui token comuni tra il testo estratto e il gold standard.
def calculate_token_level_eval(parsed_text: str, gold_text: str) -> Dict[str, float]:
    p = re.sub(r'http\S+|\[.*?\]\(.*?\)', '', parsed_text.lower())
    g = re.sub(r'http\S+|\[.*?\]\(.*?\)', '', gold_text.lower())
    p_toks = re.findall(r'\b\w+\b', p)
    g_toks = re.findall(r'\b\w+\b', g)
    if not p_toks or not g_toks: return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    common = collections.Counter(p_toks) & collections.Counter(g_toks)
    n_same = sum(common.values())
    prec = n_same / len(p_toks)
    rec = n_same / len(g_toks)
    f1 = 2 * (prec * rec) / (prec + rec) if (prec + rec) > 0 else 0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}