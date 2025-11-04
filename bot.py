import os
from fastapi import FastAPI, Request, HTTPException
from aiogram.types import Update

from bot import dp, bot  # важно: в bot.py ДОЛЖНЫ быть объявлены bot и dp

app = FastAPI()
WEBHOOK_SECRET_TOKEN = os.environ.get("WEBHOOK_SECRET_TOKEN")

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    # Проверяем секрет Telegram (если задан)
    if WEBHOOK_SECRET_TOKEN:
        got = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if got != WEBHOOK_SECRET_TOKEN:
            raise HTTPException(status_code=403, detail="Bad secret")

    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/health")
async def health():
    return {"ok": True}
