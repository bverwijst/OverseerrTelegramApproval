#!/bin/bash

# Exit on any error
set -e

echo "Starting Overseerr Telegram Bot..."

# Create data directory if it doesn't exist
mkdir -p data

# Start Gunicorn in the background for webhook handling
echo "Starting Gunicorn server..."
gunicorn --bind 0.0.0.0:5000 --workers 1 --timeout 120 bot:app &
GUNICORN_PID=$!

# Wait a moment for Gunicorn to start
sleep 2

# Start the Telegram bot polling
echo "Starting Telegram bot polling..."
python bot.py &
BOT_PID=$!

# Function to handle shutdown
cleanup() {
    echo "Shutting down services..."
    kill $GUNICORN_PID 2>/dev/null || true
    kill $BOT_PID 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Wait for either process to exit
wait $GUNICORN_PID $BOT_PID