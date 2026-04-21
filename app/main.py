import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import httpx
from blinkpy.auth import Auth
from blinkpy.blinkpy import Blink
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

CREDS_FILE     = "/app/session_data/blink/credentials.json"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
TELEGRAM_API_URL   = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

blink: Blink | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global blink
    creds_path = Path(CREDS_FILE)

    if not creds_path.exists():
        logger.critical(
            "No Blink credentials at %s — run setup_auth.py first, then restart.",
            CREDS_FILE,
        )
    else:
        try:
            with open(CREDS_FILE) as f:
                creds = json.load(f)
            blink = Blink(motion_interval=30, refresh_rate=30)
            blink.auth = Auth(creds, no_prompt=True)
            await blink.start()
            logger.info(
                "Blink session restored. Cameras: %s",
                list(blink.cameras.keys()),
            )
        except Exception:
            logger.exception("Failed to restore Blink session.")

    yield


app = FastAPI(title="Blink-Telegram Agent", lifespan=lifespan)


def _verify_secret(secret: str | None) -> None:
    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")


@app.get("/health")
async def health():
    authenticated = blink is not None and blink.auth is not None
    cameras = list(blink.cameras.keys()) if authenticated else []
    return {
        "status": "ok",
        "blink_authenticated": authenticated,
        "cameras": cameras,
    }


@app.post("/motion/{camera_name}")
async def trigger_motion(
    camera_name: str,
    background_tasks: BackgroundTasks,
    x_webhook_secret: str | None = Header(default=None),
):
    _verify_secret(x_webhook_secret)
    # URL path replaces underscores with spaces to match Blink camera names
    resolved_name = camera_name.replace("_", " ")
    logger.info("Motion trigger received → camera: '%s'", resolved_name)
    background_tasks.add_task(capture_and_send, resolved_name)
    return {"status": "accepted", "camera": resolved_name}


async def capture_and_send(camera_name: str) -> None:
    if blink is None:
        logger.error("Blink not initialized — skipping capture for '%s'.", camera_name)
        return

    safe_name = re.sub(r'[^a-zA-Z0-9\s\-]', '', camera_name).replace(' ', '_')
    temp_path = Path(f"/tmp/{safe_name}.jpg")

    try:
        await blink.refresh()

        camera = blink.cameras.get(camera_name)
        if not camera:
            logger.error(
                "Camera '%s' not found. Available: %s",
                camera_name,
                list(blink.cameras.keys()),
            )
            return

        logger.info("Snapping picture on '%s'...", camera_name)
        await camera.snap_picture()
        await asyncio.sleep(5)
        await blink.refresh()
        await asyncio.sleep(3)
        await camera.image_to_file(str(temp_path))
        logger.info("Image downloaded: %s", temp_path)

        await _send_telegram(str(temp_path), camera_name)

    except Exception:
        logger.exception("Error in capture_and_send for '%s'.", camera_name)
    finally:
        temp_path.unlink(missing_ok=True)


async def _send_telegram(image_path: str, camera_name: str) -> None:
    timestamp = datetime.now().strftime("%d %b %Y, %H:%M:%S")
    caption = f"*Motion: {camera_name}*\n_{timestamp}_"

    async with httpx.AsyncClient(timeout=30) as client:
        with open(image_path, "rb") as f:
            files = {"photo": (Path(image_path).name, f, "image/jpeg")}
            data = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            response = await client.post(
                f"{TELEGRAM_API_URL}/sendPhoto",
                files=files,
                data=data,
            )
        response.raise_for_status()
        logger.info("Telegram message sent (HTTP %d).", response.status_code)
