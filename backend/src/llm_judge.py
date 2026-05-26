import httpx
import json
import re

OLLAMA_URL = "http://ollama:11434/api/generate"
DEFAULT_MODEL = "llama3.2:3b"

async def evaluate_with_llm(parsed_text: str, gold_text: str, model_name: str = DEFAULT_MODEL) -> dict:
    """
    Invia il testo estratto e il Gold Standard a Ollama per una valutazione qualitativa,
    utilizzando una rubrica di valutazione esplicita e temperatura a 0 per determinismo.
    """
    
    # Il System Prompt definisce il ruolo, le regole di tolleranza e la rubrica.
    system_prompt = """Sei un giudice imparziale esperto in data extraction. 
Il tuo compito è valutare quanto un "Testo estratto" sia fedele al "Gold Standard".
REGOLA FONDAMENTALE: Ignora le differenze di formattazione (spazi extra, a capo mancanti, punteggiatura diversa). Valuta SOLO la presenza e la correttezza del contenuto informativo.

Usa RIGOROSAMENTE questa scala:
5: Eccellente. Il testo estratto contiene tutte le informazioni chiave del Gold Standard.
4: Buono. Manca qualche dettaglio minore o c'è un leggero rumore, ma il senso generale è perfettamente intatto.
3: Sufficiente. Manca qualche informazione rilevante, ma il nucleo del messaggio è presente.
2: Scarso. Mancano informazioni fondamentali, oppure c'è troppo testo irrilevante (HTML, script).
1: Pessimo. Testo incomprensibile, vuoto o completamente scollegato dal Gold Standard.

Devi rispondere ESCLUSIVAMENTE con un oggetto JSON."""

    # L'User Prompt contiene solo i dati e il reminder del formato in uscita.
    user_prompt = f"""
Testo estratto dal parser:
---
{parsed_text}
---

Testo di riferimento (Gold Standard):
---
{gold_text}
---

Rispondi SOLO con un JSON nel seguente formato, senza aggiungere testo prima o dopo:
{{
    "score": <intero tra 1 e 5>,
    "feedback": "<breve descrizione del perché hai assegnato il punteggio>"
}}
"""
    # Il payload per Ollama include il modello, i prompt, e le opzioni per garantire una risposta coerente e strutturata.
    payload = {
        "model": model_name,
        "system": system_prompt,
        "prompt": user_prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.0,  # Azzera la creatività per avere giudizi stabili
            "top_p": 0.9
        }
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # Inviamo la richiesta a Ollama e attendiamo la risposta, con un timeout generoso per evitare interruzioni premature.
            response = await client.post(OLLAMA_URL, json=payload, timeout=120.0)
            # Verifichiamo che la risposta sia positiva, altrimenti solleviamo un'eccezione per gestire errori di comunicazione o problemi con il modello.
            response.raise_for_status()
            
            data = response.json()
            raw_response = data.get("response", "")
            
            try:
                llm_json = json.loads(raw_response)
                score = int(llm_json.get("score", 1))
                feedback = str(llm_json.get("feedback", "Nessun feedback fornito."))
                
                # Assicuriamoci che lo score sia nei limiti
                score = max(1, min(5, score))
                
            except (json.JSONDecodeError, ValueError, TypeError):
                print(f"ATTENZIONE: Fallback attivato. Risposta raw non JSON: {raw_response}")
                
                score_match = re.search(r'"score"\s*:\s*([1-5])', raw_response)
                if score_match:
                    score = int(score_match.group(1))
                else:
                    score = 1
                    
                feedback = "Fallback attivato: il modello non ha rispettato il formato JSON. " + raw_response[:100]

            return {
                "model_name": model_name,
                "judge_score": score,
                "judge_feedback": feedback
            }
            
        except Exception as e:
            return {
                "model_name": model_name,
                "judge_score": 1,
                "judge_feedback": f"Errore di comunicazione con Ollama: {str(e)}"
            }