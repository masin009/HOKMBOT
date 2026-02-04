#!/usr/bin/env python3
"""
ربات کامل بازی حکم (Hokm) - نسخه تک فایلی
تمامی کدها در یک فایل
"""

import os
import logging
import random
import sqlite3
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
BOT_TOKEN = "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc"  # توکن رباتت را اینجا قرار بده

# تنظیمات بازی
MAX_PLAYERS = 4
CARDS_PER_PLAYER = 13
WINNING_SCORE = 7

# تنظیمات ایموجی
SUIT_EMOJIS = {
    "pik": "♠️",
    "del": "♥️",
    "khesht": "♦️",
    "gishniz": "♣️"
}

RANK_NAMES = {
    "2": "۲", "3": "۳", "4": "۴", "5": "۵", "6": "۶",
    "7": "۷", "8": "۸", "9": "۹", "10": "۱۰",
    "J": "سرباز", "Q": "بی‌بی", "K": "شاه", "A": "آس"
}

# تنظیمات لاگینگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# وضعیت‌های مکالمه
WAITING_FOR_PLAYERS, IN_GAME = range(2)

# ==================== کلاس کارت ====================
class Card:
    """کلاس کارت"""
    def __init__(self, suit: str, rank: str, value: int):
        self.suit = suit  # pik, del, khesht, gishniz
        self.rank = rank  # 2-10, J, Q, K, A
        self.value = value
        self.id = f"{suit}_{rank}"
        self.symbol = SUIT_EMOJIS.get(suit, "🃏")
    
    def to_dict(self):
        return {
            "id": self.id,
            "suit": self.suit,
            "rank": self.rank,
            "value": self.value,
            "symbol": self.symbol
        }

