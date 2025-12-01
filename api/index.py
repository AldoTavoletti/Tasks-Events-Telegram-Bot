import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

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

def get_raw_tasks():
    """Fetches the raw list of tasks (objects) from Google."""
    service = get_google_service()
    if not service: return []
    
    results = service.tasks().list(
        tasklist='@default', 
        showCompleted=False,
        showHidden=False
    ).execute()
    
    return results.get('items', [])

def add_task_to_google(task_title):
    try:
        service = get_google_service()
        service.tasks().insert(tasklist='@default', body={'title': task_title}).execute()
        return f"✅ *Added:* {task_title}"
    except Exception as e:
        return f"❌ Error: {str(e)}"

def delete_task_by_index(index):
    """
    Since IDs are too long for buttons, we fetch the list again
    and delete the item at the specific index (0, 1, 2...).
    """
    try:
        service = get_google_service()
        # 1. Get fresh list to ensure index is accurate
        tasks = get_raw_tasks()
        
        if index >= len(tasks):
            return "❌ Task not found (list might have changed)."
        
        task_to_delete = tasks[index]

        # 2. Delete using the ID found
        service.tasks().delete(tasklist='@default', task=task_to_delete['id']).execute()
        return f"🗑️ Deleted: *{task_to_delete['title']}*"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# --- BOT COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Hello! Your ID: `{update.effective_chat.id}`\n\n"
        f"Commands:\n"
        f"/todo <text> - Add a task\n"
        f"/show - Manage your tasks",
        parse_mode=ParseMode.MARKDOWN
    )

async def todo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_text = " ".join(context.args)
    if not task_text:
        await update.message.reply_text("Type a task: `/todo Buy milk`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.message.reply_text("⏳ Adding...")
    response_text = await asyncio.to_thread(add_task_to_google, task_text)
    await update.message.reply_text(response_text, parse_mode=ParseMode.MARKDOWN)

async def show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⏳ Fetching list...")
    
    # Fetch tasks
    tasks = await asyncio.to_thread(get_raw_tasks)
    
    if not tasks:
        await update.message.reply_text("🎉 You have no pending tasks!")
        return

    # Build the message and the buttons
    message_text = "📝 *Your To-Do List:*\n\n"
    keyboard = []

    for i, task in enumerate(tasks):
        # Add text line
        message_text += f"{i+1}. {task['title']}\n"
        
        # Add a delete button for this specific index
        # We pass "del_0", "del_1" etc. as hidden data
        btn = InlineKeyboardButton(f"❌ Delete #{i+1}", callback_data=f"del_{i}")
        keyboard.append([btn])

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the button click."""
    query = update.callback_query
    await query.answer() # Stop the loading animation on the button

    data = query.data
    if data.startswith("del_"):
        # Extract the index number (e.g. "del_0" -> 0)
        index = int(data.split("_")[1])
        
        await query.edit_message_text(f"⏳ Deleting task #{index+1}...")
        
        # Perform deletion
        result_text = await asyncio.to_thread(delete_task_by_index, index)
        
        # Send confirmation (or you could re-show the list)
        await context.bot.send_message(chat_id=query.message.chat_id, text=result_text, parse_mode=ParseMode.MARKDOWN)
        
        # Optional: Show the updated list automatically
        # await show(update, context) 

# --- SETUP ---

bot_app = ApplicationBuilder().token(TOKEN).build()
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("todo", todo))
# This captures any text that is NOT a command
bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), todo))
bot_app.add_handler(CommandHandler("show", show))
bot_app.add_handler(CallbackQueryHandler(button_callback)) # <--- Handles the buttons

# --- WEBHOOK & CRON ---

@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    if not TOKEN: return {"error": "Token not found"}
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.initialize()
        await bot_app.process_update(update)
        await bot_app.shutdown()
    except Exception as e:
        print(f"Error: {e}")
    return {"status": "ok"}

@app.get("/api/cron")
async def scheduled_message():
    if not TARGET_CHAT_ID: return {"error": "Target Chat ID not set"}
    
    # Fetch tasks for the morning message
    tasks = await asyncio.to_thread(get_raw_tasks)
    
    if not tasks:
        msg = "🌞 *Good morning!* You have no tasks for today. Enjoy! 🎉"
    else:
        # Format the list nicely for text only
        task_list = "\n".join([f"• {t['title']}" for t in tasks])
        msg = f"🌞 *Good morning!* Here are your tasks:\n\n{task_list}"

    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=TARGET_CHAT_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
    
    return {"status": "sent"}