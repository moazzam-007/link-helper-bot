# Python base image
FROM python:3.11-slim

# System packages + Chrome + ChromeDriver
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    gnupg \
    unzip \
    curl \
    jq \
    tzdata \                         # <-- new, for proper timestamps
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Install the exact ChromeDriver version that matches Chrome
RUN LAST_KNOWN_GOOD_VERSION_URL="https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json" && \
    CHROMEDRIVER_URL=$(curl -s $LAST_KNOWN_GOOD_VERSION_URL | jq -r '.channels.Stable.downloads.chromedriver[] | select(.platform=="linux64") | .url') && \
    wget -q $CHROMEDRIVER_URL -O chromedriver.zip && \
    unzip chromedriver.zip -d /usr/bin/ && \
    mv /usr/bin/chromedriver-linux64/chromedriver /usr/bin/chromedriver && \
    chmod +x /usr/bin/chromedriver && \
    rm chromedriver.zip

# Working directory
WORKDIR /app

# Upgrade pip (good practice) and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY . .

# Run the ASGI server (Gunicorn + Uvicorn workers)
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "bot:asgi_app"]