# ==================== کلاس بازی حکم ====================
class HokmGame:
    """کلاس اصلی بازی حکم"""
    
    def __init__(self):
        self.players = []
        self.deck = []
        self.hands = {}
        self.trump_suit = None
        self.hakem_index = 0
        self.current_player_index = 0
        self.current_trick = 0
        self.trick_cards = []
        self.team1_score = 0
        self.team2_score = 0
        self.game_started = False
        self.create_deck()
    
    def create_deck(self):
        """ایجاد دسته ۵۲ کارتی"""
        suits = ["pik", "del", "khesht", "gishniz"]
        ranks = [
            ("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6),
            ("7", 7), ("8", 8), ("9", 9), ("10", 10),
            ("J", 11), ("Q", 12), ("K", 13), ("A", 14)
        ]
        
        self.deck = []
        for suit in suits:
            for rank, value in ranks:
                self.deck.append(Card(suit, rank, value))
    
    def add_player(self, user_id: int, name: str):
        """اضافه کردن بازیکن جدید"""
        if len(self.players) >= 4:
            return False
        
        self.players.append({
            "id": user_id,
            "name": name,
            "team": len(self.players) % 2
        })
        return True
    
    def start_game(self):
        """شروع بازی"""
        if len(self.players) != 4:
            raise ValueError("باید ۴ بازیکن وجود داشته باشد")
        
        self.game_started = True
        self.hakem_index = 0
        self.team1_score = 0
        self.team2_score = 0
        self.current_trick = 0
    
    def deal_cards(self):
        """توزیع کارت‌ها"""
        random.shuffle(self.deck)
        self.hands = {player['id']: [] for player in self.players}
        
        cards_per_player = 13
        for i, player in enumerate(self.players):
            start_index = i * cards_per_player
            end_index = start_index + cards_per_player
            player_cards = self.deck[start_index:end_index]
            self.hands[player['id']] = [card.to_dict() for card in player_cards]
            self.hands[player['id']].sort(key=lambda x: (x['suit'], -x['value']))
    
    def get_player_cards(self, user_id: int):
        """دریافت کارت‌های یک بازیکن"""
        return self.hands.get(user_id, [])
    
    def get_card_by_id(self, card_id: str):
        """یافتن کارت بر اساس ID"""
        for player_id, cards in self.hands.items():
            for card in cards:
                if card['id'] == card_id:
                    return card
        return None
    
    def play_card(self, user_id: int, card_id: str):
        """بازی کردن یک کارت"""
        player_cards = self.hands.get(user_id, [])
        card_to_play = None
        card_index = -1
        
        for i, card in enumerate(player_cards):
            if card['id'] == card_id:
                card_to_play = card
                card_index = i
                break
        
        if not card_to_play:
            return False
        
        if len(self.trick_cards) == 0:
            self.trick_cards.append({
                "player_id": user_id,
                "card": card_to_play
            })
            player_cards.pop(card_index)
            return True
        
        first_card = self.trick_cards[0]['card']
        first_suit = first_card['suit']
        current_suit = card_to_play['suit']
        
        has_same_suit = any(card['suit'] == first_suit for card in player_cards if card['id'] != card_id)
        
        if has_same_suit and current_suit != first_suit:
            return False
        
        self.trick_cards.append({
            "player_id": user_id,
            "card": card_to_play
        })
        player_cards.pop(card_index)
        return True
    
    @property
    def trick_cards_count(self):
        return len(self.trick_cards)
    
    def next_player(self):
        self.current_player_index = (self.current_player_index + 1) % 4
    
    def complete_trick(self):
        """تکمیل یک دست و تعیین برنده"""
        if len(self.trick_cards) != 4:
            raise ValueError("دست باید ۴ کارت داشته باشد")
        
        first_card = self.trick_cards[0]['card']
        leading_suit = first_card['suit']
        winner_index = 0
        highest_value = 0
        
        for i, trick in enumerate(self.trick_cards):
            card = trick['card']
            
            if card['suit'] == self.trump_suit:
                if leading_suit != self.trump_suit:
                    winner_index = i
                    highest_value = card['value']
                    leading_suit = self.trump_suit
                elif card['value'] > highest_value:
                    winner_index = i
                    highest_value = card['value']
            elif card['suit'] == leading_suit and leading_suit != self.trump_suit:
                if card['value'] > highest_value:
                    winner_index = i
                    highest_value = card['value']
        
        winner_id = self.trick_cards[winner_index]['player_id']
        winner = next(p for p in self.players if p['id'] == winner_id)
        
        if winner['team'] == 0:
            self.team1_score += 1
        else:
            self.team2_score += 1
        
        self.trick_cards = []
        self.current_trick += 1
        
        for i, player in enumerate(self.players):
            if player['id'] == winner_id:
                self.current_player_index = i
                break
        
        return winner
    
    def calculate_final_score(self):
        return self.team1_score, self.team2_score

# ==================== پایگاه داده ====================
class GameDatabase:
    """مدیریت پایگاه داده بازی"""
    
    def __init__(self, db_name="hokm_games.db"):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()
    
    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                players TEXT,
                winner_team INTEGER,
                team1_score INTEGER,
                team2_score INTEGER,
                start_time TIMESTAMP,
                end_time TIMESTAMP,
                duration INTEGER
            )
        ''')
        self.conn.commit()
    
    def add_user(self, user_id: int, username: str, first_name: str):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, first_name))
        self.conn.commit()
    
    def update_user_stats(self, user_id: int, won: bool = False):
        cursor = self.conn.cursor()
        if won:
            cursor.execute('''
                UPDATE users 
                SET games_played = games_played + 1,
                    games_won = games_won + 1
                WHERE user_id = ?
            ''', (user_id,))
        else:
            cursor.execute('''
                UPDATE users 
                SET games_played = games_played + 1
                WHERE user_id = ?
            ''', (user_id,))
        self.conn.commit()

# ==================== کلاس اصلی ربات ====================
class HokmBot:
    def __init__(self, token):
        self.token = token
        self.games = {}
        self.db = GameDatabase()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await update.message.reply_text(
            f"سلام {user.first_name}! 👋\n"
            f"ربات بازی حکم (Hokm) خوش آمدید.\n\n"
            f"📌 دستورات:\n"
            f"/newgame - شروع بازی جدید\n"
            f"/join - پیوستن به بازی\n"
            f"/rules - قوانین بازی\n"
            f"/help - راهنمایی"
        )
    
    async def new_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if chat_id in self.games:
            await update.message.reply_text("⚠️ یک بازی در حال انجام است!")
            return ConversationHandler.END
        
        game = HokmGame()
        self.games[chat_id] = game
        game.add_player(user.id, user.first_name)
        
        keyboard = [
            [InlineKeyboardButton("🎮 پیوستن به بازی", callback_data="join_game")],
            [InlineKeyboardButton("▶️ شروع بازی", callback_data="start_game")],
            [InlineKeyboardButton("❌ لغو بازی", callback_data="cancel_game")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎴 بازی جدید حکم ساخته شد!\n"
            f"بازیکن ۱: {user.first_name}\n"
            f"📍 ۳ بازیکن دیگر نیاز است.\n\n"
            f"دکمه 'پیوستن به بازی' را فشار دهید.",
            reply_markup=reply_markup
        )
        return WAITING_FOR_PLAYERS
    
    async def join_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        if chat_id not in self.games:
            await query.edit_message_text("⚠️ هیچ بازی فعالی وجود ندارد!")
            return
        
        game = self.games[chat_id]
        
        if user.id in [p['id'] for p in game.players]:
            await query.answer("شما قبلاً در بازی هستید!", show_alert=True)
            return
        
        if len(game.players) >= 4:
            await query.answer("بازی پر شده است!", show_alert=True)
            return
        
        game.add_player(user.id, user.first_name)
        players_text = "\n".join([f"{i+1}. {p['name']}" for i, p in enumerate(game.players)])
        
        keyboard = [
            [InlineKeyboardButton("🎮 پیوستن به بازی", callback_data="join_game")],
            [InlineKeyboardButton("▶️ شروع بازی", callback_data="start_game")] if len(game.players) == 4 else [],
            [InlineKeyboardButton("❌ لغو بازی", callback_data="cancel_game")]
        ]
        reply_markup = InlineKeyboardMarkup([row for row in keyboard if row])
        
        await query.edit_message_text(
            f"🎴 بازی حکم\n"
            f"بازیکنان:\n{players_text}\n\n"
            f"{4 - len(game.players)} بازیکن دیگر نیاز است.",
            reply_markup=reply_markup
        )
    
    async def start_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        
        if chat_id not in self.games:
            await query.edit_message_text("⚠️ بازی پیدا نشد!")
            return ConversationHandler.END
        
        game = self.games[chat_id]
        
        if len(game.players) < 4:
            await query.answer("هنوز بازیکنان کافی نیستند!", show_alert=True)
            return WAITING_FOR_PLAYERS
        
        game.start_game()
        game.deal_cards()
        
        hakem_index = game.hakem_index
        hakem_name = game.players[hakem_index]['name']
        
        keyboard = [
            [
                InlineKeyboardButton("♠️ پیک", callback_data="hakem_pik"),
                InlineKeyboardButton("♥️ دل", callback_data="hakem_del"),
            ],
            [
                InlineKeyboardButton("♦️ خشت", callback_data="hakem_khesht"),
                InlineKeyboardButton("♣️ گیشنیز", callback_data="hakem_gishniz"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id,
            f"🎴 بازی شروع شد!\n\n"
            f"حکم: {hakem_name}\n"
            f"لطفاً رنگ حکم را انتخاب کنید:",
            reply_markup=reply_markup
        )
        return IN_GAME
    
    async def select_hakem(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        data = query.data
        
        if chat_id not in self.games:
            return
        
        game = self.games[chat_id]
        hakem_id = game.players[game.hakem_index]['id']
        
        if query.from_user.id != hakem_id:
            await query.answer("فقط حکم می‌تواند رنگ را انتخاب کند!", show_alert=True)
            return
        
        color_map = {
            "hakem_pik": "♠️ پیک",
            "hakem_del": "♥️ دل",
            "hakem_khesht": "♦️ خشت",
            "hakem_gishniz": "♣️ گیشنیز"
        }
        
        game.trump_suit = data.replace("hakem_", "")
        
        await query.edit_message_text(
            f"✅ رنگ حکم انتخاب شد: {color_map[data]}\n\n"
            f"بازی ادامه دارد..."
        )
        await self.play_round(chat_id, context)
    
    async def play_round(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]
        
        if game.current_trick >= 13:
            await self.end_game(chat_id, context)
            return
        
        for player in game.players:
            try:
                await self.send_player_cards(player['id'], game, context)
            except:
                pass
        
        current_player = game.players[game.current_player_index]
        await context.bot.send_message(
            chat_id,
            f"🎯 نوبت: {current_player['name']}"
        )
    
    async def send_player_cards(self, user_id: int, game: HokmGame, context: ContextTypes.DEFAULT_TYPE):
        player_cards = game.get_player_cards(user_id)
        
        if not player_cards:
            return
        
        suits = {
            "pik": "♠️ پیک",
            "del": "♥️ دل", 
            "khesht": "♦️ خشت",
            "gishniz": "♣️ گیشنیز"
        }
        
        message = "🎴 کارت‌های شما:\n\n"
        
        for suit, suit_name in suits.items():
            cards_in_suit = [card for card in player_cards if card['suit'] == suit]
            if cards_in_suit:
                message += f"{suit_name}:\n"
                for card in cards_in_suit:
                    message += f"  {card['rank']} - /play_{card['id']}\n"
                message += "\n"
        
        keyboard = []
        row = []
        for i, card in enumerate(player_cards):
            btn_text = f"{card['symbol']} {card['rank']}"
            row.append(InlineKeyboardButton(btn_text, callback_data=f"play_{card['id']}"))
            if len(row) == 3 or i == len(player_cards) - 1:
                keyboard.append(row)
                row = []
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        
        try:
            await context.bot.send_message(
                user_id,
                message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send cards to {user_id}: {e}")
    
    async def play_card(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        user_id = query.from_user.id
        card_id = query.data.replace("play_", "")
        
        if chat_id not in self.games:
            return
        
        game = self.games[chat_id]
        current_player = game.players[game.current_player_index]
        
        if current_player['id'] != user_id:
            await query.answer("نوبت شما نیست!", show_alert=True)
            return
        
        success = game.play_card(user_id, card_id)
        
        if success:
            try:
                await query.delete_message()
            except:
                pass
            
            card = game.get_card_by_id(card_id)
            await context.bot.send_message(
                chat_id,
                f"{current_player['name']} کارت {card['symbol']} {card['rank']} را بازی کرد."
            )
            
            if game.trick_cards_count == 4:
                winner = game.complete_trick()
                await context.bot.send_message(
                    chat_id,
                    f"🎉 برنده این دست: {winner['name']}\n"
                    f"امتیاز تیم: {game.team1_score} - {game.team2_score}"
                )
                await self.play_round(chat_id, context)
            else:
                game.next_player()
                await self.play_round(chat_id, context)
    
    async def end_game(self, chat_id: int, context: ContextTypes.DEFAULT_TYPE):
        game = self.games[chat_id]
        game.calculate_final_score()
        
        winner_text = "🎉 تیم ۱ برنده شد!" if game.team1_score > game.team2_score else \
                     "🎉 تیم ۲ برنده شد!" if game.team2_score > game.team1_score else "⚖️ مساوی!"
        
        await context.bot.send_message(
            chat_id,
            f"🎴 بازی پایان یافت!\n\n"
            f"امتیاز نهایی:\n"
            f"تیم ۱: {game.team1_score}\n"
            f"تیم ۲: {game.team2_score}\n\n"
            f"{winner_text}\n\n"
            f"/newgame - بازی جدید"
        )
        del self.games[chat_id]
    
    async def cancel_game(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        chat_id = update.effective_chat.id
        if chat_id in self.games:
            del self.games[chat_id]
        
        await query.edit_message_text("❌ بازی لغو شد.")
        return ConversationHandler.END
    
    async def show_rules(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        rules = """
📋 **قوانین بازی حکم (Hokm)**

🎴 **تعداد بازیکنان:** ۴ نفر (۲ تیم دو نفره)
🎴 **تعداد کارت‌ها:** ۵۲ کارت (بدون جوکر)
🎴 **توزیع کارت:** هر بازیکن ۱۳ کارت می‌گیرد

🏆 **هدف بازی:** کسب ۷ امتیاز زودتر از تیم حریف

🔄 **مراحل بازی:**
۱. انتخاب حکم
۲. انتخاب رنگ حکم توسط حکم
۳. شروع بازی از بازیکن سمت راست حکم
۴. بازی در دست‌های ۱۳ تایی

📌 **قوانین بازی کارت:**
- باید همیشه همخون بازی کنید
- اگر همخون ندارید، می‌توانید حکم بزنید
- اگر حکم هم ندارید، هر کارتی می‌توانید بازی کنید

🎯 **امتیازدهی:**
- برنده هر دست ۱ امتیاز می‌گیرد
- تیم اولی که به ۷ امتیاز برسد برنده بازی است

🤝 **تیم‌بندی:**
بازیکنان روبه‌روی هم تیمی هستند
        """
        await update.message.reply_text(rules, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = """
🆘 **راهنمای ربات حکم**

🎮 **شروع بازی:**
1. `/newgame` - ساخت بازی جدید
2. بازیکنان دیگر روی «پیوستن به بازی» کلیک کنند
3. وقتی ۴ نفر کامل شدند، روی «شروع بازی» کلیک کنید

🎴 **در حین بازی:**
- کارت‌ها به صورت خصوصی برای شما ارسال می‌شود
- روی کارت مورد نظر کلیک کنید تا بازی شود
- باید همخون بازی کنید (مگر نداشته باشید)

📊 **دستورات:**
`/newgame` - بازی جدید
`/rules` - قوانین بازی
`/help` - این راهنما
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

# ==================== تابع اصلی ====================
def main():
    bot = HokmBot(BOT_TOKEN)
    application = Application.builder().token(BOT_TOKEN).arbitrary_callback_data(True).build()

    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('newgame', bot.new_game)],
        states={
            WAITING_FOR_PLAYERS: [
                CallbackQueryHandler(bot.join_game, pattern='^join_game$'),
                CallbackQueryHandler(bot.start_game, pattern='^start_game$'),
                CallbackQueryHandler(bot.cancel_game, pattern='^cancel_game$'),
            ],
            IN_GAME: [
                CallbackQueryHandler(bot.select_hakem, pattern='^hakem_'),
                CallbackQueryHandler(bot.play_card, pattern='^play_'),
            ],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_game)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('start', bot.start))
    application.add_handler(CommandHandler('rules', bot.show_rules))
    application.add_handler(CommandHandler('help', bot.help_command))
    application.add_handler(CommandHandler('join', bot.join_game))
    
    print("🤖 ربات حکم در حال اجرا...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
