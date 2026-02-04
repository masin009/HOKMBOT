#!/usr/bin/env python3
"""
ربات کامل بازی حکم با تمام جزئیات
"""

import os
import logging
import random
import json
from datetime import datetime
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

# ==================== تنظیمات ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# وضعیت‌های مکالمه
WAITING, PLAYING = range(2)

# ==================== کلاس بازی ====================
class HokmGame:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.players = []  # [{id, name, team, cards, state}]
        self.deck = []
        self.trump = None
        self.hakem_index = 0
        self.current_player = 0
        self.trick_cards = []  # کارت‌های دست فعلی
        self.tricks_won = [0, 0]  # تیم ۱ و ۲
        self.current_trick = 0
        self.game_started = False
        self.player_states = {}  # وضعیت هر بازیکن
        self.lead_suit = None
        self.create_deck()
    
    def create_deck(self):
        """ایجاد ۵۲ کارت"""
        suits = ['♠️', '♥️', '♦️', '♣️']
        values = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        self.deck = [{'suit': suit, 'value': value, 'id': f"{suit}_{value}"} 
                    for suit in suits for value in values]
        random.shuffle(self.deck)
    
    def add_player(self, user_id, name):
        """اضافه کردن بازیکن"""
        if len(self.players) >= 4:
            return False
        
        # بررسی اینکه آیا کاربر ربات را استارت کرده
        # اینجا فقط اضافه می‌کنیم، بررسی در ربات انجام می‌شود
        
        self.players.append({
            'id': user_id,
            'name': name,
            'team': len(self.players) % 2,
            'cards': [],
            'state': 'waiting'
        })
        return True
    
    def deal_cards(self):
        """توزیع کارت‌ها"""
        for i, player in enumerate(self.players):
            start = i * 13
            end = start + 13
            player['cards'] = sorted(self.deck[start:end], 
                                    key=lambda x: (x['suit'], x['value']))
    
    def get_cards_keyboard(self, user_id):
        """ایجاد کیبورد کارت‌ها برای یک بازیکن"""
        player = next((p for p in self.players if p['id'] == user_id), None)
        if not player:
            return None
        
        keyboard = []
        row = []
        cards = player['cards']
        
        # دسته‌بندی کارت‌ها بر اساس خال
        suits = {'♠️': [], '♥️': [], '♦️': [], '♣️': []}
        for card in cards:
            suits[card['suit']].append(card)
        
        # ایجاد دکمه‌ها
        for suit in ['♠️', '♥️', '♦️', '♣️']:
            if suits[suit]:
                for card in suits[suit]:
                    btn_text = f"{suit} {card['value']}"
                    callback_data = f"play_{card['id']}"
                    row.append(InlineKeyboardButton(btn_text, callback_data=callback_data))
                    
                    if len(row) == 4:  # ۴ کارت در هر ردیف
                        keyboard.append(row)
                        row = []
        
        if row:  # ردیف آخر
            keyboard.append(row)
        
        # دکمه‌های کنترلی
        control_row = []
        if self.trump and self.hakem_index == self.players.index(player):
            control_row.append(InlineKeyboardButton("🔄 تغییر حکم", callback_data="change_trump"))
        
        if control_row:
            keyboard.append(control_row)
        
        return InlineKeyboardMarkup(keyboard)
    
    def play_card(self, user_id, card_id):
        """بازی کردن یک کارت"""
        player = next((p for p in self.players if p['id'] == user_id), None)
        if not player:
            return False, "بازیکن پیدا نشد"
        
        # بررسی نوبت
        if self.players[self.current_player]['id'] != user_id:
            return False, "نوبت شما نیست"
        
        # پیدا کردن کارت
        card_index = next((i for i, c in enumerate(player['cards']) 
                          if c['id'] == card_id), None)
        if card_index is None:
            return False, "کارت پیدا نشد"
        
        card = player['cards'].pop(card_index)
        
        # بررسی قوانین (همخونی)
        if self.lead_suit is None:  # اولین کارت دست
            self.lead_suit = card['suit']
        else:
            # بررسی اینکه آیا بازیکن همخون دارد
            has_lead_suit = any(c['suit'] == self.lead_suit for c in player['cards'])
            if has_lead_suit and card['suit'] != self.lead_suit:
                # کارت را برمی‌گردانیم
                player['cards'].insert(card_index, card)
                return False, f"باید همخون {self.lead_suit} بازی کنید"
        
        # ذخیره کارت بازی شده
        self.trick_cards.append({
            'player_id': user_id,
            'player_name': player['name'],
            'card': card
        })
        
        return True, card
    
    def complete_trick(self):
        """تکمیل یک دست و تعیین برنده"""
        if len(self.trick_cards) != 4:
            return None
        
        # پیدا کردن برنده
        winner_index = 0
        highest_value = 0
        
        for i, trick in enumerate(self.trick_cards):
            card = trick['card']
            
            # ارزش کارت
            value_order = ['2','3','4','5','6','7','8','9','10','J','Q','K','A']
            card_value = value_order.index(card['value'])
            
            # اگر کارت حکم است
            if card['suit'] == self.trump:
                if self.lead_suit != self.trump:
                    winner_index = i
                    highest_value = card_value
                    self.lead_suit = self.trump
                elif card_value > highest_value:
                    winner_index = i
                    highest_value = card_value
            
            # اگر کارت همخون است
            elif card['suit'] == self.lead_suit:
                if card_value > highest_value:
                    winner_index = i
                    highest_value = card_value
        
        winner = self.trick_cards[winner_index]
        
        # افزایش امتیاز تیم برنده
        winner_player = next(p for p in self.players if p['id'] == winner['player_id'])
        self.tricks_won[winner_player['team']] += 1
        
        # ریست کردن دست
        self.trick_cards = []
        self.lead_suit = None
        self.current_trick += 1
        
        # تنظیم نوبت برنده
        for i, p in enumerate(self.players):
            if p['id'] == winner['player_id']:
                self.current_player = i
                break
        
        return winner
    
    def get_game_state(self):
        """وضعیت بازی"""
        return {
            'players': [{'name': p['name'], 'team': p['team']} for p in self.players],
            'trump': self.trump,
            'hakem': self.players[self.hakem_index]['name'] if self.players else None,
            'current_player': self.players[self.current_player]['name'] if self.players else None,
            'scores': self.tricks_won,
            'current_trick': self.current_trick,
            'trick_cards': self.trick_cards
        }

