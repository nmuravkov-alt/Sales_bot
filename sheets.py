import os
import json
import base64
import datetime
import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL"]

# ---------- Google auth ----------

def _client():
    """
    Читает GOOGLE_SERVICE_ACCOUNT_JSON (base64 или «сырой» JSON).
    Чинит переносы строк в private_key.
    """
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"].strip()
    if not raw.startswith("{"):
        raw = base64.b64decode(raw).decode("utf-8")
    data = json.loads(raw)

    pk = data.get("private_key", "")
    if "\\n" in pk and "\n" not in pk:
        data["private_key"] = pk.replace("\\n", "\n")

    creds = Credentials.from_service_account_info(data, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc


def _sheet():
    gc = _client()
    return gc.open_by_key(os.environ["GOOGLE_SPREADSHEET_ID"])

# ---------- Structure ----------

def ensure_structure():
    sh = _sheet()

    # Inventory
    try:
        inv = sh.worksheet("Inventory")
    except gspread.WorksheetNotFound:
        inv = sh.add_worksheet("Inventory", rows=2000, cols=20)
        headers = ["SKU", "Name", "CostPerUnit", "DefaultSalePrice"] + SIZES + ["TotalQty", "TotalCost"]
        inv.update(
            f"A1:{chr(ord('A') + len(headers) - 1)}1",
            [headers]
        )

    # Sales
    try:
        sales = sh.worksheet("Sales")
    except gspread.WorksheetNotFound:
        sales = sh.add_worksheet("Sales", rows=20000, cols=10)
        sales.update("A1:H1", [["Timestamp", "Month", "SKU", "Name", "Size", "SalePrice", "CostPerUnit", "NetProfit"]])

    # Summary
    try:
        summary = sh.worksheet("Summary")
    except gspread.WorksheetNotFound:
        summary = sh.add_worksheet("Summary", rows=200, cols=10)
        summary.update("A1:C1", [["Month", "Total Sales", "Total Profit"]])
        # Функция QUERY работает при любой локали, но разделители отличаются.
        # Оставим англ-имена функций, а в боте дадим подсказку по локали.
        summary.update_acell(
            "A2",
            "=QUERY(Sales!A:H, "
            "\"select B, sum(F), sum(H) where B is not null group by B "
            "label sum(F) 'Total Sales', sum(H) 'Total Profit'\", 1)"
        )

# ---------- Inventory helpers ----------

def _find_inventory_row(inv, sku):
    vals = inv.get_all_values()
    if not vals:
        return None, None
    headers = vals[0]
    idx = None
    for i in range(1, len(vals)):
        row = vals[i]
        if row and row[0].strip().lower() == sku.strip().lower():
            idx = i + 1  # 1-based
            break
    return idx, headers


def _create_inventory_row(inv, sku: str, name: str = "", cost: float | None = None, default_price: float | None = None):
    """
    Создаёт новую строку в Inventory с нулевыми остатками по размерам.
    Возвращает индекс созданной строки (1-based).
    """
    # Считываем текущие данные, чтобы знать, куда вставлять
    last_row = len(inv.get_all_values()) + 1
    base = [sku, name, "", ""]
    base[2] = "" if cost is None else float(cost)
    base[3] = "" if default_price is None else float(default_price)
    size_zeros = [0 for _ in SIZES]
    tail = ["", ""]  # TotalQty, TotalCost (не используем, но оставляем под будущие формулы)
    inv.update(f"A{last_row}", [base + size_zeros + tail])
    return last_row


def get_size_col(headers, size):
    try:
        return headers.index(size) + 1
    except ValueError:
        raise ValueError(f"Размер {size} не найден в заголовках")


# ---------- Operations ----------

def record_sale(sku: str, size: str, sale_price: float | None):
    sh = _sheet()
    inv = sh.worksheet("Inventory")
    sales = sh.worksheet("Sales")

    row_idx, headers = _find_inventory_row(inv, sku)
    if not row_idx:
        raise ValueError(f"SKU {sku} не найден в листе Inventory")

    size = size.upper()
    if size not in SIZES:
        raise ValueError(f"Недопустимый размер: {size}. Допустимо: {', '.join(SIZES)}")

    size_col = get_size_col(headers, size)
    col_cost = headers.index("CostPerUnit") + 1
    col_default_price = headers.index("DefaultSalePrice") + 1

    current_qty = int(inv.cell(row_idx, size_col).value or "0")
    if current_qty <= 0:
        raise ValueError(f"Нет остатка у {sku} размера {size}")

    cost = float(inv.cell(row_idx, col_cost).value or "0")
    name = inv.cell(row_idx, 2).value or ""

    if sale_price is None:
        sale_price = float(inv.cell(row_idx, col_default_price).value or "0")
        if sale_price <= 0:
            raise ValueError("Не указана цена продажи и DefaultSalePrice пуст")

    inv.update_cell(row_idx, size_col, current_qty - 1)

    now = datetime.datetime.utcnow()
    month = now.strftime("%Y-%m")
    net = sale_price - cost
    sales.append_row(
        [now.isoformat(timespec="seconds") + "Z", month, sku, name, size, sale_price, cost, net],
        value_input_option="USER_ENTERED"
    )
    return {"sku": sku, "name": name, "size": size, "sale_price": sale_price, "cost": cost, "net": net, "remaining": current_qty - 1}


def add_stock(sku: str, size: str, qty: int, cost: float | None = None, default_price: float | None = None, auto_create: bool = True, name: str = ""):
    """
    Добавляет остаток. Если SKU нет и auto_create=True — создаёт строку в Inventory.
    """
    if qty <= 0:
        raise ValueError("Количество для пополнения должно быть > 0")

    sh = _sheet()
    inv = sh.worksheet("Inventory")

    row_idx, headers = _find_inventory_row(inv, sku)
    if not row_idx:
        if not auto_create:
            raise ValueError(f"SKU {sku} не найден в листе Inventory")
        # Создаём новую строку
        row_idx = _create_inventory_row(inv, sku, name=name, cost=cost, default_price=default_price)
        # перечитаем заголовки
        headers = inv.row_values(1)

    size = size.upper()
    if size not in SIZES:
        raise ValueError(f"Недопустимый размер: {size}. Допустимо: {', '.join(SIZES)}")

    size_col = get_size_col(headers, size)
    cur = int(inv.cell(row_idx, size_col).value or "0")
    inv.update_cell(row_idx, size_col, cur + qty)

    # Обновим цены, если даны
    if cost is not None:
        inv.update_cell(row_idx, headers.index("CostPerUnit") + 1, float(cost))
    if default_price is not None:
        inv.update_cell(row_idx, headers.index("DefaultSalePrice") + 1, float(default_price))
    # Обновим имя, если передали и ячейка пока пустая
    if name and not (inv.cell(row_idx, 2).value or "").strip():
        inv.update_cell(row_idx, 2, name)

    return {"sku": sku, "size": size, "added": qty, "new_qty": cur + qty, "created": False if cur is not None and cur != "" else True}


def refund_sale(sku: str, size: str):
    sh = _sheet()
    inv = sh.worksheet("Inventory")
    sales = sh.worksheet("Sales")
    records = sales.get_all_values()
    if not records or len(records) < 2:
        raise ValueError("В Sales нет продаж для возврата")
    headers = records[0]
    idx_sku = headers.index("SKU")
    idx_size = headers.index("Size")
    idx_price = headers.index("SalePrice")
    idx_cost = headers.index("CostPerUnit")
    idx_name = headers.index("Name")

    last = None
    for row in reversed(records[1:]):  # skip header
        if row and row[idx_sku].strip().lower() == sku.strip().lower() and row[idx_size].upper() == size.upper():
            last = row
            break
    if not last:
        raise ValueError(f"Не найдена продажа для возврата: {sku} {size}")
    sale_price = float(last[idx_price] or "0")
    cost = float(last[idx_cost] or "0")
    name = last[idx_name] or ""

    inv_row_idx, inv_headers = _find_inventory_row(inv, sku)
    if not inv_row_idx:
        raise ValueError(f"SKU {sku} не найден в Inventory")
    size_col = get_size_col(inv_headers, size.upper())
    cur = int(inv.cell(inv_row_idx, size_col).value or "0")
    inv.update_cell(inv_row_idx, size_col, cur + 1)

    now = datetime.datetime.utcnow()
    month = now.strftime("%Y-%m")
    rev_sale = -sale_price
    rev_net = -(sale_price - cost)
    sales.append_row(
        [now.isoformat(timespec="seconds") + "Z", month, sku, name, size.upper(), rev_sale, cost, rev_net],
        value_input_option="USER_ENTERED"
    )
    return {
        "sku": sku,
        "size": size.upper(),
        "restored": 1,
        "sale_reversed": sale_price,
        "net_reversed": (sale_price - cost),
        "new_qty": cur + 1
    }


def set_default_price(sku: str, new_price: float):
    sh = _sheet()
    inv = sh.worksheet("Inventory")
    row_idx, headers = _find_inventory_row(inv, sku)
    if not row_idx:
        raise ValueError(f"SKU {sku} не найден в листе Inventory")
    inv.update_cell(row_idx, headers.index("DefaultSalePrice") + 1, float(new_price))
    name = inv.cell(row_idx, 2).value or ""
    return {"sku": sku, "name": name, "new_price": float(new_price)}