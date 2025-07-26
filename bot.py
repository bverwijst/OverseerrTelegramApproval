# Create the enhanced bot.py with configurable message formatting
import os
import logging
import asyncio
import json
import httpx
import yaml
import threading
import time
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
CONFIG_FILE = os.getenv("MESSAGE_CONFIG_FILE", "message_config.yml")

# --- Initializations ---
bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = Flask(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# --- Message Configuration Management ---
class MessageConfigManager:
    def __init__(self, config_file):
        self.config_file = config_file
        self.config = {}
        self.last_modified = 0
        self.load_config()
        self.auto_reload = self.config.get('settings', {}).get('auto_reload_config', True)
        self.check_interval = self.config.get('settings', {}).get('config_check_interval', 5)
        
        if self.auto_reload:
            self.start_auto_reload()
    
    def get_default_config(self):
        """Return the default configuration if no config file exists"""
        return {
            'message_format': {
                'enabled_fields': ['picture', 'title', 'requester'],
                'field_order': ['picture', 'title', 'requester'],
                'field_settings': {
                    'picture': {'enabled': True, 'fallback_emoji': '🎬'},
                    'title': {
                        'enabled': True, 'show_year': True, 'show_emoji': True,
                        'movie_emoji': '🎬', 'tv_emoji': '📺'
                    },
                    'requester': {'enabled': True, 'format': 'Requested by: {username}'},
                    'synopsis': {
                        'enabled': False, 'max_length': 300,
                        'fallback': 'No synopsis available.'
                    },
                    'rating': {
                        'enabled': False, 'show_tmdb': True, 'show_imdb': False,
                        'fallback': 'Not Rated'
                    },
                    'links': {
                        'enabled': False, 'show_imdb': True, 'show_tmdb': True,
                        'show_tvdb': False
                    },
                    'cast': {
                        'enabled': False, 'max_items': 5, 'separator': ', ',
                        'format': 'Cast: {cast_list}'
                    },
                    'crew': {
                        'enabled': False, 'max_items': 3, 'separator': ', ',
                        'format': 'Crew: {crew_list}', 'roles': ['Director', 'Producer', 'Writer']
                    }
                }
            },
            'settings': {
                'debug_mode': False,
                'auto_reload_config': True,
                'config_check_interval': 5
            }
        }
    
    def load_config(self):
        """Load configuration from YAML file"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = yaml.safe_load(f) or {}
                self.last_modified = os.path.getmtime(self.config_file)
                logging.info(f"Loaded message configuration from {self.config_file}")
            else:
                logging.info(f"Config file {self.config_file} not found, using defaults")
                self.config = self.get_default_config()
                self.create_default_config()
        except Exception as e:
            logging.error(f"Error loading config: {e}, using defaults")
            self.config = self.get_default_config()
    
    def create_default_config(self):
        """Create default config file if it doesn't exist"""
        try:
            with open(self.config_file, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2)
            logging.info(f"Created default config file: {self.config_file}")
        except Exception as e:
            logging.error(f"Error creating default config: {e}")
    
    def check_for_updates(self):
        """Check if config file has been modified and reload if necessary"""
        try:
            if os.path.exists(self.config_file):
                current_modified = os.path.getmtime(self.config_file)
                if current_modified > self.last_modified:
                    logging.info("Config file updated, reloading...")
                    self.load_config()
                    return True
        except Exception as e:
            logging.error(f"Error checking config updates: {e}")
        return False
    
    def start_auto_reload(self):
        """Start background thread for auto-reloading config"""
        def reload_worker():
            while True:
                time.sleep(self.check_interval)
                self.check_for_updates()
        
        thread = threading.Thread(target=reload_worker, daemon=True)
        thread.start()
        logging.info("Started config auto-reload thread")
    
    def get_field_setting(self, field, setting, default=None):
        """Get a specific field setting with fallback to default"""
        return self.config.get('message_format', {}).get('field_settings', {}).get(field, {}).get(setting, default)
    
    def is_field_enabled(self, field):
        """Check if a field is enabled"""
        return self.get_field_setting(field, 'enabled', False)
    
    def get_enabled_fields(self):
        """Get list of enabled fields in order"""
        field_order = self.config.get('message_format', {}).get('field_order', [])
        enabled_fields = self.config.get('message_format', {}).get('enabled_fields', [])
        
        # Return fields in the specified order, but only if they're enabled
        ordered_enabled = [field for field in field_order if field in enabled_fields and self.is_field_enabled(field)]
        
        # Add any enabled fields not in the order list
        for field in enabled_fields:
            if field not in ordered_enabled and self.is_field_enabled(field):
                ordered_enabled.append(field)
        
        return ordered_enabled
    
    def is_debug_mode(self):
        """Check if debug mode is enabled"""
        return self.config.get('settings', {}).get('debug_mode', False)

# Initialize config manager
config_manager = MessageConfigManager(CONFIG_FILE)

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
async def fetch_media_details(media_type, tmdb_id):
    if not tmdb_id or not media_type: 
        return None
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

# --- Message Formatting Functions ---
def safe_get(data, *keys, fallback="N/A"):
    """Safely get nested dictionary values with fallback"""
    try:
        result = data
        for key in keys:
            result = result[key]
        return result if result is not None else fallback
    except (KeyError, TypeError):
        if config_manager.is_debug_mode():
            return fallback
        return None

def format_title_field(details, media_type):
    """Format the title field based on configuration"""
    if not config_manager.is_field_enabled('title'):
        return None
    
    title = safe_get(details, "title") if media_type == "movie" else safe_get(details, "name", fallback="Unknown Title")
    if not title or title == "N/A":
        return None
    
    # Add year if enabled
    if config_manager.get_field_setting('title', 'show_year', True):
        release_date = safe_get(details, "releaseDate") if media_type == "movie" else safe_get(details, "firstAirDate")
        if release_date and len(str(release_date)) >= 4:
            title += f" ({str(release_date)[:4]})"
    
    # Add emoji if enabled
    if config_manager.get_field_setting('title', 'show_emoji', True):
        movie_emoji = config_manager.get_field_setting('title', 'movie_emoji', '🎬')
        tv_emoji = config_manager.get_field_setting('title', 'tv_emoji', '📺')
        emoji = movie_emoji if media_type == "movie" else tv_emoji
        title = f"{emoji} *{title}*"
    else:
        title = f"*{title}*"
    
    return title

def format_requester_field(requester):
    """Format the requester field based on configuration"""
    if not config_manager.is_field_enabled('requester') or not requester:
        return None
    
    format_template = config_manager.get_field_setting('requester', 'format', 'Requested by: {username}')
    return format_template.format(username=requester)

def format_synopsis_field(details):
    """Format the synopsis field based on configuration"""
    if not config_manager.is_field_enabled('synopsis'):
        return None
    
    synopsis = safe_get(details, "overview")
    if not synopsis or synopsis == "N/A":
        fallback = config_manager.get_field_setting('synopsis', 'fallback', 'No synopsis available.')
        synopsis = fallback if config_manager.is_debug_mode() else None
    
    if synopsis:
        max_length = config_manager.get_field_setting('synopsis', 'max_length', 300)
        if len(synopsis) > max_length:
            synopsis = synopsis[:max_length-3] + "..."
        return f"*Synopsis:* {synopsis}"
    
    return None

def format_rating_field(details):
    """Format the rating field based on configuration"""
    if not config_manager.is_field_enabled('rating'):
        return None
    
    ratings = []
    
    if config_manager.get_field_setting('rating', 'show_tmdb', True):
        tmdb_score = safe_get(details, "voteAverage")
        if tmdb_score and tmdb_score != "N/A" and tmdb_score > 0:
            ratings.append(f"{tmdb_score:.1f}/10 (TMDb)")
    
    if config_manager.get_field_setting('rating', 'show_imdb', False):
        imdb_score = safe_get(details, "imdbRating")
        if imdb_score and imdb_score != "N/A" and imdb_score > 0:
            ratings.append(f"{imdb_score}/10 (IMDb)")
    
    if ratings:
        return f"*Rating:* {' | '.join(ratings)}"
    else:
        fallback = config_manager.get_field_setting('rating', 'fallback', 'Not Rated')
        return f"*Rating:* {fallback}" if config_manager.is_debug_mode() else None

def format_links_field(details, media_type):
    """Format the links field based on configuration"""
    if not config_manager.is_field_enabled('links'):
        return None
    
    external_ids = safe_get(details, "externalIds", fallback={})
    if not external_ids or external_ids == "N/A":
        return None
    
    links = []
    
    if config_manager.get_field_setting('links', 'show_imdb', True):
        imdb_id = safe_get(external_ids, "imdbId")
        if imdb_id and imdb_id != "N/A":
            links.append(f"[IMDb](https://www.imdb.com/title/{imdb_id}/)")
    
    if config_manager.get_field_setting('links', 'show_tmdb', True):
        tmdb_id = safe_get(external_ids, "tmdbId") or safe_get(details, "id")
        if tmdb_id and tmdb_id != "N/A":
            links.append(f"[TMDb](https://www.themoviedb.org/{media_type}/{tmdb_id})")
    
    if config_manager.get_field_setting('links', 'show_tvdb', False):
        tvdb_id = safe_get(external_ids, "tvdbId")
        if tvdb_id and tvdb_id != "N/A":
            links.append(f"[TVDB](https://www.thetvdb.com/dereferrer/series/{tvdb_id})")
    
    if links:
        return f"*Links:* {' | '.join(links)}"
    
    return None

def format_cast_field(details):
    """Format the cast field based on configuration"""
    if not config_manager.is_field_enabled('cast'):
        return None
    
    credits = safe_get(details, "credits", fallback={})
    cast_list = safe_get(credits, "cast", fallback=[])
    
    if not cast_list or cast_list == "N/A":
        return None
    
    max_items = config_manager.get_field_setting('cast', 'max_items', 5)
    separator = config_manager.get_field_setting('cast', 'separator', ', ')
    format_template = config_manager.get_field_setting('cast', 'format', 'Cast: {cast_list}')
    
    cast_names = []
    for person in cast_list[:max_items]:
        name = safe_get(person, "name")
        if name and name != "N/A":
            cast_names.append(name)
    
    if cast_names:
        cast_string = separator.join(cast_names)
        return format_template.format(cast_list=cast_string)
    
    return None

def format_crew_field(details):
    """Format the crew field based on configuration"""
    if not config_manager.is_field_enabled('crew'):
        return None
    
    credits = safe_get(details, "credits", fallback={})
    crew_list = safe_get(credits, "crew", fallback=[])
    
    if not crew_list or crew_list == "N/A":
        return None
    
    max_items = config_manager.get_field_setting('crew', 'max_items', 3)
    separator = config_manager.get_field_setting('crew', 'separator', ', ')
    format_template = config_manager.get_field_setting('crew', 'format', 'Crew: {crew_list}')
    roles = config_manager.get_field_setting('crew', 'roles', ['Director', 'Producer', 'Writer'])
    
    crew_names = []
    for person in crew_list:
        job = safe_get(person, "job")
        name = safe_get(person, "name")
        if job in roles and name and name != "N/A" and len(crew_names) < max_items:
            crew_names.append(f"{name} ({job})")
    
    if crew_names:
        crew_string = separator.join(crew_names)
        return format_template.format(crew_list=crew_string)
    
    return None

# --- Core Telegram Message Functions ---
async def send_request_message(data):
    media = data.get("media", {})
    media_type = media.get("media_type", "unknown")
    tmdb_id = media.get("tmdbId")
    poster_url = data.get("image", None)
    requester = data.get("request", {}).get("requestedBy_username", "Unknown User")
    request_id = data.get("request", {}).get("request_id")

    details = await fetch_media_details(media_type, tmdb_id)
    if not details:
        logging.error(f"Could not fetch details for media with tmdbId: {tmdb_id}")
        return

    # Build message parts based on configuration
    message_parts = []
    enabled_fields = config_manager.get_enabled_fields()
    
    for field in enabled_fields:
        field_content = None
        
        if field == 'title':
            field_content = format_title_field(details, media_type)
        elif field == 'requester':
            field_content = format_requester_field(requester)
        elif field == 'synopsis':
            field_content = format_synopsis_field(details)
        elif field == 'rating':
            field_content = format_rating_field(details)
        elif field == 'links':
            field_content = format_links_field(details, media_type)
        elif field == 'cast':
            field_content = format_cast_field(details)
        elif field == 'crew':
            field_content = format_crew_field(details)
        # 'picture' field is handled separately
        
        if field_content:
            message_parts.append(field_content)
    
    # Construct final message
    if not message_parts:
        # Fallback message if no fields are configured
        title = safe_get(details, "title") if media_type == "movie" else safe_get(details, "name", fallback="Unknown Title")
        emoji = "🎬" if media_type == "movie" else "📺"
        message = f"{emoji} *New {'Movie' if media_type == 'movie' else 'TV Show'} Request!*\\n\\n*Title:* {title}\\n*Requested by:* {requester}"
    else:
        message = "\\n\\n".join(message_parts)
    
    # Create approval/denial buttons
    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{request_id}"),
        InlineKeyboardButton("❌ Deny", callback_data=f"deny_{request_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send message with or without picture
    if config_manager.is_field_enabled('picture') and poster_url:
        await bot.send_photo(
            chat_id=TELEGRAM_CHAT_ID, 
            photo=poster_url, 
            caption=message, 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )
    else:
        # Add fallback emoji if picture is disabled but configured
        if config_manager.is_field_enabled('picture') and not poster_url:
            fallback_emoji = config_manager.get_field_setting('picture', 'fallback_emoji', '🎬')
            message = f"{fallback_emoji} {message}"
        
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID, 
            text=message, 
            parse_mode="Markdown", 
            reply_markup=reply_markup
        )

# --- Flask Webhook Routes ---
@app.route("/webhook", methods=["POST"])
def webhook():
    if request.headers.get("Authorization") != f"Bearer {WEBHOOK_SECRET}": 
        abort(401)
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
        for line in query.message.caption.split('\\n'):
            if "Title:" in line or "*" in line:
                try: 
                    title = line.split(':', 1)[1].strip() if ":" in line else line.replace("*", "").strip()
                except IndexError: 
                    pass
            if "Requested by:" in line or "requester" in line.lower():
                try: 
                    original_requester = line.split(':', 1)[1].strip()
                except IndexError: 
                    pass

    success = await approve_or_deny_request(request_id, action)
    
    if success:
        action_past_tense = "approved" if action == "approve" else "denied"
        icon = "✅" if action == "approve" else "❌"
        text = f"{icon} **{title}** (requested by {original_requester}) was {action_past_tense} by {user_who_clicked}."
        await query.message.delete()
        await context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, parse_mode="Markdown")
    else:
        text = f"❌ Failed to {action} **{title}**. There might be an issue with Overseerr."
        await query.edit_message_caption(caption=text, reply_markup=None, parse_mode="Markdown")

