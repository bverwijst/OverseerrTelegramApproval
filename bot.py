import os
import logging
import threading
import asyncio
from flask import Flask, request, abort
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, ContextTypes
import requests

from dotenv import load_dotenv
load_dotenv()

# --- Foolproof Environment Variable Checking ---
def check_env(var, name, is_secret=False):
    if var is None or var == "":
        logging.critical(f"Environment variable {name} is MISSING!")
        return False
    placeholder_values = [
        f"your-{name.lower().replace('_', '-')}",
        "changeme",
        "<changeme>",
        "<your-value-here>",
        "replace-me"
    ]
    if str(var).lower() in placeholder_values:
        logging.error(f"Environment variable {name} is set to a placeholder value ({var!r})! Please set a real value.")
        return False
    logging.info(f"{name} loaded: {'***' if is_secret else var}")
    return True

# --- Load and Check Environment Variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OVERSEERR_API_URL = os.getenv("OVERSEERR_API_URL")
OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = os.getenv("PORT", "8080")

logging.basicConfig(level=logging.INFO)

all_env_ok = True
all_env_ok &= check_env(TELEGRAM_BOT_TOKEN, "TELEGRAM_BOT_TOKEN", is_secret=True)
all_env_ok &= check_env(TELEGRAM_CHAT_ID, "TELEGRAM_CHAT_ID")
all_env_ok &= check_env(OVERSEERR_API_URL, "OVERSEERR_API_URL")
all_env_ok &= check_env(OVERSEERR_API_KEY, "OVERSEERR_API_KEY", is_secret=True)
all_env_ok &= check_env(WEBHOOK_SECRET, "WEBHOOK_SECRET", is_secret=True)
all_env_ok &= check_env(PORT, "PORT")

if not all_env_ok:
    logging.critical("Startup aborted: One or more required environment variables are missing or invalid. Please check the logs above for details.")
    exit(1)

PORT = int(PORT)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# We'll store the event loop here
telegram_event_loop = None

async def send_request_message(data):
    logging.info(f"send_request_message called with: {data}")

    media_type = data.get("media", {}).get("media_type", "unknown")
    title = data.get("subject", "Unknown Title")
    requester = data.get("request", {}).get("requestedBy_username", "Unknown User")
    poster_url = data.get("image", None)
    request_id = data.get("request", {}).get("request_id")

    message = (
        f"🎬 *New {media_type.title()} Request!*\n\n"
        f"*Title:* {title}\n"
        f"*Requested by:* {requester}"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{request_id}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny_{request_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if poster_url:
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID,
            photo=poster_url,
            caption=message,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

@app.route("/webhook", methods=["POST"])
def webhook():
    auth_header = request.headers.get("Authorization")
    expected_header = f"Bearer {WEBHOOK_SECRET}"
    if auth_header != expected_header:
        if auth_header is None:
            logging.warning("Webhook received with MISSING Authorization header!")
        else:
            logging.warning(f"Webhook received with INVALID secret! Got: {auth_header!r}, expected: {expected_header!r}")
        abort(401)
    data = request.json
    logging.info(f"Webhook received: {data}")

    if data.get("type") == "TEST_NOTIFICATION":
        logging.info("Test notification received")
        return "Test notification received!", 200

    if (
        data.get("notification_type") == "MEDIA_PENDING"
        or data.get("event") in ["New Movie Request", "New TV Request"]
    ):
        logging.info("MEDIA_PENDING or New Request event received")
        global telegram_event_loop
        if telegram_event_loop:
            asyncio.run_coroutine_threadsafe(send_request_message(data), telegram_event_loop)
        else:
            logging.error("Telegram event loop not set!")
    else:
        logging.info(f"Event not handled: {data.get('event')}")
    return "OK"

def approve_or_deny_request(request_id, action):
    url = f"{OVERSEERR_API_URL}/request/{request_id}/{action}"
    headers = {"X-Api-Key": OVERSEERR_API_KEY}
    response = requests.post(url, headers=headers)
    if response.ok:
        logging.info(f"Request {request_id} {action}d successfully via Overseerr API.")
    else:
        logging.error(f"Failed to {action} request {request_id} via Overseerr API. Status: {response.status_code}, Response: {response.text}")
    return response.ok

async def button_handler(update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("approve_") or data.startswith("deny_"):
        action = "approve" if data.startswith("approve_") else "decline"
        request_id = data.split("_")[1]
        success = approve_or_deny_request(request_id, action)
        if success:
            try:
                await query.edit_message_caption(caption=f"✅ Request {action}d!")
            except Exception:
                await query.edit_message_text(text=f"✅ Request {action}d!")
        else:
            try:
                await query.edit_message_caption(caption=f"❌ Failed to {action} request.")
            except Exception:
                await query.edit_message_text(text=f"❌ Failed to {action} request.")

def start_telegram_bot():
    global telegram_event_loop
    app_telegram = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app_telegram.add_handler(CallbackQueryHandler(button_handler))
    telegram_event_loop = asyncio.get_event_loop()
    app_telegram.run_polling()

if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=PORT)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Start Telegram bot in the main thread (this is important for asyncio!)
    start_telegram_bot()