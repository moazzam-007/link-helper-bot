import os
import re
import requests
import telegram
import asyncio
import random  # For random discounts/tags
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
        print(f"Selenium found {len(found_links)} links.")
        return list(found_links)
    except Exception as e:
        print(f"Selenium Error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

def get_final_url_from_redirect(start_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"}
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

def worker():
    """Yeh worker queue se jobs uthata hai aur process karta hai."""
    while True:
        chat_id, text = job_queue.get()
        try:
            all_final_links = []
            if '/share/' in text:
                link = get_final_url_from_redirect(text)
                if link:
                    all_final_links.append(link)
            else:
                redirect_links = get_links_with_selenium(text)
                for r_link in redirect_links:
                    final_link = get_final_url_from_redirect(r_link)
                    if final_link:
                        all_final_links.append(final_link)

            if all_final_links:
                # === UPDATED RESPONSE WITH VARIETY & SPACING ===
                response_lines = []
                # List of promotional tags for variety
                promo_tags = [
                    "🔥 Hot Deal",
                    "💰 Budget Buster",
                    "⭐ Best Offer",
                    "🎁 Limited Time",
                    "🚀 Flash Sale",
                    "✨ Exclusive Deal",
                    "🛒 Shop Now",
                    "🎯 Top Pick",
                    "🎉 Special Offer",
                    "💎 Premium Choice"
                ]
                
                for i, link in enumerate(all_final_links, 1):
                    # Random discount (50-100%) and random tag
                    discount = random.randint(50, 100)
                    tag = random.choice(promo_tags)
                    
                    # Format each link with tag, discount, and spacing
                    response_lines.append(
                        f"{tag} ({discount}% OFF)\n{link}\n\n"
                    )
                
                response_message = "🔥 Hot Deals Found!\n\n" + "".join(response_lines)
                # === END OF UPDATE ===
            else:
                response_message = "Sorry, I couldn't find any links. Please check the URL and try again."

            # Worker synchronous hai, isliye asyncio.run() se message bhej rahe hain
            asyncio.run(bot.send_message(chat_id=chat_id, text=response_message))

        except Exception as e:
            error_message = f"An error occurred: {e}"
            print(error_message)
            asyncio.run(bot.send_message(chat_id=chat_id, text=error_message))
        finally:
            job_queue.task_done()

# Worker thread ko start kar rahe hain
Thread(target=worker, daemon=True).start()

# =======================================================
# === Server Code (Jo Sirf Order Leta Hai) ===
# =======================================================

app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

async def handle_update(update_data):
    """Yeh function ab sirf job ko queue mein daalta hai."""
    update = telegram.Update.de_json(update_data, bot)
    if not update.message or not update.message.text:
        return
        
    chat_id = update.message.chat.id
    text = update.message.text

    if text == "/start":
        welcome_message = "Hi! Send me a WishLink URL to get instant deals 🔍"
        await bot.send_message(chat_id=chat_id, text=welcome_message)
        return

    # User ko turant reply bhej rahe hain aur job queue mein daal rahe hain
    await bot.send_message(chat_id=chat_id, text="Scanning for deals... ⏳")
    job_queue.put((chat_id, text))

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    update_data = request.get_json(force=True)
    asyncio.run(handle_update(update_data))
    return 'ok'

@app.route('/')
def index():
    return 'Bot is running!'
