"""
Telegram Hokm Bot - Complete 4-Player Card Game
Version: 2.0.0 - Compatible with python-telegram-bot v20+
"""

import os
import json
import asyncio
import random
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Tuple, Optional, Set, Any
from dataclasses import dataclass, field
from collections import defaultdict
from uuid import uuid4

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    InputMediaPhoto
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode

# ============ CONFIGURATION ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc")

# For Render.com deployment
if os.getenv("RENDER"):
    BOT_TOKEN = os.getenv("BOT_TOKEN")

SUITS = {
    'hearts': {'symbol': '♥', 'emoji': '❤️', 'color': 'red'},
    'diamonds': {'symbol': '♦', 'emoji': '♦️', 'color': 'red'},
    'clubs': {'symbol': '♣', 'emoji': '♣️', 'color': 'black'},
    'spades': {'symbol': '♠', 'emoji': '♠️', 'color': 'black'}
}

RANKS = {
    '2': {'value': 2, 'name': '2'},
    '3': {'value': 3, 'name': '3'},
    '4': {'value': 4, 'name': '4'},
    '5': {'value': 5, 'name': '5'},
    '6': {'value': 6, 'name': '6'},
    '7': {'value': 7, 'name': '7'},
    '8': {'value': 8, 'name': '8'},
    '9': {'value': 9, 'name': '9'},
    '10': {'value': 10, 'name': '10'},
    'J': {'value': 11, 'name': 'Jack'},
    'Q': {'value': 12, 'name': 'Queen'},
    'K': {'value': 13, 'name': 'King'},
    'A': {'value': 14, 'name': 'Ace'}
}

# ============ DATA MODELS ============
class GamePhase(Enum):
    WAITING = "waiting"
    CHOOSING_TRUMP = "choosing_trump"
    DEALING = "dealing"
    PLAYING = "playing"
    ROUND_END = "round_end"
    GAME_END = "game_end"

class Card:
    def __init__(self, suit: str, rank: str):
        self.suit = suit
        self.rank = rank
        self.value = RANKS[rank]['value']
        self.symbol = SUITS[suit]['symbol']
        self.emoji = SUITS[suit]['emoji']
        self.color = SUITS[suit]['color']
    
    def __repr__(self):
        return f"{self.symbol}{self.rank}"
    
    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.suit == other.suit and self.rank == other.rank
    
    def __hash__(self):
        return hash((self.suit, self.rank))
    
    def to_dict(self):
        return {'suit': self.suit, 'rank': self.rank}
    
    @classmethod
    def from_dict(cls, data):
        return cls(data['suit'], data['rank'])

class Player:
    def __init__(self, user_id: int, username: str, first_name: str):
        self.user_id = user_id
        self.username = username or f"user_{user_id}"
        self.first_name = first_name
        self.cards: List[Card] = []
        self.is_ready = False
        self.is_dealer = False
        self.team = 0
        self.score = 0
        self.tricks_won = 0
    
    def add_card(self, card: Card):
        self.cards.append(card)
    
    def remove_card(self, card: Card):
        for i, c in enumerate(self.cards):
            if c == card:
                del self.cards[i]
                return True
        return False
    
    def sort_cards(self):
        self.cards.sort(key=lambda x: (x.suit, x.value))
    
    def has_suit(self, suit: str) -> bool:
        return any(card.suit == suit for card in self.cards)
    
    def can_play(self, card: Card, lead_suit: Optional[str] = None) -> bool:
        if lead_suit is None:
            return True
        if card.suit == lead_suit:
            return True
        return not self.has_suit(lead_suit)

class Trick:
    def __init__(self, leader_id: int):
        self.leader_id = leader_id
        self.cards_played: Dict[int, Card] = {}
        self.order: List[int] = []
    
    def add_card(self, player_id: int, card: Card):
        self.cards_played[player_id] = card
        self.order.append(player_id)
    
    def is_complete(self, player_count: int = 4) -> bool:
        return len(self.cards_played) == player_count
    
    def get_winner(self, trump_suit: str) -> Tuple[int, Card]:
        lead_card = self.cards_played[self.leader_id]
        lead_suit = lead_card.suit
        highest_card = lead_card
        winner_id = self.leader_id
        
        for player_id, card in self.cards_played.items():
            if player_id == self.leader_id:
                continue
            
            if card.suit == trump_suit and highest_card.suit != trump_suit:
                highest_card = card
                winner_id = player_id
            elif card.suit == trump_suit and highest_card.suit == trump_suit:
                if card.value > highest_card.value:
                    highest_card = card
                    winner_id = player_id
            elif card.suit == lead_suit and highest_card.suit == lead_suit:
                if card.value > highest_card.value:
                    highest_card = card
                    winner_id = player_id
        
        return winner_id, highest_card

