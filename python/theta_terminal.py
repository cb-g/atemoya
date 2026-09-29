"""ThetaTerminal, self-contained (36): start, stop and status of ThetaData's terminal from
this repository with the user's own credentials.

    uv run python/theta_terminal.py start|stop|status

The jar lives in tools/thetaterminal/ (gitignored entirely, with its config, its logs and
the momentary creds file). A fresh clone has no jar, so start fetches ThetaTerminalv3.jar
(71) from ThetaData's open download, which needs no login, before it touches a credential:
streamed to a temporary file beside its destination, checked to be a real jar by the zip
magic and a non-trivial size, renamed into place atomically, its size and sha256 printed;
a failure removes the partial file and exits non-zero naming why. A jar already there is
never replaced unless `start --update-jar` says so, and status says the jar is missing and
that start will download it. start then reads THETADATA_EMAIL and THETADATA_PASSWORD from
the environment first and, for whichever the environment lacks, from .env at the repo root
(the same reading refresh_rates.py and fetch_sec.py do for their keys), writes them to
tools/thetaterminal/creds.txt with mode 600, launches the jar with --creds-file in a clean
environment that does not carry the two variables, waits for the terminal's port, and
removes the creds file whether or not the terminal came up. Nothing here prints a
credential or the environment, on any path.

stop's job (56) is that the port ends closed, so it signals whatever holds the port, not
whatever the pid file names: the jar launches a second JVM that outlives its launcher, so
killing the recorded pid leaves the terminal serving. The pid file is used when it is
there and the port is the fallback when it is not, both sets are signalled, and the wait
is on the port closing rather than on a pid disappearing. The exit code says whether the
port is closed at the end."""

from __future__ import annotations

import hashlib
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools" / "thetaterminal"
JAR_NAME = "ThetaTerminalv3.jar"
JAR_URL = "https://downloads.thetadata.us/ThetaTerminalv3.jar"  # published openly by ThetaData; no login
JAR_MIN_BYTES = 1_000_000  # the terminal is tens of megabytes; anything smaller is an error page, not a jar
ZIP_MAGIC = b"PK\x03\x04"  # a jar is a zip archive and begins with the local-file-header signature
DOTENV_PATH = ROOT / ".env"
PORT = 25503
HOST = "127.0.0.1"
VARS = ("THETADATA_EMAIL", "THETADATA_PASSWORD")  # the two names the environment carries


def _dotenv_values(path: Path, names: tuple[str, ...]) -> dict[str, str]:
    """NAME=value lines from the env file at the repo root, for the names asked and no
    others: the same reading fetch_sec.identity and refresh_rates._api_key do for their
    keys. Quotes are stripped, nothing else is interpreted, and nothing is printed."""
    found: dict[str, str] = {}
    if not path.is_file():
        return found
    for line in path.read_text().splitlines():
        name, sep, value = line.strip().partition("=")
        if sep and name.strip() in names:
            found[name.strip()] = value.strip().strip("'\"")
    return found


def credentials(env: Mapping[str, str], *, dotenv: Path = DOTENV_PATH) -> tuple[str, str]:
    """The two values, from the environment first and from the env file for whichever the
    environment lacks; the error names the variables, never a value."""
    values = {name: env.get(name, "").strip() for name in VARS}
    missing = tuple(name for name in VARS if not values[name])
    if missing:
        for name, value in _dotenv_values(dotenv, missing).items():
            values[name] = value.strip()
    if not all(values[name] for name in VARS):
        raise SystemExit(f"{VARS[0]} and {VARS[1]} must be set in the environment or in .env at the repo root (see .env.example)")
    return values[VARS[0]], values[VARS[1]]


def _fetch_url(url: str) -> Iterator[bytes]:
    """The download, streamed in chunks; the one function here that touches the network."""
    request = urllib.request.Request(url, headers={"User-Agent": "atemoya theta_terminal"})
    with urllib.request.urlopen(request, timeout=120) as response:
        while chunk := response.read(1 << 20):
            yield chunk


def download_jar(jar: Path, *, url: str = JAR_URL, fetch: Callable[[str], Iterable[bytes]] = _fetch_url) -> None:
    """Fetch the terminal jar into place (71): streamed to a temporary file beside its
    destination, checked to be a real jar (the zip magic and a non-trivial size), then
    renamed into place atomically, so no reader ever sees a half-written jar. On any
    failure the partial file is removed and the process exits non-zero naming why. The
    size and sha256 of what was installed are printed so a reader can compare them with
    ThetaData's own."""
    jar.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{jar.name}.", suffix=".part", dir=jar.parent)
    partial = Path(name)
    digest = hashlib.sha256()
    size = 0
    try:
        print(f"fetching {jar.name} from {url}")
        with os.fdopen(fd, "wb") as out:
            for chunk in fetch(url):
                out.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        with open(partial, "rb") as head:
            magic = head.read(len(ZIP_MAGIC))
        if magic != ZIP_MAGIC or size < JAR_MIN_BYTES:
            shape = "zip magic present" if magic == ZIP_MAGIC else "no zip magic"
            raise SystemExit(f"{jar.name}: the download is not a jar ({size} bytes, {shape}); nothing installed, the partial file removed")
        os.replace(partial, jar)
    except SystemExit:
        partial.unlink(missing_ok=True)
        raise
    except Exception as e:
        partial.unlink(missing_ok=True)
        raise SystemExit(f"{jar.name}: download failed: {type(e).__name__}: {e}; nothing installed, the partial file removed") from e
    print(f"{jar.name}: {size} bytes, sha256 {digest.hexdigest()}")


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


