import os, re
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from sheets import ensure_structure, record_sale, add_stock, refund_sale, set_default_price

bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
dp = Dispatcher()
router = Router()
dp.include_router(router)

ALLOWED_IDS = set()
if os.getenv("ALLOWED_USER_IDS"):
    ALLOWED_IDS = {int(x.strip()) for x in os.environ["ALLOWED_USER_IDS"].split(",") if x.strip()}

def _guard(user_id:int):
    return True if not ALLOWED_IDS else (user_id in ALLOWED_IDS)

@router.message(CommandStart())
async def cmd_start(msg: Message):
    if not _guard(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    ensure_structure()
    await msg.answer(
        "Готово! Форматы:\n"
        "• Продажа: `SKU SIZE [PRICE]`\n"
        "• Пополнить: `/add SKU SIZE QTY [COST] [DEFAULT_PRICE]`\n"
        "• Возврат: `/refund SKU SIZE` (отменяет последнюю продажу этого размера)\n"
        "• Цена: `/price SKU NEW_PRICE`\n"
        "/help — справка, /export — выгрузка в .xlsx",
        parse_mode="Markdown"
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "*Команды*\n"
        "• Продажа: `SKU SIZE [PRICE]`\n"
        "• Пополнить: `/add SKU SIZE QTY [COST] [DEFAULT_PRICE]`\n"
        "• Возврат: `/refund SKU SIZE`\n"
        "• Цена: `/price SKU NEW_PRICE`\n\n"
        "*Листы*\n"
        "- Inventory — остатки и цены\n"
        "- Sales — лог продаж (в т.ч. возвраты с отрицательными суммами)\n"
        "- Summary — итоги по месяцам",
        parse_mode="Markdown"
    )

sale_pat = re.compile(r"^([A-Za-z0-9\-\_]+)\s+((?:XS|S|M|L|XL|XXL))(?:\s+(\d+(?:[.,]\d+)?))?$", re.IGNORECASE)

@router.message(F.text & ~F.text.startswith("/"))
async def handle_sale(msg: Message):
    if not _guard(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    m = sale_pat.match(msg.text.strip())
    if not m:
        await msg.answer("Неверный формат. Пример: `A123 M 4500` или `A123 M`", parse_mode="Markdown")
        return
    sku, size, price = m.group(1), m.group(2), m.group(3)
    sale_price = float(str(price).replace(",", ".")) if price else None
    try:
        out = record_sale(sku, size, sale_price)
    except Exception as e:
        await msg.answer(f"Ошибка: {e}")
        return
    await msg.answer(
        f"✅ Продано: {out['sku']} {out['size']}\n"
        f"Наименование: {out['name']}\n"
        f"Цена продажи: {out['sale_price']:.2f}\n"
        f"Себестоимость: {out['cost']:.2f}\n"
        f"Чистая прибыль: {out['net']:.2f}\n"
        f"Остаток размера {out['size']}: {out['remaining']}"
    )

from aiogram.filters import CommandObject

@router.message(Command("add"))
async def cmd_add(msg: Message, command: CommandObject):
    if not _guard(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    parts = msg.text.strip().split()
    if len(parts) < 4:
        await msg.answer("Формат: `/add SKU SIZE QTY [COST] [DEFAULT_PRICE]`", parse_mode="Markdown")
        return
    _, sku, size, qty, *rest = parts
    try:
        qty = int(qty)
        cost = float(rest[0].replace(",", ".")) if len(rest) >= 1 else None
        dprice = float(rest[1].replace(",", ".")) if len(rest) >= 2 else None
        out = add_stock(sku, size.upper(), qty, cost, dprice)
    except Exception as e:
        await msg.answer(f"Ошибка: {e}")
        return
    await msg.answer(f"📦 Пополнение: {out['sku']} {out['size']} +{out['added']}. Текущий остаток: {out['new_qty']}")

@router.message(Command("refund"))
async def cmd_refund(msg: Message, command: CommandObject):
    if not _guard(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    parts = msg.text.strip().split()
    if len(parts) != 3:
        await msg.answer("Формат: `/refund SKU SIZE`", parse_mode="Markdown")
        return
    _, sku, size = parts
    try:
        out = refund_sale(sku, size.upper())
    except Exception as e:
        await msg.answer(f"Ошибка: {e}")
        return
    await msg.answer(
        f"↩️ Возврат: {out['sku']} {out['size']}\n"
        f"+1 на склад (теперь {out['new_qty']}).\n"
        f"Реверс продажи: -{out['sale_reversed']:.2f} выручки, -{out['net_reversed']:.2f} прибыли."
    )

@router.message(Command("price"))
async def cmd_price(msg: Message, command: CommandObject):
    if not _guard(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    parts = msg.text.strip().split()
    if len(parts) != 3:
        await msg.answer("Формат: `/price SKU NEW_PRICE`", parse_mode="Markdown")
        return
    _, sku, price = parts
    try:
        new_price = float(price.replace(",", "."))
        out = set_default_price(sku, new_price)
    except Exception as e:
        await msg.answer(f"Ошибка: {e}")
        return
    await msg.answer(f"💲 Цена обновлена: {out['sku']} — DefaultSalePrice = {out['new_price']:.2f}")