class HokmGame:
    def __init__(self, game_id: str, creator_id: int):
        self.game_id = game_id
        self.creator_id = creator_id
        self.players: Dict[int, Player] = {}
        self.player_order: List[int] = []
        self.phase = GamePhase.WAITING
        self.deck: List[Card] = []
        self.trump_suit: Optional[str] = None
        self.trump_chooser_id: Optional[int] = None
        self.current_trick: Optional[Trick] = None
        self.tricks: List[Trick] = []
        self.turn_index = 0
        self.lead_suit: Optional[str] = None
        self.round_number = 1
        self.scores = {0: 0, 1: 0}
        self.dealer_index = 0
        self.created_at = datetime.now()
    
    @property
    def current_player_id(self) -> Optional[int]:
        if not self.player_order:
            return None
        return self.player_order[self.turn_index % len(self.player_order)]
    
    @property
    def player_count(self):
        return len(self.players)
    
    @property
    def is_full(self):
        return self.player_count >= 4
    
    @property
    def is_ready_to_start(self):
        return self.player_count == 4 and all(p.is_ready for p in self.players.values())
    
    def add_player(self, player: Player):
        if self.player_count >= 4:
            raise Exception("Game is full")
        
        self.players[player.user_id] = player
        self.player_order.append(player.user_id)
        player.team = (self.player_count - 1) % 2
    
    def remove_player(self, user_id: int):
        if user_id in self.players:
            del self.players[user_id]
            self.player_order.remove(user_id)
            
            for i, pid in enumerate(self.player_order):
                self.players[pid].team = i % 2
    
    def create_deck(self):
        self.deck = []
        for suit in SUITS:
            for rank in RANKS:
                self.deck.append(Card(suit, rank))
        random.shuffle(self.deck)
    
    def deal_cards(self):
        for i in range(13):
            for player_id in self.player_order:
                if self.deck:
                    card = self.deck.pop()
                    self.players[player_id].add_card(card)
        
        for player in self.players.values():
            player.sort_cards()
    
    def start_game(self):
        if not self.is_ready_to_start:
            raise Exception("Game not ready")
        
        self.create_deck()
        self.deal_cards()
        
        self.dealer_index = random.randint(0, 3)
        dealer_id = self.player_order[self.dealer_index]
        self.players[dealer_id].is_dealer = True
        
        self.trump_chooser_id = self.player_order[(self.dealer_index + 1) % 4]
        self.phase = GamePhase.CHOOSING_TRUMP
        self.turn_index = (self.dealer_index + 1) % 4
    
    def choose_trump(self, player_id: int, suit: str):
        if player_id != self.trump_chooser_id:
            raise Exception("Not allowed to choose trump")
        
        self.trump_suit = suit
        self.phase = GamePhase.PLAYING
        self.current_trick = Trick(self.trump_chooser_id)
        self.turn_index = self.player_order.index(self.trump_chooser_id)
    
    def play_card(self, player_id: int, card: Card) -> Optional[int]:
        if self.current_player_id != player_id:
            raise Exception("Not your turn")
        
        player = self.players[player_id]
        
        if not player.remove_card(card):
            raise Exception("Card not in hand")
        
        if self.current_trick and len(self.current_trick.cards_played) > 0:
            lead_suit = list(self.current_trick.cards_played.values())[0].suit
            if not player.can_play(card, lead_suit):
                player.add_card(card)  # Return card
                raise Exception("Must follow suit")
        
        self.current_trick.add_card(player_id, card)
        
        if len(self.current_trick.cards_played) == 1:
            self.lead_suit = card.suit
        
        self.turn_index = (self.turn_index + 1) % 4
        
        if self.current_trick.is_complete():
            winner_id, winning_card = self.current_trick.get_winner(self.trump_suit)
            self.tricks.append(self.current_trick)
            self.players[winner_id].tricks_won += 1
            self.current_trick = Trick(winner_id)
            self.turn_index = self.player_order.index(winner_id)
            self.lead_suit = None
            
            if all(len(p.cards) == 0 for p in self.players.values()):
                self.end_round()
            
            return winner_id
        
        return None
    
    def end_round(self):
        team_tricks = {0: 0, 1: 0}
        for player in self.players.values():
            team_tricks[player.team] += player.tricks_won
        
        for team in [0, 1]:
            if team_tricks[team] > 6:
                self.scores[team] += (team_tricks[team] - 6)
        
        if max(self.scores.values()) >= 7:
            self.phase = GamePhase.GAME_END
        else:
            self.phase = GamePhase.ROUND_END
            self.round_number += 1
            
            for player in self.players.values():
                player.cards = []
                player.tricks_won = 0
                player.is_dealer = False
            
            self.dealer_index = (self.dealer_index + 1) % 4
            self.players[self.player_order[self.dealer_index]].is_dealer = True
    
    def get_winner_team(self) -> Optional[int]:
        if self.phase != GamePhase.GAME_END:
            return None
        
        if self.scores[0] >= 7:
            return 0
        elif self.scores[1] >= 7:
            return 1
        
        return None

