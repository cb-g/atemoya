"""ThetaTerminal, self-contained (36): start, stop and status of ThetaData's terminal from
this repository with the user's own credentials.

    uv run python/theta_terminal.py start|stop|status

The jar lives in tools/thetaterminal/ (gitignored entirely, with its config, its logs and
the momentary creds file); the user downloads ThetaTerminalv3.jar there from ThetaData.
start reads THETADATA_EMAIL and THETADATA_PASSWORD from the environment (direnv loads
.env), writes them to tools/thetaterminal/creds.txt with mode 600, launches the jar with
--creds-file in a clean environment that does not carry the two variables, waits for the
terminal's port, and removes the creds file whether or not the terminal came up. Nothing
here prints a credential or the environment, on any path.

stop's job (56) is that the port ends closed, so it signals whatever holds the port, not
whatever the pid file names: the jar launches a second JVM that outlives its launcher, so
killing the recorded pid leaves the terminal serving. The pid file is used when it is
there and the port is the fallback when it is not, both sets are signalled, and the wait
is on the port closing rather than on a pid disappearing. The exit code says whether the
port is closed at the end."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
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