async def reload_config_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to manually reload the message configuration"""
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can reload the configuration.")
        return
    
    try:
        config_manager.load_config()
        await update.message.reply_text("✅ Message configuration reloaded successfully!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error reloading configuration: {str(e)}")

async def config_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command to show current configuration status"""
    user_id = update.effective_user.id
    if user_id not in admins:
        await update.message.reply_text("❌ Only admins can view configuration status.")
        return
    
    enabled_fields = config_manager.get_enabled_fields()
    debug_mode = config_manager.is_debug_mode()
    auto_reload = config_manager.auto_reload
    
    status_text = f"""*Configuration Status:*
    
*Enabled Fields:* {', '.join(enabled_fields) if enabled_fields else 'None'}
*Debug Mode:* {'On' if debug_mode else 'Off'}
*Auto Reload:* {'On' if auto_reload else 'Off'}
*Config File:* {config_manager.config_file}
*File Exists:* {'Yes' if os.path.exists(config_manager.config_file) else 'No'}
"""
    
    await update.message.reply_text(status_text, parse_mode="Markdown")

# Keep all existing command handlers...
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
        "Your secure password hash is:\\n\\n"
        f"`{hashed_password}`\\n\\n"
        "Copy this entire hash and set it as the `ADMIN_PASSWORD_HASH` environment variable for the bot, then restart it."
    )
    await message.reply_text(reply_text, parse_mode="Markdown")

async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = datetime.now()

    if 'login_attempts' not in context.bot_data:
        context.bot_data['login_attempts'] = {}
    
    user_attempts = context.bot_data['login_attempts'].get(user_id, {'count': 0, 'time': now})
    
    if now - user_attempts['time'] > timedelta(minutes=5):
        user_attempts = {'count': 0, 'time': now}

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
        user_attempts['count'] += 1
        user_attempts['time'] = now
        context.bot_data['login_attempts'][user_id] = user_attempts
        await update.message.reply_text("❌ Incorrect password.")
        return
    
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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log all uncaught exceptions."""
    logging.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

# --- Main Application Startup ---
def start_telegram_bot():
    app_telegram = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app_telegram.add_error_handler(error_handler)
    
    # Register all command and callback handlers
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
    app_telegram.add_handler(CommandHandler("reloadconfig", reload_config_command))
    app_telegram.add_handler(CommandHandler("configstatus", config_status_command))
    
    app_telegram.run_polling()

if __name__ == "__main__":
    print("Starting Telegram bot directly for local testing...")
    start_telegram_bot()