# ============ GAME MANAGER ============
class GameManager:
    _instance = None
    games: Dict[str, HokmGame] = {}
    user_games: Dict[int, str] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GameManager, cls).__new__(cls)
        return cls._instance
    
    @classmethod
    def create_game(cls, creator_id: int, creator_name: str) -> HokmGame:
        game_id = str(uuid4())[:8]
        creator = Player(creator_id, "", creator_name)
        game = HokmGame(game_id, creator_id)
        game.add_player(creator)
        cls.games[game_id] = game
        cls.user_games[creator_id] = game_id
        return game
    
    @classmethod
    def join_game(cls, user_id: int, username: str, first_name: str, game_id: str) -> bool:
        if game_id not in cls.games:
            return False
        
        game = cls.games[game_id]
        if game.is_full:
            return False
        
        player = Player(user_id, username, first_name)
        game.add_player(player)
        cls.user_games[user_id] = game_id
        return True
    
    @classmethod
    def leave_game(cls, user_id: int):
        if user_id not in cls.user_games:
            return None
        
        game_id = cls.user_games[user_id]
        if game_id in cls.games:
            game = cls.games[game_id]
            game.remove_player(user_id)
            
            if game.player_count == 0:
                del cls.games[game_id]
        
        del cls.user_games[user_id]
        return game_id
    
    @classmethod
    def get_user_game(cls, user_id: int) -> Optional[HokmGame]:
        if user_id not in cls.user_games:
            return None
        return cls.games.get(cls.user_games[user_id])

