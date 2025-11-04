# Sales-bot (Telegram + Google Sheets)

Телеграм-бот для учёта остатков и продаж с хранением данных в Google Sheets. Готов к деплою на Railway (Docker).

## Возможности
- Продажа: `SKU SIZE [PRICE]` — спишет 1 с выбранного размера, запишет продажу в **Sales** и прибыль.
- Пополнение: `/add SKU SIZE QTY [COST] [DEFAULT_PRICE]` — добавит остаток и при желании обновит себестоимость/цену.
- Возврат: `/refund SKU SIZE` — вернёт 1 на склад и добавит отрицательную проводку в **Sales**.
- Цена: `/price SKU NEW_PRICE` — обновит DefaultSalePrice для товара.
- **Summary** агрегирует выручку и чистую прибыль по месяцам (YYYY-MM).

## Структура листов
**Inventory**
| SKU | Name | CostPerUnit | DefaultSalePrice | XS | S | M | L | XL | XXL | TotalQty | TotalCost |

**Sales**
| Timestamp | Month | SKU | Name | Size | SalePrice | CostPerUnit | NetProfit |

**Summary**
- Лист с формулами для суммирования по месяцам. В Google Sheets автоматически заполняется формулой QUERY.

## Быстрый старт (локально)
1. Скопируй `.env.example` в `.env` и заполни переменные.
2. Убедись, что сервисный аккаунт имеет доступ *Editor* к твоему Google Sheet.
3. Установи зависимости: `pip install -r requirements.txt`
4. Запусти: `uvicorn web:app --reload --port 8000`
5. В Telegram: отправь `/start` боту.

## Railway (Docker)
- Подключи репозиторий, установи переменные из `.env.example` в Settings → Variables.
- Деплой — контейнер стартует `uvicorn web:app` на порту 8000.
- После деплоя поставь домен Railway в `PUBLIC_BASE_URL` и перезапусти.

## Excel-шаблон
Смотри `templates/Inventory_Sales_Template.xlsx` — готовые листы Inventory / Sales / Summary.

