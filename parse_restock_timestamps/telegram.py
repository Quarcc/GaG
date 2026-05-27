import requests
from config import BOT_TOKEN, CHAT_IDS


def send_telegram(message: str, chat_id: str = None):
    """Send to a specific chat_id, or broadcast to all CHAT_IDS."""
    targets = [chat_id] if chat_id else CHAT_IDS
    for cid in targets:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": cid, "text": message, "parse_mode": "HTML"},
                timeout=10
            ).raise_for_status()
        except Exception as e:
            print(f"  [Telegram error] {e}")


_last_update_id: int = 0


def get_updates() -> list[dict]:
    """Long-poll Telegram for new incoming messages/commands."""
    global _last_update_id
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 5},
            timeout=10
        )
        r.raise_for_status()
        updates = r.json().get("result", [])
        if updates:
            _last_update_id = updates[-1]["update_id"]
        return updates
    except Exception as e:
        print(f"  [getUpdates error] {e}")
        return []