# ============ KEYBOARD FUNCTIONS ============
def create_main_menu():
    keyboard = [
        [InlineKeyboardButton("🎮 بازی جدید", callback_data="new_game")],
        [InlineKeyboardButton("🔍 پیوستن به بازی", callback_data="join_game")],
        [InlineKeyboardButton("📖 آموزش بازی", callback_data="tutorial")],
        [InlineKeyboardButton("ℹ️ راهنما", callback_data="help_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def create_waiting_room_keyboard(game_id: str, is_creator: bool):
    keyboard = [
        [InlineKeyboardButton("✅ آماده", callback_data=f"ready_{game_id}")],
        [InlineKeyboardButton("🔄 وضعیت بازی", callback_data=f"status_{game_id}")]
    ]
    if is_creator:
        keyboard.append([InlineKeyboardButton("▶️ شروع بازی", callback_data=f"start_{game_id}")])
    keyboard.append([InlineKeyboardButton("❌ خروج", callback_data=f"leave_{game_id}")])
    return InlineKeyboardMarkup(keyboard)

def create_trump_selection_keyboard(game_id: str):
    keyboard = []
    row = []
    for suit, info in SUITS.items():
        button = InlineKeyboardButton(
            f"{info['emoji']} {info['symbol']}",
            callback_data=f"trump_{game_id}_{suit}"
        )
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def create_card_keyboard(game: HokmGame, player_id: int):
    player = game.players[player_id]
    keyboard = []
    row = []
    
    cards_by_suit = defaultdict(list)
    for card in player.cards:
        cards_by_suit[card.suit].append(card)
    
    for suit in SUITS:
        if suit in cards_by_suit:
            suit_cards = cards_by_suit[suit]
            suit_cards.sort(key=lambda x: x.value)
            
            for card in suit_cards:
                is_valid = True
                if game.lead_suit and game.current_player_id == player_id:
                    is_valid = player.can_play(card, game.lead_suit)
                
                emoji = SUITS[suit]['emoji']
                button_text = f"{emoji} {card.rank}"
                
                if not is_valid:
                    button_text = f"🚫 {button_text}"
                
                callback_data = f"card_{game.game_id}_{suit}_{card.rank}"
                row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
                
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
    
    if row:
        keyboard.append(row)
    
    keyboard.extend([
        [InlineKeyboardButton("🔄 وضعیت بازی", callback_data=f"status_{game.game_id}")],
        [InlineKeyboardButton("📊 امتیازات", callback_data=f"scores_{game.game_id}")],
        [InlineKeyboardButton("🏳️ تسلیم", callback_data=f"surrender_{game.game_id}")]
    ])
    
    return InlineKeyboardMarkup(keyboard)

# ============ MESSAGE FUNCTIONS ============
def format_player_list(game: HokmGame, current_user_id: int = None) -> str:
    lines = []
    for i, player_id in enumerate(game.player_order):
        player = game.players[player_id]
        status_emoji = "✅" if player.is_ready else "⏳"
        dealer_emoji = "👑" if player.is_dealer else ""
        team_emoji = "🔵" if player.team == 0 else "🔴"
        turn_emoji = "🎮" if player_id == game.current_player_id else ""
        you_marker = " (شما)" if player_id == current_user_id else ""
        
        line = f"{i+1}. {status_emoji} {dealer_emoji} {team_emoji} {turn_emoji} "
        line += f"<b>{player.first_name}</b>{you_marker}"
        
        if game.phase == GamePhase.PLAYING:
            line += f" - {len(player.cards)} کارت"
        if player.tricks_won > 0:
            line += f" - {player.tricks_won} برد"
        
        lines.append(line)
    
    if game.player_count < 4:
        lines.append(f"\n👤 {4 - game.player_count} نفر دیگر لازم است...")
    
    return "\n".join(lines)

def format_game_status(game: HokmGame) -> str:
    if game.phase == GamePhase.WAITING:
        return "👥 <b>اتاق انتظار</b>\n\n" + format_player_list(game)
    
    elif game.phase == GamePhase.CHOOSING_TRUMP:
        chooser = game.players[game.trump_chooser_id]
        return f"🎯 <b>انتخاب حکم</b>\n\n{chooser.first_name} باید حکم بازی را انتخاب کند"
    
    elif game.phase == GamePhase.PLAYING:
        current_player = game.players[game.current_player_id]
        trump_emoji = SUITS[game.trump_suit]['emoji']
        
        message = f"🎮 <b>دست {game.round_number} - نوبت {current_player.first_name}</b>\n"
        message += f"🎯 حکم: {trump_emoji} {SUITS[game.trump_suit]['symbol']}\n\n"
        
        if game.current_trick and game.current_trick.cards_played:
            message += "🃏 کارت‌های بازی شده:\n"
            for player_id, card in game.current_trick.cards_played.items():
                player = game.players[player_id]
                card_display = f"{SUITS[card.suit]['emoji']} {card.rank}"
                message += f"  {player.first_name}: {card_display}\n"
            message += "\n"
        
        message += format_player_list(game)
        message += f"\n🏆 امتیازات: تیم 🔵 {game.scores[0]} - {game.scores[1]} تیم 🔴"
        return message
    
    elif game.phase == GamePhase.ROUND_END:
        message = f"🎊 <b>پایان دست {game.round_number - 1}</b>\n\n"
        message += f"امتیازات این دست:\n"
        message += f"تیم 🔵: {game.scores[0]}\n"
        message += f"تیم 🔴: {game.scores[1]}\n\n"
        message += "دست بعدی به زودی شروع می‌شود..."
        return message
    
    elif game.phase == GamePhase.GAME_END:
        winner_team = game.get_winner_team()
        winner_emoji = "🔵" if winner_team == 0 else "🔴"
        message = f"🏆 <b>پایان بازی!</b> 🏆\n\n"
        message += f"تیم برنده: {winner_emoji}\n\n"
        message += f"امتیاز نهایی:\n"
        message += f"تیم 🔵: {game.scores[0]}\n"
        message += f"تیم 🔴: {game.scores[1]}\n\n"
        message += "بازی به پایان رسید! ✨"
        return message
    
    return "وضعیت بازی"

def format_card_message(player: Player) -> str:
    if not player.cards:
        return "⚠️ شما کارتی ندارید!"
    
    message = "🃏 <b>کارت‌های شما:</b>\n\n"
    cards_by_suit = defaultdict(list)
    for card in player.cards:
        cards_by_suit[card.suit].append(card)
    
    for suit in SUITS:
        if suit in cards_by_suit:
            suit_cards = cards_by_suit[suit]
            suit_cards.sort(key=lambda x: x.value)
            suit_emoji = SUITS[suit]['emoji']
            suit_symbol = SUITS[suit]['symbol']
            card_symbols = [f"{card.rank}" for card in suit_cards]
            message += f"{suit_emoji} {suit_symbol}: {' '.join(card_symbols)}\n"
    
    return message

# ============ BOT HANDLERS ============
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_message = (
        f"👋 سلام {user.first_name}!\n\n"
        f"🤖 به <b>ربات بازی حکم</b> خوش آمدید!\n\n"
        f"🎮 بازی حکم ۴ نفره با گرافیک بالا و امکانات کامل\n\n"
        f"برای شروع روی <b>بازی جدید</b> کلیک کنید."
    )
    
    await update.message.reply_text(
        welcome_message,
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_menu()
    )

async def new_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    existing_game = GameManager.get_user_game(user.id)
    
    if existing_game:
        await query.edit_message_text(
            "⚠️ شما در حال حاضر در یک بازی شرکت دارید!\nبرای خروج از /leave استفاده کنید.",
            parse_mode=ParseMode.HTML
        )
        return
    
    game = GameManager.create_game(user.id, user.first_name)
    
    message = (
        f"🎮 <b>اتاق بازی جدید ایجاد شد!</b>\n\n"
        f"🆔 کد بازی: <code>{game.game_id}</code>\n\n"
        f"📋 برای دعوت دوستان، کد بالا را برای آنها بفرستید.\n\n"
        f"{format_player_list(game, user.id)}"
    )
    
    await query.edit_message_text(
        message,
        parse_mode=ParseMode.HTML,
        reply_markup=create_waiting_room_keyboard(game.game_id, True)
    )

async def join_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 لطفاً کد بازی را وارد کنید:\nمثال: /join ABC12345",
        parse_mode=ParseMode.HTML
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "⚠️ لطفاً کد بازی را وارد کنید.\nمثال: /join ABC12345",
            parse_mode=ParseMode.HTML
        )
        return
    
    game_id = context.args[0].upper()
    existing_game = GameManager.get_user_game(user.id)
    
    if existing_game:
        await update.message.reply_text("⚠️ شما در حال حاضر در یک بازی شرکت دارید!")
        return
    
    success = GameManager.join_game(user.id, user.username, user.first_name, game_id)
    
    if success:
        game = GameManager.games[game_id]
        
        for player_id in game.player_order:
            try:
                await context.bot.send_message(
                    player_id,
                    f"🎉 {user.first_name} به بازی پیوست!\n\n{format_player_list(game, player_id)}",
                    parse_mode=ParseMode.HTML,
                    reply_markup=create_waiting_room_keyboard(game_id, player_id == game.creator_id)
                )
            except:
                pass
        
        await update.message.reply_text(f"✅ با موفقیت به بازی {game_id} پیوستید!")
    else:
        await update.message.reply_text("⚠️ بازی یافت نشد یا ظرفیت آن تکمیل است!")

async def ready_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1]
    
    game = GameManager.games.get(game_id)
    if not game or user_id not in game.players:
        await query.edit_message_text("⚠️ بازی یافت نشد!")
        return
    
    player = game.players[user_id]
    player.is_ready = not player.is_ready
    
    for player_id in game.player_order:
        try:
            await context.bot.edit_message_text(
                chat_id=player_id,
                message_id=query.message.message_id,
                text=f"🎮 <b>اتاق بازی {game_id}</b>\n\n{format_player_list(game, player_id)}",
                parse_mode=ParseMode.HTML,
                reply_markup=create_waiting_room_keyboard(game_id, player_id == game.creator_id)
            )
        except:
            pass

async def start_game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1]
    
    game = GameManager.games.get(game_id)
    if not game or user_id != game.creator_id:
        await query.edit_message_text("⚠️ فقط سازنده بازی می‌تواند آن را شروع کند!")
        return
    
    if not game.is_full:
        await query.edit_message_text("⚠️ بازی باید ۴ بازیکن داشته باشد!")
        return
    
    if not game.is_ready_to_start:
        await query.edit_message_text("⚠️ همه بازیکنان باید آماده باشند!")
        return
    
    game.start_game()
    
    for player_id in game.player_order:
        player = game.players[player_id]
        card_message = format_card_message(player)
        status_message = format_game_status(game)
        
        await context.bot.send_message(player_id, card_message, parse_mode=ParseMode.HTML)
        
        if player_id == game.trump_chooser_id:
            await context.bot.send_message(
                player_id,
                "🎯 شما باید حکم بازی را انتخاب کنید:",
                parse_mode=ParseMode.HTML,
                reply_markup=create_trump_selection_keyboard(game_id)
            )
        
        await context.bot.send_message(player_id, status_message, parse_mode=ParseMode.HTML)

