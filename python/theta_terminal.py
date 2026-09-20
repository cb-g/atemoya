"""ThetaTerminal, self-contained (36): start, stop and status of ThetaData's terminal from
this repository with the user's own credentials.

    uv run python/theta_terminal.py start|stop|status

The jar lives in tools/thetaterminal/ (gitignored entirely, with its config, its logs and
the momentary creds file); the user downloads ThetaTerminalv3.jar there from ThetaData.
start reads THETADATA_EMAIL and THETADATA_PASSWORD from the environment (direnv loads
.env), writes them to tools/thetaterminal/creds.txt with mode 600, launches the jar with
--creds-file in a clean environment that does not carry the two variables, waits for the
terminal's port, and removes the creds file whether or not the terminal came up. Nothing
here prints a credential or the environment, on any path."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "thetaterminal"
JAR_NAME = "ThetaTerminalv3.jar"
PORT = 25503
HOST = "127.0.0.1"
VARS = ("THETADATA_EMAIL", "THETADATA_PASSWORD")  # the two names the environment carries


def credentials(env: Mapping[str, str]) -> tuple[str, str]:
    """The two values from the environment; the error names the variables, never a value."""
    email = env.get(VARS[0], "").strip()
    password = env.get(VARS[1], "").strip()
    if not email or not password:
        raise SystemExit(f"{VARS[0]} and {VARS[1]} must be set in the environment (put them in .env; direnv loads it)")
    return email, password


def write_creds(path: Path, email: str, password: str) -> None:
    """The two-line creds file the terminal reads, created with mode 600 and never wider."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, f"{email}\n{password}\n".encode())
    finally:
        os.close(fd)
    os.chmod(path, 0o600)


def port_open(host: str = HOST, port: int = PORT, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def clean_env(env: Mapping[str, str]) -> dict[str, str]:
    """The launch environment: everything but the credentials, which travel by file only."""
    return {k: v for k, v in env.items() if k not in VARS}


def start(env: Mapping[str, str], *, tools: Path = TOOLS, java: str = "java", port: int = PORT, wait: float = 120.0) -> int:
    jar = tools / JAR_NAME
    if port_open(port=port):
        print(f"ThetaTerminal already answering on {HOST}:{port}")
        return 0
    if not jar.exists():
        print(f"{jar} not found: download {JAR_NAME} from ThetaData into {tools}/ (it is gitignored)", file=sys.stderr)
        return 1
    email, password = credentials(env)
    creds = tools / "creds.txt"
    log = tools / "terminal.log"
    pid_file = tools / "terminal.pid"
    write_creds(creds, email, password)
    try:
        with open(log, "ab") as out:
            proc = subprocess.Popen(
                [java, "-jar", str(jar), "--creds-file", str(creds)],
                cwd=tools,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=clean_env(env),
                start_new_session=True,
            )
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                print(f"ThetaTerminal exited with code {proc.returncode} before answering on port {port}; see {log}", file=sys.stderr)
                return 1
            if port_open(port=port):
                pid_file.write_text(f"{proc.pid}\n")
                print(f"ThetaTerminal up on {HOST}:{port} (pid {proc.pid}); log at {log}")
                return 0
            time.sleep(1.0)
        print(f"ThetaTerminal did not answer on port {port} within {wait:.0f}s; it is still running (pid {proc.pid}); see {log}", file=sys.stderr)
        pid_file.write_text(f"{proc.pid}\n")
        return 1
    finally:
        creds.unlink(missing_ok=True)


def stop(*, tools: Path = TOOLS) -> int:
    pid_file = tools / "terminal.pid"
    if not pid_file.exists():
        print("no terminal.pid: nothing started from here" + (" (something else answers on the port)" if port_open() else ""))
        return 1
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"pid {pid} is not running; removing terminal.pid")
        pid_file.unlink()
        return 0
    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(1.0)
    pid_file.unlink(missing_ok=True)
    print(f"sent SIGTERM to pid {pid}")
    return 0


def status(*, tools: Path = TOOLS, port: int = PORT) -> int:
    pid_file = tools / "terminal.pid"
    pid = pid_file.read_text().strip() if pid_file.exists() else None
    up = port_open(port=port)
    print(f"port {HOST}:{port}: {'answering' if up else 'closed'}; pid file: {pid or 'none'}; jar: {'present' if (tools / JAR_NAME).exists() else 'missing'}")
    return 0 if up else 1


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("start", "stop", "status"):
        print("usage: uv run python/theta_terminal.py start|stop|status", file=sys.stderr)
        return 2
    if argv[0] == "start":
        return start(os.environ)
    if argv[0] == "stop":
        return stop()
    return status()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
