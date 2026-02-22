#!/usr/bin/env python3
"""
ntfy.sh notification client for watchlist alerts.

ntfy.sh is a simple pub-sub notification service:
- Free, no account required
- Works on iOS, Android, Desktop, CLI
- Self-hostable for privacy

Usage:
    python notify.py --alerts analysis.json --topic my-alerts
    python notify.py --alerts analysis.json --topic my-alerts --dry-run

Environment variables:
    NTFY_TOPIC: Default topic name
    NTFY_SERVER: Server URL (default: https://ntfy.sh)
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path


def send_notification(
    topic: str,
    message: str,
    title: str = None,
    priority: int = 3,
    tags: list[str] = None,
    server: str = "https://ntfy.sh",
) -> bool:
    """
    Send a notification via ntfy.sh.

    Args:
        topic: Topic name (like a channel)
        message: Notification body
        title: Optional title
        priority: 1 (min) to 5 (max), default 3
        tags: Optional emoji tags (e.g., ["warning", "money_bag"])
        server: ntfy server URL

    Returns:
        True if sent successfully
    """
    url = f"{server.rstrip('/')}/{topic}"
    data = message.encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Priority", str(priority))

    if title:
        req.add_header("Title", title)
    if tags:
        req.add_header("Tags", ",".join(tags))

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            if 200 <= resp.status < 300:
                return True
            print(f"Unexpected status {resp.status}: {body}", file=sys.stderr)
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {e.reason}: {body}", file=sys.stderr)
        return False
    except (urllib.error.URLError, OSError) as e:
        print(f"Network error: {e}", file=sys.stderr)
        return False


def load_alerts(filepath: Path) -> list[dict]:
    """Load alerts from analysis JSON file."""
    if not filepath.exists():
        return []

    with open(filepath) as f:
        data = json.load(f)

    return data.get("alerts", [])


# Map OCaml priority strings to ntfy priority levels
PRIORITY_MAP = {
    "URGENT": 5,  # max — persistent, sound
    "HIGH": 4,    # high — sound
    "NORMAL": 3,  # default
    "INFO": 2,    # low — no sound
}

# Map alert message patterns to ntfy emoji tags
ALERT_TAGS = {
    "STOP LOSS": ["rotating_light", "red_circle"],
    "stop loss": ["warning", "red_circle"],
    "sell target": ["chart_with_upwards_trend", "money_bag"],
    "buy target": ["chart_with_downwards_trend", "green_circle"],
    "Up ": ["arrow_up", "green_circle"],
    "Down ": ["arrow_down", "red_circle"],
}


def format_alert_message(alert: dict) -> tuple[str, str, int, list[str]]:
    """
    Format an alert into notification components.

    Expects alert format from OCaml save_analysis:
        {"ticker": "PLTR", "priority": "HIGH", "message": "Hit sell target! ..."}

    Returns:
        (message, title, priority, tags)
    """
    ticker = alert.get("ticker", "???")
    priority_str = alert.get("priority", "NORMAL")
    message = alert.get("message", "Alert triggered")

    priority = PRIORITY_MAP.get(priority_str, 3)

    tags = []
    for pattern, tag_list in ALERT_TAGS.items():
        if pattern in message:
            tags = tag_list
            break

    title = f"{ticker}: {priority_str}"

    return message, title, priority, tags


def main():
    parser = argparse.ArgumentParser(description="Send watchlist alerts via ntfy.sh")
    parser.add_argument("--alerts", required=True, help="Analysis JSON file with alerts")
    parser.add_argument(
        "--topic", default=os.environ.get("NTFY_TOPIC", ""), help="ntfy topic"
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("NTFY_SERVER", "https://ntfy.sh"),
        help="ntfy server",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print alerts without sending"
    )

    args = parser.parse_args()

    if not args.topic:
        print(
            "Error: --topic required or set NTFY_TOPIC environment variable",
            file=sys.stderr,
        )
        sys.exit(1)

    alerts = load_alerts(Path(args.alerts))

    if not alerts:
        print("No alerts to send")
        return

    print(f"Sending {len(alerts)} alert(s) to {args.server}/{args.topic}")

    sent = 0
    failed = 0
    for alert in alerts:
        message, title, priority, tags = format_alert_message(alert)

        if args.dry_run:
            tag_str = f" [{','.join(tags)}]" if tags else ""
            print(f"  [DRY RUN] (p={priority}) {title}: {message}{tag_str}")
        else:
            success = send_notification(
                topic=args.topic,
                message=message,
                title=title,
                priority=priority,
                tags=tags,
                server=args.server,
            )
            if success:
                sent += 1
                print(f"  [sent] {title}: {message}")
            else:
                failed += 1
                print(f"  [FAILED] {title}: {message}")

    if not args.dry_run:
        print(f"\n{sent} sent, {failed} failed")


if __name__ == "__main__":
    main()