async def trump_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    _, game_id, suit = query.data.split('_')
    
    game = GameManager.games.get(game_id)
    if not game or game.phase != GamePhase.CHOOSING_TRUMP:
        await query.edit_message_text("⚠️ زمان انتخاب حکم گذشته است!")
        return
    
    if user_id != game.trump_chooser_id:
        await query.edit_message_text("⚠️ فقط انتخاب‌کننده حکم می‌تواند انتخاب کند!")
        return
    
    try:
        game.choose_trump(user_id, suit)
    except Exception as e:
        await query.edit_message_text(f"⚠️ خطا: {str(e)}")
        return
    
    trump_emoji = SUITS[suit]['emoji']
    trump_symbol = SUITS[suit]['symbol']
    
    for player_id in game.player_order:
        player = game.players[player_id]
        await context.bot.send_message(
            player_id,
            f"🎯 {game.players[game.trump_chooser_id].first_name} "
            f"حکم بازی را انتخاب کرد: {trump_emoji} {trump_symbol}",
            parse_mode=ParseMode.HTML
        )
        
        status_message = format_game_status(game)
        
        if player_id == game.current_player_id:
            await context.bot.send_message(
                player_id,
                format_card_message(player),
                parse_mode=ParseMode.HTML,
                reply_markup=create_card_keyboard(game, player_id)
            )
        
        await context.bot.send_message(player_id, status_message, parse_mode=ParseMode.HTML)

