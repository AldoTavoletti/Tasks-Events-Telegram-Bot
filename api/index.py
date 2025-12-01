import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Google Libraries
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# 1. Load Environment Variables
TOKEN = os.environ.get("TELEGRAM_TOKEN")
TARGET_CHAT_ID = os.environ.get("TARGET_CHAT_ID")

# Google Credentials
GOOGLE_REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

app = FastAPI()

# 2. Helper Function: Talk to Google
def add_task_to_google(task_title):
    """
    Connects to Google using the Refresh Token and adds a task.
    This runs synchronously, so we will wrap it later.
    """
    if not GOOGLE_REFRESH_TOKEN:
        return "Error: Google Login details missing on Vercel."

    try:
        # Reconstruct the credentials using the Refresh Token
        creds = Credentials(
            None, # No access token initially (it will fetch one automatically)
            refresh_token=GOOGLE_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GOOGLE_CLIENT_ID,
            client_secret=GOOGLE_CLIENT_SECRET
        )

        # Build the service
        service = build('tasks', 'v1', credentials=creds)

        # Create the task in the default list
        result = service.tasks().insert(
            tasklist='@default',
            body={'title': task_title}
        ).execute()

        return f"✅ Task added: {result['title']}"
    except Exception as e:
        print(f"Google Error: {e}")
        return f"❌ Failed to add task. Error: {str(e)}"

# 3. Bot Commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hello! I am ready.\n\n"
        f"Your ID: `{update.effective_chat.id}`\n"
        f"Try: /todo Buy milk"
    )

async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Get the text after the command (e.g. "Buy milk")
    task_text = " ".join(context.args)
    
    if not task_text:
        await update.message.reply_text("Please type a task. Example: /todo Buy milk")
        return

    await update.message.reply_text("⏳ Adding to Google Tasks...")

    # 2. Run the Google code in a separate thread (so we don't block the bot)
    # This is important because the Google library is "blocking"
    response_text = await asyncio.to_thread(add_task_to_google, task_text)

    # 3. Reply with result
    await update.message.reply_text(response_text)

# 4. Setup Bot
bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("todo", todo)) # <--- New Command

# 5. Webhook & Cron
@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    if not TOKEN:
        return {"error": "Token not found"}
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.initialize()
        await bot_app.process_update(update)
        await bot_app.shutdown()
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error"}
    return {"status": "ok"}

@app.get("/api/cron")
async def scheduled_message():
    if not TARGET_CHAT_ID:
        return {"error": "Target Chat ID not set"}
    
    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=TARGET_CHAT_ID, text="🌞 Good morning! Don't forget to check your /todo list.")
    return {"status": "sent"}