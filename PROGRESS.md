# Blink-Telegram Motion Agent — Build Progress Log

## What This Project Does

Autonomous motion-alert system:
1. Blink camera detects motion → sends push notification to Android phone
2. Android Tasker intercepts the notification → HTTP POSTs to laptop webhook
3. FastAPI agent on laptop receives webhook → triggers blinkpy to snap a photo
4. Photo downloaded from Blink → sent to Telegram bot

---

## Current Status (as of 2026-04-20)

| Component | Status | Notes |
|-----------|--------|-------|
| Blink authentication | **DONE** | credentials.json saved, 4 cameras confirmed |
| FastAPI agent (`app/main.py`) | **DONE** | Health check, motion webhook, photo capture all working |
| Docker container (`blink-agent`) | **DONE** | Healthy, auto-restores Blink session on start |
| Telegram delivery | **IMPLEMENTED** | Wired to Telegram Bot API, simple 2-min setup |
| Tasker on Android | **NEXT** | Ready to set up once Telegram token/chat ID are in .env |

---

## Repository Layout

```
blink-telegram/
├── app/
│   ├── main.py            # FastAPI agent (primary service)
│   ├── setup_auth.py      # One-time Blink 2FA script (already run)
│   ├── Dockerfile
│   └── requirements.txt
├── wa-server/             # Abandoned — old WhatsApp attempt
│   ├── server.js
│   └── package.json
├── data/
│   └── blink/
│       └── credentials.json   # Valid Blink session — DO NOT DELETE
├── docker-compose.yml
├── .env.example
└── PROGRESS.md            # This file
```

---

## Blink Authentication — SOLVED

### How it works
- `setup_auth.py` does a one-time login with email + password + 2FA PIN
- Saves session to `data/blink/credentials.json`
- `main.py` restores the session on every Docker startup (no re-login needed)
- Confirmed cameras: `['family room', 'front door', 'kitchen', 'living room']`

### Key fix that was needed
blinkpy's `blink.start()` raises `BlinkTwoFARequiredError` and stops. After catching it:
```python
await blink.auth.complete_2fa_login(pin)
blink.setup_urls()          # CRITICAL — sets blink.urls (None after 2FA interrupt)
await blink.setup_post_verify()
```
Without `setup_urls()`, you get `NoneType has no attribute base_url`.

---

## FastAPI Agent — `app/main.py`

### Endpoints
- `GET /health` — returns Blink auth status + camera list
- `POST /motion/{camera_name}` — triggers capture+send (auth via `X-Webhook-Secret` header)

### Camera name mapping
URL path uses underscores, Blink uses spaces. The route does:
```python
resolved_name = camera_name.replace("_", " ")
```
So `POST /motion/front_door` maps to Blink camera `"front door"`.

### Image capture flow
1. `blink.refresh()` — syncs Blink state
2. `camera.async_snap_picture()` — triggers live snapshot
3. Poll up to 18s (6 × 3s) for `camera.last_image_url` to be populated
4. `camera.async_image_to_file(path)` — downloads the image
5. Send to Telegram, then delete temp file

---

## Telegram Delivery — IMPLEMENTED

### Why Telegram?
- **No restrictions**: Personal bot, no business verification
- **Truly free**: No per-message charges, ever
- **Simple setup**: 2 minutes via @BotFather
- **Works on both phones**: iOS and Android have Telegram

### Setup (one-time, ~2 min)

1. Open Telegram → Search **@BotFather**
2. Send `/newbot` → pick a name (e.g., "BlinkBot") and unique username
3. BotFather replies with your **BOT TOKEN** (e.g., `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
4. Message your new bot once (any text), then run:
   ```
   curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates"
   ```
5. In the JSON response, find `"chat": {"id": 123456789}` — that's your **CHAT_ID**
6. Add both to your `.env`:
   ```
   TELEGRAM_BOT_TOKEN=<token from step 3>
   TELEGRAM_CHAT_ID=<id from step 5>
   ```

### API flow (in `_send_telegram`)
```
POST https://api.telegram.org/bot<TOKEN>/sendPhoto
├── file: JPEG image (multipart)
├── chat_id: <your chat ID>
├── caption: "Motion: front door\n20 Apr 2026, 14:35:22"
└── parse_mode: "Markdown"  # makes caption bold/italic
```

---

## Docker Compose

```yaml
services:
  blink-agent:
    build: ./app
    volumes:
      - ./data:/app/session_data
    env_file: .env
    ports:
      - "8000:8000"
    restart: always
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
```

---

## Environment Variables (`.env`)

```ini
# Blink — used only by setup_auth.py (already run)
BLINK_USERNAME=your@email.com
BLINK_PASSWORD=yourpassword

# Webhook auth — Tasker must send this in X-Webhook-Secret header
WEBHOOK_SECRET=<random string>

# Telegram Bot (from @BotFather setup)
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>
```

---

## Tasker Setup (Android) — NEXT STEP

Plan:
1. Profile: Notification Received → App: Amazon Alexa (Blink uses Alexa notifications)
2. Condition: Notification text contains "Motion" or camera name
3. Task: HTTP Post to `http://<laptop-ip>:8000/motion/<camera_name>`
   - Header: `X-Webhook-Secret: <your secret>`
4. Test with `adb` or Tasker's built-in HTTP test before going live

---

## What Changed From WhatsApp

- **Rejected**: Green API (Russian), Meta Cloud API (account restrictions), Twilio Sandbox (media limitations)
- **Chosen**: Telegram Bot API (no restrictions, truly free, simplest setup)
- All code updated: `_send_whatsapp` → `_send_telegram`, uses Telegram's `sendPhoto` endpoint
