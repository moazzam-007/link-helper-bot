# UPDATED bot.py (only relevant parts shown, replace your original file)
import os
import re
import requests
import telegram
import asyncio
import random
from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin
from queue import Queue
from threading import Thread
from telegram.request import HTTPXRequest

# ---------------------------
# Config / env
# ---------------------------
TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_CHROME_BIN = os.environ.get("GOOGLE_CHROME_BIN", "/usr/bin/google-chrome")

# ---------------------------
# HTTPXRequest initialization (use documented args, NOT httpx_settings=)
# ---------------------------
# Use connection_pool_size to control max concurrent connections the PTB request uses.
# Use connect/read/write timeouts to avoid long hangs.
request = HTTPXRequest(
    connect_timeout=10.0,
    read_timeout=20.0,
    write_timeout=20.0,
    pool_timeout=5.0,
    connection_pool_size=25,   # roughly equivalent to your previous max_connections
)

bot = telegram.Bot(token=TOKEN, request=request)

# ---------------------------
# Helper functions
# ---------------------------
def get_links_with_selenium(page_url):
    print(f"Selenium worker starting for: {page_url}")
    chrome_options = Options()
    # newer chrome headless flag can be --headless=new but --headless is fine for compatibility
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.binary_location = GOOGLE_CHROME_BIN

    driver = None
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(page_url)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/share/']"))
        )
        link_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/share/']")
        found_links = {urljoin(page_url, tag.get_attribute('href')) for tag in link_elements if tag.get_attribute('href')}
        print(f"Selenium found {len(found_links)} unique links.")
        return list(found_links)
    except Exception as e:
        print(f"Selenium Error: {e}")
        return None
    finally:
        if driver:
            driver.quit()

def get_final_url_from_redirect(start_url, max_redirects=5):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        # requests will follow redirects and stop if too many
        resp = requests.get(start_url, timeout=15, headers=headers, allow_redirects=True)
        return resp.url
    except requests.RequestException as e:
        print(f"Redirect Error for {start_url}: {e}")
        return None

# safer URL extractor handling both 'url' and 'text_link' entity types
def find_url_in_message(message):
    if getattr(message, "entities", None):
        for entity in message.entities:
            if entity.type == 'text_link' and getattr(entity, "url", None):
                return entity.url
            if entity.type == 'url' and message.text:
                # extract substring using offset/length (works for plain url entities)
                return message.text[entity.offset: entity.offset + entity.length]
    if message.text:
        match = re.search(r'https?://\S+', message.text)
        if match:
            return match.group(0)
    return None

# ---------------------------
# Worker / job queue (unchanged mostly)
# ---------------------------
job_queue = Queue()

DISCOUNT_PERCENTAGES = [
    '30%', '35%', '40%', '45%', '50%', '55%', '60%', '65%', '70%', '75%', '80%',
    # ... (rest omitted for brevity) ...
    '90%'
]

def worker():
    while True:
        chat_id, message_id, url_to_process = job_queue.get()
        try:
            print(f"Worker processing URL for chat {chat_id}: {url_to_process}")
            all_final_links = []
            redirect_links = get_links_with_selenium(url_to_process)

            if redirect_links is None:
                response_message = "Maaf kijiye, is link se products nahi mil paaye. 🙁\nHo sakta hai link galat ho ya private ho."
                # use asyncio.run here because we're in a background thread; it's acceptable for occasional calls
                asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_message))
                job_queue.task_done()
                continue

            for r_link in redirect_links:
                final_link = get_final_url_from_redirect(r_link)
                if final_link:
                    all_final_links.append(final_link)

            if all_final_links:
                response_parts = []
                for i, link in enumerate(all_final_links, 1):
                    discount = random.choice(DISCOUNT_PERCENTAGES)
                    # Use Markdown link to keep message tidy
                    response_parts.append(f"{i}. ({discount} OFF) [Open link]({link})")
                response_message = "\n\n".join(response_parts)
                asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id,
                                                  text=response_message, parse_mode="Markdown"))
            else:
                response_message = "Is link mein koi product links nahi mile. Please doosra link try karein."
                asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_message))

        except Exception as e:
            print(f"Worker unexpected error: {e}")
            asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="Kuch takneeki samasya aa gayi hai. Kripya baad mein prayas karein."))
        finally:
            job_queue.task_done()

Thread(target=worker, daemon=True).start()

# ---------------------------
# Flask webhook (unchanged)
# ---------------------------
app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

async def handle_update(update_data):
    update = telegram.Update.de_json(update_data, bot)
    if not update.message:
        return

    chat_id = update.message.chat.id
    message = update.message

    if message.text and message.text.strip() == "/start":
        welcome_message = "Hi! I am your Link Helper Bot. ✨\n\nPlease send or forward me a Wishlink page URL to get started."
        await bot.send_message(chat_id=chat_id, text=welcome_message)
        return

    url_found = find_url_in_message(message)
    if url_found and 'wishlink.com' in url_found.lower():
        sent_message = await bot.send_message(chat_id=chat_id, text="Processing... ⏳")
        job_queue.put((chat_id, sent_message.message_id, url_found))
    else:
        await bot.send_message(chat_id=chat_id, text="Please send me a message that contains a valid **wishlink.com** URL.")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook_handler():
    update_data = request.get_json(force=True)
    asyncio.run(handle_update(update_data))
    return 'ok'
