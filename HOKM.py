# requirements.txt
# python-telegram-bot[job-queue]==20.7
# python-dotenv==1.0.0

import os
import logging
from enum import Enum
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
import json
import random

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# ==================== تنظیمات ====================
TOKEN = os.environ.get("TOKEN")  # در رندر: Environment Variable با نام TOKEN

if not TOKEN:
    try:
        from dotenv import load_dotenv
        load_dotenv()
        TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
    except:
        pass

if not TOKEN:
    print("❌ توکن یافت نشد!")
    print("در رندر: Environment Variable با نام TOKEN ایجاد کن")
    print("مثال: Key: TOKEN, Value: توکن_ربات_شما")
    exit(1)

print(f"✅ توکن خوانده شد")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== کلاس‌های بازی ====================

class GameSymbol(Enum):
    X = "❌"
    O = "⭕"
    EMPTY = "⬜"

class GameStatus(Enum):
    WAITING = "در انتظار بازیکن دوم"
    PLAYING = "در حال بازی"
    X_WON = "❌ برنده شد!"
    O_WON = "⭕ برنده شد!"
    DRAW = "مساوی!"
    CANCELLED = "لغو شد"

@dataclass
class Player:
    user_id: int
    username: str = ""
    first_name: str = ""
    symbol: GameSymbol = GameSymbol.EMPTY
    
    @property
    def display_name(self):
        if self.username:
            return f"@{self.username}"
        return self.first_name or f"User_{self.user_id}"

