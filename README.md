# Overseerr Telegram Approver Bot

Get instant Telegram notifications for new Overseerr requests and approve/deny them with a single tap.

## Features

- Instant notifications for new movie/TV requests
- Approve or deny requests directly from Telegram
- Easy Docker deployment

## Setup

1. Clone this repo.
2. Copy `.env.example` to `.env` and fill in your details.
3. Build and run with Docker:

   ```bash
   docker build -t overseerr-telegram-approver .
   docker run --env-file .env -p 8080:8080 overseerr-telegram-approver