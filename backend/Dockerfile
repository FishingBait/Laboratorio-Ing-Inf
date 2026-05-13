FROM python:3.10-slim

# 1. Installiamo i driver, i compilatori e le dipendenze di sistema
RUN apt-get update && \
    apt-get install -y libmariadb-dev libmariadb-dev-compat gcc build-essential pkg-config python3-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# 2. Aggiorniamo pip
RUN pip install --upgrade pip

# 3. Installiamo i pacchetti
RUN pip install --no-cache-dir -r requirements.txt

# 4. FIX ERRORE 127: Installiamo i browser direttamente dal modulo Python di Playwright
RUN python -m playwright install --with-deps chromium

# 5. Copiamo il codice
# FIX: Invece di creare una sottocartella, copiamo tutto direttamente in /app
COPY src/ .

EXPOSE 8003

# FIX: Ora che i file sono nella directory principale, avviamo direttamente main:app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003"]