@dataclass
class TicTacToeGame:
    game_id: str
    chat_id: int
    message_id: int = 0
    board: List[List[GameSymbol]] = field(default_factory=lambda: [
        [GameSymbol.EMPTY, GameSymbol.EMPTY, GameSymbol.EMPTY],
        [GameSymbol.EMPTY, GameSymbol.EMPTY, GameSymbol.EMPTY],
        [GameSymbol.EMPTY, GameSymbol.EMPTY, GameSymbol.EMPTY]
    ])
    player1: Optional[Player] = None
    player2: Optional[Player] = None
    current_turn: Optional[Player] = None
    status: GameStatus = GameStatus.WAITING
    created_at: datetime = field(default_factory=datetime.now)
    moves: List[Tuple[int, int, int]] = field(default_factory=list)  # (row, col, user_id)
    
    def add_player(self, player: Player) -> bool:
        if not self.player1:
            self.player1 = player
            self.player1.symbol = GameSymbol.X
            return True
        elif not self.player2 and player.user_id != self.player1.user_id:
            self.player2 = player
            self.player2.symbol = GameSymbol.O
            return True
        return False
    
    def start_game(self):
        if self.player1 and self.player2:
            self.status = GameStatus.PLAYING
            self.current_turn = random.choice([self.player1, self.player2])
            return True
        return False
    
    def make_move(self, player: Player, row: int, col: int) -> bool:
        if self.status != GameStatus.PLAYING:
            return False
        
        if player.user_id != self.current_turn.user_id:
            return False
        
        if not (0 <= row < 3 and 0 <= col < 3):
            return False
        
        if self.board[row][col] != GameSymbol.EMPTY:
            return False
        
        self.board[row][col] = player.symbol
        self.moves.append((row, col, player.user_id))
        
        # بررسی برنده
        winner = self.check_winner()
        if winner:
            self.status = GameStatus.X_WON if winner == GameSymbol.X else GameStatus.O_WON
        elif self.is_board_full():
            self.status = GameStatus.DRAW
        else:
            # تغییر نوبت
            self.current_turn = self.player2 if self.current_turn.user_id == self.player1.user_id else self.player1
        
        return True
    
    def check_winner(self) -> Optional[GameSymbol]:
        # بررسی سطرها
        for row in range(3):
            if self.board[row][0] == self.board[row][1] == self.board[row][2] != GameSymbol.EMPTY:
                return self.board[row][0]
        
        # بررسی ستون‌ها
        for col in range(3):
            if self.board[0][col] == self.board[1][col] == self.board[2][col] != GameSymbol.EMPTY:
                return self.board[0][col]
        
        # بررسی قطر اصلی
        if self.board[0][0] == self.board[1][1] == self.board[2][2] != GameSymbol.EMPTY:
            return self.board[0][0]
        
        # بررسی قطر فرعی
        if self.board[0][2] == self.board[1][1] == self.board[2][0] != GameSymbol.EMPTY:
            return self.board[0][2]
        
        return None
    
    def is_board_full(self) -> bool:
        for row in range(3):
            for col in range(3):
                if self.board[row][col] == GameSymbol.EMPTY:
                    return False
        return True
    
    def get_board_keyboard(self) -> InlineKeyboardMarkup:
        keyboard = []
        for row in range(3):
            row_buttons = []
            for col in range(3):
                symbol = self.board[row][col]
                if self.status == GameStatus.PLAYING and symbol == GameSymbol.EMPTY:
                    # دکمه‌های شیشه‌ای برای خانه‌های خالی
                    button_text = "▫️"
                    callback_data = f"move_{self.game_id}_{row}_{col}"
                else:
                    button_text = symbol.value
                    callback_data = f"none"
                
                row_buttons.append(
                    InlineKeyboardButton(button_text, callback_data=callback_data)
                )
            keyboard.append(row_buttons)
        
        # دکمه‌های کنترلی
        control_row = []
        
        if self.status == GameStatus.WAITING:
            control_row.append(
                InlineKeyboardButton("🎮 پیوستن به بازی", callback_data=f"join_{self.game_id}")
            )
        elif self.status == GameStatus.PLAYING:
            control_row.append(
                InlineKeyboardButton("🔄 بازی جدید", callback_data="new_game")
            )
        
        control_row.append(
            InlineKeyboardButton("❌ حذف بازی", callback_data=f"delete_{self.game_id}")
        )
        
        keyboard.append(control_row)
        
        return InlineKeyboardMarkup(keyboard)
    
    def get_game_info_text(self) -> str:
        text = f"🎮 بازی دوز (Tic Tac Toe)\n\n"
        
        if self.status == GameStatus.WAITING:
            text += f"⏳ در انتظار بازیکن دوم...\n\n"
            text += f"👤 بازیکن ۱ (❌): {self.player1.display_name if self.player1 else '?'}\n"
            text += f"👤 بازیکن ۲ (⭕): منتظر پیوستن...\n"
            text += f"\nبرای پیوستن روی دکمه '🎮 پیوستن به بازی' کلیک کنید."
        
        elif self.status == GameStatus.PLAYING:
            text += f"🎯 نوبت: {self.current_turn.display_name} ({self.current_turn.symbol.value})\n\n"
            text += f"👤 {self.player1.display_name if self.player1 else '?'} : ❌\n"
            text += f"👤 {self.player2.display_name if self.player2 else '?'} : ⭕\n"
            text += f"\n📍 حرکت: {len(self.moves)}/9"
        
        elif self.status in [GameStatus.X_WON, GameStatus.O_WON, GameStatus.DRAW]:
            winner_text = ""
            if self.status == GameStatus.X_WON:
                winner_text = f"🎉 برنده: {self.player1.display_name if self.player1 else '?'} (❌)"
            elif self.status == GameStatus.O_WON:
                winner_text = f"🎉 برنده: {self.player2.display_name if self.player2 else '?'} (⭕)"
            else:
                winner_text = "🤝 بازی مساوی شد!"
            
            text += f"{winner_text}\n\n"
            text += f"👤 {self.player1.display_name if self.player1 else '?'} : ❌\n"
            text += f"👤 {self.player2.display_name if self.player2 else '?'} : ⭕\n"
            text += f"\n🔄 برای بازی جدید، روی دکمه پایین کلیک کنید."
        
        return text

# ==================== مدیریت بازی‌ها ====================

class GameManager:
    def __init__(self):
        self.games: Dict[str, TicTacToeGame] = {}
        self.user_games: Dict[int, str] = {}  # user_id -> game_id
    
    def create_game(self, chat_id: int, player1: Player) -> TicTacToeGame:
        game_id = f"ttt_{chat_id}_{int(datetime.now().timestamp())}"
        game = TicTacToeGame(game_id=game_id, chat_id=chat_id, player1=player1)
        self.games[game_id] = game
        self.user_games[player1.user_id] = game_id
        return game
    
    def get_game(self, game_id: str) -> Optional[TicTacToeGame]:
        return self.games.get(game_id)
    
    def delete_game(self, game_id: str):
        game = self.games.get(game_id)
        if game:
            if game.player1:
                self.user_games.pop(game.player1.user_id, None)
            if game.player2:
                self.user_games.pop(game.player2.user_id, None)
            del self.games[game_id]
    
    def get_player_game(self, user_id: int) -> Optional[TicTacToeGame]:
        game_id = self.user_games.get(user_id)
        if game_id:
            return self.get_game(game_id)
        return None

