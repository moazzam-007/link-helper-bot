# bot_fastapi.py
import os, random, logging, asyncio
from urllib.parse import urljoin
from queue import Queue
from threading import Thread

import httpx, telegram
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import NetworkError, TimedOut
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
# YAHAN SE WsgiToAsgi WALA IMPORT HATA DIYA GAYA HAI
from dotenv import load_dotenv

# ------------------------------------------------------------
# 1️⃣ Environment & Logging
# ------------------------------------------------------------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN not set in environment")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ------------------------------------------------------------
# 2️⃣ Global async http client (large connection pool)
# ------------------------------------------------------------
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
    timeout=httpx.Timeout(30.0, read=30.0, write=30.0, connect=15.0),
)

# ------------------------------------------------------------
# 3️⃣ Telegram Bot (uses the same http client)
# ------------------------------------------------------------
bot = Bot(token=TOKEN, request=telegram.Request(httpclient=http_client))

# ------------------------------------------------------------
# 4️⃣ Random “Deal” titles — आपका चाहा फ़ॉर्मेट
# ------------------------------------------------------------
DEAL_TITLES = [
    "Loot Deal", "Price Alert", "Super Sale", "Budget Deal", "Mega Discount",
    "Flash Offer", "Hot Pick", "Special Savings", "Crazy Deal", "Limited Time",
    "Best Price", "Exclusive Offer", "Deal of the Day", "Clearance",
]

def format_output(link: str) -> str:
    """(xx% OFF) https://example.com … — RandomTitle"""
    discount = random.randint(10, 70)          # 10‑70 %
    title    = random.choice(DEAL_TITLES)
    return f"({discount}% OFF) {link}  — {title}"

# ------------------------------------------------------------
# 5️⃣ Selenium – अभी भी sync (क्यू में background worker चलाता है)
# ------------------------------------------------------------
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def get_links_with_selenium(page_url: str):
    logging.info(f"Selenium processing: {page_url}")
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

        # Wait for any <a href="…/share/…">
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/share/']"))
        )
        elems = driver.find_elements(By.CSS_SELECTOR, "a[href*='/share/']")
        return [
            urljoin(page_url, e.get_attribute("href"))
            for e in elems if e.get_attribute("href")
        ]
    finally:
        if driver:
            driver.quit()

# ------------------------------------------------------------
# 6️⃣ Async helper – final URL after all redirects
# ------------------------------------------------------------
async def resolve_redirect(url: str) -> str | None:
    try:
        resp = await http_client.get(url, follow_redirects=True)
        return str(resp.url)
    except Exception as exc:
        logging.error(f"Redirect error for {url}: {exc}")
        return None

# ------------------------------------------------------------
# 7️⃣ Background worker (async queue) – एक ही worker पर्याप्त है,
#     आप ज़रूरत पड़ने पर कई workers बना सकते हैं
# ------------------------------------------------------------
job_queue: asyncio.Queue = asyncio.Queue()

async def worker():
    while True:
        chat_id, text = await job_queue.get()
        try:
            final_links = []

            if "/share/" in text:
                # सीधे एक share‑link → सिर्फ redirect resolve
                link = await resolve_redirect(text)
                if link:
                    final_links.append(link)
            else:
                # Selenium के साथ कई share‑links निकालें
                loop = asyncio.get_event_loop()
                selenium_links = await loop.run_in_executor(
                    None, get_links_with_selenium, text
                )
                for sl in selenium_links:
                    rl = await resolve_redirect(sl)
                    if rl:
                        final_links.append(rl)

            if final_links:
                formatted = "\n".join(format_output(l) for l in final_links)
                reply = f"Done! ✨\nFound {len(final_links)} link(s):\n\n{formatted}"
            else:
                reply = "Sorry, I couldn't find any links. Please check the URL and try again."

            await bot.send_message(chat_id=chat_id, text=reply)

        except (NetworkError, TimedOut) as exc:
            logging.warning(f"Network glitch: {exc}")
            await bot.send_message(chat_id=chat_id, text=str(exc))

        except Exception as exc:
            logging.exception("Worker error")
            await bot.send_message(chat_id=chat_id, text=f"Error: {exc}")

        finally:
            job_queue.task_done()

# ------------------------------------------------------------
# 8️⃣ FastAPI app (ASGI) – Render में यही सर्विस चलती है
# ------------------------------------------------------------
app = FastAPI()
# YAHAN SE 'asgi_app = WsgiToAsgi(app)' WALI LINE HATA DI GAYI HAI

@app.on_event("startup")
async def startup_event():
    # शुरू‑में एक worker task बनाओ
    asyncio.create_task(worker())
    logging.info("✅ Background worker started")

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        update_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    # FastAPI के इवेंट‑लूप में सीधे कॉल – **कोई asyncio.run नहीं**
    await handle_update(update_data)
    return JSONResponse(content={"ok": True})

# -----------------------------------------------------------------
# Update dispatcher (जैसे पहले था, अब async)
# -----------------------------------------------------------------
async def handle_update(update_data: dict):
    update = telegram.Update.de_json(update_data, bot)

    # सिर्फ़ टेक्स्ट‑मैसेज प्रोसेस
    if not (update.message and update.message.text):
        return

    chat_id = update.message.chat.id
    text    = update.message.text.strip()

    if text == "/start":
        await bot.send_message(
            chat_id=chat_id,
            text="Hi! I am your Link Helper Bot.\n\nSend me a Wishlink URL and I'll fetch the product links for you."
        )
        return

    # तुरंत “Processing…” संदेश भेजो
    await bot.send_message(chat_id=chat_id, text="Processing... Please wait. ⏳")
    await job_queue.put((chat_id, text))

@app.get("/")
def index():
    return "Bot is running – FastAPI version!"

# ------------------------------------------------------------
# 9️⃣ Graceful shutdown (optional)
# ------------------------------------------------------------
import atexit

@atexit.register
def shutdown():
    logging.info("Closing http client …")
    asyncio.run(http_client.aclose())
