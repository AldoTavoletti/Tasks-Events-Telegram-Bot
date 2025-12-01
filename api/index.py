import os
from fastapi import FastAPI, Request
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# 1. Load your keys (Vercel will provide these securely)
TOKEN = os.environ.get("TELEGRAM_TOKEN")
TARGET_CHAT_ID = os.environ.get("TARGET_CHAT_ID") # The chat where the morning message goes

app = FastAPI()

# 2. Setup the Bot logic
# We build the app globally so it's ready, but we initialize it per-request for Vercel
bot_app = ApplicationBuilder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # This sends your chat ID back to you so you can find out what it is
    await update.message.reply_text(f"Hello! Your Chat ID is: {update.effective_chat.id}")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"I received: {update.message.text}")

# Register the commands
bot_app.add_handler(CommandHandler("start", start))
# bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo)) # Uncomment to echo text

# 3. The "Doorbell" (Webhook) - Telegram calls this when you send a message
@app.post("/api/webhook")
async def telegram_webhook(request: Request):
    if not TOKEN:
        return {"error": "Token not found"}

    # Get the data from Telegram
    data = await request.json()
    update = Update.de_json(data, bot_app.bot)
    
    # Process the update
    # In Vercel/Serverless, we must manage the lifecycle manually for each request
    await bot_app.initialize()
    await bot_app.process_update(update)
    await bot_app.shutdown()
    
    return {"status": "ok"}

# 4. The "Alarm Clock" (Cron) - Vercel calls this every morning
@app.get("/api/cron")
async def scheduled_message():
    if not TARGET_CHAT_ID:
        return {"error": "Target Chat ID not set"}
    
    bot = Bot(token=TOKEN)
    await bot.send_message(chat_id=TARGET_CHAT_ID, text="🌞 Good morning! This is your daily scheduled message.")
    
    return {"status": "sent"}