async def card_play_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    _, game_id, suit, rank = query.data.split('_')
    
    game = GameManager.games.get(game_id)
    if not game or game.phase != GamePhase.PLAYING:
        await query.edit_message_text("⚠️ بازی در حال اجرا نیست!")
        return
    
    if user_id != game.current_player_id:
        await query.answer("⏳ نوبت شما نیست!", show_alert=True)
        return
    
    player = game.players[user_id]
    card_to_play = None
    for card in player.cards:
        if card.suit == suit and card.rank == rank:
            card_to_play = card
            break
    
    if not card_to_play:
        await query.answer("⚠️ این کارت در دست شما نیست!", show_alert=True)
        return
    
    try:
        winner_id = game.play_card(user_id, card_to_play)
    except Exception as e:
        await query.answer(f"⚠️ {str(e)}", show_alert=True)
        return
    
    card_display = f"{SUITS[suit]['emoji']} {rank}"
    
    for player_id in game.player_order:
        try:
            await context.bot.send_message(
                player_id,
                f"🎴 {player.first_name} کارت {card_display} را بازی کرد",
                parse_mode=ParseMode.HTML
            )
        except:
            pass
    
    if winner_id:
        winner = game.players[winner_id]
        for player_id in game.player_order:
            try:
                await context.bot.send_message(
                    player_id,
                    f"🏆 {winner.first_name} این دست را برد!",
                    parse_mode=ParseMode.HTML
                )
            except:
                pass
    
    if game.phase in [GamePhase.PLAYING, GamePhase.ROUND_END, GamePhase.GAME_END]:
        for player_id in game.player_order:
            player = game.players[player_id]
            status_message = format_game_status(game)
            
            if game.phase == GamePhase.PLAYING and player_id == game.current_player_id:
                await context.bot.send_message(
                    player_id,
                    format_card_message(player),
                    parse_mode=ParseMode.HTML,
                    reply_markup=create_card_keyboard(game, player_id)
                )
            
            await context.bot.send_message(player_id, status_message, parse_mode=ParseMode.HTML)
    
    try:
        await query.delete_message()
    except:
        pass

