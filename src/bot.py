"""Telegram bot command handlers for interactive use."""
import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from . import database
from .ai_advisor import ask_claude

logger = logging.getLogger(__name__)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *LinkedIn Job Bot — Claude Edition*\n\n"
        "Comandos disponíveis:\n"
        "• /vagas — Ver últimas vagas salvas\n"
        "• /ask <pergunta> — Consultar o Claude sobre vagas e carreira\n"
        "• /status — Status do bot\n\n"
        "O bot busca vagas automaticamente 3x por dia e envia as melhores aqui.",
        parse_mode="Markdown",
    )


async def cmd_vagas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = database.get_recent_jobs(limit=10)
    if not jobs:
        await update.message.reply_text("Nenhuma vaga salva ainda. Aguarde a próxima busca automática!")
        return

    lines = ["📋 *Últimas vagas salvas:*\n"]
    for j in jobs:
        stars = "⭐" * (j["score"] // 20)
        lines.append(f"{stars} `{j['score']}/100` — *{j['title']}*")
        lines.append(f"  🏢 {j['company']}")
        if j.get("link"):
            lines.append(f"  [Ver vaga]({j['link']})\n")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text(
            "Uso: /ask <sua pergunta>\n\n"
            "Exemplo: /ask Qual vaga tem o melhor salário?\n"
            "Exemplo: /ask Devo aceitar uma vaga remota fora de BH?"
        )
        return

    await update.message.reply_text("⏳ Consultando Claude...")

    jobs = database.get_recent_jobs(limit=15)
    jobs_ctx = ""
    if jobs:
        jobs_ctx = "\n".join(
            f"- Score {j['score']}/100: {j['title']} @ {j['company']}"
            for j in jobs
        )

    answer = ask_claude(question, jobs_ctx)

    # Telegram has a 4096-char limit per message
    for chunk_start in range(0, len(answer), 4096):
        await update.message.reply_text(answer[chunk_start : chunk_start + 4096])


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    total = database.count_jobs()
    recent = database.get_recent_jobs(limit=1)
    last_seen = recent[0]["seen_at"][:10] if recent else "—"

    await update.message.reply_text(
        f"🟢 *Bot ativo*\n"
        f"📊 Total de vagas salvas: {total}\n"
        f"📅 Última vaga: {last_seen}",
        parse_mode="Markdown",
    )


def start_bot():
    """Start Telegram bot polling. This call blocks until the bot is stopped."""
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.error("TELEGRAM_TOKEN não configurado — bot interativo não iniciado")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("vagas", cmd_vagas))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("status", cmd_status))

    logger.info("Bot interativo iniciado — aguardando comandos no Telegram...")
    app.run_polling(drop_pending_updates=True)
