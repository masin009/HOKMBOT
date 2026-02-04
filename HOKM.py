#!/usr/bin/env python3
"""
ربات کامل بازی حکم - با pyTelegramBotAPI
"""

import os
import logging
import random
import telebot
from telebot import types
from flask import Flask, request

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")

# لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== ربات ====================
bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== کلاس بازی ====================
class HokmGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = []
        self.deck = []
        self.hands = {}
        self.trump = None
        self.hakem = None
        self.current_player = 0
        self.scores = [0, 0]  # تیم ۱ و ۲
        self.game_started = False
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

# ذخیره بازی‌ها
games = {}

# ==================== دستورات ====================
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message,
        "🎴 *ربات بازی حکم*\n\n"
        "دستورات:\n"
        "/newgame - شروع بازی جدید\n"
        "/join - پیوستن به بازی\n"
        "/rules - قوانین بازی\n"
        "/help - راهنما\n\n"
        "برای شروع، در یک گروه دستور /newgame را وارد کنید.",
        parse_mode='Markdown'
    )

@bot.message_handler(commands=['help'])
def help_cmd(message):
    help_text = """
🆘 *راهنمای ربات*

🎮 **شروع بازی:**
1. در گروه `/newgame` را بفرستید
2. بازیکنان دیگر روی دکمه 'پیوستن' کلیک کنند
3. وقتی ۴ نفر شدند، روی 'شروع بازی' کلیک کنید

🎴 **در حین بازی:**
- کارت‌ها به صورت خصوصی ارسال می‌شوند
- باید همخون بازی کنید
- بازی ۱۳ دست دارد

📊 **دستورات:**
`/newgame` - بازی جدید
`/rules` - قوانین
`/help` - این راهنما
    """
    bot.reply_to(message, help_text, parse_mode='Markdown')

@bot.message_handler(commands=['rules'])
def rules(message):
    rules_text = """
📋 *قوانین بازی حکم*

🎴 **تعداد بازیکنان:** ۴ نفر (۲ تیم دو نفره)
🎴 **تعداد کارت‌ها:** ۵۲ کارت
🎴 **توزیع کارت:** هر بازیکن ۱۳ کارت

🏆 **هدف:** کسب ۷ امتیاز قبل از تیم حریف

🔄 **مراحل:**
۱. انتخاب حکم (کارت ۷ دل)
۲. انتخاب رنگ حکم
۳. شروع بازی از سمت راست حکم
۴. بازی ۱۳ دست

📌 **قوانین بازی:**
- باید همخون بازی کنید
- اگر همخون ندارید، می‌توانید حکم بزنید
- اگر حکم هم ندارید، هر کارتی می‌توانید

🎯 **امتیازدهی:**
- برنده هر دست ۱ امتیاز می‌گیرد
- تیم اولی که به ۷ امتیاز برسد برنده است

🤝 **تیم‌بندی:**
بازیکنان ۱ و ۳ تیم ۱
بازیکنان ۲ و ۴ تیم ۲
    """
    bot.reply_to(message, rules_text, parse_mode='Markdown')

