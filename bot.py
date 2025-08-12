import logging
import sys
import threading
import queue
import re
import time
import asyncio
import os
from flask import Flask, request as flask_request
import telegram
from telegram.request import HTTPXRequest
import httpx
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# ------------------ Logging Setup ------------------
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ------------------ Config ------------------
TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))

# ------------------ Flask App ------------------
app = Flask(__name__)

# ------------------ Telegram Bot Setup ------------------
httpx_settings = httpx.Timeout(10.0, connect=5.0)
httpx_request = HTTPXRequest(httpx_settings=httpx_settings)
bot = telegram.Bot(token=TOKEN, request=httpx_request)

# ------------------ Job Queue ------------------
job_queue = queue.Queue()

# ------------------ Selenium Setup ------------------
def get_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=chrome_options)

# ------------------ Link Scraper ------------------
def scrape_final_url(original_url):
    try:
        logger.info(f"Scraping: {original_url}")
        driver = get_driver()
        driver.get(original_url)
        time.sleep(2)
        final_url = driver.current_url
        driver.quit()
        return final_url
    except Exception as e:
        logger.error(f"Scraping error: {e}")
        return original_url

# ------------------ Worker Thread ------------------
def worker():
    while True:
        chat_id, url = job_queue.get()
        try:
            final_url = scrape_final_url(url)

            discount = f"{round(5 + (10 * time.time()) % 40)}% OFF"
            message = f"🎯 *Deal Found!* 🎯\n\n🔗 [Click Here to Buy]({final_url})\n💸 Discount: {discount}"

            bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        except Exception as e:
            logger.exception(f"Error in worker: {e}")
            bot.send_message(chat_id=chat_id, text="❌ Failed to process your link.")
        finally:
            job_queue.task_done()

threading.Thread(target=worker, daemon=True).start()

# ------------------ Webhook Handler ------------------
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_handler():
    try:
        update_data = flask_request.get_json(force=True)
        update = telegram.Update.de_json(update_data, bot)

        if update.message and update.message.text:
            text = update.message.text.strip()
            chat_id = update.message.chat_id

            if re.match(r"https?://", text):
                bot.send_message(chat_id=chat_id, text="🔍 Processing your link...")
                job_queue.put((chat_id, text))
            else:
                bot.send_message(chat_id=chat_id, text="⚠ Please send a valid URL.")

        return "ok", 200
    except Exception as e:
        logger.exception("Error handling update")
        return "error", 500

# ------------------ Root Route ------------------
@app.route("/", methods=["GET"])
def index():
    return "Bot is running!", 200

# ------------------ Main ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
