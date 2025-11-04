import os
from fastapi import FastAPI, Request, Header, HTTPException
from aiogram import Bot
from aiogram.types import Update
from bot import dp, bot

app = FastAPI()

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET_TOKEN", "secret")
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"].rstrip("/")

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(
        url=f"{PUBLIC_BASE_URL}/telegram/webhook",
        secret_token=WEBHOOK_SECRET,
        drop_pending_updates=False
    )

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook(drop_pending_updates=False)

@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(None)):
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret token")
    data = await request.json()
    update = Update.model_validate(data)
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
def root():
    return {"ok": True, "status": "running"}