# ==================== ذخیره بازی‌ها ====================
games = {}
user_started_bot = set()  # کاربرانی که ربات را استارت کرده‌اند

# ==================== دستورات ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /start"""
    user = update.effective_user
    
    # ذخیره اینکه کاربر ربات را استارت کرده
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
    """شروع بازی جدید"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id in games:
        await update.message.reply_text("⚠️ یک بازی در حال انجام است!")
        return ConversationHandler.END
    
    # بررسی اینکه کاربر ربات را استارت کرده
    if user.id not in user_started_bot:
        keyboard = [[InlineKeyboardButton("🚀 استارت ربات", url=f"https://t.me/{(await context.bot.get_me()).username}?start=start")]]
        await update.message.reply_text(
            "⚠️ ابتدا باید ربات را در پیوی استارت کنید!\n"
            "روی دکمه زیر کلیک کنید و سپس /start را بفرستید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ConversationHandler.END
    
    # ایجاد بازی جدید
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
        f"تیم: 🟦\n\n"
        f"📍 ۳ بازیکن دیگر نیاز است.\n\n"
        f"⚠️ *توجه:* بازیکنان باید ربات را در پیوی استارت کرده باشند.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    return WAITING

async def join_game_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور /join"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    if chat_id not in games:
        await update.message.reply_text("⚠️ هیچ بازی فعالی وجود ندارد!")
        return
    
    game = games[chat_id]
    
    # بررسی وضعیت بازی
    if game.game_started:
        await update.message.reply_text("⚠️ بازی قبلاً شروع شده است!")
        return
    
    # بررسی تعداد بازیکنان
    if len(game.players) >= 4:
        await update.message.reply_text("⚠️ بازی پر شده است!")
        return
    
    # بررسی تکراری نبودن
    if any(p['id'] == user.id for p in game.players):
        await update.message.reply_text("⚠️ شما قبلاً در بازی هستید!")
        return
    
    # بررسی استارت ربات
    if user.id not in user_started_bot:
        keyboard = [[InlineKeyboardButton("🚀 استارت ربات", url=f"https://t.me/{(await context.bot.get_me()).username}?start=start")]]
        await update.message.reply_text(
            "⚠️ ابتدا باید ربات را در پیوی استارت کنید!\n"
            "روی دکمه زیر کلیک کنید و سپس /start را بفرستید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # اضافه کردن بازیکن
    game.add_player(user.id, user.first_name)
    
    # به روزرسانی پیام بازی
    players_text = "\n".join([f"{i+1}. {p['name']} (تیم {'🟦' if p['team'] == 0 else '🟥'})" 
                             for i, p in enumerate(game.players)])
    
    keyboard = [[InlineKeyboardButton("🎮 پیوستن به بازی", callback_data='join_game')]]
    if len(game.players) == 4:
        keyboard.append([InlineKeyboardButton("▶️ شروع بازی", callback_data='start_game')])
    keyboard.append([InlineKeyboardButton("❌ لغو بازی", callback_data='cancel_game')])
    
    # پیدا کردن پیام اصلی بازی
    if context.chat_data.get('game_message_id'):
        try:
            await context.bot.edit_message_text(
                f"🎴 *بازی حکم*\n\n"
                f"بازیکنان:\n{players_text}\n\n"
                f"{'✅ آماده شروع!' if len(game.players) == 4 else f'📍 {4-len(game.players)} بازیکن دیگر نیاز است.'}",
                chat_id=chat_id,
                message_id=context.chat_data['game_message_id'],
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except:
            pass
    
    await update.message.reply_text(
        f"✅ {user.first_name} به بازی پیوست!\n"
        f"تیم: {'🟦' if game.players[-1]['team'] == 0 else '🟥'}"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک روی دکمه‌ها"""
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
        
        # بررسی شرایط
        if game.game_started:
            await query.answer("بازی قبلاً شروع شده!", show_alert=True)
            return PLAYING
        
        if len(game.players) >= 4:
            await query.answer("بازی پر شده است!", show_alert=True)
            return WAITING
        
        if any(p['id'] == user.id for p in game.players):
            await query.answer("شما قبلاً در بازی هستید!", show_alert=True)
            return WAITING
        
        # بررسی استارت ربات
        if user.id not in user_started_bot:
            keyboard = [[InlineKeyboardButton("🚀 استارت ربات", url=f"https://t.me/{(await context.bot.get_me()).username}?start=start")]]
            await query.message.reply_text(
                f"⚠️ {user.first_name} باید ربات را در پیوی استارت کنید!\n"
                "روی دکمه زیر کلیک کنید و سپس /start را بفرستید:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return WAITING
        
        # اضافه کردن بازیکن
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
        
        # شروع بازی
        game.game_started = True
        game.deal_cards()
        
        # انتخاب حکم (کسی که ۷ دل دارد)
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
        
        # تنظیم نوبت (بازیکن سمت راست حکم)
        game.current_player = (game.hakem_index + 1) % 4
        
        await query.edit_message_text(
            f"✅ *رنگ حکم انتخاب شد:* {trump}\n\n"
            f"کارت‌ها توزیع شدند. نوبت: {game.players[game.current_player]['name']}",
            parse_mode='Markdown'
        )
        
        # ارسال کارت‌ها به همه بازیکنان
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
        
        # اطلاع در گروه
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
        
        # بازی کردن کارت
        success, result = game.play_card(user.id, card_id)
        
        if not success:
            await query.answer(result, show_alert=True)
            return PLAYING
        
        card = result
        
        # پنهان کردن پیام کارت‌های قبلی
        try:
            await query.delete_message()
        except:
            pass
        
        # اطلاع در گروه
        await query.message.reply_text(
            f"🎴 {user.first_name} کارت {card['suit']} {card['value']} را بازی کرد."
        )
        
        # اگر دست کامل شد
        if len(game.trick_cards) == 4:
            winner = game.complete_trick()
            
            await query.message.reply_text(
                f"🏆 برنده این دست: {winner['player_name']}\n"
                f"با کارت {winner['card']['suit']} {winner['card']['value']}\n\n"
                f"امتیازها:\n"
                f"تیم 🟦: {game.tricks_won[0]}\n"
                f"تیم 🟥: {game.tricks_won[1]}"
            )
            
            # بررسی پایان بازی
            if game.current_trick >= 13:
                await end_game(chat_id, query.message, context)
                return ConversationHandler.END
            
            # ارسال کارت‌های جدید به بازیکن بعدی
            next_player = game.players[game.current_player]
            try:
                keyboard = game.get_cards_keyboard(next_player['id'])
                if keyboard:
                    await context.bot.send_message(
                        next_player['id'],
                        f"🎴 نوبت شماست!\n"
                        f"کارت‌های شما:",
                        reply_markup=keyboard,
                        parse_mode='Markdown'
                    )
            except:
                pass
            
            await query.message.reply_text(f"🎯 نوبت: {next_player['name']}")
        
        else:
            # نوبت بازیکن بعدی
            game.current_player = (game.current_player + 1) % 4
            next_player = game.players[game.current_player]
            
            # ارسال کارت‌های جدید به بازیکن بعدی
            try:
                keyboard = game.get_cards_keyboard(next_player['id'])
                if keyboard:
                    await context.bot.send_message(
                        next_player['id'],
                        f"🎴 نوبت شماست!\n"
                        f"کارت‌های شما:",
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
    """پایان بازی"""
    if chat_id not in games:
        return
    
    game = games[chat_id]
    
    # تعیین برنده
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
    
    # حذف بازی
    del games[chat_id]

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قوانین بازی"""
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
    """راهنما"""
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

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وضعیت فعلی"""
    chat_id = update.effective_chat.id
    
    if chat_id in games:
        game = games[chat_id]
        state = game.get_game_state()
        
        status_text = f"🎴 *وضعیت بازی*\n\n"
        status_text += f"بازیکنان:\n"
        for p in state['players']:
            status_text += f"• {p['name']} (تیم {'🟦' if p['team'] == 0 else '🟥'})\n"
        
        if state['trump']:
            status_text += f"\nحکم: {state['trump']}\n"
            status_text += f"نوبت: {state['current_player']}\n"
            status_text += f"امتیازها: 🟦 {state['scores'][0]} - {state['scores'][1]} 🟥\n"
            status_text += f"دست: {state['current_trick']}/۱۳"
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    else:
        await update.message.reply_text("⚠️ هیچ بازی فعالی در این گروه وجود ندارد.")

# ==================== اصلی ====================
def main():
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
            CommandHandler('status', status)
        ],
    )
    
    # اضافه کردن هندلرها
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('rules', rules))
    application.add_handler(CommandHandler('help', help_cmd))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('join', join_game_cmd))
    
    # شروع ربات
    print("🤖 ربات حکم در حال اجرا...")
    application.run_polling()

if __name__ == '__main__':
    main()
