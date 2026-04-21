# Blink-Telegram Motion Alert Agent

**Project Repository**: `blink-telegram`

An autonomous motion detection system that captures photos from Blink cameras and sends them to Telegram via your local laptop.

## What It Does

1. **Blink camera detects motion** → sends notification to Amazon Alexa app on your phone
2. **Android Automate app intercepts the notification** → sends HTTP POST to your laptop webhook
3. **FastAPI agent on laptop receives webhook** → uses blinkpy to snap a photo from the Blink camera
4. **Photo is downloaded from Blink** → sent to Telegram via the official Telegram Bot API
5. **You get a Telegram message** with the photo, timestamp, and camera name

**Flow**: Blink Motion → Alexa Notification → Automate → Local Webhook → Photo Capture → Telegram Message

---

## Architecture

```
┌─────────────────┐
│  Blink Camera   │ (detects motion)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Amazon Alexa   │ (sends notification)
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│  Android Phone  │
│   (Automate)    │ (intercepts notification, sends HTTP POST)
└────────┬────────┘
         │
         ↓ POST /motion/{camera_name}
         │
┌─────────────────────────────────────────┐
│  Laptop (192.168.x.x:8000)              │
│  ┌──────────────────────────────────┐   │
│  │  FastAPI Agent (Docker)          │   │
│  │  - Restore Blink session         │   │
│  │  - Snap photo via blinkpy        │   │
│  │  - Download image                │   │
│  └──────────────────────────────────┘   │
└──────────────┬──────────────────────────┘
               │
               ↓ sendPhoto
         ┌─────────────┐
         │  Telegram   │ (Bot API)
         └─────────────┘
               │
               ↓
         Your Telegram Chat
```

---

## Prerequisites

### On Your Laptop (Mac/Linux)
- Docker Desktop running
- Python 3.11+ (for one-time Blink auth script)
- Same Wi-Fi network as your Android phone

### On Your Android Phone
- **Automate** app (free from Google Play)
- **Telegram** app (to receive photos)
- Connected to the same Wi-Fi as your laptop
- Blink notifications enabled (via Amazon Alexa app)

### Cloud Accounts (Free)
- **Telegram Bot** (created via @BotFather in Telegram, takes 2 min)
- **Blink Account** (you already have this)

---

## Complete Setup Guide

### Phase 1: Blink Authentication (One-time, ~5 min)

1. **Create `.env` file** in the project root:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Fill in:
   ```ini
   BLINK_USERNAME=your.email@example.com
   BLINK_PASSWORD=yourBlinkPassword
   WEBHOOK_SECRET=&lt;your_random_webhook_secret&gt;
   TELEGRAM_BOT_TOKEN=
   TELEGRAM_CHAT_ID=
   ```

2. **Run the one-time auth script**:
   ```bash
   docker build -t blink-auth ./app
   docker run -it -v $(pwd)/data:/app/session_data --env-file .env blink-auth python setup_auth.py
   ```
   When prompted, enter the 2FA PIN from your Blink email.

3. **Verify credentials saved**:
   ```bash
   ls -la data/blink/credentials.json
   ```
   Should exist and contain your session tokens.

---

### Phase 2: Telegram Bot Setup (One-time, ~2 min)

1. **Open Telegram** → search for **@BotFather**

2. **Send `/newbot`** and follow the prompts:
   - Name: `BlinkBot` (or any name)
   - Username: `blink_bot_2024` (must be unique, must end with `_bot`)

3. **BotFather replies with your BOT TOKEN** (format: `123456:ABC-DEF1234...`)
   - Copy this token

4. **Get your chat ID**:
   - Message your new bot (just say "hi")
   - Run in your terminal:
     ```bash
     curl "https://api.telegram.org/bot<PASTE_YOUR_TOKEN>/getUpdates"
     ```
   - Look for `"chat": {"id": 123456789}` — that's your CHAT_ID

5. **Update `.env`** with both values:
   ```ini
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234...
   TELEGRAM_CHAT_ID=123456789
   ```

---

### Phase 3: Start the Docker Agent (~2 min)

1. **Build and run the container**:
   ```bash
   docker compose up --build -d
   ```

2. **Verify it's healthy**:
   ```bash
   docker compose logs blink-agent --tail=20
   ```
   Should show:
   ```
   [INFO] Blink session restored. Cameras: ['family room', 'front door', 'kitchen', 'living room']
   [INFO] Application startup complete.
   ```

