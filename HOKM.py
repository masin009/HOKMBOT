#!/usr/bin/env python3
"""
ربات کامل بازی حکم - نسخه Webhook برای رندر
"""

import os
import logging
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from flask import Flask, request

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc")
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://hokmbot.onrender.com")  # آدرس رندرت

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== Flask App ====================
app = Flask(__name__)

# ==================== کلاس بازی ====================
class HokmGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = []
        self.deck = []
        self.trump = None
        self.hakem_index = 0
        self.current_player = 0
        self.trick_cards = []
        self.tricks_won = [0, 0]
        self.current_trick = 0
        self.game_started = False
        self.lead_suit = None
        self.create_deck()
    
    def create_deck(self):
        suits = ['♠️', '♥️', '♦️', '♣️']
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.deck = [{'suit': suit, 'value': value, 'id': f"{suit}_{value}"} 
                    for suit in suits for value in values]
        random.shuffle(self.deck)
    
    def add_player(self, user_id, name):
        if len(self.players) >= 4:
            return False
        
        self.players.append({
            'id': user_id,
            'name': name,
            'team': len(self.players) % 2,
            'cards': [],
            'state': 'waiting'
        })
        return True
    
    def deal_cards(self):
        for i, player in enumerate(self.players):
            start = i * 13
            end = start + 13
            player['cards'] = sorted(self.deck[start:end], 
                                    key=lambda x: (x['suit'], x['value']))
    
    def get_cards_keyboard(self, user_id):
        player = next((p for p in self.players if p['id'] == user_id), None)
        if not player:
            return None
        
        keyboard = []
        row = []
        cards = player['cards']
        
        suits = {'♠️': [], '♥️': [], '♦️': [], '♣️': []}
        for card in cards:
            suits[card['suit']].append(card)
        
        for suit in ['♠️', '♥️', '♦️', '♣️']:
            if suits[suit]:
                for card in suits[suit]:
                    btn_text = f"{suit} {card['value']}"
                    callback_data = f"play_{card['id']}"
                    row.append(InlineKeyboardButton(btn_text, callback_data=callback_data))
                    
                    if len(row) == 4:
                        keyboard.append(row)
                        row = []
        
        if row:
            keyboard.append(row)
        
        return InlineKeyboardMarkup(keyboard) if keyboard else None
    
    def play_card(self, user_id, card_id):
        player = next((p for p in self.players if p['id'] == user_id), None)
        if not player:
            return False, "بازیکن پیدا نشد"
        
        if self.players[self.current_player]['id'] != user_id:
            return False, "نوبت شما نیست"
        
        card_index = next((i for i, c in enumerate(player['cards']) 
                          if c['id'] == card_id), None)
        if card_index is None:
            return False, "کارت پیدا نشد"
        
        card = player['cards'].pop(card_index)
        
        if self.lead_suit is None:
            self.lead_suit = card['suit']
        else:
            has_lead_suit = any(c['suit'] == self.lead_suit for c in player['cards'])
            if has_lead_suit and card['suit'] != self.lead_suit:
                player['cards'].insert(card_index, card)
                return False, f"باید همخون {self.lead_suit} بازی کنید"
        
        self.trick_cards.append({
            'player_id': user_id,
            'player_name': player['name'],
            'card': card
        })
        
        return True, card
    
    def complete_trick(self):
        if len(self.trick_cards) != 4:
            return None
        
        winner_index = 0
        highest_value = 0
        
        for i, trick in enumerate(self.trick_cards):
            card = trick['card']
            
            value_order = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
            card_value = value_order.index(card['value'])
            
            if card['suit'] == self.trump:
                if self.lead_suit != self.trump:
                    winner_index = i
                    highest_value = card_value
                    self.lead_suit = self.trump
                elif card_value > highest_value:
                    winner_index = i
                    highest_value = card_value
            elif card['suit'] == self.lead_suit:
                if card_value > highest_value:
                    winner_index = i
                    highest_value = card_value
        
        winner = self.trick_cards[winner_index]
        winner_player = next(p for p in self.players if p['id'] == winner['player_id'])
        self.tricks_won[winner_player['team']] += 1
        
        self.trick_cards = []
        self.lead_suit = None
        self.current_trick += 1
        
        for i, p in enumerate(self.players):
            if p['id'] == winner['player_id']:
                self.current_player = i
                break
        
        return winner

