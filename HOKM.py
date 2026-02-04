"""
Hokm Game Bot - Optimized for Render.com
"""

import os
import logging
import random
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
from uuid import uuid4

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode

# ============ CONFIG ============
BOT_TOKEN = os.getenv("BOT_TOKEN")

# برای Render
if not BOT_TOKEN:
    BOT_TOKEN = "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc"  # در Render از محیطی می‌گیرد

# ============ GAME LOGIC ============
SUITS = ['hearts', 'diamonds', 'clubs', 'spades']
SUIT_SYMBOLS = {'hearts': '❤️', 'diamonds': '♦️', 'clubs': '♣️', 'spades': '♠️'}
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {rank: i+2 for i, rank in enumerate(RANKS)}

class Card:
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.value = RANK_VALUES[rank]
    
    def __str__(self):
        return f"{SUIT_SYMBOLS[self.suit]}{self.rank}"

class Player:
    def __init__(self, user_id: int, name: str):
        self.user_id = user_id
        self.name = name
        self.cards: List[Card] = []
        self.team = 0
        self.tricks_won = 0
        self.is_ready = False
    
    def add_card(self, card: Card):
        self.cards.append(card)
    
    def remove_card(self, suit: str, rank: str) -> bool:
        for i, card in enumerate(self.cards):
            if card.suit == suit and card.rank == rank:
                del self.cards[i]
                return True
        return False
    
    def has_suit(self, suit: str) -> bool:
        return any(card.suit == suit for card in self.cards)

class Game:
    def __init__(self, game_id: str, creator_id: int):
        self.game_id = game_id
        self.players: Dict[int, Player] = {}
        self.player_order: List[int] = []
        self.phase = "waiting"  # waiting, choosing_trump, playing, ended
        self.trump_suit: Optional[str] = None
        self.dealer_index = 0
        self.current_player_index = 0
        self.current_trick: List[Tuple[int, Card]] = []
        self.scores = {0: 0, 1: 0}
        self.round = 1
    
    @property
    def current_player_id(self) -> Optional[int]:
        if not self.player_order:
            return None
        return self.player_order[self.current_player_index]
    
    @property
    def player_count(self):
        return len(self.players)
    
    def add_player(self, player: Player):
        if self.player_count >= 4:
            return False
        self.players[player.user_id] = player
        self.player_order.append(player.user_id)
        player.team = (self.player_count - 1) % 2
        return True
    
    def remove_player(self, user_id: int):
        if user_id in self.players:
            del self.players[user_id]
            self.player_order.remove(user_id)
            return True
        return False
    
    def start_game(self):
        if self.player_count != 4:
            return False
        
        # Create and shuffle deck
        deck = [Card(suit, rank) for suit in SUITS for rank in RANKS]
        random.shuffle(deck)
        
        # Deal 13 cards to each player
        for i in range(13):
            for player_id in self.player_order:
                if deck:
                    self.players[player_id].add_card(deck.pop())
        
        # Set initial dealer
        self.dealer_index = random.randint(0, 3)
        self.current_player_index = (self.dealer_index + 1) % 4
        self.phase = "choosing_trump"
        return True

# ============ BOT HANDLERS ============
games: Dict[str, Game] = {}
user_games: Dict[int, str] = {}

