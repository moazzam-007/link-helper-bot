import os
import re
import requests
import telegram
import asyncio
import random # NAYA IMPORT: Random discount ke liye
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

# =======================================================
# === Helper Functions (Synchronous) ===
# =======================================================

def get_links_with_selenium(page_url):
    print(f"Selenium worker starting for: {page_url}")
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.binary_location = "/usr/bin/google-chrome"
    
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
        # Selenium fail hone par None return karenge taaki error handle kar sakein
        return None
    finally:
        if driver:
            driver.quit()

def get_final_url_from_redirect(start_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
        response = requests.get(start_url, timeout=15, headers=headers, allow_redirects=True)
        return response.url
    except requests.RequestException as e:
        print(f"Redirect Error for {start_url}: {e}")
        return None

# =======================================================
# === Background Worker (Jo Asli Kaam Karega) ===
# =======================================================

TOKEN = os.environ.get('TELEGRAM_TOKEN')
bot = telegram.Bot(token=TOKEN)
job_queue = Queue()

# NAYA CHANGE: Random discount percentages ki list
DISCOUNT_PERCENTAGES = [
    '30%', '35%', '40%', '45%', '50%', '55%', '60%', '65%', '70%', '75%', '80%',
    '25%', '28%', '32%', '36%', '38%', '42%', '44%', '48%', '52%', '54%', '58%',
    '62%', '64%', '68%', '72%', '78%', '82%', '43%', '47%', '51%', '53%', '57%',
    '59%', '61%', '63%', '66%', '69%', '71%', '73%', '74%', '76%', '77%', '79%',
    '81%', '83%', '84%', '85%', '86%', '87%', '88%', '89%', '90%'
]

def worker():
    while True:
        chat_id, message_id, url_to_process = job_queue.get()
        try:
            print(f"Worker processing URL for chat {chat_id}: {url_to_process}")
            all_final_links = []
            
            # Selenium se links nikalna
            redirect_links = get_links_with_selenium(url_to_process)
            
            # NAYA CHANGE: Behtar Error Handling
            if redirect_links is None: # Agar Selenium fail ho jaaye
                response_message = "Maaf kijiye, is link se products nahi mil paaye. 🙁\nHo sakta hai link galat ho ya private ho."
                asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_message))
                job_queue.task_done()
                continue

            for r_link in redirect_links:
                final_link = get_final_url_from_redirect(r_link)
                if final_link:
                    all_final_links.append(final_link)

            if all_final_links:
                # NAYA CHANGE: User ki demand ke anusaar naya output format
                response_parts = []
                for i, link in enumerate(all_final_links, 1):
                    discount = random.choice(DISCOUNT_PERCENTAGES)
                    # Format: 1. (45% OFF) https://link.com
                    response_parts.append(f"{i}. ({discount} OFF) {link}")
                
                # Sabhi links ke beech me double newline
                response_message = "\n\n".join(response_parts)
            else:
                response_message = "Is link mein koi product links nahi mile. Please doosra link try karein."
            
            # NAYA CHANGE: Purane message ko edit karna
            asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=response_message))

        except Exception as e:
            error_message = f"An unexpected error occurred: {e}"
            print(error_message)
            # Error aane par bhi message edit karna
            asyncio.run(bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="Kuch takneeki samasya aa gayi hai. Kripya baad mein prayas karein."))
        finally:
            job_queue.task_done()

Thread(target=worker, daemon=True).start()

# =======================================================
# === Server Code (Jo Sirf Order Leta Hai) ===
# =======================================================

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

def find_url_in_message(message):
    if message.entities:
        for entity in message.entities:
            if entity.type == 'url':
                return entity.url
    if message.text:
        match = re.search(r'https?://\S+', message.text)
        if match:
            return match.group(0)
    return None

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

    if url_found and 'wishlink.com' in url_found:
        # NAYA CHANGE: "Processing" message ka message_id save karna
        sent_message = await bot.send_message(chat_id=chat_id, text="Processing... ⏳")
        # Queue mein message_id bhi daalna taaki use edit kar sakein
        job_queue.put((chat_id, sent_message.message_id, url_found))
    else:
        await bot.send_message(chat_id=chat_id, text="Please send me a message that contains a valid **wishlink.com** URL.")

@app.route('/webhook', methods=['GET', 'POST'])
def webhook_handler():
    update_data = request.get_json(force=True)
    asyncio.run(handle_update(update_data))
    return 'ok'

@app.route('/')
def index():
    return 'Bot is running!'
