# Overseerr Telegram Approver Bot

Get instant Telegram notifications for new Overseerr requests and approve/deny them with a tap!  
Admins can manage who is allowed to approve/deny requests, all from Telegram.

---

## Features

- Instant notifications for new Overseerr requests
- Approve or deny requests directly from Telegram
- Only approved users (added by an admin) can approve/deny
- Admins can add/remove users via Telegram commands
- Persistent admin/user lists (survive restarts)
- Healthcheck endpoint and command
- Easy Docker deployment

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
        ADMIN_PASSWORD: "your-admin-password"
        ADMINS_FILE: "data/admins.json"
        USERS_FILE: "data/users.json"
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
  -e ADMIN_PASSWORD=your-admin-password \
  -e ADMINS_FILE=data/admins.json \
  -e USERS_FILE=data/users.json \
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

## Usage
**1. Log in as an Admin**
In Telegram, send your bot the command:
```/login <admin_password>```
You’ll get a confirmation:
✅ You are now an admin!

**2. Add Users**
To allow someone to approve/deny requests, you (as admin) must add their Telegram user ID:
```/adduser <user_id>```

**3. Remove Users**
To remove a user’s access:
```/removeuser <user_id>```

**4. List Users/Admins**
- List users: ```/listusers```
- List admins: ```/listadmins```

**5. Approve/Deny Requests**
When a new request comes in, the bot will post it in your Telegram chat with Approve/Deny buttons.
Only users or admins can approve/deny.

**6. Healthcheck**
HTTP: Visit ```http://<your-server>:8080/health```
Telegram: ```/health```

**7. Log Out**
```/logout```

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

| **Variable**       | **Description**                                             |
|--------------------|-------------------------------------------------------------|
| TELEGRAM_BOT_TOKEN | Your Telegram bot token                                     |
| TELEGRAM_CHAT_ID   | Your Telegram chat ID (group or user)                       |
| OVERSEERR_API_URL  | Your Overseerr API URL (e.g., http://overseerr:5055/api/v1) |
| OVERSEERR_API_KEY  | Your Overseerr API key                                      |
| WEBHOOK_SECRET     | Secret for webhook authentication (must match Overseerr)    |
| PORT               | Port to run the bot on (default: 8080)                      |
| ADMIN_PASSWORD     | Your Admin password                                         |
| ADMINS_FILE        | Persistent storage for Admin ID's (data/admins.json)        |
| USERS_FILE         | Persistent storage for User ID's (data/users.json)          |

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

---
## Contributing
Contributions are welcome! 

---
## License
This project is licensed under the MIT License. See the [LICENSE](https://github.com/bverwijst/OverseerrTelegramApproval/blob/main/LICENSE) file for details