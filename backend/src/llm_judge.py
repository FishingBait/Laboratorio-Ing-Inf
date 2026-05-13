import httpx
import json
import re

# L'URL punta al nome del container definito nel docker-compose
OLLAMA_URL = "http://ollama:11434/api/generate"
DEFAULT_MODEL = "llama3.2:3b"

async def evaluate_with_llm(parsed_text: str, gold_text: str, model_name: str = DEFAULT_MODEL) -> dict:
    """
    Invia il testo estratto e il Gold Standard a Ollama per una valutazione qualitativa.
    """
    prompt = f"""
    Valuta la qualità del seguente testo estratto da una pagina web.
    
    Testo estratto dal parser:
    {parsed_text}
    
    Testo di riferimento (Gold Standard):
    {gold_text}
    
    Rispondi SOLO con un JSON nel seguente formato:
    {{
        "score": <intero tra 1 e 5>,
        "feedback": "<breve descrizione della qualità del testo, ad esempio 'Testo troncato', 'Ottimo', ecc.>"
    }}
    """
    
    payload = {
        "model": model_name,
        "prompt": prompt,
        "format": "json", # Forza Ollama a restituire un formato JSON
        "stream": False
    }
    
    async with httpx.AsyncClient() as client:
        try:
            # Timeout lungo perché l'LLM potrebbe impiegare qualche decina di secondi su CPU
            response = await client.post(OLLAMA_URL, json=payload, timeout=120.0)
            response.raise_for_status()
            
            data = response.json()
            raw_response = data.get("response", "")
            
            # PARSING E FALLBACK OBBLIGATORIO
            try:
                llm_json = json.loads(raw_response)
                score = int(llm_json.get("score", 1))
                feedback = str(llm_json.get("feedback", "Nessun feedback fornito."))
                
                # Assicuriamoci che lo score sia tra 1 e 5
                score = max(1, min(5, score))
                
            except (json.JSONDecodeError, ValueError, TypeError):
                # FALLBACK: Se il modello non restituisce un JSON valido, cerchiamo un numero con le regex
                print(f"ATTENZIONE: Fallback attivato. Risposta raw non JSON: {raw_response}")
                
                score_match = re.search(r'"score"\s*:\s*([1-5])', raw_response)
                if score_match:
                    score = int(score_match.group(1))
                else:
                    score = 1 # Score di default in caso di fallimento totale
                    
                feedback = "Fallback attivato: il modello non ha rispettato il formato JSON. " + raw_response[:100]

            return {
                "model_name": model_name,
                "judge_score": score,
                "judge_feedback": feedback
            }
            
        except Exception as e:
            # Gestione errori di rete o se Ollama è spento
            return {
                "model_name": model_name,
                "judge_score": 1,
                "judge_feedback": f"Errore di comunicazione con Ollama: {str(e)}"
            }