@bot.message_handler(commands=['newgame'])
def new_game(message):
    chat_id = message.chat.id
    user = message.from_user
    
    if chat_id in games:
        bot.reply_to(message, "⚠️ یک بازی در حال انجام است!")
        return
    
    # ایجاد بازی جدید
    game = HokmGame(chat_id)
    game.add_player(user.id, user.first_name)
    games[chat_id] = game
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join_game')
    btn2 = types.InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')
    btn3 = types.InlineKeyboardButton("❌ لغو بازی", callback_data='cancel_game')
    markup.add(btn1, btn2, btn3)
    
    bot.reply_to(message,
        f"🎴 *بازی جدید حکم ساخته شد!*\n\n"
        f"بازیکن ۱: {user.first_name}\n"
        f"📍 ۳ بازیکن دیگر نیاز است.\n\n"
        "روی دکمه 'پیوستن به بازی' کلیک کنید.",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    chat_id = call.message.chat.id
    user = call.from_user
    
    if call.data == 'join_game':
        if chat_id not in games:
            bot.answer_callback_query(call.id, "بازی پیدا نشد!")
            return
        
        game = games[chat_id]
        
        if len(game.players) >= 4:
            bot.answer_callback_query(call.id, "بازی پر شده است!")
            return
        
        if any(p['id'] == user.id for p in game.players):
            bot.answer_callback_query(call.id, "شما قبلاً در بازی هستید!")
            return
        
        # اضافه کردن بازیکن
        game.add_player(user.id, user.first_name)
        
        # آپدیت پیام
        players_list = "\n".join([f"{i+1}. {p['name']}" for i, p in enumerate(game.players)])
        remaining = 4 - len(game.players)
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join_game')
        btn2 = types.InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')
        btn3 = types.InlineKeyboardButton("❌ لغو بازی", callback_data='cancel_game')
        
        if remaining == 0:
            markup.add(btn2, btn3)
        else:
            markup.add(btn1, btn2, btn3)
        
        bot.edit_message_text(
            f"🎴 *بازی حکم*\n\n"
            f"بازیکنان:\n{players_list}\n\n"
            f"{'✅ آماده شروع!' if remaining == 0 else f'📍 {remaining} بازیکن دیگر نیاز است.'}",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, "شما به بازی پیوستید!")
    
    elif call.data == 'start_game':
        if chat_id not in games:
            bot.answer_callback_query(call.id, "بازی پیدا نشد!")
            return
        
        game = games[chat_id]
        
        if len(game.players) < 4:
            bot.answer_callback_query(call.id, "هنوز بازیکنان کافی نیستند!", show_alert=True)
            return
        
        # شروع بازی
        game.game_started = True
        game.deal_cards()
        game.hakem = game.players[0]
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("♠️ پیک", callback_data='trump_♠️')
        btn2 = types.InlineKeyboardButton("♥️ دل", callback_data='trump_♥️')
        btn3 = types.InlineKeyboardButton("♦️ خشت", callback_data='trump_♦️')
        btn4 = types.InlineKeyboardButton("♣️ گیشنیز", callback_data='trump_♣️')
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.edit_message_text(
            f"🎴 *بازی شروع شد!*\n\n"
            f"حکم: {game.hakem['name']}\n"
            f"لطفاً رنگ حکم را انتخاب کنید:",
            chat_id=chat_id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id)
    
    elif call.data.startswith('trump_'):
        if chat_id not in games:
            return
        
        game = games[chat_id]
        trump = call.data.replace('trump_', '')
        game.trump = trump
        
        # ارسال کارت‌ها به هر بازیکن
        for player in game.players:
            try:
                cards = game.get_player_cards(player['id'])
                if cards:
                    cards_text = "\n".join([f"{suit} {value}" for suit, value in cards])
                    bot.send_message(
                        player['id'],
                        f"🎴 *کارت‌های شما:*\n\n{cards_text}\n\n"
                        f"*حکم:* {trump}\n"
                        f"*نوبت:* {game.players[0]['name']}",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"خطا در ارسال کارت به {player['id']}: {e}")
        
        bot.edit_message_text(
            f"✅ *رنگ حکم انتخاب شد:* {trump}\n\n"
            f"کارت‌ها توزیع شدند. بازی شروع می‌شود...\n\n"
            f"برای ادامه، کارت‌های خود را بررسی کنید.",
            chat_id=chat_id,
            message_id=call.message.message_id,
            parse_mode='Markdown'
        )
        bot.answer_callback_query(call.id, f"حکم: {trump}")
    
    elif call.data == 'cancel_game':
        if chat_id in games:
            del games[chat_id]
        
        bot.edit_message_text(
            "❌ بازی لغو شد.",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
        bot.answer_callback_query(call.id)

@bot.message_handler(commands=['join'])
def join_cmd(message):
    bot.reply_to(message, "لطفاً روی دکمه 'پیوستن به بازی' در پیام بازی کلیک کنید.")

# ==================== Flask برای رندر ====================
@app.route('/')
def index():
    return "🤖 ربات حکم در حال اجرا است!"

@app.route('/' + BOT_TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'OK'

# ==================== اجرا ====================
if __name__ == '__main__':
    if WEBHOOK_URL:
        # حالت وب‌هوک برای رندر
        bot.remove_webhook()
        bot.set_webhook(url=WEBHOOK_URL + '/' + BOT_TOKEN)
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
    else:
        # حالت polling برای تست محلی
        print("🤖 ربات حکم در حال اجرا (Polling)...")
        bot.infinity_polling()