# ==================== ذخیره بازی‌ها ====================
games = {}
user_started_bot = set()

# ==================== وضعیت‌های مکالمه ====================
WAITING, PLAYING = range(2)

# ==================== دستورات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_started_bot.add(user.id)
    
    await update.message.reply_text(
        f"سلام {user.first_name}! 👋\n"
        f"🎴 *ربات بازی حکم*\n\n"
        f"📌 برای بازی در گروه:\n"
        f"۱. در گروه `/newgame` را وارد کن\n"
        f"۲. بازیکنان دیگر با `/join` می‌پیوندند\n"
        f"۳. وقتی ۴ نفر شدید بازی شروع می‌شود\n\n"
        f"✅ شما اکنون می‌توانید در بازی‌ها شرکت کنید.",
        parse_mode='Markdown'
    )

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id in games:
        await update.message.reply_text("⚠️ یک بازی در حال انجام است!")
        return ConversationHandler.END
    
    if user.id not in user_started_bot:
        keyboard = [[InlineKeyboardButton("🚀 استارت ربات", 
                     url=f"https://t.me/{(await context.bot.get_me()).username}?start=start")]]
        await update.message.reply_text(
            "⚠️ ابتدا باید ربات را در پیوی استارت کنید!\n"
            "روی دکمه زیر کلیک کنید و سپس /start را بفرستید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    game = HokmGame(chat_id)
    game.add_player(user.id, user.first_name)
    games[chat_id] = game
    
    keyboard = [[
        InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join_game'),
        InlineKeyboardButton("❌ لغو بازی", callback_data='cancel_game')
    ]]
    
    await update.message.reply_text(
        f"🎴 *بازی جدید حکم ساخته شد!*\n\n"
        f"بازیکن ۱: {user.first_name}\n"
        f"تیم: {'🟦' if game.players[0]['team'] == 0 else '🟥'}\n\n"
        f"📍 ۳ بازیکن دیگر نیاز است.\n\n"
        f"⚠️ *توجه:* بازیکنان باید ربات را در پیوی استارت کرده باشند.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return WAITING

async def join_game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in games:
        await update.message.reply_text("⚠️ هیچ بازی فعالی وجود ندارد!")
        return
    
    game = games[chat_id]
    
    if game.game_started:
        await update.message.reply_text("⚠️ بازی قبلاً شروع شده است!")
        return
    
    if len(game.players) >= 4:
        await update.message.reply_text("⚠️ بازی پر شده است!")
        return
    
    if any(p['id'] == user.id for p in game.players):
        await update.message.reply_text("⚠️ شما قبلاً در بازی هستید!")
        return
    
    if user.id not in user_started_bot:
        keyboard = [[InlineKeyboardButton("🚀 استارت ربات", 
                     url=f"https://t.me/{(await context.bot.get_me()).username}?start=start")]]
        await update.message.reply_text(
            "⚠️ ابتدا باید ربات را در پیوی استارت کنید!\n"
            "روی دکمه زیر کلیک کنید و سپس /start را بفرستید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    game.add_player(user.id, user.first_name)
    
    players_text = "\n".join([f"{i+1}. {p['name']} (تیم {'🟦' if p['team'] == 0 else '🟥'})" 
                             for i, p in enumerate(game.players)])
    
    keyboard = [[InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join_game')]]
    if len(game.players) == 4:
        keyboard.append([InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')])
    keyboard.append([InlineKeyboardButton("❌ لغو بازی", callback_data='cancel_game')])
    
    await update.message.reply_text(
        f"🎴 *بازی حکم - به‌روزرسانی*\n\n"
        f"بازیکنان:\n{players_text}\n\n"
        f"{'✅ آماده شروع!' if len(game.players) == 4 else f'📍 {4-len(game.players)} بازیکن دیگر نیاز است.'}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    await update.message.reply_text(
        f"✅ {user.first_name} به بازی پیوست!\n"
        f"تیم: {'🟦' if game.players[-1]['team'] == 0 else '🟥'}"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if data == 'join_game':
        if chat_id not in games:
            await query.edit_message_text("⚠️ بازی پیدا نشد!")
            return WAITING
        
        game = games[chat_id]
        
        if game.game_started:
            await query.answer("بازی قبلاً شروع شده!", show_alert=True)
            return PLAYING
        
        if len(game.players) >= 4:
            await query.answer("بازی پر شده است!", show_alert=True)
            return WAITING
        
        if any(p['id'] == user.id for p in game.players):
            await query.answer("شما قبلاً در بازی هستید!", show_alert=True)
            return WAITING
        
        if user.id not in user_started_bot:
            keyboard = [[InlineKeyboardButton("🚀 استارت ربات", 
                         url=f"https://t.me/{(await context.bot.get_me()).username}?start=start")]]
            await query.message.reply_text(
                f"⚠️ {user.first_name} باید ربات را در پیوی استارت کنید!\n"
                "روی دکمه زیر کلیک کنید و سپس /start را بفرستید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING
        
        game.add_player(user.id, user.first_name)
        
        players_text = "\n".join([f"{i+1}. {p['name']} (تیم {'🟦' if p['team'] == 0 else '🟥'})" 
                                 for i, p in enumerate(game.players)])
        
        keyboard = [[InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join_game')]]
        if len(game.players) == 4:
            keyboard.append([InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')])
        keyboard.append([InlineKeyboardButton("❌ لغو بازی", callback_data='cancel_game')])
        
        await query.edit_message_text(
            f"🎴 *بازی حکم*\n\n"
            f"بازیکنان:\n{players_text}\n\n"
            f"{'✅ آماده شروع!' if len(game.players) == 4 else f'📍 {4-len(game.players)} بازیکن دیگر نیاز است.'}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        await query.message.reply_text(f"✅ {user.first_name} به بازی پیوست!")
        
        if len(game.players) == 4:
            keyboard = [[InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')]]
            await query.message.reply_text(
                "🎯 همه بازیکنان حاضرند! برای شروع بازی کلیک کنید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        
        return WAITING
    
    elif data == 'start_game':
        if chat_id not in games:
            await query.edit_message_text("⚠️ بازی پیدا نشد!")
            return ConversationHandler.END
        
        game = games[chat_id]
        
        if len(game.players) < 4:
            await query.answer("هنوز بازیکنان کافی نیستند!", show_alert=True)
            return WAITING
        
        game.game_started = True
        game.deal_cards()
        
        for i, player in enumerate(game.players):
            if any(card['suit'] == '♥️' and card['value'] == '7' for card in player['cards']):
                game.hakem_index = i
                break
        
        hakem = game.players[game.hakem_index]
        
        keyboard = [[
            InlineKeyboardButton("♠️ پیک", callback_data='trump_♠️'),
            InlineKeyboardButton("♥️ دل", callback_data='trump_♥️'),
        ], [
            InlineKeyboardButton("♦️ خشت", callback_data='trump_♦️'),
            InlineKeyboardButton("♣️ گیشنیز", callback_data='trump_♣️'),
        ]]
        
        await query.edit_message_text(
            f"🎴 *بازی شروع شد!*\n\n"
            f"تیم‌بندی:\n"
            f"تیم 🟦: {game.players[0]['name']} & {game.players[2]['name']}\n"
            f"تیم 🟥: {game.players[1]['name']} & {game.players[3]['name']}\n\n"
            f"حکم: {hakem['name']}\n"
            f"لطفاً رنگ حکم را انتخاب کنید:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return PLAYING
    
    elif data.startswith('trump_'):
        if chat_id not in games:
            return ConversationHandler.END
        
        game = games[chat_id]
        trump = data.replace('trump_', '')
        game.trump = trump
        game.current_player = (game.hakem_index + 1) % 4
        
        await query.edit_message_text(
            f"✅ *رنگ حکم انتخاب شد:* {trump}\n\n"
            f"کارت‌ها توزیع شدند. نوبت: {game.players[game.current_player]['name']}",
            parse_mode='Markdown'
        )
        
        for player in game.players:
            try:
                keyboard = game.get_cards_keyboard(player['id'])
                if keyboard:
                    await context.bot.send_message(
                        player['id'],
                        f"🎴 *کارت‌های شما*\n"
                        f"حکم: {trump}\n"
                        f"تیم: {'🟦' if player['team'] == 0 else '🟥'}\n\n"
                        f"برای بازی کردن روی کارت کلیک کنید:",
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"خطا در ارسال کارت به {player['id']}: {e}")
                await query.message.reply_text(
                    f"⚠️ {player['name']} ربات را در پیوی استارت نکرده است!\n"
                    f"لطفاً با ربات در تماس باشید."
                )
        
        await query.message.reply_text(
            f"🎯 نوبت: {game.players[game.current_player]['name']}\n"
            f"کارت‌ها به صورت خصوصی برای بازیکنان ارسال شد."
        )
        
        return PLAYING
    
    elif data.startswith('play_'):
        if chat_id not in games:
            return ConversationHandler.END
        
        game = games[chat_id]
        card_id = data.replace('play_', '')
        
        success, result = game.play_card(user.id, card_id)
        
        if not success:
            await query.answer(result, show_alert=True)
            return PLAYING
        
        card = result
        
        try:
            await query.delete_message()
        except:
            pass
        
        await query.message.reply_text(
            f"🎴 {user.first_name} کارت {card['suit']} {card['value']} را بازی کرد."
        )
        
        if len(game.trick_cards) == 4:
            winner = game.complete_trick()
            
            await query.message.reply_text(
                f"🏆 برنده این دست: {winner['player_name']}\n"
                f"با کارت {winner['card']['suit']} {winner['card']['value']}\n\n"
                f"امتیازها:\n"
                f"تیم 🟦: {game.tricks_won[0]}\n"
                f"تیم 🟥: {game.tricks_won[1]}"
            )
            
            if game.current_trick >= 13:
                await end_game(chat_id, query.message, context)
                return ConversationHandler.END
            
            next_player = game.players[game.current_player]
            try:
                keyboard = game.get_cards_keyboard(next_player['id'])
                if keyboard:
                    await context.bot.send_message(
                        next_player['id'],
                        f"🎴 نوبت شماست!\nکارت‌های شما:",
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
            except:
                pass
            
            await query.message.reply_text(f"🎯 نوبت: {next_player['name']}")
        
        else:
            game.current_player = (game.current_player + 1) % 4
            next_player = game.players[game.current_player]
            
            try:
                keyboard = game.get_cards_keyboard(next_player['id'])
                if keyboard:
                    await context.bot.send_message(
                        next_player['id'],
                        f"🎴 نوبت شماست!\nکارت‌های شما:",
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
            except:
                pass
            
            await query.message.reply_text(f"🎯 نوبت: {next_player['name']}")
        
        return PLAYING
    
    elif data == 'cancel_game':
        if chat_id in games:
            del games[chat_id]
        
        await query.edit_message_text("❌ بازی لغو شد.")
        return ConversationHandler.END

async def end_game(chat_id, message, context):
    if chat_id not in games:
        return
    
    game = games[chat_id]
    
    if game.tricks_won[0] > game.tricks_won[1]:
        winner = "🎉 *تیم 🟦 برنده شد!*"
    elif game.tricks_won[1] > game.tricks_won[0]:
        winner = "🎉 *تیم 🟥 برنده شد!*"
    else:
        winner = "⚖️ *مساوی!*"
    
    await message.reply_text(
        f"🎴 *پایان بازی*\n\n"
        f"امتیاز نهایی:\n"
        f"تیم 🟦: {game.tricks_won[0]}\n"
        f"تیم 🟥: {game.tricks_won[1]}\n\n"
        f"{winner}\n\n"
        f"/newgame - بازی جدید",
        parse_mode='Markdown'
    )
    
    del games[chat_id]

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules_text = """
📋 *قوانین بازی حکم*

🎴 **تعداد بازیکنان:** ۴ نفر (۲ تیم دو نفره)
🎴 **تعداد کارت‌ها:** ۵۲ کارت (بدون جوکر)
🎴 **توزیع کارت:** هر بازیکن ۱۳ کارت می‌گیرد

🏆 **هدف بازی:** کسب ۷ امتیاز قبل از تیم حریف

🔄 **مراحل بازی:**
۱. انتخاب حکم (کسی که ۷ دل دارد)
۲. انتخاب رنگ حکم توسط حکم
۳. شروع بازی از بازیکن سمت راست حکم
۴. بازی در ۱۳ دست

📌 **قوانین بازی کارت:**
- باید همیشه همخون بازی کنید
- اگر همخون ندارید، می‌توانید حکم بزنید
- اگر حکم هم ندارید، هر کارتی می‌توانید بازی کنید

🎯 **امتیازدهی:**
- برنده هر دست ۱ امتیاز می‌گیرد
- تیم اولی که به ۷ امتیاز برسد برنده بازی است

🤝 **تیم‌بندی:**
بازیکنان ۱ و ۳: تیم 🟦
بازیکنان ۲ و ۴: تیم 🟥
    """
    await update.message.reply_text(rules_text, parse_mode='Markdown')

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
🆘 *راهنمای ربات حکم*

🎮 **شروع بازی در گروه:**
۱. `/newgame` - ساخت بازی جدید
۲. بازیکنان دیگر با کلیک روی «پیوستن به بازی» می‌پیوندند
۳. وقتی ۴ نفر کامل شدند، روی «شروع بازی» کلیک کنید

⚠️ **شرایط لازم:**
- همه بازیکنان باید ربات را در پیوی استارت کرده باشند
- برای استارت: روی ربات کلیک کنید و `/start` بفرستید

🎴 **در حین بازی:**
- کارت‌ها به صورت خصوصی برای شما ارسال می‌شوند
- روی کارت مورد نظر کلیک کنید تا بازی شود
- باید همخون بازی کنید (مگر نداشته باشید)

📊 **دستورات:**
`/start` - فعال‌سازی ربات
`/newgame` - بازی جدید
`/join` - پیوستن به بازی
`/rules` - قوانین بازی
`/help` - این راهنما
    """
    await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== Flask Routes ====================
@app.route('/')
def home():
    return "🤖 ربات حکم فعال است!"

@app.route('/webhook', methods=['POST'])
def webhook():
    """دریافت وب‌هوک از تلگرام"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_json(force=True)
        update = Update.de_json(json_string, application.bot)
        application.update_queue.put(update)
        return 'OK'
    return 'Bad Request', 400

# ==================== تنظیمات Application ====================
# ساخت application
application = Application.builder().token(BOT_TOKEN).build()

# مکالمه برای بازی
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('newgame', new_game)],
    states={
        WAITING: [
            CallbackQueryHandler(button_handler, pattern='^join_game$'),
            CallbackQueryHandler(button_handler, pattern='^start_game$'),
            CallbackQueryHandler(button_handler, pattern='^cancel_game$'),
            CommandHandler('join', join_game_cmd),
        ],
        PLAYING: [
            CallbackQueryHandler(button_handler, pattern='^trump_'),
            CallbackQueryHandler(button_handler, pattern='^play_'),
            CallbackQueryHandler(button_handler, pattern='^cancel_game$'),
        ],
    },
    fallbacks=[
        CommandHandler('cancel', button_handler),
    ],
)

# اضافه کردن هندلرها
application.add_handler(conv_handler)
application.add_handler(CommandHandler('start', start))
application.add_handler(CommandHandler('rules', rules))
application.add_handler(CommandHandler('help', help_cmd))
application.add_handler(CommandHandler('join', join_game_cmd))

# ==================== راه‌اندازی ====================
async def setup_webhook():
    """تنظیم وب‌هوک"""
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook set to: {webhook_url}")
    else:
        logger.warning("⚠️ WEBHOOK_URL not set")

def run_flask():
    """راه‌اندازی Flask"""
    app.run(host='0.0.0.0', port=PORT)

async def main():
    """تابع اصلی"""
    await application.initialize()
    await setup_webhook()
    
    if WEBHOOK_URL:
        # حالت Webhook
        print(f"🤖 ربات حکم در حال اجرا (Webhook) روی پورت {PORT}...")
        
        # راه‌اندازی Flask در thread جداگانه
        import threading
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        
        # نگه داشتن برنامه فعال
        await application.start()
        await asyncio.Event().wait()
    else:
        # حالت Polling (برای تست)
        print("🤖 ربات حکم در حال اجرا (Polling)...")
        await application.start()
        await application.updater.start_polling()
        await application.idle()

if __name__ == '__main__':
    # برای رندر باید requirements.txt داشته باشی:
    # python-telegram-bot==20.7
    # flask==2.3.3
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 ربات متوقف شد.")
