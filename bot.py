import os
import logging
import asyncio
import json
from flask import Flask, request, abort
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
import requests

from dotenv import load_dotenv
load_dotenv()

# --- Environment Variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OVERSEERR_API_URL = os.getenv("OVERSEERR_API_URL")
OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")
ADMINS_FILE = os.getenv("ADMINS_FILE", "admins.json")
USERS_FILE = os.getenv("USERS_FILE", "users.json")

# --- Initializations ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

# --- Helper Functions for User/Admin Management ---
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

# --- Overseerr API Functions ---
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
        logging.error(f"Error fetching media details: {e}")
        return None

def approve_or_deny_request(request_id, action):
    url = f"{OVERSEERR_API_URL}/request/{request_id}/{action}"
    headers = {"X-Api-Key": OVERSEERR_API_KEY}
    try:
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"Error approving/denying request: {e}")
        return False

# --- Core Telegram Message Functions ---
async def send_request_message(data):
    media = data.get("media", {})
    media_type = media.get("media_type", "unknown")
    tmdb_id = media.get("tmdbId")
    poster_url = data.get("image", None)
    requester = data.get("request", {}).get("requestedBy_username", "Unknown User")

    details = fetch_media_details(media_type, tmdb_id) if tmdb_id else None
    if not details:
        logging.error(f"Could not fetch details for media with tmdbId: {tmdb_id}")
        return

    title = details.get("title") if media_type == "movie" else details.get("name", "Unknown Title")
    overview = details.get("overview", "No synopsis available.")
    release_date = details.get("releaseDate") if media_type == "movie" else details.get("firstAirDate")
    year = f" ({release_date[:4]})" if release_date and len(release_date) >= 4 else ""
    score = details.get("voteAverage")
    score_text = f"{score:.1f}/10 (TMDb)" if score is not None and score > 0 else "Not Rated"
    emoji = "🎬" if media_type == "movie" else "📺"

    message = (
        f"{emoji} *New {'Movie' if media_type == 'movie' else 'TV Show'} Request!*\n\n"
        f"*Title:* {title}{year}\n"
        f"*Synopsis:* {overview}\n\n"
        f"*Score:* {score_text}\n"
        f"*Requester:* {requester}\n"
    )
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{data.get('request', {}).get('request_id')}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"deny_{data.get('request', {}).get('request_id')}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if poster_url:
        await bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=poster_url, caption=message, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message, parse_mode="Markdown", reply_markup=reply_markup)

# --- Flask Webhook Routes ---
@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("Authorization") != f"Bearer {WEBHOOK_SECRET}":
        abort(401)
    
    data = request.json
    notification_type = data.get("notification_type")
    
    logging.info(f"Received webhook notification: {notification_type}")

    if notification_type == "TEST_NOTIFICATION":
        logging.info("Test notification received successfully!")
        return "Test notification received!", 200

    if notification_type == "MEDIA_PENDING":
        try:
            # --- THIS IS THE KEY CHANGE ---
            # Run the async function in its own event loop. No need for global variables.
            asyncio.run(send_request_message(data))
            logging.info("Successfully processed MEDIA_PENDING notification.")
        except Exception as e:
            logging.error(f"Failed to process MEDIA_PENDING notification: {e}")
            return "Error processing notification", 500
            
    return "OK", 200

@app.route("/health", methods=["GET"])
def health():
    return "OK", 200

# --- Telegram Bot Handlers ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if user_id not in admins and user_id not in users:
        await query.answer("You are not authorized to approve or deny requests.", show_alert=True)
        return

    await query.answer()

    action = "approve" if data.startswith("approve_") else "decline"
    request_id = data.split("_")[1]
    
    title = "The request"
    user_who_clicked = query.from_user.first_name
    if query.message and query.message.caption:
        for line in query.message.caption.split('\n'):
            if "Title:" in line:
                try:
                    title = line.split(':', 1)[1].strip()
                    break
                except IndexError:
                    logging.warning(f"Could not parse title from line: {line}")

    success = approve_or_deny_request(request_id, action)
    
    if success:
        action_past_tense = "approved" if action == "approve" else "denied"
        icon = "✅" if action == "approve" else "❌"
        text = f"{icon} **{title}** was {action_past_tense} by {user_who_clicked}."
        await query.message.delete()
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    else:
        text = f"❌ Failed to {action} **{title}**. There might be an issue with Overseerr."
        await query.edit_message_caption(caption=text, reply_markup=None, parse_mode="Markdown")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    if not args or args[0] != ADMIN_PASSWORD:
        await update.message.reply_text("❌ Incorrect password.")
        return
    admins.add(user_id)
    save_ids(ADMINS_FILE, admins)
    await update.message.reply_text("✅ You are now an admin!")

# ... (other command handlers like logout, adduser, etc. are unchanged) ...
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

# --- Main Application Startup ---
def start_telegram_bot():
    """This function is called by start.sh to run the Telegram bot."""
    app_telegram = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app_telegram.add_handler(CallbackQueryHandler(button_handler))
    app_telegram.add_handler(CommandHandler("login", login_command))
    app_telegram.add_handler(CommandHandler("logout", logout_command))
    app_telegram.add_handler(CommandHandler("adduser", adduser_command))
    app_telegram.add_handler(CommandHandler("removeuser", removeuser_command))
    app_telegram.add_handler(CommandHandler("listusers", listusers_command))
    app_telegram.add_handler(CommandHandler("listadmins", listadmins_command))
    app_telegram.add_handler(CommandHandler("health", health_command))
    app_telegram.run_polling()

# --- This block is no longer needed for starting the app ---
# The start.sh script now handles running Gunicorn and the bot.
# It's kept here in case you ever want to run the bot directly for local testing.
if __name__ == "__main__":
    print("Starting Telegram bot directly for local testing...")
    start_telegram_bot()