def get_user_game(user_id: int) -> Optional[Game]:
    game_id = user_games.get(user_id)
    return games.get(game_id) if game_id else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎮 بازی جدید", callback_data="new_game")],
        [InlineKeyboardButton("📖 آموزش بازی", callback_data="tutorial")]
    ]
    
    await update.message.reply_text(
        "🤖 به ربات بازی حکم خوش آمدید!\n\n"
        "🎯 یک بازی کارتی ۴ نفره با قوانین کامل حکم\n\n"
        "برای شروع روی «بازی جدید» کلیک کنید.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )

async def new_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    
    # Check if user already in a game
    if user.id in user_games:
        await query.edit_message_text(
            "⚠️ شما در حال حاضر در یک بازی هستید!\n"
            "برای خروج از /leave استفاده کنید."
        )
        return
    
    # Create new game
    game_id = str(uuid4())[:6].upper()
    game = Game(game_id, user.id)
    game.add_player(Player(user.id, user.first_name))
    
    games[game_id] = game
    user_games[user.id] = game_id
    
    # Create waiting room
    players_text = "\n".join([
        f"{i+1}. 👤 {game.players[pid].name}" 
        for i, pid in enumerate(game.player_order)
    ])
    
    message = (
        f"🎮 <b>اتاق بازی جدید</b>\n\n"
        f"🆔 کد بازی: <code>{game_id}</code>\n\n"
        f"👥 بازیکنان:\n{players_text}\n\n"
        f"📝 برای دعوت دوستان، کد بالا را بفرستید."
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ من آماده‌ام", callback_data=f"ready_{game_id}")],
        [InlineKeyboardButton("🔄 وضعیت", callback_data=f"status_{game_id}")],
        [InlineKeyboardButton("❌ خروج", callback_data=f"leave_{game_id}")]
    ]
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def join_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 برای پیوستن به بازی، کد بازی را وارد کنید:\n\n"
        "مثال: <code>/join ABC123</code>",
        parse_mode=ParseMode.HTML
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "⚠️ لطفاً کد بازی را وارد کنید:\n"
            "<code>/join ABC123</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    game_id = context.args[0].upper()
    user = update.effective_user
    
    if user.id in user_games:
        await update.message.reply_text("⚠️ شما در حال حاضر در بازی‌ای هستید!")
        return
    
    if game_id not in games:
        await update.message.reply_text("⚠️ بازی یافت نشد!")
        return
    
    game = games[game_id]
    if game.player_count >= 4:
        await update.message.reply_text("⚠️ بازی تکمیل است!")
        return
    
    # Add player
    game.add_player(Player(user.id, user.first_name))
    user_games[user.id] = game_id
    
    # Notify all players
    for player_id in game.player_order:
        try:
            players_list = "\n".join([
                f"{i+1}. 👤 {game.players[pid].name}" 
                for i, pid in enumerate(game.player_order)
            ])
            
            await context.bot.send_message(
                player_id,
                f"🎉 {user.first_name} به بازی پیوست!\n\n"
                f"👥 بازیکنان:\n{players_list}\n\n"
                f"🆔 کد بازی: <code>{game_id}</code>",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    
    await update.message.reply_text(f"✅ به بازی {game_id} پیوستید!")

async def ready_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1]
    
    if game_id not in games or user_id not in games[game_id].players:
        await query.edit_message_text("⚠️ بازی یافت نشد!")
        return
    
    game = games[game_id]
    player = game.players[user_id]
    player.is_ready = not player.is_ready
    
    # Count ready players
    ready_count = sum(1 for p in game.players.values() if p.is_ready)
    
    # Update message
    players_text = "\n".join([
        f"{i+1}. {'✅' if game.players[pid].is_ready else '⏳'} {game.players[pid].name}" 
        for i, pid in enumerate(game.player_order)
    ])
    
    message = (
        f"🎮 <b>اتاق بازی {game_id}</b>\n\n"
        f"👥 بازیکنان ({ready_count}/4 آماده):\n{players_text}\n\n"
        f"{'🎯 همه آماده هستند! سازنده می‌تواند بازی را شروع کند.' if ready_count == 4 else '⏳ منتظر آماده شدن بقیه...'}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ من آماده‌ام", callback_data=f"ready_{game_id}")],
        [InlineKeyboardButton("🔄 وضعیت", callback_data=f"status_{game_id}")]
    ]
    
    if user_id == game.creator_id and ready_count == 4:
        keyboard.append([InlineKeyboardButton("▶️ شروع بازی", callback_data=f"start_{game_id}")])
    
    keyboard.append([InlineKeyboardButton("❌ خروج", callback_data=f"leave_{game_id}")])
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def start_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1]
    
    if game_id not in games or user_id != games[game_id].creator_id:
        await query.edit_message_text("⚠️ فقط سازنده می‌تواند بازی را شروع کند!")
        return
    
    game = games[game_id]
    
    if game.player_count != 4:
        await query.edit_message_text("⚠️ بازی باید ۴ بازیکن داشته باشد!")
        return
    
    # Start the game
    if not game.start_game():
        await query.edit_message_text("⚠️ خطا در شروع بازی!")
        return
    
    # Notify all players
    for player_id in game.player_order:
        player = game.players[player_id]
        
        # Show cards
        cards_by_suit = defaultdict(list)
        for card in player.cards:
            cards_by_suit[card.suit].append(card)
        
        cards_text = ""
        for suit in SUITS:
            if suit in cards_by_suit:
                cards_text += f"{SUIT_SYMBOLS[suit]}: "
                cards_text += " ".join([card.rank for card in cards_by_suit[suit]]) + "\n"
        
        # Trump selection
        if player_id == game.current_player_id:
            keyboard = []
            for suit in SUITS:
                keyboard.append([
                    InlineKeyboardButton(
                        f"{SUIT_SYMBOLS[suit]} انتخاب حکم",
                        callback_data=f"trump_{game_id}_{suit}"
                    )
                ])
            
            await context.bot.send_message(
                player_id,
                f"🎴 <b>کارت‌های شما:</b>\n\n{cards_text}\n\n"
                f"🎯 شما باید حکم بازی را انتخاب کنید:",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await context.bot.send_message(
                player_id,
                f"🎴 <b>کارت‌های شما:</b>\n\n{cards_text}\n\n"
                f"⏳ منتظر انتخاب حکم توسط {game.players[game.current_player_id].name}...",
                parse_mode=ParseMode.HTML
            )

async def leave_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1] if '_' in query.data else None
    
    if not game_id:
        game = get_user_game(user_id)
        game_id = user_games.get(user_id)
    else:
        game = games.get(game_id)
    
    if not game or user_id not in game.players:
        await query.edit_message_text("⚠️ شما در بازی‌ای نیستید!")
        return
    
    player_name = game.players[user_id].name
    
    # Remove player
    game.remove_player(user_id)
    if user_id in user_games:
        del user_games[user_id]
    
    # Remove empty game
    if game.player_count == 0:
        if game_id in games:
            del games[game_id]
    
    # Notify others
    if game.player_count > 0:
        for pid in game.player_order:
            try:
                await context.bot.send_message(
                    pid,
                    f"👋 {player_name} از بازی خارج شد.\n"
                    f"👥 {game.player_count}/4 بازیکن باقی‌مانده.",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    await query.edit_message_text(
        "✅ شما از بازی خارج شدید.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎮 منوی اصلی", callback_data="main_menu")]
        ])
    )

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎮 بازی جدید", callback_data="new_game")],
        [InlineKeyboardButton("📖 آموزش بازی", callback_data="tutorial")]
    ]
    
    await query.edit_message_text(
        "🎮 <b>منوی اصلی ربات حکم</b>\n\n"
        "برای شروع بازی جدید کلیک کنید:",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    tutorial_text = (
        "📖 <b>آموزش بازی حکم:</b>\n\n"
        "🎯 یک بازی ۴ نفره با ۵۲ کارت\n\n"
        "👥 <b>تیم‌بندی:</b>\n"
        "• ۲ تیم دو نفره\n"
        "• بازیکنان روبه‌رو هم‌تیمی\n\n"
        "🎴 <b>مراحل:</b>\n"
        "۱. انتخاب حکم (ترامپ)\n"
        "۲. پخش ۱۳ کارت به هرکس\n"
        "۳. بازی ۱۳ دست\n"
        "۴. تیم با حداقل ۷ برد برنده\n\n"
        "⚖️ <b>قوانین:</b>\n"
        "• باید هم‌خال بازی کنید\n"
        "• اگر خال نداشتید، هرکارتی\n"
        "• خال حکم از همه قوی‌تر\n"
        "• نوبت ساعتگرد\n\n"
        "🎮 برای شروع: بازی جدید ← کد را بده ← شروع بازی"
    )
    
    await query.edit_message_text(
        tutorial_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="main_menu")]
        ])
    )

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚠️ دستور نامعتبر!\n\n"
        "📋 دستورات موجود:\n"
        "/start - راه‌اندازی\n"
        "/new - بازی جدید\n"
        "/join [کد] - پیوستن\n"
        "/leave - خروج\n"
        "/help - راهنما"
    )

# ============ MAIN ============
def main():
    """Start the bot."""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("new", start))  # Alias
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("leave", lambda u,c: leave_game(u,c)))
    application.add_handler(CommandHandler("help", tutorial))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(new_game, pattern="^new_game$"))
    application.add_handler(CallbackQueryHandler(join_game, pattern="^join_game$"))
    application.add_handler(CallbackQueryHandler(ready_handler, pattern="^ready_"))
    application.add_handler(CallbackQueryHandler(start_game_handler, pattern="^start_"))
    application.add_handler(CallbackQueryHandler(leave_game, pattern="^leave_"))
    application.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
    application.add_handler(CallbackQueryHandler(tutorial, pattern="^tutorial$"))
    
    # Unknown command handler
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    
    # Start polling
    print("🤖 ربات حکم راه‌اندازی شد...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    main()
