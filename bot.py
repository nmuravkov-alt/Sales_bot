import os
from aiogram import Router, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from typing import List, Optional

from sheets import (
    ensure_structure,
    add_stock,
    record_sale,
    refund_sale,
    set_default_price,
    SIZES,
)

# ВАЖНО: web.py импортирует dp из этого файла и создаёт Bot отдельно.
dp = Dispatcher()
router = Router()
dp.include_router(router)

# --------- helpers ---------

def _allowed(user_id: int) -> bool:
    allow_raw = os.getenv("ALLOWED_USER_IDS", "").strip()
    if not allow_raw:
        return True
    try:
        allowed: List[int] = [int(x) for x in allow_raw.replace(",", " ").split() if x.strip().isdigit()]
    except Exception:
        return True
    return user_id in allowed

def _help_text() -> str:
    return (
        "Команды\n"
        "• Продажа: /sale SKU SIZE [PRICE]\n"
        "• Пополнить: /add SKU SIZE QTY [COST] [DEFAULT_PRICE]\n"
        "• Возврат: /refund SKU SIZE\n"
        "• Цена: /price SKU NEW_PRICE\n"
        "\n"
        "Листы\n"
        " - Inventory — остатки и цены\n"
        " - Sales — лог продаж (в т.ч. возвраты с отрицательными суммами)\n"
        " - Summary — итоги по месяцам\n"
    )

def _parse_args(text: str) -> List[str]:
    # убираем команду и разбиваем по пробелам
    parts = text.split()
    if not parts:
        return []
    # отрезаем первый токен (команду)
    return parts[1:]

def _to_int(x: str) -> int:
    return int(x.replace(",", ".").strip())

def _to_float(x: str) -> float:
    return float(x.replace(",", ".").strip())

# --------- handlers ---------

@router.message(Command("start"))
async def cmd_start(message: Message):
    if not _allowed(message.from_user.id):
        return await message.answer("Доступ ограничен.")
    ensure_structure()
    await message.answer("Готово. Таблица проверена/создана.\n\n" + _help_text() +
                         "\nЕсли Summary ругается на формулу — поменяй локаль файла на US или замени запятые на ; в формуле QUERY.")

@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(_help_text())

@router.message(Command("add"))
async def cmd_add(message: Message):
    if not _allowed(message.from_user.id):
        return await message.answer("Доступ ограничен.")
    args = _parse_args(message.text)
    # /add SKU SIZE QTY [COST] [DEFAULT_PRICE]
    if len(args) < 3:
        return await message.answer("Неверный формат. Пример: /add A123 M 5 1500 1990")

    sku = args[0].strip()
    size = args[1].strip().upper()
    if size not in SIZES:
        return await message.answer(f"Недопустимый размер: {size}. Допустимые: {', '.join(SIZES)}")

    try:
        qty = _to_int(args[2])
        cost = _to_float(args[3]) if len(args) >= 4 else None
        default_price = _to_float(args[4]) if len(args) >= 5 else None
        # имя товара (если хочешь, можно поддержать через кавычки, но пока оставим пустым)
        res = add_stock(sku, size, qty, cost=cost, default_price=default_price, auto_create=True)
    except Exception as e:
        return await message.answer(f"Ошибка: {e}")

    created_txt = " (создан новый SKU)" if res.get("created") else ""
    await message.answer(f"✅ Пополнено: {sku} {size} +{qty}. Новый остаток: {res['new_qty']}{created_txt}")

@router.message(Command("sale"))
async def cmd_sale(message: Message):
    if not _allowed(message.from_user.id):
        return await message.answer("Доступ ограничен.")
    args = _parse_args(message.text)
    # /sale SKU SIZE [PRICE]
    if len(args) < 2:
        return await message.answer("Неверный формат. Пример: /sale A123 M 1990")

    sku = args[0].strip()
    size = args[1].strip().upper()
    price = None
    if len(args) >= 3:
        try:
            price = _to_float(args[2])
        except Exception:
            return await message.answer("Цена должна быть числом")

    try:
        res = record_sale(sku, size, price)
    except Exception as e:
        return await message.answer(f"Ошибка: {e}")

    await message.answer(
        f"🧾 Продажа: {res['sku']} {res['size']} за {res['sale_price']:.2f} "
        f"(себестоимость {res['cost']:.2f}, прибыль {res['net']:.2f}). "
        f"Остаток: {res['remaining']}"
    )

@router.message(Command("refund"))
async def cmd_refund(message: Message):
    if not _allowed(message.from_user.id):
        return await message.answer("Доступ ограничен.")
    args = _parse_args(message.text)
    if len(args) < 2:
        return await message.answer("Неверный формат. Пример: /refund A123 M")

    sku = args[0].strip()
    size = args[1].strip().upper()

    try:
        res = refund_sale(sku, size)
    except Exception as e:
        return await message.answer(f"Ошибка: {e}")

    await message.answer(
        f"↩️ Возврат: {res['sku']} {res['size']}. Остаток: {res['new_qty']} "
        f"(отменена продажа {res['sale_reversed']:.2f}, прибыль {res['net_reversed']:.2f})."
    )

@router.message(Command("price"))
async def cmd_price(message: Message):
    if not _allowed(message.from_user.id):
        return await message.answer("Доступ ограничен.")
    args = _parse_args(message.text)
    if len(args) < 2:
        return await message.answer("Неверный формат. Пример: /price A123 2190")

    sku = args[0].strip()
    try:
        new_price = _to_float(args[1])
    except Exception:
        return await message.answer("Цена должна быть числом")

    try:
        res = set_default_price(sku, new_price)
    except Exception as e:
        return await message.answer(f"Ошибка: {e}")

    await message.answer(f"💲 Цена по умолчанию обновлена: {res['sku']} → {res['new_price']:.2f}")

# запасной обработчик
@router.message(F.text.startswith("/"))
async def cmd_unknown(message: Message):
    await message.answer("Неизвестная команда.\n\n" + _help_text())