# Overseerr Telegram Approver Bot

Get instant Telegram notifications for new Overseerr requests and approve/deny them with a single tap.

## Features

- Instant notifications for new movie/TV requests
- Approve or deny requests directly from Telegram
- Foolproof Docker deployment
- Detailed logging for easy troubleshooting

## Quick Start (Docker Compose)

1. **Create a `docker-compose.yml` file:**

   ```yaml
   services:
     overseerrtelegramapprover:
       container_name: overseerr-telegram-approver
       image: xnotorious/overseerr-telegram-approver
       restart: unless-stopped
       ports:
         - "8080:8080"
       environment:
         TELEGRAM_BOT_TOKEN: "your-telegram-bot-token"
         TELEGRAM_CHAT_ID: "your-telegram-chat-id"
         OVERSEERR_API_URL: "http://your-overseerr-url/api/v1"
         OVERSEERR_API_KEY: "your-overseerr-api-key"
         WEBHOOK_SECRET: "your-webhook-secret"
         PORT: 8080
   ```

2. **Start the bot:**
```docker compose up -d```

## Quick Start (Docker Run)
If you prefer a single command use: 
```
docker run -d \
  --name overseerr-telegram-approver \
  -e TELEGRAM_BOT_TOKEN=your-telegram-bot-token \
  -e TELEGRAM_CHAT_ID=your-telegram-chat-id \
  -e OVERSEERR_API_URL=http://your-overseerr-url/api/v1 \
  -e OVERSEERR_API_KEY=your-overseerr-api-key \
  -e WEBHOOK_SECRET=your-webhook-secret \
  -e PORT=8080 \
  -p 8080:8080 \
  xnotorious/overseerr-telegram-approver
```

## Setting up Overseerr Webhook
1. In Overseerr, go to **Settings > Notifications > Webhook**
2. Select **Enable Agent**
3. Set the **Webook URL** to:
```http://<your-server-ip>:<port>/webhook```
4. Set the **Authorization Header** to:
 ```Bearer your-webhook-secret```
5. Check the **Notofication Types:** **Request Pending Approval**
6. Test the connection, you will see a green popup confirming the connection.
7. Save changes

> **Note**: The ```WEBHOOK_SECRET``` in your Docker environment and the secret in Overseerr **must match exactly**

## Environment Variables

| **Variable**       | **Description**                                             |
|--------------------|-------------------------------------------------------------|
| TELEGRAM_BOT_TOKEN | Your Telegram bot token                                     |
| TELEGRAM_CHAT_ID   | Your Telegram chat ID (group or user)                       |
| OVERSEERR_API_URL  | Your Overseerr API URL (e.g., http://overseerr:5055/api/v1) |
| OVERSEERR_API_KEY  | Your Overseerr API key                                      |
| WEBHOOK_SECRET     | Secret for webhook authentication (must match Overseerr)    |
| PORT               | Port to run the bot on (default: 8080)                      |

## Logging
This bot is designed to be foolproof. On startup, it checks all required environment variables:

- If a variable is **missing**, you’ll see a log like:
```CRITICAL:root:Environment variable TELEGRAM_BOT_TOKEN is MISSING!```
- If a variable is set to a **placeholder value** (like your-telegram-bot-token), you’ll see:
```ERROR:root:Environment variable TELEGRAM_BOT_TOKEN is set to a placeholder value ('your-telegram-bot-token')! Please set a real value.```
- If all is well, you’ll see:
```INFO:root:TELEGRAM_BOT_TOKEN loaded: ***```

Webhook authentication issues are also clearly logged, so you’ll know if the secret is missing or incorrect.

Check your container logs for any issues—setup problems will be obvious and easy to fix!