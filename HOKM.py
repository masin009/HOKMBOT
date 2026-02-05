# requirements.txt
# python-telegram-bot==20.7
# python-dotenv==1.0.0
# Pillow==10.0.0

import os
import random
import logging
from enum import Enum
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
from dotenv import load_dotenv

# بارگذاری متغیرهای محیطی
load_dotenv()

# تنظیمات لاگ
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات (از محیط یا فایل .env بخوانید)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# حالت‌های مکالمه
class ConversationStates(Enum):
    WAITING_FOR_PLAYERS = 1
    IN_GAME = 2
    CHOOSING_TRUMP = 3
    PLAYING_CARD = 4

# خال‌های کارت
class Suit(Enum):
    HEARTS = "♥"      # دل
    DIAMONDS = "♦"    # خشت
    CLUBS = "♣"       # پیک
    SPADES = "♠"      # گیشنیز
    
    @property
    def persian_name(self):
        names = {
            Suit.HEARTS: "دل",
            Suit.DIAMONDS: "خشت",
            Suit.CLUBS: "پیک",
            Suit.SPADES: "گیشنیز"
        }
        return names[self]

# رتبه‌های کارت
class Rank(Enum):
    TWO = ("2", 2)
    THREE = ("3", 3)
    FOUR = ("4", 4)
    FIVE = ("5", 5)
    SIX = ("6", 6)
    SEVEN = ("7", 7)
    EIGHT = ("8", 8)
    NINE = ("9", 9)
    TEN = ("10", 10)
    JACK = ("J", 11)
    QUEEN = ("Q", 12)
    KING = ("K", 13)
    ACE = ("A", 14)
    
    def __init__(self, symbol, value):
        self.symbol = symbol
        self.value = value

# کارت
@dataclass
class Card:
    suit: Suit
    rank: Rank
    
    def __str__(self):
        return f"{self.suit.value}{self.rank.symbol}"
    
    def __repr__(self):
        return str(self)
    
    @property
    def persian_name(self):
        rank_names = {
            Rank.ACE: "آس",
            Rank.KING: "شاه",
            Rank.QUEEN: "بی‌بی",
            Rank.JACK: "سرباز",
            Rank.TEN: "۱۰",
            Rank.NINE: "۹",
            Rank.EIGHT: "۸",
            Rank.SEVEN: "۷",
            Rank.SIX: "۶",
            Rank.FIVE: "۵",
            Rank.FOUR: "۴",
            Rank.THREE: "۳",
            Rank.TWO: "۲"
        }
        return f"{rank_names[self.rank]} {self.suit.persian_name}"

# بازیکن
@dataclass
class Player:
    user_id: int
    username: str
    first_name: str
    cards: List[Card] = field(default_factory=list)
    score: int = 0
    tricks_won: int = 0
    is_ready: bool = False
    
    def __hash__(self):
        return hash(self.user_id)
    
    @property
    def display_name(self):
        if self.username:
            return f"@{self.username}"
        return self.first_name

# دست بازی (Round)
@dataclass
class Round:
    cards_played: Dict[int, Card] = field(default_factory=dict)  # user_id -> Card
    starting_player: Optional[int] = None
    trump_suit: Optional[Suit] = None
    winner: Optional[int] = None
    
    def is_complete(self, players: List[Player]) -> bool:
        return len(self.cards_played) == len(players)
    
    def get_winning_player(self, players: List[Player]) -> Optional[int]:
        if not self.is_complete(players):
            return None
        
        # اولین کارت را پیدا کن
        first_player_id = self.starting_player
        first_card = self.cards_played[first_player_id]
        leading_suit = first_card.suit
        
        # برنده را پیدا کن (با در نظر گرفتن خال حکم)
        winning_player_id = first_player_id
        winning_card = first_card
        
        for player_id, card in self.cards_played.items():
            # اگر کارت خال حکم دارد
            if card.suit == self.trump_suit and winning_card.suit != self.trump_suit:
                winning_player_id = player_id
                winning_card = card
            # اگر هر دو خال حکم دارند
            elif card.suit == self.trump_suit and winning_card.suit == self.trump_suit:
                if card.rank.value > winning_card.rank.value:
                    winning_player_id = player_id
                    winning_card = card
            # اگر هر دو خال معمولی دارند
            elif card.suit == leading_suit and winning_card.suit == leading_suit:
                if card.rank.value > winning_card.rank.value:
                    winning_player_id = player_id
                    winning_card = card
        
        return winning_player_id

