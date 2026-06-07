setup:
    uv sync
    test -f .env || cp .env.example .env
    @echo "Edite .env com TELEGRAM_TOKEN, TELEGRAM_CHAT_ID e LI_AT_COOKIE"

run:
    uv run python main.py

once:
    uv run python main.py --once

install:
    uv sync