async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1]
    
    game = GameManager.games.get(game_id)
    if not game or user_id not in game.players:
        await query.edit_message_text("⚠️ بازی یافت نشد!")
        return
    
    status_message = format_game_status(game)
    await query.edit_message_text(status_message, parse_mode=ParseMode.HTML)

async def leave_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    game_id = query.data.split('_')[1] if '_' in query.data else None
    
    if game_id:
        game = GameManager.games.get(game_id)
    else:
        game = GameManager.get_user_game(user_id)
        game_id = GameManager.user_games.get(user_id)
    
    if not game or user_id not in game.players:
        await query.edit_message_text("⚠️ شما در بازی‌ای شرکت ندارید!")
        return
    
    leaver_name = game.players[user_id].first_name
    old_game_id = GameManager.leave_game(user_id)
    
    if old_game_id:
        game = GameManager.games.get(old_game_id)
        
        if game and game.player_count > 0:
            for player_id in game.player_order:
                try:
                    await context.bot.send_message(
                        player_id,
                        f"👋 {leaver_name} از بازی خارج شد.\n\n{format_player_list(game, player_id)}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=create_waiting_room_keyboard(old_game_id, player_id == game.creator_id)
                    )
                except:
                    pass
    
    await query.edit_message_text(
        "✅ شما از بازی خارج شدید.",
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_menu()
    )

async def tutorial_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    tutorial_text = (
        "📖 <b>آموزش بازی حکم:</b>\n\n"
        "🎯 <b>هدف بازی:</b>\nبردن حداقل ۷ دست از ۱۳ دست\n\n"
        "👥 <b>تیم‌بندی:</b>\n۴ بازیکن در ۲ تیم دو نفره\n\n"
        "🃏 <b>مراحل بازی:</b>\n"
        "۱. انتخاب حکم\n۲. پخش کارت\n"
        "۳. بازی ۱۳ دست\n۴. محاسبه امتیاز\n\n"
        "⚖️ <b>قوانین:</b>\n"
        "- باید هم‌خال بازی کنید\n"
        "- خال حکم قوی‌ترین است\n"
        "- برنده دست بعدی را شروع می‌کند\n\n"
        "🏆 <b>امتیازدهی:</b>\n"
        "- هر دستی بیش از ۶، ۱ امتیاز\n"
        "- تیم اول به ۷ امتیاز برنده\n\n"
        "🎮 برای شروع روی «بازی جدید» کلیک کنید."
    )
    
    await query.edit_message_text(
        tutorial_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ])
    )

async def back_to_main_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎮 <b>منوی اصلی</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=create_main_menu()
    )