# بازی
@dataclass
class Game:
    game_id: str
    chat_id: int
    players: List[Player] = field(default_factory=list)
    deck: List[Card] = field(default_factory=list)
    current_round: Round = field(default_factory=Round)
    rounds: List[Round] = field(default_factory=list)
    turn_order: List[int] = field(default_factory=list)  # user_id ها به ترتیب
    current_turn_index: int = 0
    dealer_index: int = 0
    trump_suit: Optional[Suit] = None
    trump_chooser: Optional[int] = None
    state: str = "waiting"  # waiting, choosing_trump, playing, finished
    created_at: datetime = field(default_factory=datetime.now)
    messages_to_delete: List[int] = field(default_factory=list)
    
    def add_player(self, player: Player) -> bool:
        if len(self.players) >= 4:
            return False
        if any(p.user_id == player.user_id for p in self.players):
            return False
        self.players.append(player)
        return True
    
    def remove_player(self, user_id: int) -> bool:
        for i, player in enumerate(self.players):
            if player.user_id == user_id:
                self.players.pop(i)
                return True
        return False
    
    def initialize_deck(self):
        self.deck = []
        for suit in Suit:
            for rank in Rank:
                self.deck.append(Card(suit, rank))
        random.shuffle(self.deck)
    
    def deal_cards(self):
        # به هر بازیکن 13 کارت بده
        for i, player in enumerate(self.players):
            start = i * 13
            end = start + 13
            player.cards = self.deck[start:end]
            # کارت‌ها را بر اساس خال و ارزش مرتب کن
            player.cards.sort(key=lambda c: (c.suit.value, c.rank.value))
    
    def start_game(self):
        self.initialize_deck()
        self.deal_cards()
        self.turn_order = [p.user_id for p in self.players]
        self.current_turn_index = 0
        self.state = "choosing_trump"
        
        # تعیین بازیکنی که باید خال حکم را انتخاب کند
        self.trump_chooser = self.turn_order[0]
    
    def choose_trump(self, user_id: int, suit: Suit) -> bool:
        if self.state != "choosing_trump" or user_id != self.trump_chooser:
            return False
        
        self.trump_suit = suit
        self.current_round.trump_suit = suit
        self.state = "playing"
        return True
    
    def play_card(self, user_id: int, card_index: int) -> Optional[Card]:
        # بررسی نوبت
        if self.state != "playing":
            return None
        
        current_player_id = self.turn_order[self.current_turn_index]
        if user_id != current_player_id:
            return None
        
        # پیدا کردن بازیکن
        player = next((p for p in self.players if p.user_id == user_id), None)
        if not player or card_index >= len(player.cards):
            return None
        
        # بیرون آوردن کارت از دست بازیکن
        card = player.cards.pop(card_index)
        
        # اگر اولین کارت دست است، بازیکن شروع‌کننده را تنظیم کن
        if len(self.current_round.cards_played) == 0:
            self.current_round.starting_player = user_id
        
        # کارت را به دست اضافه کن
        self.current_round.cards_played[user_id] = card
        
        # نوبت را به بازیکن بعدی بده
        self.current_turn_index = (self.current_turn_index + 1) % len(self.players)
        
        # اگر دست کامل شد، برنده را تعیین کن
        if self.current_round.is_complete(self.players):
            winner_id = self.current_round.get_winning_player(self.players)
            self.current_round.winner = winner_id
            
            # برنده دست بعدی را شروع می‌کند
            winner_index = self.turn_order.index(winner_id)
            self.current_turn_index = winner_index
            
            # این دست را به تاریخچه اضافه کن
            self.rounds.append(self.current_round)
            
            # دست جدید شروع کن
            self.current_round = Round()
            self.current_round.trump_suit = self.trump_suit
            
            # اگر بازی تمام شده (کارت‌ها تمام شده)
            if all(len(p.cards) == 0 for p in self.players):
                self.state = "finished"
        
        return card
    
    def get_player_by_id(self, user_id: int) -> Optional[Player]:
        for player in self.players:
            if player.user_id == user_id:
                return player
        return None

