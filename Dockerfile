# ------------------------------
# 1️⃣ Base image
# ------------------------------
FROM python:3.11-slim

# -------------------------------------------------
# 2️⃣ System packages + Chrome + ChromeDriver
#    (ek hi RUN block, proper line‑continuation)
# -------------------------------------------------
# Install basic utilities, tzdata (for correct timestamps)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    curl \
    jq \
    tzdata \
# ----------------------------------------------------------------
# Add Google Chrome repository (use gpg key, apt-key is deprecated)
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | \
        gpg --dearmor -o /usr/share/keyrings/google-linux-signing-key.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-key.gpg] \
        http://dl.google.com/linux/chrome/deb/ stable main" > \
        /etc/apt/sources.list.d/google.list \
# ----------------------------------------------------------------
# Install Chrome, then clean apt lists
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------
# 3️⃣ ChromeDriver – version is matched to installed Chrome
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
# 4️⃣ Work directory
# -------------------------------------------------
WORKDIR /app

# -------------------------------------------------
# 5️⃣ Python dependencies
# -------------------------------------------------
COPY requirements.txt .
# Upgrade pip first (helps on slim images)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# -------------------------------------------------
# 6️⃣ Copy source code
# -------------------------------------------------
COPY . .

# -------------------------------------------------
# 7️⃣ Start the ASGI server (Gunicorn + Uvicorn workers)
# -------------------------------------------------
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "bot:asgi_app"]
