# Overseerr Telegram Approver Bot

Get instant Telegram notifications for new Overseerr requests and approve/deny them with a tap!  
Admins can manage who is allowed to approve/deny requests, all from Telegram.

---

## Features

- **Real-time Notifications:** Get instant Telegram messages for new Overseerr requests.
- **Interactive Buttons:** Approve or deny requests directly from Telegram.
- **Rich Media Information:** Notifications include titles, synopses, ratings, and links (IMDb/TMDb).
- **Secure Admin System:** Password-protected login for admins with brute-force protection.
- **User Management:** Admins can add/remove authorized users who can approve/deny requests.
- **High Performance:** Built with an asynchronous core (`httpx`) to handle multiple requests without blocking.
- **Robust & Resilient:** Features a global error handler and a Docker healthcheck to ensure high availability.
- **Easy Deployment:** Runs in a Docker container with a simple setup.

## Quick Start (Docker Compose)

1. **Create a `docker-compose.yml` file:**

   ```yaml
   services:
    overseerrtelegramapprover:
      container_name: overseerr-telegram-approver
      image: xnotorious/overseerr-telegram-approver
      restart: unless-stopped
      volumes:
        - ./data:app/data
      ports:
        - "8080:8080"
      environment:
        TELEGRAM_BOT_TOKEN: "your-telegram-bot-token"
        TELEGRAM_CHAT_ID: "your-telegram-chat-id"
        OVERSEERR_API_URL: "http://your-overseerr-url/api/v1"
        OVERSEERR_API_KEY: "your-overseerr-api-key"
        WEBHOOK_SECRET: "your-webhook-secret"
        PORT: 8080
        ADMIN_PASSWORD_HASH: "your-admin-password"
        ADMINS_FILE: "data/admins.json"
        USERS_FILE: "data/users.json"
      healthcheck:
        test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
        interval: 1m30s
        timeout: 10s
        retries: 3
        start_period: 40s
   ```
> **IMPORTANT:** When you paste your `ADMIN_PASSWORD_HASH` into the `.env` file, you **must** wrap it in single quotes (`'`). This is because the hash contains special characters (`$`) that will otherwise break the configuration.

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
  -e ADMIN_PASSWORD_HASH=your-generated-password-hash \
  -e ADMINS_FILE=/app/data/admins.json \
  -e USERS_FILE=/app/data/users.json \
  -p 8080:8080 \
  -v ./data:/app/data \
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

## Usage

### 1. Set Your Admin Password (Easy Method)

This bot uses a secure hashed password so your actual password is never stored.

1.  Start the bot container for the first time.
2.  Send your bot a **private message** (not in a group, this is also not possible, the bot will not send a hashed password back) with your desired password. For example:
    `/generatehash my super secret password`
3.  The bot will reply with a long string of text (the hash). Copy this entire string. The hashed password might contain characters as $ or :. If you use a .env file, make sure to save your hashed password within single quotes like this: ```'supersafe:hashed$password'```
4.  Stop the bot container.
5.  In your `.env` file or `docker run` command, set the copied hash as the value for the `ADMIN_PASSWORD_HASH` environment variable.
6.  Restart the bot container. It is now securely configured.

### 2. Log in as an Admin

In Telegram, send your bot the command with your **plaintext** password:
`/login my super secret password`

You’ll get a confirmation: `✅ You are now an admin!`

### 3. Add Users

The easiest way to add a user is to have them send a message in the chat, then reply to their message with the `/add` command.

1.  Ask the user to send any message (e.g., "add me").
2.  As an admin, reply directly to their message and type: `/add`
3.  The bot will confirm that the user has been added.

Alternatively, you can still add a user by their numerical Telegram ID:
`/adduser <user_id>`

### 4. Manage Users and Admins

*   **Remove a user:** `/removeuser <user_id>`
*   **List authorized users:** `/listusers`
*   **List admins:** `/listadmins`

### 5. Approve/Deny Requests

When a new request comes in, the bot will post it in your Telegram chat with Approve/Deny buttons and links to IMDb/TMDb. Only authorized users or admins can approve/deny.

The final confirmation message will show what was requested, who requested it, and who took action on it.

### 6. Healthcheck & Logout

*   **Check bot health (HTTP):** `http://<your-server>:8080/health`
*   **Check bot health (Telegram):** `/health`
*   **Log out:** `/logout`

