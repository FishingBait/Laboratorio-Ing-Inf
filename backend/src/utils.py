import json
import os
import re
import collections
from typing import List, Dict

def get_exact_domain(url: str) -> str:
    return url.split("/")[2] if "://" in url else url.split("/")[0]

def load_domains() -> List[str]:
    try:
        with open("/app/domains.json", "r") as f:
            return json.load(f).get("domains", [])
    except: return []

def get_domain_gs_from_json(domain: str) -> List[Dict]:
    path = f"/app/gs_data/{domain}_gs.json"
    if not os.path.exists(path): return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("gold_standard", [])

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