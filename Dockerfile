# Python ka base image istemal kar rahe hain
FROM python:3.11-slim

# Zaroori packages, Google Chrome, aur JSON processor install kar rahe hain
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    curl \
    jq \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# NAYA AUR SAHI TAREEKA: ChromeDriver install kar rahe hain
RUN LAST_KNOWN_GOOD_VERSION_URL="https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" && \
    CHROMEDRIVER_URL=$(curl -s $LAST_KNOWN_GOOD_VERSION_URL | jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') && \
    wget -q $CHROMEDRIVER_URL -O chromedriver.zip && \
    unzip chromedriver.zip -d /usr/bin/ && \
    mv /usr/bin/chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
    chmod +x /usr/bin/chromedriver && \
    rm chromedriver.zip

# Kaam karne ke liye ek directory bana rahe hain
WORKDIR /app

# Requirements file copy aur install kar rahe hain
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baaki saari project files copy kar rahe hain
COPY . .

# Server ko start karne ka command
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "bot:asgi_app"]
