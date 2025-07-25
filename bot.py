import os
import logging
import asyncio
import json
import httpx
from datetime import datetime, timedelta
from flask import Flask, request, abort
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes
from werkzeug.security import check_password_hash, generate_password_hash

from dotenv import load_dotenv
load_dotenv()

# --- 1. Improved Configuration Handling & Validation ---
# Fail fast if critical environment variables are missing.
REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "OVERSEERR_API_URL",
    "OVERSEERR_API_KEY", "WEBHOOK_SECRET", "ADMIN_PASSWORD_HASH"
]
missing_vars = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing_vars:
    logging.critical(f"FATAL ERROR: Missing required environment variables: {', '.join(missing_vars)}")
    exit(1)

# --- Environment Variables ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
OVERSEERR_API_URL = os.getenv("OVERSEERR_API_URL")
OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")
ADMINS_FILE = os.getenv("ADMINS_FILE", "data/admins.json")
USERS_FILE = os.getenv("USERS_FILE", "data/users.json")

# --- Initializations ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Helper Functions ---
def load_ids(filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return set(json.load(f))
    return set()

def save_ids(filename, ids):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as f:
        json.dump(list(ids), f)

admins = load_ids(ADMINS_FILE)
users = load_ids(USERS_FILE)

# --- 2. Asynchronous API Calls with httpx ---
# Switched from synchronous `requests` to asynchronous `httpx` for non-blocking I/O.
async def fetch_media_details(media_type, tmdb_id):
    if not tmdb_id or not media_type: return None
    url = f"{OVERSEERR_API_URL}/{media_type}/{tmdb_id}"
    headers = {"X-Api-Key": OVERSEERR_API_KEY}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logging.error(f"Error fetching media details: {e}")
        return None

async def approve_or_deny_request(request_id, action):
    url = f"{OVERSEERR_API_URL}/request/{request_id}/{action}"
    headers = {"X-Api-Key": OVERSEERR_API_KEY}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers)
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

    details = await fetch_media_details(media_type, tmdb_id) # Added await
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

    external_ids = details.get("externalIds", {})
    imdb_id = external_ids.get("imdbId")
    tmdb_id_from_details = external_ids.get("tmdbId")
    links = []
    if imdb_id:
        links.append(f"[IMDb](https://www.imdb.com/title/{imdb_id}/)")
    if tmdb_id_from_details:
        links.append(f"[TMDb](https://www.themoviedb.org/{media_type}/{tmdb_id_from_details})")
    links_text = " | ".join(links)

    message = (
        f"{emoji} *New {'Movie' if media_type == 'movie' else 'TV Show'} Request!*\n\n"
        f"*Title:* {title}{year}\n"
        f"*Synopsis:* {overview}\n\n"
        f"*Score:* {score_text}\n"
        f"*Requester:* {requester}\n"
        f"*Links:* {links_text}\n"
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
    if request.headers.get("Authorization") != f"Bearer {WEBHOOK_SECRET}": abort(401)
    data = request.json
    notification_type = data.get("notification_type")
    logging.info(f"Received webhook notification: {notification_type}")
    if notification_type == "TEST_NOTIFICATION":
        return "Test notification received!", 200
    if notification_type == "MEDIA_PENDING":
        try:
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
    if user_id not in admins and user_id not in users:
        await query.answer("You are not authorized to approve or deny requests.", show_alert=True)
        return
    await query.answer()

    action = "approve" if query.data.startswith("approve_") else "decline"
    request_id = query.data.split("_")[1]
    
    title = "The request"
    original_requester = "Unknown"
    user_who_clicked = query.from_user.first_name
    if query.message and query.message.caption:
        for line in query.message.caption.split('\n'):
            if "Title:" in line:
                try: title = line.split(':', 1)[1].strip()
                except IndexError: pass
            if "Requester:" in line:
                try: original_requester = line.split(':', 1)[1].strip()
                except IndexError: pass

    success = await approve_or_deny_request(request_id, action) # Added await
    
    if success:
        action_past_tense = "approved" if action == "approve" else "denied"
        icon = "✅" if action == "approve" else "❌"
        text = f"{icon} **{title}** (requested by {original_requester}) was {action_past_tense} by {user_who_clicked}."
        await query.message.delete()
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    else:
        text = f"❌ Failed to {action} **{title}**. There might be an issue with Overseerr."
        await query.edit_message_caption(caption=text, reply_markup=None, parse_mode="Markdown")

async def generate_hash_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message:
        logging.warning("generate_hash_command received an update with no effective_message.")
        return
    if message.chat.type != 'private':
        await message.reply_text("For security, please send this command as a private message to the bot.")
        return
    if not context.args:
        await message.reply_text("Usage: /generatehash <your-password>")
        return
    password = " ".join(context.args)
    hashed_password = generate_password_hash(password, method='scrypt')
    reply_text = (
        "Your secure password hash is:\n\n"
        f"`{hashed_password}`\n\n"
        "Copy this entire hash and set it as the `ADMIN_PASSWORD_HASH` environment variable for the bot, then restart it."
    )
    await message.reply_text(reply_text, parse_mode="Markdown")

# --- 3. Login Command with Rate Limiting ---
async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now()

    # Initialize attempts dictionary if it doesn't exist
    if 'login_attempts' not in context.bot_data:
        context.bot_data['login_attempts'] = {}
    
    # Get user's attempt history, or create a new one
    user_attempts = context.bot_data['login_attempts'].get(user_id, {'count': 0, 'time': now})
    
    # Reset counter if the last attempt was more than 5 minutes ago
    if now - user_attempts['time'] > timedelta(minutes=5):
        user_attempts = {'count': 0, 'time': now}

    # Block user if they have too many recent failed attempts
    if user_attempts['count'] >= 5:
        await update.message.reply_text("❌ Too many failed login attempts. Please try again in 5 minutes.")
        return

    if update.message.chat.type != 'private':
        await update.message.reply_text("For security, please use the /login command in a private message to the bot.")
        return
    
    password_attempt = " ".join(context.args)
    if not ADMIN_PASSWORD_HASH:
        await update.message.reply_text("❌ Admin password has not been set by the administrator.")
        return
    
    if not password_attempt or not check_password_hash(ADMIN_PASSWORD_HASH, password_attempt):
        # On failure, increment the attempt counter and update the timestamp
        user_attempts['count'] += 1
        user_attempts['time'] = now
        context.bot_data['login_attempts'][user_id] = user_attempts
        await update.message.reply_text("❌ Incorrect password.")
        return
    
    # On success, clear the user's attempt history and log them in
    context.bot_data['login_attempts'].pop(user_id, None)
    admins.add(user_id)
    save_ids(ADMINS_FILE, admins)
    await update.message.reply_text("✅ You are now an admin! You can now use admin commands in the group channel.")

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

async def adduser_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can use this command.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Usage: Reply to a user's message with the /add command to add them.")
        return
    user_to_add = update.message.reply_to_message.from_user
    new_user_id = user_to_add.id
    new_user_name = user_to_add.first_name
    if new_user_id in users:
        await update.message.reply_text(f"✅ User {new_user_name} is already an authorized user.")
        return
    users.add(new_user_id)
    save_ids(USERS_FILE, users)
    await update.message.reply_text(f"✅ User {new_user_name} ({new_user_id}) has been added.")

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

# --- 4. Global Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all uncaught exceptions."""
    logging.error(f"Exception while handling an update: {context.error}", exc_info=context.error)
    # You could optionally add a notification to yourself here, e.g.:
    # await context.bot.send_message(chat_id=YOUR_PERSONAL_CHAT_ID, text=f"Bot encountered an error: {context.error}")

# --- Main Application Startup ---
def start_telegram_bot():
    app_telegram = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Register the global error handler
    app_telegram.add_error_handler(error_handler)
    
    # Register all your command and callback handlers
    app_telegram.add_handler(CommandHandler("generatehash", generate_hash_command))
    app_telegram.add_handler(CommandHandler("add", adduser_reply_command))
    app_telegram.add_handler(CallbackQueryHandler(button_handler))
    app_telegram.add_handler(CommandHandler("login", login_command))
    app_telegram.add_handler(CommandHandler("logout", logout_command))
    app_telegram.add_handler(CommandHandler("adduser", adduser_command))
    app_telegram.add_handler(CommandHandler("removeuser", removeuser_command))
    app_telegram.add_handler(CommandHandler("listusers", listusers_command))
    app_telegram.add_handler(CommandHandler("listadmins", listadmins_command))
    app_telegram.add_handler(CommandHandler("health", health_command))
    
    app_telegram.run_polling()

if __name__ == "__main__":
    print("Starting Telegram bot directly for local testing...")
    start_telegram_bot()