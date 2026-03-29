"""
Shared ntfy.sh notification client.

Sends notifications via ntfy.sh, reading NTFY_TOPIC from .env at project root.
Used by skew scanner, variance swaps, pre-earnings straddle, and watchlist modules.

Usage:
    from lib.python.notify import send_notification, get_topic

    topic = get_topic()
    send_notification(topic, message="Trade idea", title="Skew Scanner: 5 ideas")
"""

import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_env(env_path: Path = None) -> dict[str, str]:
    """Load .env file as key=value pairs."""
    if env_path is None:
        env_path = PROJECT_ROOT / ".env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env[key.strip()] = val.strip().strip('"').strip("'")
    return env


def get_topic() -> str:
    """Resolve NTFY_TOPIC from env var or .env file."""
    topic = os.environ.get("NTFY_TOPIC", "")
    if not topic:
        env = load_env()
        topic = env.get("NTFY_TOPIC", "")
    return topic


def get_server() -> str:
    """Resolve NTFY_SERVER from env var or .env file."""
    server = os.environ.get("NTFY_SERVER", "")
    if not server:
        env = load_env()
        server = env.get("NTFY_SERVER", "https://ntfy.sh")
    return server


def send_notification(
    topic: str,
    message: str,
    title: str = None,
    priority: int = 3,
    tags: list[str] = None,
    server: str = None,
) -> bool:
    """
    Send a notification via ntfy.sh.

    Args:
        topic: Topic name (the secret)
        message: Notification body
        title: Optional title
        priority: 1 (min) to 5 (max), default 3
        tags: Optional emoji tags
        server: ntfy server URL (default from env)

    Returns:
        True if sent successfully
    """
    if server is None:
        server = get_server()

    # ntfy.sh message body limit is 4096 bytes. Truncate if needed.
    MAX_BYTES = 4096
    encoded = message.encode("utf-8")
    if len(encoded) > MAX_BYTES:
        lines = message.split("\n")
        truncated = []
        size = 0
        for line in lines:
            line_size = len(line.encode("utf-8")) + 1  # +1 for newline
            if size + line_size > MAX_BYTES - 40:  # reserve space for footer
                break
            truncated.append(line)
            size += line_size
        remaining = len(lines) - len(truncated)
        truncated.append(f"... and {remaining} more signals")
        message = "\n".join(truncated)

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
            return 200 <= resp.status < 300
    except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
        print(f"Notification error: {e}", file=sys.stderr)
        return False