# مدیریت بازی‌های فعال
class GameManager:
    def __init__(self):
        self.active_games: Dict[int, Game] = {}  # chat_id -> Game
        self.player_games: Dict[int, int] = {}   # user_id -> chat_id
    
    def create_game(self, chat_id: int) -> Game:
        game_id = f"game_{chat_id}_{datetime.now().timestamp()}"
        game = Game(game_id=game_id, chat_id=chat_id)
        self.active_games[chat_id] = game
        return game
    
    def get_game(self, chat_id: int) -> Optional[Game]:
        return self.active_games.get(chat_id)
    
    def end_game(self, chat_id: int):
        if chat_id in self.active_games:
            # حذف رکوردهای بازیکنان
            game = self.active_games[chat_id]
            for player in game.players:
                if player.user_id in self.player_games:
                    del self.player_games[player.user_id]
            del self.active_games[chat_id]
    
    def register_player(self, user_id: int, chat_id: int):
        self.player_games[user_id] = chat_id
    
    def get_player_game(self, user_id: int) -> Optional[Game]:
        chat_id = self.player_games.get(user_id)
        if chat_id:
            return self.get_game(chat_id)
        return None

# ایجاد مدیر بازی
game_manager = GameManager()

# دستورات ربات
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع ربات"""
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}! 👋\n\n"
        "به ربات بازی پاسور (حکم) خوش آمدید! 🃏\n\n"
        "برای شروع یک بازی جدید در گروه، از دستور /newgame استفاده کنید.\n"
        "برای پیوستن به بازی از /join استفاده کنید.\n"
        "برای شروع بازی از /startgame استفاده کنید.\n\n"
        "📖 قوانین بازی:\n"
        "• بازی ۴ نفره است\n"
        "• هر بازیکن ۱۳ کارت دریافت می‌کند\n"
        "• یک خال به عنوان خال حکم انتخاب می‌شود\n"
        "• هر دست توسط بازیکنی شروع می‌شود و بقیه باید همخال بیاورند\n"
        "• اگر همخال نداشته باشند، می‌توانند هر کارتی بگذارند\n"
        "• برنده دست، کسی است که بالاترین کارت خال حکم را آورده باشد\n"
        "• امتیاز بر اساس تعداد بردها (دست‌ها) محاسبه می‌شود"
    )

async def new_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد یک بازی جدید"""
    chat_id = update.effective_chat.id
    
    # بررسی اینکه آیا بازی فعالی در این چت وجود دارد
    existing_game = game_manager.get_game(chat_id)
    if existing_game and existing_game.state != "finished":
        await update.message.reply_text(
            "⚠️ در این گروه یک بازی در حال اجرا وجود دارد. "
            "برای شروع بازی جدید باید بازی قبلی تمام شود."
        )
        return
    
    # ایجاد بازی جدید
    game = game_manager.create_game(chat_id)
    
    # اضافه کردن سازنده بازی به عنوان اولین بازیکن
    user = update.effective_user
    player = Player(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    game.add_player(player)
    game_manager.register_player(user.id, chat_id)
    
    # ایجاد دکمه‌های شیشه‌ای
    keyboard = [
        [InlineKeyboardButton("🎮 پیوستن به بازی", callback_data="join_game")],
        [InlineKeyboardButton("▶️ شروع بازی", callback_data="start_game")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = await update.message.reply_text(
        "🎉 یک بازی جدید پاسور (حکم) ایجاد شد!\n\n"
        f"بازیکنان ({len(game.players)}/4):\n" +
        "\n".join([f"• {p.display_name}" for p in game.players]) +
        "\n\nبرای پیوستن به بازی روی دکمه زیر کلیک کنید:",
        reply_markup=reply_markup
    )
    
    # ذخیره ID پیام برای به روزرسانی بعدی
    game.messages_to_delete.append(message.message_id)

async def join_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیوستن به بازی از طریق دکمه"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    game = game_manager.get_game(chat_id)
    if not game:
        await query.edit_message_text("❌ بازی یافت نشد. لطفا یک بازی جدید ایجاد کنید.")
        return
    
    if game.state != "waiting":
        await query.edit_message_text("❌ بازی در حال اجراست. نمی‌توانید الان بپیوندید.")
        return
    
    # بررسی اینکه آیا بازیکن قبلا پیوسته
    if any(p.user_id == user.id for p in game.players):
        await query.edit_message_text("✅ شما قبلا به بازی پیوسته‌اید!")
        return
    
    # بررسی تعداد بازیکنان
    if len(game.players) >= 4:
        await query.edit_message_text("❌ بازی تکمیل است. حداکثر ۴ بازیکن مجاز است.")
        return
    
    # اضافه کردن بازیکن جدید
    player = Player(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    game.add_player(player)
    game_manager.register_player(user.id, chat_id)
    
    # به روزرسانی پیام
    keyboard = [
        [InlineKeyboardButton("🎮 پیوستن به بازی", callback_data="join_game")],
        [InlineKeyboardButton("▶️ شروع بازی", callback_data="start_game")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🎮 بازی پاسور (حکم)\n\n"
        f"بازیکنان ({len(game.players)}/4):\n" +
        "\n".join([f"• {p.display_name}" for p in game.players]) +
        "\n\nبرای پیوستن به بازی روی دکمه زیر کلیک کنید:",
        reply_markup=reply_markup
    )

async def start_game_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بازی"""
    query = update.callback_query
    await query.answer()
    
    chat_id = update.effective_chat.id
    game = game_manager.get_game(chat_id)
    
    if not game:
        await query.edit_message_text("❌ بازی یافت نشد.")
        return
    
    if len(game.players) < 2:
        await query.edit_message_text("❌ حداقل ۲ بازیکن برای شروع بازی لازم است.")
        return
    
    # شروع بازی
    game.start_game()
    
    # حذف پیام قبلی
    await query.delete_message()
    
    # ارسال پیام شروع بازی
    start_message = await context.bot.send_message(
        chat_id,
        "🎉 بازی شروع شد!\n\n"
        f"بازیکنان: {', '.join([p.display_name for p in game.players])}\n"
        f"تعداد دست‌ها: {len(game.rounds) + 1}/13\n\n"
        f"🃏 خال حکم: در حال انتخاب..."
    )
    
    # نمایش کارت‌های بازیکن شروع کننده (کسی که باید خال حکم را انتخاب کند)
    trump_chooser = game.get_player_by_id(game.trump_chooser)
    if trump_chooser:
        # ایجاد دکمه‌های انتخاب خال حکم
        keyboard = [
            [
                InlineKeyboardButton(f"♥ دل", callback_data="trump_hearts"),
                InlineKeyboardButton(f"♦ خشت", callback_data="trump_diamonds")
            ],
            [
                InlineKeyboardButton(f"♣ پیک", callback_data="trump_clubs"),
                InlineKeyboardButton(f"♠ گیشنیز", callback_data="trump_spades")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        chooser_message = await context.bot.send_message(
            chat_id,
            f"👑 {trump_chooser.display_name}، لطفا خال حکم را انتخاب کنید:",
            reply_markup=reply_markup
        )
        
        game.messages_to_delete.append(chooser_message.message_id)
    
    game.messages_to_delete.append(start_message.message_id)

async def choose_trump_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """انتخاب خال حکم"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    game = game_manager.get_game(chat_id)
    if not game or game.state != "choosing_trump":
        await query.edit_message_text("❌ بازی در مرحله انتخاب خال حکم نیست.")
        return
    
    # بررسی اینکه آیا کاربر مجاز به انتخاب خال حکم است
    if user.id != game.trump_chooser:
        await query.answer("شما نوبت انتخاب خال حکم را ندارید!", show_alert=True)
        return
    
    # شناسایی خال انتخاب شده
    trump_map = {
        "trump_hearts": Suit.HEARTS,
        "trump_diamonds": Suit.DIAMONDS,
        "trump_clubs": Suit.CLUBS,
        "trump_spades": Suit.SPADES
    }
    
    chosen_trump = trump_map.get(query.data)
    if not chosen_trump:
        await query.edit_message_text("❌ انتخاب نامعتبر.")
        return
    
    # ثبت انتخاب خال حکم
    game.choose_trump(user.id, chosen_trump)
    
    # به روزرسانی پیام
    await query.edit_message_text(
        f"✅ خال حکم انتخاب شد: {chosen_trump.value} {chosen_trump.persian_name}\n\n"
        f"اولین دست را {game.players[0].display_name} شروع می‌کند."
    )
    
    # شروع اولین دست
    await play_round(context, chat_id)

async def play_round(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """مدیریت بازی یک دست"""
    game = game_manager.get_game(chat_id)
    if not game:
        return
    
    # پاک کردن پیام‌های قبلی
    for msg_id in game.messages_to_delete:
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except:
            pass
    game.messages_to_delete.clear()
    
    # اگر بازی تمام شده
    if game.state == "finished":
        await end_game(context, chat_id)
        return
    
    # بازیکن نوبت
    current_player_id = game.turn_order[game.current_turn_index]
    current_player = game.get_player_by_id(current_player_id)
    
    # ایجاد نمایش وضعیت بازی
    status_message = await create_game_status(context, chat_id)
    game.messages_to_delete.append(status_message.message_id)
    
    # اگر نوبت کاربری است که با ربات در حال تعامل است
    if current_player:
        # نمایش کارت‌های بازیکن
        await show_player_cards(context, chat_id, current_player_id)

async def create_game_status(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """ایجاد پیام وضعیت بازی"""
    game = game_manager.get_game(chat_id)
    if not game:
        return None
    
    # اطلاعات دست فعلی
    round_info = ""
    if game.current_round.cards_played:
        round_info = "\n🎴 کارت‌های بازی شده در این دست:\n"
        for player_id, card in game.current_round.cards_played.items():
            player = game.get_player_by_id(player_id)
            round_info += f"• {player.display_name}: {card.persian_name}\n"
    
    # بازیکن نوبت
    current_player_id = game.turn_order[game.current_turn_index]
    current_player = game.get_player_by_id(current_player_id)
    
    status_text = (
        f"🎮 بازی پاسور (حکم)\n\n"
        f"🃏 خال حکم: {game.trump_suit.value} {game.trump_suit.persian_name}\n"
        f"👤 نوبت: {current_player.display_name}\n"
        f"📊 دست‌های برداشته شده:\n"
    )
    
    # اضافه کردن اطلاعات دست‌های برداشته شده
    for player in game.players:
        status_text += f"• {player.display_name}: {player.tricks_won} دست\n"
    
    status_text += round_info
    status_text += f"\n♻️ دست: {len(game.rounds) + 1}/13"
    
    return await context.bot.send_message(chat_id, status_text)

async def show_player_cards(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int):
    """نمایش کارت‌های بازیکن"""
    game = game_manager.get_game(chat_id)
    if not game:
        return
    
    player = game.get_player_by_id(user_id)
    if not player:
        return
    
    # گروه‌بندی کارت‌ها بر اساس خال
    cards_by_suit = defaultdict(list)
    for i, card in enumerate(player.cards):
        cards_by_suit[card.suit].append((i, card))
    
    # ایجاد دکمه‌های کارت
    keyboard = []
    for suit in Suit:
        row = []
        for card_index, card in cards_by_suit.get(suit, []):
            # رنگ‌بندی دکمه‌ها بر اساس خال
            emoji = "♥️" if suit == Suit.HEARTS else "♦️" if suit == Suit.DIAMONDS else "♣️" if suit == Suit.CLUBS else "♠️"
            button_text = f"{emoji} {card.rank.symbol}"
            row.append(InlineKeyboardButton(button_text, callback_data=f"play_card_{card_index}"))
        
        if row:
            keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # ارسال پیام به بازیکن
    try:
        message = await context.bot.send_message(
            user_id,
            f"🎴 کارت‌های شما:\n\n"
            f"خال حکم: {game.trump_suit.value} {game.trump_suit.persian_name}\n\n"
            f"یک کارت برای بازی انتخاب کنید:",
            reply_markup=reply_markup
        )
        game.messages_to_delete.append(message.message_id)
    except Exception as e:
        # اگر نتوانستیم پیام خصوصی بفرستیم، در گروه اعلام می‌کنیم
        await context.bot.send_message(
            chat_id,
            f"⚠️ {player.display_name}، لطفا ابتدا به ربات پیام خصوصی بفرستید: @{context.bot.username}"
        )

async def play_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بازی کردن یک کارت"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    game = game_manager.get_player_game(user.id)
    
    if not game:
        await query.edit_message_text("❌ شما در بازی فعالی نیستید.")
        return
    
    # استخراج اندیس کارت
    card_index = int(query.data.split("_")[-1])
    
    # بازی کردن کارت
    played_card = game.play_card(user.id, card_index)
    
    if not played_card:
        await query.answer("❌ نمی‌توانید این کارت را بازی کنید!", show_alert=True)
        return
    
    # به روزرسانی پیام کارت‌ها
    await query.edit_message_text(
        f"✅ کارت بازی شد: {played_card.persian_name}\n\n"
        f"در حال انتظار برای بازیکنان دیگر..."
    )
    
    # بررسی اینکه آیا دست کامل شده
    if game.current_round.is_complete(game.players):
        # پیدا کردن برنده دست
        winner_id = game.current_round.winner
        winner = game.get_player_by_id(winner_id)
        
        if winner:
            winner.tricks_won += 1
            
            # اعلام برنده دست
            await context.bot.send_message(
                game.chat_id,
                f"🏆 برنده این دست: {winner.display_name}\n"
                f"با کارت: {game.current_round.cards_played[winner_id].persian_name}\n\n"
                f"دست بعدی را {winner.display_name} شروع می‌کند."
            )
    
    # ادامه بازی
    await play_round(context, game.chat_id)

async def end_game(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """پایان بازی و نمایش نتایج"""
    game = game_manager.get_game(chat_id)
    if not game:
        return
    
    # پیدا کردن برنده (کسی که بیشترین دست را برده)
    winner = max(game.players, key=lambda p: p.tricks_won)
    
    # ایجاد متن نتایج
    results_text = "🎊 بازی به پایان رسید! 🎊\n\nنتایج نهایی:\n\n"
    
    for player in sorted(game.players, key=lambda p: p.tricks_won, reverse=True):
        trophy = "🏆" if player == winner else "🎯"
        results_text += f"{trophy} {player.display_name}: {player.tricks_won} دست\n"
    
    results_text += f"\n🎉 برنده بازی: {winner.display_name} 🎉"
    
    # ارسال نتایج
    await context.bot.send_message(chat_id, results_text)
    
    # پاک کردن پیام‌های بازی
    for msg_id in game.messages_to_delete:
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except:
            pass
    
    # پایان بازی
    game_manager.end_game(chat_id)

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش قوانین بازی"""
    rules_text = (
        "📖 قوانین بازی پاسور (حکم):\n\n"
        "🎯 هدف بازی:\n"
        "بردیدن بیشترین تعداد دست (تریک) در هر دور بازی\n\n"
        "👥 تعداد بازیکنان:\n"
        "۴ نفر\n\n"
        "🃏 نحوه بازی:\n"
        "۱. هر بازیکن ۱۳ کارت دریافت می‌کند\n"
        "۲. یک خال به عنوان خال حکم انتخاب می‌شود\n"
        "۳. اولین بازیکن یک کارت بازی می‌کند\n"
        "۴. بازیکنان بعدی باید اگر بتوانند همخال بیاورند\n"
        "۵. اگر همخال نداشته باشند، می‌توانند هر کارتی بگذارند\n"
        "۶. برنده دست، کسی است که بالاترین کارت خال حکم را آورده باشد\n"
        "۷. اگر کسی خال حکم نیاورده باشد، برنده کسی است که بالاترین کارت خال اول را آورده باشد\n"
        "۸. برنده دست بعدی را شروع می‌کند\n\n"
        "🏆 امتیازدهی:\n"
        "• هر دست برده شده = ۱ امتیاز\n"
        "• برنده بازی: کسی که بیشترین امتیاز را داشته باشد\n\n"
        "💡 نکات:\n"
        "• کارت‌ها از کم به زیاد: ۲, ۳, ۴, ۵, ۶, ۷, ۸, ۹, ۱۰, سرباز, بی‌بی, شاه, آس\n"
        "• خال حکم از همه خال‌ها قوی‌تر است\n"
        "• باید حتما همخال آورد مگر اینکه اصلا همخال نداشته باشید"
    )
    
    await update.message.reply_text(rules_text)

async def leave_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ترک بازی"""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    game = game_manager.get_game(chat_id)
    if not game:
        await update.message.reply_text("❌ بازی فعالی در این گروه وجود ندارد.")
        return
    
    if game.state != "waiting":
        await update.message.reply_text("❌ بازی در حال اجراست. نمی‌توانید بازی را ترک کنید.")
        return
    
    if game.remove_player(user.id):
        await update.message.reply_text("✅ شما از بازی خارج شدید.")
        
        # اگر بازیکنی باقی نمانده، بازی را پایان بده
        if len(game.players) == 0:
            game_manager.end_game(chat_id)
            await update.message.reply_text("🔄 بازی به دلیل عدم وجود بازیکن لغو شد.")
    else:
        await update.message.reply_text("❌ شما در این بازی عضو نیستید.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت فعلی بازی"""
    chat_id = update.effective_chat.id
    
    game = game_manager.get_game(chat_id)
    if not game:
        await update.message.reply_text("📭 در حال حاضر هیچ بازی فعالی در این گروه وجود ندارد.")
        return
    
    if game.state == "waiting":
        players_text = "\n".join([f"• {p.display_name}" for p in game.players])
        await update.message.reply_text(
            f"⏳ بازی در انتظار بازیکنان...\n\n"
            f"بازیکنان ({len(game.players)}/4):\n{players_text}\n\n"
            f"برای پیوستن به بازی از /join استفاده کنید."
        )
    else:
        # نمایش وضعیت بازی در حال اجرا
        status_text = (
            f"🎮 بازی در حال اجرا\n\n"
            f"بازیکنان: {', '.join([p.display_name for p in game.players])}\n"
            f"خال حکم: {game.trump_suit.value if game.trump_suit else 'در حال انتخاب'}\n"
            f"تعداد دست‌ها: {len(game.rounds)}/13\n"
            f"وضعیت: {'در حال انتخاب خال حکم' if game.state == 'choosing_trump' else 'در حال بازی'}\n\n"
        )
        
        # نمایش برنده هر دور
        if game.rounds:
            status_text += "نتایج دست‌های قبلی:\n"
            for i, round in enumerate(game.rounds, 1):
                winner = game.get_player_by_id(round.winner) if round.winner else None
                if winner:
                    status_text += f"دست {i}: {winner.display_name}\n"
        
        await update.message.reply_text(status_text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش راهنمای دستورات"""
    help_text = (
        "📋 راهنمای دستورات ربات پاسور:\n\n"
        "🔹 /start - شروع ربات و نمایش خوش‌آمد\n"
        "🔹 /newgame - ایجاد یک بازی جدید\n"
        "🔹 /join - پیوستن به بازی در انتظار\n"
        "🔹 /startgame - شروع بازی با بازیکنان حاضر\n"
        "🔹 /leave - ترک بازی (قبل از شروع)\n"
        "🔹 /status - نمایش وضعیت فعلی بازی\n"
        "🔹 /rules - نمایش قوانین بازی\n"
        "🔹 /help - نمایش این راهنما\n"
        "🔹 /cancel - لغو بازی فعلی\n\n"
        "🎮 نحوه بازی:\n"
        "۱. با /newgame یک بازی جدید ایجاد کنید\n"
        "۲. بازیکنان با /join به بازی می‌پیوندند\n"
        "۳. با /startgame بازی را شروع کنید\n"
        "۴. خال حکم انتخاب می‌شود\n"
        "۵. بازی کارت به کارت پیش می‌رود\n"
        "۶. پس از ۱۳ دست، برنده اعلام می‌شود\n\n"
        "💡 نکته: برای بازی نیاز است که به ربات پیام خصوصی بفرستید."
    )
    
    await update.message.reply_text(help_text)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو بازی فعلی"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    game = game_manager.get_game(chat_id)
    if not game:
        await update.message.reply_text("❌ بازی فعالی برای لغو وجود ندارد.")
        return
    
    # فقط سازنده بازی یا ادمین‌ها می‌توانند بازی را لغو کنند
    # در این پیاده‌سازی ساده، همه می‌توانند لغو کنند
    game_manager.end_game(chat_id)
    
    # پاک کردن پیام‌های بازی
    for msg_id in game.messages_to_delete:
        try:
            await context.bot.delete_message(chat_id, msg_id)
        except:
            pass
    
    await update.message.reply_text("🔄 بازی فعلی لغو شد.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت خطاها"""
    logger.error(f"خطا رخ داد: {context.error}")
    
    try:
        # اطلاع به کاربر در صورت امکان
        if update and update.effective_chat:
            await context.bot.send_message(
                update.effective_chat.id,
                "⚠️ متاسفانه خطایی رخ داد. لطفا دوباره تلاش کنید."
            )
    except:
        pass

def main():
    """تابع اصلی برای اجرای ربات"""
    # ایجاد برنامه ربات
    application = Application.builder().token(TOKEN).build()
    
    # اضافه کردن هندلرهای دستورات
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("newgame", new_game_command))
    application.add_handler(CommandHandler("join", join_game_callback))
    application.add_handler(CommandHandler("startgame", start_game_callback))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("leave", leave_game_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # اضافه کردن هندلرهای callback
    application.add_handler(CallbackQueryHandler(join_game_callback, pattern="^join_game$"))
    application.add_handler(CallbackQueryHandler(start_game_callback, pattern="^start_game$"))
    application.add_handler(CallbackQueryHandler(choose_trump_callback, pattern="^trump_"))
    application.add_handler(CallbackQueryHandler(play_card_callback, pattern="^play_card_"))
    
    # اضافه کردن هندلر خطا
    application.add_error_handler(error_handler)
    
    # شروع ربات
    print("🤖 ربات بازی پاسور (حکم) در حال اجراست...")
    print(f"🔗 لینک ربات: https://t.me/{application.bot.username}")
    print("🃏 برای شروع بازی در یک گروه از دستور /newgame استفاده کنید.")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