# ایجاد مدیر بازی
game_manager = GameManager()

# ==================== دستورات ربات ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور شروع ربات"""
    user = update.effective_user
    await update.message.reply_text(
        f"سلام {user.first_name}! 👋\n\n"
        "به ربات بازی دوز (Tic Tac Toe) خوش آمدید! 🎮\n\n"
        "📌 دستورات:\n"
        "/start - نمایش این راهنما\n"
        "/newgame - شروع یک بازی جدید\n"
        "/tictactoe - شروع بازی دوز\n"
        "/help - راهنمای بازی\n\n"
        "🎮 برای شروع یک بازی جدید در گروه، از دستور /newgame استفاده کنید."
    )

async def new_game_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ایجاد یک بازی جدید"""
    chat_id = update.effective_chat.id
    user = update.effective_user
    
    # ایجاد بازیکن
    player = Player(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # ایجاد بازی
    game = game_manager.create_game(chat_id, player)
    
    # ایجاد کیبورد بازی
    keyboard = game.get_board_keyboard()
    
    # ارسال پیام بازی
    message = await update.message.reply_text(
        game.get_game_info_text(),
        reply_markup=keyboard
    )
    
    # ذخیره آیدی پیام
    game.message_id = message.message_id

async def tictactoe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """شروع بازی دوز"""
    await new_game_command(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """راهنمای بازی"""
    help_text = (
        "🎮 راهنمای بازی دوز (Tic Tac Toe)\n\n"
        "📌 قوانین بازی:\n"
        "• بازی بین دو نفر انجام می‌شود\n"
        "• یک نفر ❌ و دیگری ⭕ بازی می‌کند\n"
        "• بازیکنان به نوبت در خانه‌های خالی کلیک می‌کنند\n"
        "• اولین کسی که ۳ علامت خود را در یک خط قرار دهد برنده است\n"
        "• خط می‌تواند افقی، عمودی یا مورب باشد\n"
        "• اگر همه خانه‌ها پر شوند و برنده‌ای نباشد، بازی مساوی است\n\n"
        "🔄 نحوه بازی:\n"
        "۱. در گروه دستور /newgame را بزنید\n"
        "۲. نفر دوم روی دکمه 'پیوستن' کلیک کند\n"
        "۳. بازی شروع می‌شود و نوبت به صورت تصادفی انتخاب می‌شود\n"
        "۴. هر بازیکن در نوبت خود روی یک خانه خالی کلیک کند\n"
        "۵. بازی تا برد یکی از بازیکنان یا مساوی ادامه دارد\n\n"
        "🎯 نکات:\n"
        "• فقط بازیکنان بازی می‌توانند حرکت کنند\n"
        "• در نوبت خود فقط یک بار می‌توانید کلیک کنید\n"
        "• برای شروع بازی جدید می‌توانید از دکمه 'بازی جدید' استفاده کنید"
    )
    
    await update.message.reply_text(help_text)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک‌های دکمه‌ها"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    # جدا کردن اطلاعات callback_data
    parts = data.split("_")
    
    if parts[0] == "new":
        # بازی جدید
        await query.delete_message()
        await new_game_command(update, context)
        return
    
    elif parts[0] == "join" and len(parts) >= 2:
        # پیوستن به بازی
        game_id = parts[1]
        game = game_manager.get_game(game_id)
        
        if not game:
            await query.edit_message_text("❌ بازی یافت نشد!")
            return
        
        if game.status != GameStatus.WAITING:
            await query.answer("بازی قبلا شروع شده!", show_alert=True)
            return
        
        # بررسی اینکه آیا کاربر قبلاً در بازی است
        if user.id == game.player1.user_id:
            await query.answer("شما در حال حاضر در این بازی هستید!", show_alert=True)
            return
        
        # اضافه کردن بازیکن دوم
        player2 = Player(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name
        )
        
        if game.add_player(player2):
            game_manager.user_games[user.id] = game_id
            game.start_game()
            
            # به‌روزرسانی پیام
            keyboard = game.get_board_keyboard()
            await query.edit_message_text(
                game.get_game_info_text(),
                reply_markup=keyboard
            )
        else:
            await query.answer("بازی تکمیل است!", show_alert=True)
    
    elif parts[0] == "move" and len(parts) >= 4:
        # حرکت در بازی
        game_id = parts[1]
        try:
            row = int(parts[2])
            col = int(parts[3])
        except:
            return
        
        game = game_manager.get_game(game_id)
        
        if not game:
            await query.edit_message_text("❌ بازی یافت نشد!")
            return
        
        if game.status != GameStatus.PLAYING:
            await query.answer("بازی تمام شده!", show_alert=True)
            return
        
        # پیدا کردن بازیکن
        player = None
        if user.id == game.player1.user_id:
            player = game.player1
        elif game.player2 and user.id == game.player2.user_id:
            player = game.player2
        
        if not player:
            await query.answer("شما بازیکن این بازی نیستید!", show_alert=True)
            return
        
        # انجام حرکت
        if game.make_move(player, row, col):
            # به‌روزرسانی پیام
            keyboard = game.get_board_keyboard()
            await query.edit_message_text(
                game.get_game_info_text(),
                reply_markup=keyboard
            )
        else:
            await query.answer("حرکت نامعتبر! یا نوبت شما نیست!", show_alert=True)
    
    elif parts[0] == "delete" and len(parts) >= 2:
        # حذف بازی
        game_id = parts[1]
        game = game_manager.get_game(game_id)
        
        if not game:
            await query.edit_message_text("❌ بازی یافت نشد!")
            return
        
        # فقط سازنده بازی یا بازیکنان می‌توانند حذف کنند
        if user.id not in [game.player1.user_id, game.player2.user_id if game.player2 else -1]:
            await query.answer("شما مجاز به حذف این بازی نیستید!", show_alert=True)
            return
        
        game_manager.delete_game(game_id)
        await query.edit_message_text("🗑️ بازی حذف شد!")
    
    elif parts[0] == "none":
        # کلیک روی خانه پر یا غیرفعال
        await query.answer("این خانه قابل انتخاب نیست!", show_alert=True)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت بازی‌های فعال"""
    chat_id = update.effective_chat.id
    
    # پیدا کردن بازی‌های فعال در این چت
    active_games = []
    for game in game_manager.games.values():
        if game.chat_id == chat_id and game.status in [GameStatus.WAITING, GameStatus.PLAYING]:
            active_games.append(game)
    
    if not active_games:
        await update.message.reply_text("📭 هیچ بازی فعالی در این گروه وجود ندارد.")
        return
    
    text = f"🎮 بازی‌های فعال در این گروه: {len(active_games)}\n\n"
    
    for i, game in enumerate(active_games, 1):
        status_text = ""
        if game.status == GameStatus.WAITING:
            status_text = "⏳ در انتظار بازیکن دوم"
        elif game.status == GameStatus.PLAYING:
            status_text = f"🎯 در حال بازی - نوبت: {game.current_turn.display_name if game.current_turn else '?'}"
        
        text += f"{i}. ID: {game.game_id[-6:]}\n"
        text += f"   👤 بازیکنان: {game.player1.display_name}"
        if game.player2:
            text += f" vs {game.player2.display_name}"
        text += f"\n   📊 وضعیت: {status_text}\n"
        text += f"   🕐 ایجاد: {game.created_at.strftime('%H:%M')}\n\n"
    
    text += "برای پیوستن به بازی‌های در انتظار، روی آنها کلیک کنید."
    
    await update.message.reply_text(text)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لغو بازی فعلی کاربر"""
    user = update.effective_user
    
    game = game_manager.get_player_game(user.id)
    if not game:
        await update.message.reply_text("❌ شما در هیچ بازی فعالی نیستید.")
        return
    
    game_manager.delete_game(game.game_id)
    await update.message.reply_text("✅ بازی شما لغو شد.")

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

# ==================== اجرای ربات ====================

def main():
    """تابع اصلی برای اجرای ربات"""
    # ایجاد برنامه ربات
    application = Application.builder().token(TOKEN).build()
    
    # اضافه کردن هندلرهای دستورات
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("newgame", new_game_command))
    application.add_handler(CommandHandler("tictactoe", tictactoe_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # اضافه کردن هندلر callback
    application.add_handler(CallbackQueryHandler(callback_handler))
    
    # اضافه کردن هندلر خطا
    application.add_error_handler(error_handler)
    
    # شروع ربات
    print("🤖 ربات بازی دوز (Tic Tac Toe) در حال اجراست...")
    print("🎮 برای شروع بازی در یک گروه از دستور /newgame استفاده کنید.")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
