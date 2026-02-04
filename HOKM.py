#!/usr/bin/env python3
"""
ربات حکم - نسخه Webhook برای رندر
"""

import os
import logging
import asyncio
from threading import Thread
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from flask import Flask, request

# ==================== تنظیمات ====================
BOT_TOKEN = "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc"
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://hokmbot.onrender.com")
PORT = int(os.environ.get('PORT', 10000))

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== Flask App ====================
app = Flask(__name__)

# ==================== ذخیره داده‌ها ====================
games = {}

# ==================== دستورات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع"""
    await update.message.reply_text(
        "🎴 *ربات بازی حکم*\n\n"
        "برای شروع بازی در گروه:\n"
        "1. /newgame - ساخت بازی جدید\n"
        "2. بازیکنان با /join می‌پیوندند\n"
        "3. وقتی ۴ نفر شدید بازی شروع می‌شود\n\n"
        "/rules - قوانین بازی",
        parse_mode='Markdown'
    )

async def newgame(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بازی جدید"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id in games:
        await update.message.reply_text("⚠️ یک بازی در حال انجام است!")
        return
    
    games[chat_id] = {
        'players': [user.first_name],
        'team1': [],
        'team2': [],
        'started': False
    }
    
    keyboard = [
        [InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join')],
        [InlineKeyboardButton("❌ لغو بازی", callback_data='cancel')]
    ]
    
    await update.message.reply_text(
        f"🎮 *بازی جدید ساخته شد!*\n\n"
        f"بازیکن ۱: {user.first_name}\n"
        f"📍 ۳ بازیکن دیگر نیاز است.\n\n"
        f"برای پیوستن روی دکمه زیر کلیک کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def join_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوستن به بازی"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in games:
        await update.message.reply_text("⚠️ هیچ بازی فعالی وجود ندارد!")
        return
    
    game = games[chat_id]
    
    if user.first_name in game['players']:
        await update.message.reply_text("⚠️ شما قبلاً در بازی هستید!")
        return
    
    if len(game['players']) >= 4:
        await update.message.reply_text("⚠️ بازی پر شده است!")
        return
    
    game['players'].append(user.first_name)
    
    players_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(game['players'])])
    
    if len(game['players']) == 4:
        # تقسیم به تیم‌ها
        game['team1'] = [game['players'][0], game['players'][2]]
        game['team2'] = [game['players'][1], game['players'][3]]
        
        keyboard = [[InlineKeyboardButton("▶️ شروع بازی", callback_data='start')]]
        
        await update.message.reply_text(
            f"✅ همه بازیکنان حاضرند!\n\n"
            f"🎴 بازیکنان:\n{players_text}\n\n"
            f"🟦 تیم ۱: {game['team1'][0]} & {game['team1'][1]}\n"
            f"🟥 تیم ۲: {game['team2'][0]} & {game['team2'][1]}\n\n"
            f"برای شروع بازی کلیک کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            f"✅ {user.first_name} به بازی پیوست!\n\n"
            f"🎴 بازیکنان: {len(game['players'])}/۴\n"
            f"{players_text}\n\n"
            f"📍 {4-len(game['players'])} نفر دیگر نیاز است."
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک دکمه"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    
    if data == 'join':
        if chat_id not in games:
            await query.edit_message_text("⚠️ بازی پیدا نشد!")
            return
        
        game = games[chat_id]
        user = update.effective_user
        
        if user.first_name in game['players']:
            await query.answer("شما قبلاً در بازی هستید!", show_alert=True)
            return
        
        if len(game['players']) >= 4:
            await query.answer("بازی پر شده است!", show_alert=True)
            return
        
        game['players'].append(user.first_name)
        
        players_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(game['players'])])
        
        if len(game['players']) == 4:
            # تقسیم به تیم‌ها
            game['team1'] = [game['players'][0], game['players'][2]]
            game['team2'] = [game['players'][1], game['players'][3]]
            
            keyboard = [[InlineKeyboardButton("▶️ شروع بازی", callback_data='start')]]
            
            await query.edit_message_text(
                f"✅ همه بازیکنان حاضرند!\n\n"
                f"🎴 بازیکنان:\n{players_text}\n\n"
                f"🟦 تیم ۱: {game['team1'][0]} & {game['team1'][1]}\n"
                f"🟥 تیم ۲: {game['team2'][0]} & {game['team2'][1]}\n\n"
                f"برای شروع بازی کلیک کنید:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        else:
            keyboard = [
                [InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join')],
                [InlineKeyboardButton("❌ لغو بازی", callback_data='cancel')]
            ]
            
            await query.edit_message_text(
                f"✅ {user.first_name} به بازی پیوست!\n\n"
                f"🎴 بازیکنان ({len(game['players'])}/۴):\n{players_text}\n\n"
                f"📍 {4-len(game['players'])} نفر دیگر نیاز است.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    elif data == 'start':
        if chat_id not in games:
            await query.edit_message_text("⚠️ بازی پیدا نشد!")
            return
        
        game = games[chat_id]
        
        if len(game['players']) < 4:
            await query.answer("هنوز بازیکنان کافی نیستند!", show_alert=True)
            return
        
        game['started'] = True
        
        # انتخاب رنگ حکم
        keyboard = [
            [
                InlineKeyboardButton("♠️", callback_data='trump_♠️'),
                InlineKeyboardButton("♥️", callback_data='trump_♥️'),
            ],
            [
                InlineKeyboardButton("♦️", callback_data='trump_♦️'),
                InlineKeyboardButton("♣️", callback_data='trump_♣️'),
            ]
        ]
        
        await query.edit_message_text(
            f"🎮 *بازی شروع شد!*\n\n"
            f"🟦 تیم ۱: {game['team1'][0]} & {game['team1'][1]}\n"
            f"🟥 تیم ۲: {game['team2'][0]} & {game['team2'][1]}\n\n"
            f"🎴 *حکم بازی را انتخاب کنید:*",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    
    elif data.startswith('trump_'):
        if chat_id not in games:
            return
        
        game = games[chat_id]
        trump = data.replace('trump_', '')
        
        await query.edit_message_text(
            f"✅ *رنگ حکم انتخاب شد:* {trump}\n\n"
            f"🎲 بازی در حال انجام...\n"
            f"📊 کارت‌ها توزیع شدند.\n\n"
            f"🎯 هر بازیکن ۱۳ کارت دریافت کرد.\n"
            f"🏆 اولین نفری که کارت بازی کند برنده دست است."
        )
        
        # شبیه‌سازی بازی
        await query.message.reply_text(
            f"🎴 *نوبت بازی*\n\n"
            f"حکم: {trump}\n"
            f"تیم‌ها اماده بازی هستند!\n\n"
            f"✍️ این نسخه نمایشی است. نسخه کامل به زودی..."
        )
    
    elif data == 'cancel':
        if chat_id in games:
            del games[chat_id]
        
        await query.edit_message_text("❌ بازی لغو شد.")

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قوانین بازی"""
    rules_text = """
📋 *قوانین بازی حکم*

🎴 **تعداد بازیکنان:** ۴ نفر (۲ تیم دو نفره)
🎴 **تعداد کارت‌ها:** ۵۲ کارت
🎴 **توزیع کارت:** هر بازیکن ۱۳ کارت

🏆 **هدف:** کسب ۷ امتیاز قبل از تیم حریف

📌 **قوانین:**
- باید همخون بازی کنید
- اگر همخون ندارید، حکم بزنید
- اگر حکم هم ندارید، هر کارتی می‌توانید

🎯 **امتیازدهی:**
برنده هر دست = ۱ امتیاز
اولین تیمی که ۷ امتیاز بگیرد برنده است
    """
    await update.message.reply_text(rules_text, parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راهنما"""
    help_text = """
🆘 *راهنمای ربات حکم*

🎮 **مراحل بازی:**
۱. یک نفر /newgame می‌زند
۲. ۳ نفر دیگر با /join یا کلیک روی دکمه می‌پیوندند
۳. وقتی ۴ نفر شدید، روی «شروع بازی» کلیک کنید
۴. رنگ حکم را انتخاب کنید
۵. بازی شروع می‌شود

📊 **دستورات:**
/start - فعال‌سازی ربات
/newgame - بازی جدید
/join - پیوستن به بازی
/rules - قوانین بازی
/help - این راهنما
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== Flask Routes ====================
@app.route('/')
def home():
    return "🤖 ربات حکم فعال است! (Webhook)"

@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت وب‌هوک از تلگرام"""
    if request.headers.get('content-type') == 'application/json':
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put(update)
        return 'OK'
    return 'Bad Request', 400

# ==================== راه‌اندازی ====================
# ساخت application
application = Application.builder().token(BOT_TOKEN).build()

# اضافه کردن هندلرها
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("newgame", newgame))
application.add_handler(CommandHandler("join", join_cmd))
application.add_handler(CommandHandler("rules", rules))
application.add_handler(CommandHandler("help", help_cmd))
application.add_handler(CallbackQueryHandler(button_handler))

async def setup_webhook():
    """تنظیم وب‌هوک"""
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook set to: {webhook_url}")
    else:
        print("⚠️ WEBHOOK_URL not set, using polling")

async def main():
    """تابع اصلی"""
    print("🤖 راه‌اندازی ربات حکم...")
    
    # راه‌اندازی
    await application.initialize()
    await setup_webhook()
    await application.start()
    
    if not WEBHOOK_URL:
        # حالت polling برای تست
        print("🔎 حالت Polling فعال شد")
        await application.updater.start_polling()
    
    print(f"✅ ربات فعال شد روی پورت {PORT}")
    
    # نگه داشتن برنامه
    await asyncio.Event().wait()

if __name__ == '__main__':
    # اجرای Flask در background
    def run_flask():
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    
    # شروع Flask در thread جدا
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # اجرای ربات
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 ربات متوقف شد.")
