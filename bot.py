import os
import logging
import threading
import asyncio
import json
from flask import Flask, request, abort
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
import requests

from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OVERSEERR_API_URL = os.getenv("OVERSEERR_API_URL")
OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", 8080))
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")
ADMINS_FILE = os.getenv("ADMINS_FILE", "admins.json")
USERS_FILE = os.getenv("USERS_FILE", "users.json")

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

telegram_event_loop = None

def load_ids(filename):
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return set(json.load(f))
    return set()

def save_ids(filename, ids):
    with open(filename, "w") as f:
        json.dump(list(ids), f)

admins = load_ids(ADMINS_FILE)
users = load_ids(USERS_FILE)

def fetch_media_details(media_type, tmdb_id):
    if not tmdb_id or not media_type:
        return None
    url = f"{OVERSEERR_API_URL}/movie/{tmdb_id}" if media_type == "movie" else f"{OVERSEERR_API_URL}/tv/{tmdb_id}"
    headers = {"X-Api-Key": OVERSEERR_API_KEY}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching media details: {e}")
        return None

async def send_request_message(data):
    # Get basic info from webhook to find the media
    media = data.get("media", {})
    media_type = media.get("media_type", "unknown")
    tmdb_id = media.get("tmdbId")
    poster_url = data.get("image", None)
    requester = data.get("request", {}).get("requestedBy_username", "Unknown User")

    # The webhook payload is minimal, so we must fetch full details from the API
    details = fetch_media_details(media_type, tmdb_id) if tmdb_id else None

    # If we couldn't fetch details, we can't build a proper message
    if not details:
        logging.error(f"Could not fetch details for media with tmdbId: {tmdb_id}")
        return

    # --- CORRECTED SECTION ---
    # Extract rich details from the full API response
    # Movie titles are in 'title', TV show titles are in 'name'
    title = details.get("title") if media_type == "movie" else details.get("name", "Unknown Title")
    
    # Use the full overview from the details
    overview = details.get("overview", "No synopsis available.")
    
    # Get year from 'releaseDate' (movies) or 'firstAirDate' (tv)
    release_date = details.get("releaseDate") if media_type == "movie" else details.get("firstAirDate")
    year = f" ({release_date[:4]})" if release_date and len(release_date) >= 4 else ""

    # Get score from 'voteAverage' (this is the TMDb score)
    score = details.get("voteAverage")
    score_text = f"{score:.1f}/10 (TMDb)" if score is not None and score > 0 else "Not Rated"
    # --- END CORRECTED SECTION ---

    emoji = "🎬" if media_type == "movie" else "📺"

    message = (
        f"{emoji} *New {'Movie' if media_type == 'movie' else 'TV Show'} Request!*\n\n"
        f"*Title:* {title}{year}\n"
        f"*Synopsis:* {overview}\n\n"
        f"*Score:* {score_text}\n"
        f"*Requester:* {requester}\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{data.get('request', {}).get('request_id')}"),
            InlineKeyboardButton("❌ Deny", callback_data=f"deny_{data.get('request', {}).get('request_id')}")
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
    if request.headers.get("Authorization") != f"Bearer {WEBHOOK_SECRET}":
        abort(401)
    data = request.json
    if data.get("type") == "TEST_NOTIFICATION":
        return "Test notification received!", 200

    if (
        data.get("notification_type") == "MEDIA_PENDING"
        or data.get("event") in ["New Movie Request", "New TV Request"]
    ):
        global telegram_event_loop
        if telegram_event_loop:
            asyncio.run_coroutine_threadsafe(send_request_message(data), telegram_event_loop)
    return "OK"

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

