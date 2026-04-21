"""
One-time Blink authentication script.

Run this BEFORE starting Docker. It completes the Blink 2FA flow (email PIN)
and saves the session to data/blink/credentials.json so the main agent can
start without any interactive prompts on every restart.

Usage:
    pip install blinkpy python-dotenv
    python app/setup_auth.py
"""

import asyncio
import json
import os
from pathlib import Path

from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from dotenv import load_dotenv

load_dotenv()

CREDS_FILE = Path("./data/blink/credentials.json")


async def main():
    print("=== Blink One-Time Authentication ===\n")

    username = os.getenv("BLINK_USERNAME") or input("Blink email: ").strip()
    password = os.getenv("BLINK_PASSWORD") or input("Blink password: ").strip()

    blink = Blink()
    auth = Auth({"username": username, "password": password}, no_prompt=False)
    blink.auth = auth

    print("\nStarting Blink session — check your email for a PIN...")

    # blinkpy raises BlinkTwoFARequiredError instead of prompting inline.
    # We catch it, collect the PIN, then complete auth manually.
    from blinkpy.auth import BlinkTwoFARequiredError

    try:
        await blink.start()
    except BlinkTwoFARequiredError:
        pin = input("Enter the PIN Blink emailed you: ").strip()
        await blink.auth.complete_2fa_login(pin)
        blink.setup_urls()           # sets blink.urls — skipped when 2FA interrupted start()
        await blink.setup_post_verify()

    CREDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    await blink.save(str(CREDS_FILE))

    print(f"\nCredentials saved to {CREDS_FILE}")

    camera_names = list(blink.cameras.keys())
    if camera_names:
        print(f"Cameras found: {camera_names}")
        print("\nUse these exact names in Tasker (spaces are fine — the agent handles them).")
    else:
        print("No cameras found. Check that your Blink system is armed and connected.")


if __name__ == "__main__":
    asyncio.run(main())