3. **Test the endpoint** from your Mac:
   ```bash
   curl -X POST http://localhost:8000/motion/front_door \
     -H "X-Webhook-Secret: &lt;your_random_webhook_secret&gt;"
   ```
   Should return: `{"status":"accepted","camera":"front door"}`

4. **Check your Telegram** — you should receive a photo from the front door camera in ~15 seconds.

---

### Phase 4: Find Your Laptop's IP Address

1. **Get your Wi-Fi IP**:
   ```bash
   ifconfig | grep "inet " | grep -v 127.0.0.1
   ```
   Look for something like `&lt;YOUR_LAPTOP_IP&gt;` or `10.0.x.x`

2. **Verify it from your Android phone**:
   - Open Chrome on your phone
   - Go to: `http://<YOUR_IP>:8000/health`
   - Should show: `{"status":"ok","blink_authenticated":true,...}`

3. **If connection fails** → macOS Firewall is blocking it
   - System Settings → Privacy & Security → Firewall Options
   - Add `Docker` or `uvicorn` to the allowed apps list
   - Test again from your phone

---

### Phase 5: Set Up Automate on Android (~5 min per camera)

#### Flow for Front Door (repeat for each camera)

1. **Open Automate** on your Android phone

2. **Create a new Flow**:
   - Tap **+** → **Flow**
   - Name: `BlinkMotion_FrontDoor`
   - Tap **CREATE**

3. **Add Notification Listener block**:
   - Tap **+** → search `Notification posted`
   - **Title**: `*Motion*` (glob pattern)
   - **Application package**: Select **Alexa** (or **Blink**)
   - Continue

4. **Add HTTP Request block**:
   - Tap **+** → search `HTTP request`
   - **URL**: `http://&lt;YOUR_LAPTOP_IP&gt;:8000/motion/front_door`
     - Replace `&lt;YOUR_LAPTOP_IP&gt;` with your actual IP from Phase 4
     - Replace `front_door` with the camera name (use underscores for spaces)
   - **Method**: `POST`
   - **Headers**: 
     ```json
     {
       "X-Webhook-Secret": "&lt;your_random_webhook_secret&gt;"
     }
     ```
   - Tap to finish

5. **Enable the Flow**:
   - Go back to flows list
   - Toggle the flow **ON** (green checkmark)

6. **Repeat for other cameras**:
   - `family_room` → `http://.../motion/family_room`
   - `kitchen` → `http://.../motion/kitchen`
   - `living_room` → `http://.../motion/living_room`

---

## Testing End-to-End

1. **Trigger motion** on a Blink camera (or just wave your hand in front of it)
2. **Alexa notifies** your phone with "Motion detected: Front Door"
3. **Automate intercepts** the notification
4. **15 seconds later** → Telegram sends you a photo with timestamp

If it doesn't work:
- Check `docker compose logs blink-agent` for errors
- Verify the IP address is correct (test `http://<IP>:8000/health` from phone)
- Confirm Automate flow is enabled (toggle ON)
- Check that the webhook secret matches between Automate and `.env`

---

## File Structure

```
blink-telegram/
├── app/
│   ├── main.py                # FastAPI agent (primary service)
│   ├── setup_auth.py          # One-time Blink 2FA authentication
│   ├── Dockerfile             # Docker image definition
│   └── requirements.txt        # Python dependencies
├── data/
│   └── blink/
│       └── credentials.json    # Blink session (auto-generated, DO NOT DELETE)
├── docker-compose.yml         # Docker service orchestration
├── .env                        # Environment variables (DO NOT COMMIT)
├── .env.example               # Template for .env
├── .gitignore                 # Excludes .env and data/
├── PROGRESS.md                # Build progress log
└── README.md                  # This file
```

---

## Environment Variables (`.env`)

```ini
# Blink Authentication (one-time, from setup_auth.py)
BLINK_USERNAME=your.email@example.com
BLINK_PASSWORD=yourBlinkPassword

# Webhook Security
# Random token that Automate must send in X-Webhook-Secret header
WEBHOOK_SECRET=&lt;your_random_webhook_secret&gt;

# Telegram Bot (from @BotFather)
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=987654321
```

---

## API Endpoints

### `GET /health`
Returns Blink authentication status and list of cameras.

**Response**:
```json
{
  "status": "ok",
  "blink_authenticated": true,
  "cameras": ["family room", "front door", "kitchen", "living room"]
}
```

### `POST /motion/{camera_name}`
Triggers photo capture and send to Telegram.

**Headers**:
- `X-Webhook-Secret: <your_webhook_secret>` (required)