def approve_or_deny_request(request_id, action):
    url = f"{OVERSEERR_API_URL}/request/{request_id}/{action}"
    headers = {"X-Api-Key": OVERSEERR_API_KEY}
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"Error approving/denying request: {e}")
        return False

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    # Only allow users or admins to approve/deny
    if user_id not in admins and user_id not in users:
        # Try to send a visible reply in the chat (group or private)
        try:
            if query.message:
                await query.message.reply_text(
                    "❌ Sorry, you are not authorized to approve or deny requests. Ask an admin to add you."
                )
        except Exception:
            pass
        # Also send a popup alert (works in private chat, sometimes in groups)
        try:
            await query.answer(
                "You are not authorized. Ask an admin to add you.",
                show_alert=True
            )
        except Exception:
            pass
        return

    await query.answer()  # Acknowledge the button press for authorized users

    action = None
    if data.startswith("approve_"):
        action = "approve"
    elif data.startswith("deny_"):
        action = "decline"

    if action:
        request_id = data.split("_")[1]
        success = approve_or_deny_request(request_id, action)
        # Try to get the title from the original message
        title = "Request"
        try:
            if query.message.caption:
                for line in query.message.caption.split('\n'):
                    if line.startswith("*Title:*"):
                        title = line.replace("*Title:*", "").strip()
                        break
        except Exception:
            pass
        if success:
            text = f"✅ {title} approved!" if action == "approve" else f"❌ {title} denied!"
        else:
            text = f"❌ Failed to {action} {title}."
        try:
            await query.edit_message_caption(caption=text, reply_markup=None)
        except Exception:
            await query.edit_message_text(text=text, reply_markup=None)

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /login <admin_password>")
        return
    pw = args[0]
    if pw == ADMIN_PASSWORD:
        admins.add(user_id)
        save_ids(ADMINS_FILE, admins)
        await update.message.reply_text("✅ You are now an admin!")
    else:
        await update.message.reply_text("❌ Incorrect password.")

async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admins:
        admins.remove(user_id)
        save_ids(ADMINS_FILE, admins)
        await update.message.reply_text("✅ You have been logged out as admin.")
    elif user_id in users:
        users.remove(user_id)
        save_ids(USERS_FILE, users)
        await update.message.reply_text("✅ You have been logged out as user.")
    else:
        await update.message.reply_text("You are not logged in.")

async def adduser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can add users.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /adduser <user_id>")
        return
    try:
        new_user_id = int(args[0])
        users.add(new_user_id)
        save_ids(USERS_FILE, users)
        await update.message.reply_text(f"✅ User {new_user_id} added.")
    except Exception:
        await update.message.reply_text("Invalid user_id.")

async def removeuser_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can remove users.")
        return
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /removeuser <user_id>")
        return
    try:
        rem_user_id = int(args[0])
        if rem_user_id in users:
            users.remove(rem_user_id)
            save_ids(USERS_FILE, users)
            await update.message.reply_text(f"✅ User {rem_user_id} removed.")
        else:
            await update.message.reply_text("User not found.")
    except Exception:
        await update.message.reply_text("Invalid user_id.")

async def listusers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can list users.")
        return
    await update.message.reply_text(f"Users: {', '.join(map(str, users))}")

async def listadmins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can list admins.")
        return
    await update.message.reply_text(f"Admins: {', '.join(map(str, admins))}")

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running and healthy!")

def start_telegram_bot():
    global telegram_event_loop
    app_telegram = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app_telegram.add_handler(CallbackQueryHandler(button_handler))
    app_telegram.add_handler(CommandHandler("login", login_command))
    app_telegram.add_handler(CommandHandler("logout", logout_command))
    app_telegram.add_handler(CommandHandler("adduser", adduser_command))
    app_telegram.add_handler(CommandHandler("removeuser", removeuser_command))
    app_telegram.add_handler(CommandHandler("listusers", listusers_command))
    app_telegram.add_handler(CommandHandler("listadmins", listadmins_command))
    app_telegram.add_handler(CommandHandler("health", health_command))
    telegram_event_loop = asyncio.get_event_loop()
    app_telegram.run_polling()

if __name__ == "__main__":
    def run_flask():
        app.run(host="0.0.0.0", port=PORT)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    start_telegram_bot()