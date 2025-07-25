import os
import re
import requests # Iski zaroorat ab sirf synchronous function ke liye hai
import httpx     # Naya import async requests ke liye
import json
from flask import Flask, request
import telegram
import asyncio

# ===================================================================
# === Helper functions (Ab Async/Await ke saath) ===
# ===================================================================

async def get_final_url_from_redirect(start_url: str) -> str | None:
    try:
        async with httpx.AsyncClient() as client:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"}
            response = await client.get(start_url, headers=headers, timeout=15, follow_redirects=True)
            return str(response.url)
    except httpx.RequestError:
        return None

async def get_links_via_api(page_url: str) -> list:
    match = re.search(r'/post/(\d+)', page_url)
    if not match:
        return []
    post_id = match.group(1)

    headers = {
        'accept': '*/*', 'accept-language': 'en-GB,en-IN;q=0.9,en-US;q=0.8,en;q=0.7,hi;q=0.6',
        'content-type': 'application/json', 'gaid;': '', 'origin': 'https://www.wishlink.com',
        'priority': 'u=1, i', 'referer': 'https://www.wishlink.com/',
        'sec-ch-ua': '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"', 'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-site',
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36',
    }
    
    api_url = f'https://api.wishlink.com/api/store/getPostOrCollectionProducts?page=1&limit=50&postType=POST&postOrCollectionId={post_id}&sourceApp=STOREFRONT'
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, headers=headers, timeout=20)
            response.raise_for_status()
            data = response.json()
            products = data.get('data', {}).get('products', [])
            final_product_links = [product['purchaseUrl'] for product in products if 'purchaseUrl' in product]
            return final_product_links
    except httpx.RequestError:
        return []

# =======================================================
# === Telegram Bot aur Web Service ka Code ===
# =======================================================

TOKEN = os.environ.get('TELEGRAM_TOKEN')
bot = telegram.Bot(token=TOKEN)
app = Flask(__name__)
from asgiref.wsgi import WsgiToAsgi # Yeh line sabse upar imports ke saath daalein

# ... baaki ka code ...

app = Flask(__name__)
asgi_app = WsgiToAsgi(app) # Yeh nayi line app = Flask... ke theek neeche daalein

async def handle_update(update):
    """Is function mein bot ka saara async logic hai."""
    if not update.message or not update.message.text:
        return
        
    chat_id = update.message.chat.id
    text = update.message.text

    if text == "/start":
        welcome_message = "Hi! I am your Link Helper Bot. \n\nPlease send me a Wishlink URL to get started."
        await bot.send_message(chat_id=chat_id, text=welcome_message)
        return

    try:
        await bot.send_message(chat_id=chat_id, text="Processing... Please wait. ⏳")
        
        all_final_links = []
        if '/share/' in text:
            # Ab hum async function ko await karenge
            final_link = await get_final_url_from_redirect(text)
            if final_link:
                all_final_links.append(final_link)
        else:
            # Ab hum async function ko await karenge
            links_from_api = await get_links_via_api(text)
            if links_from_api:
                all_final_links.extend(links_from_api)

        if all_final_links:
            response_message = f"Done! ✨\nFound {len(all_final_links)} links:\n\n" + "\n\n".join(all_final_links)
        else:
            response_message = "Sorry, I couldn't find any links from the URL you provided. Please check the link and try again."
            
        await bot.send_message(chat_id=chat_id, text=response_message)
        
    except Exception as e:
        await bot.send_message(chat_id=chat_id, text=f"An error occurred: {e}")

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    asyncio.run(handle_update(update))
    return 'ok'

@app.route('/')
def index():
    return 'Bot is running!'

if __name__ == "__main__":
    app.run(threaded=True)
