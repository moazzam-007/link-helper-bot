import os
import re
import requests
import json
from flask import Flask, request
import telegram

# ===================================================================
# === Purane functions jo humne pehle banaye the (koi badlaav nahi) ===
# ===================================================================

def get_final_url_from_redirect(start_url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"}
        response = requests.get(start_url, timeout=15, headers=headers, allow_redirects=True)
        return response.url
    except requests.RequestException:
        return None

def get_links_via_api(page_url):
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
    
    try:
        api_url = f'https://api.wishlink.com/api/store/getPostOrCollectionProducts?page=1&limit=50&postType=POST&postOrCollectionId={post_id}&sourceApp=STOREFRONT'
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        products = data.get('data', {}).get('products', [])
        final_product_links = [product['purchaseUrl'] for product in products if 'purchaseUrl' in product]
        return final_product_links
    except requests.RequestException:
        return []

# ================================================
# === Naya Code: Telegram Bot aur Web Service ===
# ================================================

# BotFather se mila token yahan daalna hai, lekin hum ise Environment Variable se lenge
TOKEN = os.environ.get('TELEGRAM_TOKEN')
bot = telegram.Bot(token=TOKEN)

# Flask Web Service start kar rahe hain
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    # Telegram se aaya hua message
    update = telegram.Update.de_json(request.get_json(force=True), bot)
    
    chat_id = update.message.chat.id
    text = update.message.text

    # User ke message ko process kar rahe hain
    try:
        bot.send_message(chat_id=chat_id, text="Processing... Please wait.")
        
        # User ne jo link bheja hai, uspar kaam shuru
        all_final_links = []
        if '/share/' in text:
            final_link = get_final_url_from_redirect(text)
            if final_link:
                all_final_links.append(final_link)
        else:
            links_from_api = get_links_via_api(text)
            if links_from_api:
                all_final_links.extend(links_from_api)

        # Result wapas bhej rahe hain
        if all_final_links:
            response_message = f"Found {len(all_final_links)} links:\n\n" + "\n\n".join(all_final_links)
        else:
            response_message = "Sorry, I couldn't find any links from the URL you provided."
            
        bot.send_message(chat_id=chat_id, text=response_message)
        
    except Exception as e:
        bot.send_message(chat_id=chat_id, text=f"An error occurred: {e}")
        
    return 'ok'

# Ek simple sa route yeh check karne ke liye ki service chal rahi hai ya nahi
@app.route('/')
def index():
    return 'Bot is running!'

if __name__ == "__main__":
    app.run(threaded=True)
