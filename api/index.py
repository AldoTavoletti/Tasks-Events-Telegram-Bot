import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.constants import ParseMode
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

# --- GOOGLE HELPERS ---

def get_google_service():
    """Authenticates and returns the Google Tasks service."""
    if not GOOGLE_REFRESH_TOKEN:
        return None
    
    creds = Credentials(
        None,
        refresh_token=GOOGLE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET
    )
    return build('tasks', 'v1', credentials=creds)

def add_task_to_google(task_title):
    try:
        service = get_google_service()
        if not service:
            return "Error: Google Login details missing."

        result = service.tasks().insert(
            tasklist='@default',
            body={'title': task_title}
        ).execute()

        return f"✅ *Task added:* {result['title']}"
    except Exception as e:
        print(f"Google Error: {e}")
        return f"❌ Failed to add task."

def get_pending_tasks_from_google():
    """Fetches all incomplete tasks."""
    try:
        service = get_google_service()
        if not service:
            return "Error: Google Login details missing."

        # 'showCompleted=False' hides tasks you've already checked off
        results = service.tasks().list(
            tasklist='@default', 
            showCompleted=False,
            showHidden=False
        ).execute()
        
        items = results.get('items', [])

        if not items:
            return "You have no pending tasks! 🎉"

        # Format the list nicely
        message = "📝 *Your Pending Tasks:*\n"
        for task in items:
            # We use a bullet point for each task
            message += f"• {task['title']}\n"
        
        return message

    except Exception as e:
        print(f"Google Error: {e}")
        return f"❌ Failed to get tasks."

# --- BOT COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hello! I am ready.\n\n"
        f"Your ID: `{update.effective_chat.id}`\n"
        f"Try:\n"
        f"/todo Buy milk\n"
        f"/show",
        parse_mode=ParseMode.MARKDOWN
    )

async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_text = " ".join(context.args)
    if not task_text:
        await update.message.reply_text("Please type a task. Example: `/todo Buy milk`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text("⏳ Adding to Google Tasks...")
    response_text = await asyncio.to_thread(add_task_to_google, task_text)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching your list...")
    # Run the blocking Google code in a separate thread
    response_text = await asyncio.to_thread(get_pending_tasks_from_google)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)

# --- SETUP ---

bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("todo", todo))
bot_app.add_handler(CommandHandler("show", show)) # <--- New Handler

# --- WEBHOOK & CRON ---

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
    
    # 1. Fetch the tasks first
    task_list_text = await asyncio.to_thread(get_pending_tasks_from_google)
    
    # 2. Build the final morning message
    morning_text = f"🌞 *Good morning!*\n\n{task_list_text}"

    # 3. Send it
    bot = Bot(token=TOKEN)
    await bot.send_message(
        chat_id=TARGET_CHAT_ID, 
        text=morning_text, 
        parse_mode=ParseMode.MARKDOWN
    )
    
    return {"status": "sent"}