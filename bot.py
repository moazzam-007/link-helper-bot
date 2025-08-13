# -*- coding: utf-8 -*-
import os
import re
import random
import asyncio
import logging
from queue import Queue
from threading import Thread
from urllib.parse import urljoin

import requests
import telegram
from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv

# ------------------------------------------------------------
# Load env‑variables (TOKEN, etc.)
# ------------------------------------------------------------
load_dotenv()                     # reads .env if present
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("❗️ TELEGRAM_TOKEN not set in environment")

# ------------------------------------------------------------
# Logging – helpful while debugging on Render
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ------------------------------------------------------------
# Helper: random title + random discount formatting
# ------------------------------------------------------------
DEAL_TITLES = [
    "Loot Deal", "Price Alert", "Super Sale", "Budget Deal", "Mega Discount",
    "Flash Offer", "Hot Pick", "Special Savings", "Crazy Deal", "Limited Time",
    "Best Price", "Exclusive Offer", "Deal of the Day", "Clearance"
]

def format_output(link: str) -> str:
    """
    Returns a string like "(45% OFF) https://example.com/product"
    The discount and title are random – just for display purposes.
    """
    discount = random.randint(10, 70)          # 10‑70 %
    title = random.choice(DEAL_TITLES)
    # You can prepend the title if you want, e.g. f"{title}: ({discount}% OFF) {link}"
    # Keeping exactly the format you asked for:
    return f"({discount}% OFF) {link}  — {title}"

# ------------------------------------------------------------
# Selenium – fetch share‑links from a page
# ------------------------------------------------------------
def get_links_with_selenium(page_url: str):
    logging.info(f"Selenium worker started for: {page_url}")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    # Path to Chrome binary inside the container
    chrome_options.binary_location = "/usr/bin/google-chrome"

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(page_url)

        # Wait for any link that contains '/share/'
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/share/']"))
        )
        elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/share/']")
        links = {
            urljoin(page_url, el.get_attribute("href"))
            for el in elements if el.get_attribute("href")
        }
        logging.info(f"Found {len(links)} share‑links via Selenium")
        return list(links)
    except Exception as exc:
        logging.error(f"Selenium error: {exc}")
        return []
    finally:
        if driver:
            driver.quit()

# ------------------------------------------------------------
# Simple GET‑redirect resolver (gives final destination URL)
# ------------------------------------------------------------
def get_final_url_from_redirect(start_url: str):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(start_url, timeout=15, headers=headers, allow_redirects=True)
        return resp.url
    except requests.RequestException as exc:
        logging.error(f"Redirect error for {start_url}: {exc}")
        return None

# ------------------------------------------------------------
# Telegram bot / job‑queue
# ------------------------------------------------------------
bot = telegram.Bot(token=TOKEN)
job_queue = Queue()

def worker():
    """Background thread that consumes (chat_id, text) jobs."""
    while True:
        chat_id, text = job_queue.get()
        try:
            final_links = []

            if "/share/" in text:
                # Direct short link – just resolve once
                link = get_final_url_from_redirect(text)
                if link:
                    final_links.append(link)
            else:
                # Need to scrape page for many share‑links first
                scraped_links = get_links_with_selenium(text)
                for sl in scraped_links:
                    resolved = get_final_url_from_redirect(sl)
                    if resolved:
                        final_links.append(resolved)

            if final_links:
                # Build the **pretty** output using format_output()
                formatted = "\n".join(format_output(l) for l in final_links)
                response = f"Done! ✨\nFound {len(final_links)} link(s):\n\n{formatted}"
            else:
                response = "Sorry, I couldn't find any links. Please check the URL and try again."

            asyncio.run(bot.send_message(chat_id=chat_id, text=response))
        except Exception as exc:
            err_msg = f"An error occurred: {exc}"
            logging.exception(err_msg)
            asyncio.run(bot.send_message(chat_id=chat_id, text=err_msg))
        finally:
            job_queue.task_done()

# Start the worker thread as daemon
Thread(target=worker, daemon=True).start()

# ------------------------------------------------------------
# Flask → ASGI (needed for Gunicorn + Uvicorn workers)
# ------------------------------------------------------------
app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

# ------------------------------------------------------------
# Async handler that just queues the job
# ------------------------------------------------------------
async def handle_update(update_data: dict):
    update = telegram.Update.de_json(update_data, bot)

    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat.id
    text = update.message.text.strip()

    if text == "/start":
        await bot.send_message(
            chat_id=chat_id,
            text="Hi! I am your Link Helper Bot.\n\nSend me a Wishlink URL and I'll fetch the product links for you."
        )
        return

    # Acknowledge immediately and push work to background
    await bot.send_message(chat_id=chat_id, text="Processing... Please wait. ⏳")
    job_queue.put((chat_id, text))

# ------------------------------------------------------------
# Webhook endpoints
# ------------------------------------------------------------
@app.route("/webhook", methods=["POST"])
def webhook_handler():
    update_data = request.get_json(force=True)
    # Run the async handler in a new event loop
    asyncio.run(handle_update(update_data))
    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

# ------------------------------------------------------------
# End of file
# ------------------------------------------------------------
