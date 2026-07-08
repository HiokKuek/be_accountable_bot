# Accountability Bot

Telegram accountability/check-in bot for two people.

## Rules implemented

- Normal Telegram bot added to a group chat.
- Two players register with `/register`.
- Singapore timezone (`Asia/Singapore`).
- 8:00am reminder to send goals.
- 9:30am reminder tagging users who have not submitted goals.
- Goals due at 10:00am.
- Missing goals by 10:00am counts as a failed day.
- Completion reporting uses `/done 0`, `/done 1`, `/done 2`, `/done 3`.
- 10:00pm completion reminder tagging users who have not reported.
- Completion due at 5:00am next day.
- Missing completion report counts as failed day.
- 2/3 or 3/3 goals completed = pass.
- Month-end net settlement: person with more failed days pays `$5 × difference`; tie means nobody pays.

## Commands

```text
/register
/goals
- investment stuff
- intervals
- read
/done 2
/today
/score
/rules
/help
```

The bot also accepts your example style:

```text
8/7 checkins:
- investment stuff
- intervals
- read!
```

## Local setup

```bash
cd /root/workspace/accountability-bot
cp .env.example .env
# edit .env; paste BotFather token and set WEBHOOK_SECRET
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest -q
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Docker

```bash
cd /root/workspace/accountability-bot
cp .env.example .env
# edit .env first
docker compose up -d --build
```

The container exposes:

```text
host:      http://localhost:8788
container: http://accountability-bot:8080
health:    http://localhost:8788/health
```

For Cloudflare Tunnel, point:

```text
https://accountability.hiok.dev -> http://localhost:8788
```

Webhook endpoint:

```text
https://accountability.hiok.dev/telegram/webhook
```

## Register Telegram webhook

After Cloudflare Tunnel is working, run this from the server with `.env` loaded.

Important:

- Telegram webhook `secret_token` only allows `A-Z`, `a-z`, `0-9`, `_`, and `-`.
- Generate a safe secret with: `python3 -c "import secrets; print(secrets.token_urlsafe(48).rstrip('='))"`
- After changing `.env`, use `docker compose up -d --force-recreate accountability-bot`; `docker compose restart` does not reload env vars.


```bash
set -a
. ./.env
set +a
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook"   -d "url=${PUBLIC_BASE_URL}/telegram/webhook"   -d "secret_token=${WEBHOOK_SECRET}"
```

Check status:

```bash
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

## Secret handling

`.env` is gitignored. Do not commit Telegram tokens or webhook secrets.