## How to Get a Telegram User ID

To add a user who can approve or deny requests, you need their Telegram user ID.

**Easiest method:**
1. Ask the user to message [@userinfobot](https://t.me/userinfobot) on Telegram.
2. The bot will reply with their user ID.
3. As an admin, use the command `/adduser <user_id>` in the group or in a DM with the bot to grant them access.

## (Alternative) Add the Bot to a Group Chat

You can use this bot in a group chat instead of (or in addition to) direct messages.

**To add the bot to a group:**

1. **Invite the bot to your group:**
   - In Telegram, open your group chat.
   - Tap the group name at the top, then “Add Members.”
   - Search for your bot’s username (from @BotFather) and add it.

2. **Promote the bot to admin (recommended):**
   - In the group’s member list, tap your bot and choose “Promote to admin.”
   - The bot does not need all permissions, but it must be able to send messages and reply to messages.

3. **Get the group chat ID:**
   - Add the bot to the group.
   - Send a message in the group.
   - Use a tool like [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot) to get the group’s chat ID.
   - The group chat ID usually starts with a `-` (e.g., `-1001234567890`).

4. **Update your `.env`:**
   - Set `TELEGRAM_CHAT_ID` to your group chat ID.

5. **Restart your bot container** for changes to take effect.

**Now, all notifications and approval/denial actions will happen in your group chat!**

## Environment Variables

| **Variable**       | **Description**                                                                                              | **Example**
|--------------------|--------------------------------------------------------------------------------------------------------------|----------------------------------------------|
| TELEGRAM_BOT_TOKEN | Your Telegram bot's token from BotFather.                                                                    | '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'  |
| TELEGRAM_CHAT_ID   | The ID of the Telegram chat/group where notifications will be sent.                                          | -1001234567890                               |
| OVERSEERR_API_URL  | The full URL to your Overseerr API.                                                                          | http://192.168.1.100:5055/api/v1             |
| OVERSEERR_API_KEY  | Your Overseerr API key                                                                                       | a1b2c3d4-e5f6-7890-1234-567890abcdef         |
| WEBHOOK_SECRET     | A long, random secret string for securing the webhook endpoint.                                              | my-super-secret-webhook-string               |
| PORT               | The port the internal Flask web server will listen on. Must match the internal port in `docker-compose.yml`. | 8080                                         |
| ADMIN_PASSWORD_HASH| The hashed password for the first admin. Use `/generatehash` in a PM to the bot to get this.                 | 'scrypt:32768:8:1$Pt...b4eb'                 |
| ADMINS_FILE        | (Optional) Path to the file storing admin IDs.                                                               | data/admins.json                             |
| USERS_FILE         | (Optional) Path to the file storing user IDs.                                                                | data/users.json                              |

## Security

- The webhook endpoint is protected by a bearer token (`WEBHOOK_SECRET`).
- Admin commands are restricted to users who have logged in with the admin password.
- The `/generatehash` and `/login` commands only work in private messages to the bot for privacy.
- **Brute-Force Protection:** The `/login` command is rate-limited to prevent password-guessing attacks. After 5 failed attempts, a user is temporarily locked out.

## Logging
This bot is designed to be foolproof. On startup, it checks all required environment variables:

- If a variable is **missing**, you’ll see a log like:
```CRITICAL:root:Environment variable TELEGRAM_BOT_TOKEN is MISSING!```
- If a variable is set to a **placeholder value** (like your-telegram-bot-token), you’ll see:
```ERROR:root:Environment variable TELEGRAM_BOT_TOKEN is set to a placeholder value ('your-telegram-bot-token')! Please set a real value.```
- If all is well, you’ll see:
```INFO:root:TELEGRAM_BOT_TOKEN loaded: ***```

Webhook authentication issues are also clearly logged, so you’ll know if the secret is missing or incorrect.

Check your container logs for any issues, setup problems will be obvious and easy to fix!

---
## Contributing
Contributions are welcome! 

---
## License
This project is licensed under the MIT License. See the [LICENSE](https://github.com/bverwijst/OverseerrTelegramApproval/blob/main/LICENSE) file for details.
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker Pulls](https://img.shields.io/docker/pulls/xnotorious/overseerr-telegram-approver.svg)](https://hub.docker.com/r/xnotorious/overseerr-telegram-approver)