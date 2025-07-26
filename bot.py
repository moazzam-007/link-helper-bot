import os
import re
import httpx # requests ko httpx se replace kar rahe hain
from flask import Flask, request
from asgiref.wsgi import WsgiToAsgi
import telegram
import asyncio
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urljoin

# =======================================================
# === Helper Functions (Fully Async/Optimized) ===
# =======================================================
def get_links_with_selenium(page_url):
    print("Selenium ke zariye links nikale ja rahe hain...")
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
        
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/share/']"))
        )
        
        link_elements = driver.find_elements(By.CSS_SELECTOR, "a[href*='/share/']")
        found_links = set()
        for link_tag in link_elements:
            href = link_tag.get_attribute('href')
            if href:
                full_redirect_link = urljoin(page_url, href)
                found_links.add(full_redirect_link)
        
        print(f"Selenium se {len(found_links)} links mile.")
        return list(found_links)

    except Exception as e:
        print(f"Selenium Error: {e}")
        return []
    finally:
        if driver:
            driver.quit()

# === YAHAN BADLAAV KIYA GAYA HAI ===
# requests ko httpx se badal diya gaya hai
async def get_final_url_from_redirect(start_url: str) -> str | None:
    try:
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"}
            response = await client.get(start_url, headers=headers, timeout=15, follow_redirects=True)
            return str(response.url)
    except httpx.RequestError as e:
        print(f"Redirect Error: {e}")
        return None
        
# =======================================================
# === Bot Logic & Server Code ===
# =======================================================

TOKEN = os.environ.get('TELEGRAM_TOKEN')
bot = telegram.Bot(token=TOKEN)
app = Flask(__name__)
asgi_app = WsgiToAsgi(app)

async def handle_update(update_data):
    update = telegram.Update.de_json(update_data, bot)
    if not update.message or not update.message.text:
        return
        
    chat_id = update.message.chat.id
    text = update.message.text

    if text == "/start":
        await bot.send_message(chat_id=chat_id, text="Hi! I am your Link Helper Bot. \n\nPlease send me a Wishlink URL to get started.")
        return

    try:
        await bot.send_message(chat_id=chat_id, text="Processing... Please wait. ⏳")
        
        loop = asyncio.get_running_loop()
        all_final_links = []
        
        if '/share/' in text:
            # Ab hum async function ko await karenge
            link = await get_final_url_from_redirect(text)
            if link:
                all_final_links.append(link)
        else:
            # Lambe Selenium process ko alag thread me chala rahe hain
            redirect_links = await loop.run_in_executor(None, get_links_with_selenium, text)
            
            # === YAHAN BHI BADLAAV KIYA GAYA HAI ===
            # Ab hum in links ko aaram se async tareeke se check karenge
            tasks = [get_final_url_from_redirect(r_link) for r_link in redirect_links]
            results = await asyncio.gather(*tasks)
            all_final_links = [res for res in results if res is not None]

        if all_final_links:
            response_message = f"Done! ✨\nFound {len(all_final_links)} links:\n\n" + "\n\n".join(all_final_links)
        else:
            response_message = "Sorry, I couldn't find any links. Please check the URL and try again."
            
        await bot.send_message(chat_id=chat_id, text=response_message)
        
    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)
        await bot.send_message(chat_id=chat_id, text=error_message)

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    update_data = request.get_json(force=True)
    asyncio.run(handle_update(update_data))
    return 'ok'

@app.route('/')
def index():
    return 'Bot is running!'
