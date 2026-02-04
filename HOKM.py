#!/usr/bin/env python3
"""
ربات کامل بازی حکم - نسخه اصلاح شده برای رندر
"""

import os
import logging
import random
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc")

# لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# وضعیت‌های مکالمه
WAITING, PLAYING = range(2)

# ==================== کلاس بازی ====================
class HokmGame:
    def __init__(self):
        self.players = []
        self.deck = []
        self.hands = {}
        self.trump = None
        self.hakem = None
        self.current_player = 0
        self.scores = [0, 0]  # تیم ۱ و ۲
        self.create_deck()
    
    def create_deck(self):
        suits = ['♠️', '♥️', '♦️', '♣️']
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.deck = [(suit, value) for suit in suits for value in values]
        random.shuffle(self.deck)
    
    def add_player(self, user_id, name):
        if len(self.players) >= 4:
            return False
        self.players.append({'id': user_id, 'name': name, 'team': len(self.players) % 2})
        return True
    
    def deal_cards(self):
        for i, player in enumerate(self.players):
            start = i * 13
            end = start + 13
            self.hands[player['id']] = self.deck[start:end]
    
    def get_player_cards(self, user_id):
        return self.hands.get(user_id, [])

# ==================== ربات ====================
games = {}

# دستور /start
def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "🎴 *ربات بازی حکم*\n\n"
        "دستورات:\n"
        "/newgame - شروع بازی جدید\n"
        "/join - پیوستن به بازی\n"
        "/rules - قوانین بازی\n\n"
        "برای شروع بازی در گروه، دستور /newgame را وارد کنید.",
        parse_mode='Markdown'
    )

# دستور /newgame
def new_game(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id in games:
        update.message.reply_text("⚠️ یک بازی در حال انجام است!")
        return ConversationHandler.END
    
    # ایجاد بازی جدید
    game = HokmGame()
    game.add_player(user.id, user.first_name)
    games[chat_id] = game
    
    keyboard = [[
        InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join'),
        InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"🎴 *بازی جدید ساخته شد!*\n\n"
        f"بازیکن ۱: {user.first_name}\n"
        f"۳ بازیکن دیگر نیاز است.\n\n"
        "روی 'پیوستن به بازی' کلیک کنید.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return WAITING

# پیوستن به بازی
def join_game(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in games:
        query.edit_message_text("⚠️ بازی پیدا نشد!")
        return
    
    game = games[chat_id]
    
    if len(game.players) >= 4:
        query.answer("بازی پر شده است!", show_alert=True)
        return
    
    if any(p['id'] == user.id for p in game.players):
        query.answer("شما قبلاً در بازی هستید!", show_alert=True)
        return
    
    # اضافه کردن بازیکن
    game.add_player(user.id, user.first_name)
    
    # آپدیت پیام
    players_list = "\n".join([f"{i+1}. {p['name']}" for i, p in enumerate(game.players)])
    remaining = 4 - len(game.players)
    
    keyboard = [[InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join')]]
    if len(game.players) == 4:
        keyboard.append([InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        f"🎴 *بازی حکم*\n\n"
        f"بازیکنان:\n{players_list}\n\n"
        f"{'✅ آماده شروع!' if remaining == 0 else f'📍 {remaining} بازیکن دیگر نیاز است.'}",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# شروع بازی
def start_game(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    chat_id = update.effective_chat.id
    
    if chat_id not in games:
        query.edit_message_text("⚠️ بازی پیدا نشد!")
        return ConversationHandler.END
    
    game = games[chat_id]
    
    if len(game.players) < 4:
        query.answer("هنوز بازیکنان کافی نیستند!", show_alert=True)
        return WAITING
    
    # توزیع کارت‌ها
    game.deal_cards()
    
    # انتخاب حکم (بازیکن اول)
    game.hakem = game.players[0]
    
    # نمایش حکم
    keyboard = [[
        InlineKeyboardButton("♠️ پیک", callback_data='trump_♠️'),
        InlineKeyboardButton("♥️ دل", callback_data='trump_♥️'),
    ], [
        InlineKeyboardButton("♦️ خشت", callback_data='trump_♦️'),
        InlineKeyboardButton("♣️ گیشنیز", callback_data='trump_♣️'),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    query.edit_message_text(
        f"🎴 *بازی شروع شد!*\n\n"
        f"حکم: {game.hakem['name']}\n"
        f"لطفاً رنگ حکم را انتخاب کنید:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    
    return PLAYING

# انتخاب حکم
def choose_trump(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    chat_id = update.effective_chat.id
    trump = query.data.replace('trump_', '')
    
    if chat_id not in games:
        return
    
    game = games[chat_id]
    game.trump = trump
    
    # ارسال کارت‌ها به هر بازیکن
    for player in game.players:
        try:
            cards = game.get_player_cards(player['id'])
            cards_text = "\n".join([f"{suit} {value}" for suit, value in cards])
            context.bot.send_message(
                player['id'],
                f"🎴 *کارت‌های شما:*\n\n{cards_text}\n\n"
                f"حکم: {trump}\n"
                f"نوبت: {game.players[0]['name']}",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"خطا در ارسال کارت به {player['id']}: {e}")
    
    query.edit_message_text(
        f"✅ *رنگ حکم انتخاب شد:* {trump}\n\n"
        f"کارت‌ها توزیع شدند. بازی شروع می‌شود...",
        parse_mode='Markdown'
    )
    
    return PLAYING

# قوانین بازی
def rules(update: Update, context: CallbackContext):
    rules_text = """
📋 *قوانین بازی حکم*

🎴 تعداد بازیکنان: ۴ نفر (۲ تیم دو نفره)
🎴 تعداد کارت‌ها: ۵۲ کارت
🎴 توزیع کارت: هر بازیکن ۱۳ کارت

🏆 هدف: کسب ۷ امتیاز قبل از تیم حریف

🔄 مراحل:
۱. انتخاب حکم (کارت ۷ دل)
۲. انتخاب رنگ حکم
۳. شروع بازی
۴. بازی ۱۳ دست

📌 قوانین:
- باید همخون بازی کنید
- اگر همخون ندارید، حکم بزنید
- اگر حکم ندارید، هر کارتی می‌توانید

🤝 تیم‌بندی:
بازیکنان روبه‌رو تیمی هستند
    """
    update.message.reply_text(rules_text, parse_mode='Markdown')

# لغو بازی
def cancel(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    chat_id = update.effective_chat.id
    if chat_id in games:
        del games[chat_id]
    
    query.edit_message_text("❌ بازی لغو شد.")
    return ConversationHandler.END

# ==================== اصلی ====================
def main():
    # ساخت updater
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # مکالمه
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('newgame', new_game)],
        states={
            WAITING: [
                CallbackQueryHandler(join_game, pattern='^join$'),
                CallbackQueryHandler(start_game, pattern='^start_game$'),
            ],
            PLAYING: [
                CallbackQueryHandler(choose_trump, pattern='^trump_'),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    # اضافه کردن هندلرها
    dp.add_handler(conv_handler)
    dp.add_handler(CommandHandler('start', start))
    dp.add_handler(CommandHandler('rules', rules))
    dp.add_handler(CommandHandler('join', join_game))
    
    # شروع ربات
    print("🤖 ربات حکم در حال اجرا...")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
