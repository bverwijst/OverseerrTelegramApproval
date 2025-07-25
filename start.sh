#!/bin/bash

# Set the script to exit immediately if any command fails
set -e

# Start the Gunicorn server in the background.
# This will serve your Flask app and handle the webhooks from Overseerr.
# It listens on port 8080 and uses 4 worker processes for efficiency.
echo "Starting Gunicorn..."
gunicorn --bind 0.0.0.0:8080 --workers 4 bot:app &

# Start the Telegram bot polling in the foreground.
# This is a clean way to call the specific function from your script.
# This process will keep the container running and handle Telegram commands.
echo "Starting Telegram Bot Polling..."
python -c 'from bot import start_telegram_bot; start_telegram_bot()'