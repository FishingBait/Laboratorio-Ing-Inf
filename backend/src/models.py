from pydantic import BaseModel
from typing import Optional

# Definizione dei modelli di dati per le richieste API, utilizzati per validare e strutturare i dati in ingresso nelle rotte del backend, 
# facilitando la gestione delle richieste e garantendo che i dati siano nel formato corretto prima di essere elaborati dalle funzioni di parsing ed evaluazione.

#Questo modello rappresenta la richiesta per il parsing di una risorsa web, con campi per l'URL, un flag per indicare se la risorsa è locale, 
# e campi opzionali per l'HTML completo e il testo estratto, che possono essere utilizzati sia per il nostro frontend che per il Grader del Prof.
class ParseRequest(BaseModel):
    url: str
    local: Optional[bool] = False
    html: Optional[str] = None       # Aggiunto per il Grader del Prof!
    html_text: Optional[str] = None  # Mantenuto per il nostro frontend

# Questo modello rappresenta la richiesta per la valutazione del testo estratto, con campi per il testo estratto e il gold standard, 
# utilizzati per inviare i dati a Ollama e ottenere un giudizio qualitativo sulla qualità del parsing.
class EvaluateRequest(BaseModel):
    parsed_text: str
    gold_text: str

# Questo modello rappresenta la richiesta per la valutazione con giudizio qualitativo, includendo l'URL della risorsa, 
# il testo estratto e il gold standard, utilizzati per inviare tutti i dati necessari a Ollama e ottenere sia un punteggio che un feedback testuale sulla qualità del parsing.
class EvaluateJudgeRequest(BaseModel):
    url: str  
    parsed_text: str
    gold_text: str

# Questo modello rappresenta la richiesta per aggiungere una nuova risorsa web al database, con campi per l'URL, 
# l'HTML completo e il testo pulito (gold standard), utilizzati per salvare le nuove risorse web e i loro gold standard associati nel database, 
# facilitando la costruzione del gold standard da parte degli utenti attraverso il nostro frontend.
class ResourceRequest(BaseModel):
    url: str
    html_text: Optional[str] = None
    gold_text: Optional[str] = None