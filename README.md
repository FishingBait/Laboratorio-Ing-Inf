# 🕸️ Web Parsing & Evaluation Pipeline

Un sistema software completo e automatizzato per estrarre, pulire e valutare contenuti testuali da pagine web complesse. Il progetto gestisce lo scraping dinamico, la pulizia del DOM e integra un sistema di valutazione ibrido (matematico e basato su Intelligenza Artificiale) per misurare la qualità dei dati estratti.

Questo progetto è stato sviluppato per l'esame di **Laboratorio di Informatica**, all'interno del corso di laurea in **Ingegneria Informatica** presso **Sapienza Università di Roma**.

## 👥 Autori
- **Lorenzo Bordi** (Matricola: 2066423)
- **Claudio Frontoni** (Matricola: 2089078)
- **Lorenzo Labella** (Matricola: 2135570)

---

## 🚀 Caratteristiche Principali

- **Scraping Dinamico:** Utilizzo di `Crawl4AI` e Chromium headless per eseguire il rendering del codice JavaScript (essenziale per siti moderni come Amazon).
- **Pulizia del DOM su misura:** Strategie di estrazione e filtraggio personalizzate per 4 domini complessi:
  - *Wikipedia:* Estrazione pulita del corpo escludendo tabelle e note.
  - *Il Manifesto:* Bypass di paywall e rimozione chirurgica di banner e call-to-action ("Abbonati").
  - *Amazon:* Filtraggio del rumore di marketing (caroselli, prodotti sponsorizzati).
  - *Rotten Tomatoes:* Utilizzo di Regex avanzate per mantenere intatti cast e trama rimuovendo recensioni esterne e gallerie media.
- **Valutazione Ibrida (Evaluation):**
  - **Token-Level:** Calcolo rigoroso di Precision, Recall e F1-Score tra il testo estratto e il Gold Standard.
  - **LLM Judge:** Valutazione qualitativa (voto 1-5 e feedback testuale) generata localmente da `llama3.2:3b` tramite **Ollama**.
- **Dashboard Web Resiliente:** Un frontend intuitivo sviluppato con FastAPI e Jinja2, dotato di *graceful degradation*: l'interfaccia non va in crash anche se i servizi sottostanti (DB o LLM) sono temporaneamente offline.
- **Supporto Offline (Test Grader):** Capacità di parsare codice HTML testuale fornito direttamente alla pipeline tramite la creazione *on-the-fly* di file temporanei, garantendo il superamento di test automatizzati su URL non più online.

---

## 🛠️ Stack Tecnologico

- **Backend / API:** Python 3, FastAPI, Pydantic, Httpx
- **Web Scraping:** Crawl4AI
- **Frontend:** FastAPI, Jinja2, Bootstrap 5
- **Database:** MariaDB
- **Intelligenza Artificiale:** Ollama (Modello: llama3.2:3b)
- **Infrastruttura:** Docker, Docker Compose

---

## ⚙️ Architettura del Database

Il sistema utilizza MariaDB con il seguente schema relazionale:
1. `web_resources`: Memorizza gli URL, i domini e l'HTML grezzo scaricato.
2. `gold_standard`: Memorizza i testi puliti di riferimento creati manualmente. Si lega a `web_resources` tramite l'URL.
3. `evaluations`: Funge da cache per le metriche F1 e i giudizi dell'LLM, permettendo tempi di caricamento istantanei per la dashboard delle statistiche.

---

## 📦 Installazione e Avvio

Il progetto è interamente containerizzato. Non è necessario installare Python o database localmente, basta avere Docker installato sul proprio sistema.

1. **Clona il repository:**
   ```bash
   git clone [https://github.com/tuo-username/nome-repo.git](https://github.com/tuo-username/nome-repo.git)
   cd nome-repo
2. **Avvia container docker:**
   ```bash
   docker compose up --build
