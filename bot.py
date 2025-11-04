# bot.py
import os
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties  # <— добавили

from sheets import ensure_structure, add_stock, record_sale, refund_sale, set_default_price

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_IDS = {
    s.strip() for s in os.environ.get("ALLOWED_USER_IDS", "").split(",") if s.strip()
}

# ✅ aiogram 3.7+: parse_mode задаём через default=DefaultBotProperties
bot = Bot(
    token=TELEGRAM_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

def _allowed(msg: Message) -> bool:
    uid = str(msg.from_user.id) if msg.from_user else ""
    return (not ALLOWED_USER_IDS) or (uid in ALLOWED_USER_IDS)

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not _allowed(message):
        return await message.answer("Доступ запрещён.")
    ensure_structure()
    await message.answer(
        "Команды:\n"
        "• Продажа: /sale SKU SIZE [PRICE]\n"
        "• Пополнить: /add_stock SKU SIZE QTY [COST] [DEFAULT_PRICE]\n"
        "• Возврат: /refund SKU SIZE\n"
        "• Цена: /price SKU NEW_PRICE\n\n"
        "Листы:\n— Inventory — остатки и цены\n— Sales — лог продаж\n— Summary — итоги по месяцам"
    )

@dp.message(Command("add_stock"))
async def cmd_add_stock(message: Message):
    if not _allowed(message): return
    parts = message.text.split()
    if len(parts) not in (4, 5, 6):
        return await message.answer("Неверный формат. Пример: /add_stock A123 M 5 1500 1990")
    _, sku, size, qty, *rest = parts
    cost = float(rest[0]) if len(rest) >= 1 else None
    default_price = float(rest[1]) if len(rest) >= 2 else None
    res = add_stock(sku, size, int(qty), cost, default_price)
    await message.answer(f"OK: {res}")

@dp.message(Command("sale"))
async def cmd_sale(message: Message):
    if not _allowed(message): return
    parts = message.text.split()
    if len(parts) not in (3, 4):
        return await message.answer("Неверный формат. Пример: /sale A123 M 1990")
    _, sku, size, *rest = parts
    price = float(rest[0]) if rest else None
    res = record_sale(sku, size, price)
    await message.answer(f"Продано: {res}")

@dp.message(Command("refund"))
async def cmd_refund(message: Message):
    if not _allowed(message): return
    parts = message.text.split()
    if len(parts) != 3:
        return await message.answer("Неверный формат. Пример: /refund A123 M")
    _, sku, size = parts
    res = refund_sale(sku, size)
    await message.answer(f"Возврат: {res}")

@dp.message(Command("price"))
async def cmd_price(message: Message):
    if not _allowed(message): return
    parts = message.text.split()
    if len(parts) != 3:
        return await message.answer("Неверный формат. Пример: /price A123 2190")
    _, sku, p = parts
    res = set_default_price(sku, float(p))
    await message.answer(f"Цена обновлена: {res}")