**Path Parameters**:
- `camera_name`: Camera name with underscores for spaces (e.g., `front_door`)

**Response**:
```json
{
  "status": "accepted",
  "camera": "front door"
}
```

**Note**: The endpoint returns immediately. Photo capture happens in the background (~15 seconds).

---

## How the Photo Capture Works

1. **Snap picture**: `camera.snap_picture()` tells Blink to take a live photo
2. **Wait for image**: Sleep 5s, refresh Blink state, wait 3s for image to be available
3. **Download image**: `camera.image_to_file()` saves JPEG locally
4. **Send to Telegram**:
   - Upload image to Telegram's servers: `POST /bot<TOKEN>/sendPhoto`
   - Telegram stores and sends the image to your chat
5. **Clean up**: Delete the local temp file

Total time: ~15 seconds from motion trigger to Telegram message.

---

## Troubleshooting

### "Connection refused" from Automate
- Verify your laptop IP with: `ifconfig | grep "inet " | grep -v 127.0.0.1`
- Test from phone: `http://<IP>:8000/health` in Chrome
- If fails, add firewall exception: Settings → Privacy & Security → Firewall Options → Add Docker

### "No image received after motion"
- Check `docker compose logs blink-agent` for errors
- Verify Blink cameras are online in the Blink app
- Try manually triggering via curl:
  ```bash
  curl -X POST http://localhost:8000/motion/front_door \
    -H "X-Webhook-Secret: &lt;your_random_webhook_secret&gt;"
  ```

### "401 Unauthorized" in Docker logs
- The `X-Webhook-Secret` header in Automate doesn't match `.env`
- Verify they're identical

### "Blink session not restored"
- The `data/blink/credentials.json` file is missing or corrupt
- Run `setup_auth.py` again to re-authenticate

### Automate flow doesn't trigger
- Confirm flow is **enabled** (green toggle)
- Confirm notification title contains `*Motion*` pattern
- Check if Blink/Alexa notifications are enabled on your phone

---

## Technical Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Motion Detection | Blink Camera + Amazon Alexa | Detects motion and sends notification |
| Notification Interception | Automate (Android) | Listens for notifications, triggers webhook |
| Agent | FastAPI + Python | Receives webhook, orchestrates photo capture |
| Camera API | blinkpy (Python library) | Communicates with Blink cloud API |
| Image Delivery | Telegram Bot API | Sends photos to your chat |
| Containerization | Docker + Docker Compose | Runs the agent locally, isolates dependencies |
| Session Management | Persistent credentials.json | Restores Blink session on agent restart |

---

## Security Notes

- **Webhook Secret**: The `X-Webhook-Secret` header acts as basic authentication. Change it to a unique random value.
- **Credentials**: Blink username/password stored in plaintext in `.env` (local machine only). Add to `.gitignore` to prevent accidental commits.
- **Telegram Token**: Treat the bot token as a password. Anyone with this token can send messages to your chat. Keep it private.
- **Local Network**: The agent listens on port 8000 on your Wi-Fi network. Only your Automate flows can trigger it (requires the secret header).

---

## Future Enhancements

- **Video clips** instead of still photos (Blink supports video recording)
- **Multi-recipient**: Send alerts to multiple Telegram chats
- **Smart filtering**: Only alert on specific cameras or times of day
- **Motion history**: Store photos with timestamps for later review
- **Cloud backup**: Upload photos to cloud storage (AWS S3, Google Drive)

---

## Maintenance

### Daily
- No maintenance needed. The agent runs continuously.

### Weekly
- Check `docker compose logs blink-agent` for any errors
- Verify Telegram messages are still arriving after motion

### Monthly
- Refresh Blink tokens (automatic via blinkpy's refresh mechanism)
- Review Docker image for updates: `docker compose pull`

### On Major Changes
- After updating `.env`, restart the container: `docker compose restart`
- After modifying `main.py`, rebuild: `docker compose up --build`

---

## References

- **Blink API**: [blinkpy GitHub](https://github.com/fronzbot/blinkpy)
- **Telegram Bot API**: [Telegram Docs](https://core.telegram.org/bots/api)
- **FastAPI**: [FastAPI Documentation](https://fastapi.tiangolo.com/)
- **Docker Compose**: [Docker Docs](https://docs.docker.com/compose/)
- **Automate Android**: [LlamaLab Automate](https://llamalab.com/automate/)

---

## License

This project is for personal home automation use. No warranty is provided.

---

**Last Updated**: 2026-04-21  
**Status**: Fully operational — ready for production use