def start(env: Mapping[str, str], *, tools: Path = TOOLS, java: str = "java", port: int = PORT, wait: float = 120.0,
          update_jar: bool = False, dotenv: Path = DOTENV_PATH,
          fetch: Callable[[str], Iterable[bytes]] = _fetch_url) -> int:
    jar = tools / JAR_NAME
    if port_open(port=port):
        note = "; stop it before updating the jar" if update_jar else ""
        print(f"ThetaTerminal already answering on {HOST}:{port}{note}")
        return 0
    if update_jar or not jar.exists():
        download_jar(jar, fetch=fetch)  # before the credentials step: no creds file exists yet
    email, password = credentials(env, dotenv=dotenv)
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


def listening_pids(port: int = PORT, *, proc: Path = Path("/proc")) -> list[int]:
    """Every pid holding a listening socket on [port], found through /proc: the listening
    sockets' inodes from net/tcp and net/tcp6, then the processes whose open descriptors
    point at one of them. A pid whose descriptors cannot be read is skipped, not guessed
    at; an unreadable /proc gives an empty list and the caller falls back to the pid file."""
    inodes: set[str] = set()
    for name in ("net/tcp", "net/tcp6"):
        try:
            lines = (proc / name).read_text().splitlines()[1:]
        except OSError:
            continue
        for line in lines:
            fields = line.split()
            if len(fields) < 10:
                continue
            local, state, inode = fields[1], fields[3], fields[9]
            if state != "0A":  # LISTEN
                continue
            _, _, hex_port = local.rpartition(":")
            try:
                if int(hex_port, 16) == port:
                    inodes.add(inode)
            except ValueError:
                continue
    if not inodes:
        return []
    wanted = {f"socket:[{i}]" for i in inodes}
    found: list[int] = []
    try:
        entries = list(proc.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            for fd in (entry / "fd").iterdir():
                if os.readlink(fd) in wanted:
                    found.append(int(entry.name))
                    break
        except OSError:
            continue  # not ours, or gone between the listing and the read
    return sorted(found)


def stop(*, tools: Path = TOOLS, port: int = PORT, wait: float = 30.0,
         proc: Path = Path("/proc"), kill: Callable[[int, int], None] = os.kill,
         is_open: Callable[[], bool] = port_open) -> int:
    """Stop the terminal: signal every process holding the port, and the pid file's process
    when it names one, then wait for the port to close. Success is the port being closed,
    so a terminal that was never running is success and a survivor is not."""
    pid_file = tools / "terminal.pid"
    targets: list[int] = []
    recorded: int | None = None
    if pid_file.exists():
        try:
            recorded = int(pid_file.read_text().strip())
            targets.append(recorded)
        except ValueError:
            print(f"{pid_file.name} does not name a pid; falling back to the port")
    holders = listening_pids(port, proc=proc)
    source = "the pid file" if recorded is not None else "the port"
    targets += [pid for pid in holders if pid not in targets]
    if not targets:
        if not is_open():
            print("terminal is not running")
            pid_file.unlink(missing_ok=True)
            return 0
        print(f"something answers on port {port} and no process holding it could be found; nothing was signalled", file=sys.stderr)
        return 1
    signalled: list[int] = []
    for pid in targets:
        try:
            kill(pid, signal.SIGTERM)
            signalled.append(pid)
        except ProcessLookupError:
            continue
        except PermissionError:
            print(f"pid {pid} is not ours to signal", file=sys.stderr)
    deadline = time.monotonic() + wait
    while is_open() and time.monotonic() < deadline:
        time.sleep(1.0)
        for pid in listening_pids(port, proc=proc):
            if pid not in signalled:
                try:
                    kill(pid, signal.SIGTERM)  # a survivor the first pass did not see
                    signalled.append(pid)
                except (ProcessLookupError, PermissionError):
                    pass
    if is_open():
        print(f"sent SIGTERM to {', '.join(str(p) for p in signalled) or 'nothing'}; port {port} is still answering after {wait:.0f}s", file=sys.stderr)
        return 1
    pid_file.unlink(missing_ok=True)
    named = ", ".join(str(p) for p in signalled) or "nothing"
    print(f"terminal stopped: sent SIGTERM to {named} (found through {source}); port {port} is closed")
    return 0


def status(*, tools: Path = TOOLS, port: int = PORT) -> int:
    pid_file = tools / "terminal.pid"
    pid = pid_file.read_text().strip() if pid_file.exists() else None
    up = port_open(port=port)
    jar = tools / JAR_NAME
    jar_state = f"present ({jar.stat().st_size} bytes)" if jar.exists() else "missing (start will download it)"
    print(f"port {HOST}:{port}: {'answering' if up else 'closed'}; pid file: {pid or 'none'}; jar: {jar_state}")
    return 0 if up else 1


USAGE = "usage: uv run python/theta_terminal.py start [--update-jar] | stop | status"


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("start", "stop", "status"):
        print(USAGE, file=sys.stderr)
        return 2
    flags = set(argv[1:])
    if flags - ({"--update-jar"} if argv[0] == "start" else set()):
        print(USAGE, file=sys.stderr)
        return 2
    if argv[0] == "start":
        return start(os.environ, update_jar="--update-jar" in flags)
    if argv[0] == "stop":
        return stop()
    return status()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
