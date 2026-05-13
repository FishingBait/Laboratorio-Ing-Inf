"""
Modulo parser_logic.py
Gestisce il core dello scraping asincrono tramite Crawl4AI.
Si occupa di scaricare l'HTML (o leggerlo dal DB locale), estrarre il Markdown 
e applicare regole di pulizia specifiche per ogni dominio.
"""

import os
import tempfile
import re
from fastapi import HTTPException
from crawl4ai import AsyncWebCrawler
from utils import get_exact_domain, load_domains
from database import get_db_connection

async def perform_parse(url: str, local: bool = False, provided_html: str = ""):
    """
    Esegue il parsing di una pagina web restituendo il testo pulito in Markdown.
    
    Args:
        url (str): L'indirizzo della pagina da analizzare.
        local (bool): Se True, forza la lettura dell'HTML dal database locale (modalità offline).
        provided_html (str): HTML grezzo passato direttamente dal grader del professore.
        
    Returns:
        dict: Dizionario contenente url, dominio, titolo, html originale e testo parsato.
    """
    domain = get_exact_domain(url)
    clean_domain = domain[4:] if domain.startswith("www.") else domain
    
    # 1. Validazione del dominio contro la lista dei domini supportati
    if domain not in load_domains() and clean_domain not in load_domains():
        raise HTTPException(status_code=400, detail="Dominio non supportato")

    html_da_usare = provided_html

    # 2. Gestione offline e bypass paywall (es. Il Manifesto)
    # Se è richiesta la modalità locale, o se il sito ha un paywall e non ci è stato fornito HTML, cerchiamo nel DB.
    if local or ("ilmanifesto.it" in domain and not html_da_usare):
        conn = get_db_connection()
        if conn:
            cur = conn.cursor()
            cur.execute("SELECT html_text FROM web_resources WHERE url=?", (url,))
            row = cur.fetchone()
            if row and row[0]: 
                html_da_usare = row[0]
            conn.close()
            
        # Se l'utente ha richiesto esplicitamente 'local' ma il DB è vuoto, fermiamo l'esecuzione.
        if local and not html_da_usare:
            raise HTTPException(status_code=404, detail="URL non trovato nel Database per il parsing locale")

    crawl_url = url
    tmp_path = None
    html_to_return = html_da_usare

    # 3. Creazione di un file temporaneo locale
    # Crawl4AI ha bisogno di un URL o di un file fisico. Se abbiamo l'HTML in memoria,
    # creiamo un file finto per istruire il crawler a leggerlo dal disco anziché da internet.
    if html_da_usare:
        fd, tmp_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(html_da_usare)
        crawl_url = f"file://{tmp_path}"

    try:
        headers = {"Accept-Language": "it-IT,it;q=0.9"}
        async with AsyncWebCrawler(headers=headers) as crawler:
            
            # 4. Configurazione dinamica dei selettori CSS in base al dominio
            if "wikipedia.org" in domain:
                css_sel = "#bodyContent" # Puntiamo al corpo centrale, escludendo la sidebar
                esclusi = ['.navbox', '.toc', '.mw-editsection', '.hatnote', '#catlinks', '.printfooter', '.metadata', '.noprint', '.thumb', '.reference']
            elif "ilmanifesto.it" in domain:
                css_sel = "article"  
                esclusi = ['.header', '.footer', '.aside', '.ad', '.advertisement', '.related', '.social-share', 'figure', '.comments', '.newsletter-box']
            elif "rottentomatoes.com" in domain:
                css_sel = "main" 
                esclusi = ['rt-header', 'rt-footer', 'nav', '.ad-slot', '.ad-container', '#footer', 'rt-footer-nav', '.js-ad']
            elif "amazon.it" in domain:
                css_sel = "#centerCol" # Puntiamo al blocco centrale del prodotto
                esclusi = ['#promoPriceBlockMessage_feature_div', '#sns-right-box', '.a-popover-preload', '#buybox']
            else:
                css_sel = "body"
                esclusi = []
                
            # Esecuzione del crawler asincrono
            result = await crawler.arun(url=crawl_url, css_selector=css_sel, excluded_tags=esclusi)
            
            if not result.success: 
                raise HTTPException(status_code=400, detail="URL irraggiungibile o errore Crawler")
            
            testo_estratto = result.markdown
            if not testo_estratto: 
                testo_estratto = "## Contenuto vuoto\nTesto non trovato."
            if not html_to_return: 
                html_to_return = result.html or ""
            
            # --- 5. POST-PROCESSING E PULIZIA DEL TESTO ---
            # Applichiamo euristiche specifiche per rimuovere il "rumore" residuo che il crawler non ha filtrato
            
            if "wikipedia.org" in domain:
                # Troncamento alla fine del corpo principale (ignoriamo note e bibliografia)
                for s in ["## Note", "## Voci correlate", "## Altri progetti", "## Collegamenti esterni"]:
                    if s in testo_estratto: 
                        testo_estratto = testo_estratto.split(s)[0]
            
            elif "ilmanifesto.it" in domain:
                # Rimozione dei blocchi pubblicitari o suggerimenti di lettura interni all'articolo
                for s in ["Aggiornamenti", "### Da leggere", "**Esplora gli argomenti**", "Dalla parte del torto", "Registrati e scopri"]:
                    if s in testo_estratto: 
                        testo_estratto = testo_estratto.split(s)[0]
                
                # Rimozione del blocco paywall se accidentalmente incluso nel testo utile
                link_abbonamento = "](https://ilmanifesto.it/abbonamenti/acquista/abbonamento-digitale-4x4)"
                if link_abbonamento in testo_estratto: 
                    testo_estratto = testo_estratto.split(link_abbonamento)[-1]
                elif "Abbonati per 10 giorni" in testo_estratto: 
                    testo_estratto = testo_estratto.split("Abbonati per 10 giorni")[-1]

            elif "rottentomatoes.com" in domain:
                try:
                    # Normalizzazione degli header markdown
                    testo_estratto = re.sub(r'##\s+', '## ', testo_estratto)
                    
                    # Estrazione della parte centrale (Info del film) ignorando la testata della pagina
                    for marker in ["## Where to Watch", "## What to Know", "## Movie Info"]:
                        if marker in testo_estratto:
                            testo_estratto = marker + testo_estratto.split(marker, 1)[1]
                            break
                    
                    # Rimozione delle griglie raccomandate a fondo pagina
                    for marker in ["Most Popular at Home Now", "About Tomatometer", "Community Watch"]:
                        if marker in testo_estratto:
                            testo_estratto = testo_estratto.split(marker)[0]
                            
                    # Pulizia chirurgica della sezione "Movie Info", rimuovendo recensioni utenti e cast
                    if "## Movie Info" in testo_estratto:
                        inizio_spazzatura = -1
                        for trash in ["## Critics Reviews", "## Audience Reviews", "## My Rating", "## Cast & Crew", "## Photos", "## Videos"]:
                            idx = testo_estratto.find(trash)
                            if idx != -1 and (inizio_spazzatura == -1 or idx < inizio_spazzatura):
                                inizio_spazzatura = idx
                        
                        if inizio_spazzatura != -1:
                            parte_iniziale = testo_estratto[:inizio_spazzatura]
                            parte_finale = "## Movie Info" + testo_estratto.split("## Movie Info")[-1]
                            testo_estratto = parte_iniziale + "\n" + parte_finale
                except Exception as e:
                    print(f"⚠️ Errore pulizia Rotten Tomatoes ignorato: {e}")
                    pass # Silenziamo l'errore per non interrompere la pipeline e restituire comunque il testo parziale
                    
            elif "amazon.it" in domain:
                try:
                    # Estrazione del titolo del prodotto
                    linee = [line for line in testo_estratto.split('\n') if line.strip()]
                    titolo = linee[1] if len(linee) > 1 else ""
                    
                    # Ricerca del punto d'inizio delle informazioni utili sul prodotto
                    inizio_utile = -1
                    for marker in ["Opzioni di acquisto", "Specifiche prodotto", "Dettagli prodotto", "Informazioni su questo articolo"]:
                        idx = testo_estratto.find(marker)
                        if idx != -1:
                            inizio_utile = idx
                            break
                    if inizio_utile != -1:
                        parte_utile = testo_estratto[inizio_utile:]
                        testo_estratto = titolo + "\n\n### " + parte_utile
                        
                    # Troncamento delle sezioni di marketing e up-selling di Amazon
                    cut_words = [
                        "› [ Visualizza", "› Visualizza", "Visualizza altri dettagli", "Brief content visible",
                        "Marchio di qualità", "Spesso comprati insieme", "Prodotti correlati", "Descrizione prodotto"
                    ]
                    for cw in cut_words:
                        if cw in testo_estratto:
                            testo_estratto = testo_estratto.split(cw)[0]
                            
                    # Pulizia tramite Regex di bottoni javascript e immagini rotte rimaste nel Markdown
                    testo_estratto = re.sub(r'\[.*?\]\(javascript:void\\\(0\\\)\)', '', testo_estratto)
                    testo_estratto = re.sub(r'!\[.*?\]\(.*?\)', '', testo_estratto)
                except Exception as e:
                    print(f"⚠️ Errore pulizia Amazon ignorato: {e}")
                    pass 
            
            # Ritorno dell'oggetto finale formattato
            return {
                "url": url,
                "domain": clean_domain,
                "title": url.split("/")[-1],
                "html_text": html_to_return,
                "parsed_text": testo_estratto.strip()
            }
    finally:
        # 6. Pulizia di sistema
        # Garantiamo sempre la rimozione del file temporaneo creato al punto 3,
        # anche in caso di eccezioni o crash del parser, per non intasare l'hard disk del container.
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)