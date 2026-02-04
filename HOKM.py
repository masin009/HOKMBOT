import os
import random
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import Command

TOKEN = os.getenv("8316915338:AAEo62io5KHBhq-MOMA-BRgSD9VleSDoRGc")

bot = Bot(TOKEN)
dp = Dispatcher()

# ---------- کارت‌ها ----------
SUITS = {
    "S": "♠️",
    "H": "♥️",
    "D": "♦️",
    "C": "♣️"
}
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def build_deck():
    deck = [f"{r}{s}" for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

# ---------- وضعیت بازی ----------
games = {}

class Game:
    def __init__(self, owner, chat_id):
        self.owner = owner
        self.chat_id = chat_id
        self.players = []
        self.hands = {}
        self.turn = 0
        self.started = False
        self.hokm = None
        self.table = []

    def add_player(self, uid):
        if uid not in self.players and len(self.players) < 4:
            self.players.append(uid)

    def ready(self):
        return len(self.players) == 4

    def start(self):
        deck = build_deck()
        self.hokm = random.choice(list(SUITS.values()))
        self.hands = {
            self.players[i]: deck[i*13:(i+1)*13]
            for i in range(4)
        }
        self.started = True
        self.turn = 0
        self.table = []

    def current_player(self):
        return self.players[self.turn]

# ---------- کیبورد کارت ----------
def cards_keyboard(cards):
    rows = []
    row = []
    for i, c in enumerate(cards, 1):
        row.append(
            InlineKeyboardButton(text=c, callback_data=f"play:{c}")
        )
        if i % 4 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)

# ---------- دستورات ----------
@dp.message(Command("startgame"))
async def startgame(msg: Message):
    if msg.chat.id in games:
        await msg.answer("❗️بازی قبلاً ساخته شده")
        return
    games[msg.chat.id] = Game(msg.from_user.id, msg.chat.id)
    await msg.answer(
        "🎴 **بازی حکم ساخته شد**\n"
        "👥 برای ورود: /join\n"
        "▶️ شروع بازی: /play"
    )

@dp.message(Command("join"))
async def join(msg: Message):
    game = games.get(msg.chat.id)
    if not game:
        return
    game.add_player(msg.from_user.id)
    await msg.answer(
        f"👤 {msg.from_user.first_name} وارد شد "
        f"({len(game.players)}/4)"
    )

@dp.message(Command("play"))
async def play(msg: Message):
    game = games.get(msg.chat.id)
    if not game:
        return
    if msg.from_user.id != game.owner:
        await msg.answer("⛔️ فقط سازنده بازی می‌تونه شروع کنه")
        return
    if not game.ready():
        await msg.answer("⛔️ هنوز ۴ نفر کامل نیست")
        return

    game.start()
    await msg.answer(
        f"🎮 **بازی شروع شد**\n"
        f"🃏 حکم: {game.hokm}\n"
        f"👉 نوبت: نفر اول"
    )

    for p in game.players:
        await bot.send_message(
            p,
            "🃏 **کارت‌های شما**\n"
            "برای بازی روی کارت بزن",
            reply_markup=cards_keyboard(game.hands[p])
        )

@dp.callback_query(F.data.startswith("play:"))
async def play_card(call: CallbackQuery):
    card = call.data.split(":")[1]

    for game in games.values():
        if call.from_user.id not in game.players:
            continue

        if not game.started:
            return

        if call.from_user.id != game.current_player():
            await call.answer("❌ نوبت شما نیست", show_alert=True)
            return

        if card not in game.hands[call.from_user.id]:
            return

        game.hands[call.from_user.id].remove(card)
        game.table.append((call.from_user.first_name, card))

        game.turn = (game.turn + 1) % 4

        await call.message.edit_text(
            "🃏 کارت‌های شما:",
            reply_markup=cards_keyboard(game.hands[call.from_user.id])
        )

        text = "🃏 **کارت‌های زمین:**\n"
        for name, c in game.table:
            text += f"{name}: {c}\n"

        if len(game.table) == 4:
            text += "\n✅ دست تموم شد"
            game.table = []

        await bot.send_message(game.chat_id, text)
        return

# ---------- اجرا ----------
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