async def help_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    help_text = (
        "❓ <b>راهنمای دستورات:</b>\n\n"
        "🎮 <b>شروع بازی:</b>\n"
        "/start - راه‌اندازی ربات\n"
        "/new - ایجاد بازی جدید\n"
        "/join [کد] - پیوستن به بازی\n\n"
        "🕹️ <b>حین بازی:</b>\n"
        "/status - وضعیت بازی\n"
        "/leave - ترک بازی\n"
        "/cards - کارت‌های شما\n\n"
        "📊 <b>سایر:</b>\n"
        "/help - این راهنما\n"
        "/rules - قوانین بازی"
    )
    
    await query.edit_message_text(
        help_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_main")]
        ])
    )

# ============ COMMAND HANDLERS ============
async def new_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await new_game_handler(update, context)

async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game = GameManager.get_user_game(user_id)
    
    if not game:
        await update.message.reply_text("⚠️ شما در بازی‌ای شرکت ندارید!")
        return
    
    leaver_name = game.players[user_id].first_name
    game_id = GameManager.user_games[user_id]
    old_game_id = GameManager.leave_game(user_id)
    
    if old_game_id:
        game = GameManager.games.get(old_game_id)
        
        if game and game.player_count > 0:
            for player_id in game.player_order:
                try:
                    await context.bot.send_message(
                        player_id,
                        f"👋 {leaver_name} از بازی خارج شد.\n\n{format_player_list(game, player_id)}",
                        parse_mode=ParseMode.HTML,
                        reply_markup=create_waiting_room_keyboard(old_game_id, player_id == game.creator_id)
                    )
                except:
                    pass
    
    await update.message.reply_text("✅ شما از بازی خارج شدید.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    game = GameManager.get_user_game(user_id)
    
    if not game:
        await update.message.reply_text("⚠️ شما در بازی‌ای شرکت ندارید!")
        return
    
    status_message = format_game_status(game)
    await update.message.reply_text(status_message, parse_mode=ParseMode.HTML)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "❓ <b>راهنمای ربات حکم:</b>\n\n"
        "🎮 <b>برای شروع بازی:</b>\n"
        "1. روی «بازی جدید» کلیک کنید\n"
        "2. کد بازی را به دوستانتان بدهید\n"
        "3. وقتی ۴ نفر کامل شدند، بازی را شروع کنید\n\n"
        "🕹️ <b>دستورات:</b>\n"
        "/start - راه‌اندازی ربات\n"
        "/new - بازی جدید\n"
        "/join [کد] - پیوستن\n"
        "/status - وضعیت بازی\n"
        "/leave - ترک بازی\n\n"
        "📞 <b>پشتیبانی:</b>\n"
        "در صورت مشکل با @پشتیبان تماس بگیرید."
    )
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await tutorial_handler(update, context)

# ============ MAIN FUNCTION ============
def main():
    """Start the bot."""
    # Configure logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    logger = logging.getLogger(__name__)
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("new", new_command))
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("leave", leave_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rules", rules_command))
    
    # Add callback query handlers
    application.add_handler(CallbackQueryHandler(new_game_handler, pattern="^new_game$"))
    application.add_handler(CallbackQueryHandler(join_game_handler, pattern="^join_game$"))
    application.add_handler(CallbackQueryHandler(tutorial_handler, pattern="^tutorial$"))
    application.add_handler(CallbackQueryHandler(help_menu_handler, pattern="^help_menu$"))
    application.add_handler(CallbackQueryHandler(ready_handler, pattern="^ready_"))
    application.add_handler(CallbackQueryHandler(start_game_handler, pattern="^start_"))
    application.add_handler(CallbackQueryHandler(trump_selection_handler, pattern="^trump_"))
    application.add_handler(CallbackQueryHandler(card_play_handler, pattern="^card_"))
    application.add_handler(CallbackQueryHandler(status_handler, pattern="^status_"))
    application.add_handler(CallbackQueryHandler(leave_handler, pattern="^leave_"))
    application.add_handler(CallbackQueryHandler(back_to_main_handler, pattern="^back_to_main$"))
    
    # Add empty handlers for other patterns
    application.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^scores_"))
    application.add_handler(CallbackQueryHandler(lambda u,c: u.answer(), pattern="^surrender_"))
    
    # Start the bot
    logger.info("🤖 ربات بازی حکم راه‌اندازی شد...")
    logger.info("📡 در حال گوش دادن به دستورات...")
    
    # Run the bot
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()
