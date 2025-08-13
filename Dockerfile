# ------------------------------
# 1️⃣ Base image
# ------------------------------
FROM python:3.11-slim

# -------------------------------------------------
# 2️⃣ System packages + Chrome + ChromeDriver (Yahan tabdeeli ki gayi hai)
# -------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg curl unzip jq \
    # Google Chrome key add karne ka naya aur mehfooz tareeqa
    && install -m 0755 -d /etc/apt/keyrings \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /etc/apt/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list \
    # Ab Chrome install karein
    && apt-get update && apt-get install -y google-chrome-stable \
    # Safai
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------
# 3️⃣ ChromeDriver (match Chrome version)
# -------------------------------------------------
RUN LAST_KNOWN_GOOD_VERSION_URL="https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" && \
    CHROMEDRIVER_URL=$(curl -s $LAST_KNOWN_GOOD_VERSION_URL | \
        jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') && \
    wget -q $CHROMEDRIVER_URL -O chromedriver.zip && \
    unzip chromedriver.zip -d /usr/bin/ && \
    mv /usr/bin/chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
    chmod +x /usr/bin/chromedriver && \
    rm chromedriver.zip

# -------------------------------------------------
# 4️⃣ Working directory
# -------------------------------------------------
WORKDIR /app

# -------------------------------------------------
# 5️⃣ Python dependencies
# -------------------------------------------------
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -------------------------------------------------
# 6️⃣ Copy source code (including bot_fastapi.py)
# -------------------------------------------------
COPY . .

# -------------------------------------------------
# 7️⃣ Start command (FastAPI version)
# -------------------------------------------------
# Render sets `$PORT` automatically (default 10000)
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:${PORT:-10000}", "bot_fastapi:asgi_app"]
