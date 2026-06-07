import asyncio
import logging
import os

from telegram import Bot
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)


def _get_bot() -> Bot:
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        raise EnvironmentError("TELEGRAM_TOKEN not set")
    return Bot(token=token)


def _get_chat_id() -> str:
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise EnvironmentError("TELEGRAM_CHAT_ID not set")
    return chat_id


def _build_message(job: dict, score: int, breakdown: dict) -> str:
    stars = "⭐" * (score // 20)
    remote_tag = "🌐 Remoto" if job.get("remote") else f"📍 {job.get('location', '?')}"

    salary_txt = ""
    if job.get("salary"):
        lo, hi = job["salary"]
        salary_txt = f"\n💰 R$ {lo:,.0f} – R$ {hi:,.0f}"

    matched = breakdown.get("matched_skills") or []
    missing = breakdown.get("missing_skills") or []

    skills_txt = ""
    if matched:
        skills_txt += f"\n✅ Skills: {', '.join(matched)}"
    if missing:
        skills_txt += f"\n❌ Faltando: {', '.join(missing)}"

    return (
        f"{stars} *Score: {score}/100*\n"
        f"💼 {_esc(job['title'])} — {_esc(job['company'])}\n"
        f"{remote_tag}{salary_txt}\n"
        f"🔗 [Ver vaga]({job['link']})"
        f"{skills_txt}"
    )


def _esc(text: str) -> str:
    for ch in r"_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


async def _send_async(message: str):
    bot = _get_bot()
    chat_id = _get_chat_id()
    await bot.send_message(
        chat_id=chat_id,
        text=message,
        parse_mode=ParseMode.MARKDOWN_V2,
        disable_web_page_preview=True,
    )


def send(job: dict, score: int, breakdown: dict):
    message = _build_message(job, score, breakdown)
    try:
        asyncio.run(_send_async(message))
        logger.info("Notified: %s (score=%d)", job["title"], score)
    except Exception as exc:
        logger.error("Telegram error for %s: %s", job.get("title"), exc)
