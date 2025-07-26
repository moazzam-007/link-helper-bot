# Python ka base image istemal kar rahe hain
FROM python:3.11-slim

# Zaroori packages aur Google Chrome install kar rahe hain
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    unzip \
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y \
    google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# ChromeDriver install kar rahe hain
RUN CHROME_VERSION=$(google-chrome --version | cut -f 3 -d ' ' | cut -d '.' -f 1-3) && \
    DRIVER_VERSION=$(wget -qO- https://chromedriver.storage.googleapis.com/LATEST_RELEASE_${CHROME_VERSION}) && \
    wget https://chromedriver.storage.googleapis.com/${DRIVER_VERSION}/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/bin/chromedriver && \
    chown root:root /usr/bin/chromedriver && \
    chmod +x /usr/bin/chromedriver && \
    rm chromedriver_linux64.zip

# Kaam karne ke liye ek directory bana rahe hain
WORKDIR /app

# Requirements file copy aur install kar rahe hain
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Baaki saari project files copy kar rahe hain
COPY . .

# Server ko start karne ka command
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "bot:asgi_app"]
