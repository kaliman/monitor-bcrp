#!/usr/bin/env python3
"""Discover and store the Telegram chat_id. Never prints the token."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from bcrp_monitor.config import (
    LOCAL_CONFIG_PATH,
    ConfigError,
    load_secrets,
)
from bcrp_monitor.constants import TELEGRAM_API_BASE, TELEGRAM_WEB_BASE


def api(token: str, method: str, **params) -> dict:
    url = f"{TELEGRAM_API_BASE}/bot{token}/{method}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.loads(response.read())


def chats_from(updates: list[dict]) -> dict[int, str]:
    found: dict[int, str] = {}
    for update in updates:
        for key in ("message", "edited_message", "channel_post", "my_chat_member"):
            message = update.get(key)
            if not message or "chat" not in message:
                continue
            chat = message["chat"]
            label = (
                chat.get("title")
                or chat.get("first_name")
                or chat.get("username")
                or "?"
            )
            found[chat["id"]] = f"{chat.get('type')} · {label}"
    return found


def _save_chat_id(chat_id: int) -> None:
    data: dict = {}
    if LOCAL_CONFIG_PATH.exists():
        data = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8-sig"))
    data.setdefault("telegram", {})["chat_id"] = str(chat_id)
    LOCAL_CONFIG_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--chat-id",
        type=int,
        help="chat id to use when more than one conversation is found",
    )
    args = parser.parse_args()

    try:
        secrets = load_secrets(require_chat_id=False)
    except ConfigError as exc:
        print(exc)
        return 1
    token = secrets.telegram_bot_token
    if not token:
        print("TELEGRAM_BOT_TOKEN is missing in the environment or config.local.json")
        return 1

    try:
        bot = api(token, "getMe")["result"]
    except urllib.error.HTTPError as exc:
        print(
            f"Telegram rejected the token (HTTP {exc.code}). "
            "Paste it in full, colon included."
        )
        return 1

    print(f"Token OK · bot @{bot['username']} ({bot['first_name']})")

    info = api(token, "getWebhookInfo")["result"]
    if info.get("url"):
        print("A webhook was active; removing it.")
        api(token, "deleteWebhook")

    updates = api(token, "getUpdates")["result"]
    chats = chats_from(updates)

    if not chats:
        print(f"\nNo messages yet. Open {TELEGRAM_WEB_BASE}/{bot['username']} and press START.")
        return 1

    print("\nChats found:")
    for chat_id, label in chats.items():
        print(f"  {chat_id}  ({label})")

    if args.chat_id:
        if args.chat_id not in chats:
            print(f"\nChat {args.chat_id} was not found. Use one of the ids above.")
            return 1
        target = args.chat_id
    elif len(chats) == 1:
        target = next(iter(chats))
    else:
        print("\nMore than one chat found. Rerun with --chat-id <id>.")
        return 1

    _save_chat_id(target)
    print(f"\nSaved: telegram.chat_id = {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
