"""The terminal script (36) never emits a credential: on a fake environment with a fake
java, the creds file exists with mode 600 exactly while the jar runs and is gone after,
and nothing the script prints on any path contains either value."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

import theta_terminal as tt

FAKE_EMAIL = "someone@example.org"
FAKE_PASSWORD = "not-a-secret"


def test_missing_credentials_name_the_variables_only() -> None:
    with pytest.raises(SystemExit) as e:
        tt.credentials({"THETADATA_EMAIL": FAKE_EMAIL})
    assert "THETADATA_PASSWORD" in str(e.value) and FAKE_EMAIL not in str(e.value)


def test_creds_file_is_two_lines_with_mode_600(tmp_path: Path) -> None:
    path = tmp_path / "creds.txt"
    tt.write_creds(path, FAKE_EMAIL, FAKE_PASSWORD)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == f"{FAKE_EMAIL}\n{FAKE_PASSWORD}\n"


def test_start_never_emits_the_credential(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    tools = tmp_path / "thetaterminal"
    tools.mkdir()
    (tools / tt.JAR_NAME).write_bytes(b"not a jar")
    # A stand-in for java: records the creds file's mode and line count, then fails.
    fake_java = tmp_path / "java"
    fake_java.write_text("#!/bin/sh\nstat -c %a \"$4\" > \"$(dirname \"$4\")/mode.txt\"\nwc -l < \"$4\" > \"$(dirname \"$4\")/lines.txt\"\nenv > \"$(dirname \"$4\")/env.txt\"\nexit 3\n")
    fake_java.chmod(0o755)
    env = {"PATH": os.environ.get("PATH", ""), "THETADATA_EMAIL": FAKE_EMAIL, "THETADATA_PASSWORD": FAKE_PASSWORD}
    rc = tt.start(env, tools=tools, java=str(fake_java), port=1, wait=5.0)
    out, err = capsys.readouterr()
    assert rc == 1 and "exited with code 3" in err
    for text in (out, err, (tools / "terminal.log").read_text(), (tools / "env.txt").read_text()):
        assert FAKE_EMAIL not in text and FAKE_PASSWORD not in text
    assert (tools / "mode.txt").read_text().strip() == "600"
    assert (tools / "lines.txt").read_text().strip() == "2"
    assert not (tools / "creds.txt").exists()


def test_start_without_the_jar_says_where_to_put_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = tt.start({"THETADATA_EMAIL": FAKE_EMAIL, "THETADATA_PASSWORD": FAKE_PASSWORD}, tools=tmp_path, port=1, wait=1.0)
    _, err = capsys.readouterr()
    assert rc == 1 and tt.JAR_NAME in err and FAKE_EMAIL not in err and FAKE_PASSWORD not in err
    assert not (tmp_path / "creds.txt").exists()


def fake_proc(tmp_path: Path, port: int, pids_and_inodes: list[tuple[int, str]], *, listening: bool = True) -> Path:
    """A /proc just wide enough for listening_pids: one net/tcp row per socket and one
    process directory per pid whose descriptor points at that socket's inode."""
    proc = tmp_path / "proc"
    (proc / "net").mkdir(parents=True)
    rows = ["  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode"]
    for i, (_, inode) in enumerate(pids_and_inodes):
        state = "0A" if listening else "01"
        rows.append(f"  {i}: 0100007F:{port:04X} 00000000:0000 {state} 00000000:00000000 00:00000000 00000000  1000        0 {inode} 1 0000 100 0")
    (proc / "net" / "tcp").write_text("\n".join(rows) + "\n")
    (proc / "net" / "tcp6").write_text(rows[0] + "\n")
    for pid, inode in pids_and_inodes:
        fds = proc / str(pid) / "fd"
        fds.mkdir(parents=True)
        os.symlink(f"socket:[{inode}]", fds / "3")
    (proc / "not-a-pid").mkdir()
    return proc


def test_listening_pids_finds_the_holder_through_proc(tmp_path: Path) -> None:
    """(56) The port's listening socket by inode, then the process holding it."""
    proc = fake_proc(tmp_path, tt.PORT, [(4242, "99001"), (4243, "99002")])
    assert tt.listening_pids(tt.PORT, proc=proc) == [4242, 4243]
    assert tt.listening_pids(tt.PORT + 1, proc=proc) == []  # another port, no holder
    # a socket that is not LISTEN is not the terminal's
    other = fake_proc(tmp_path / "established", tt.PORT, [(4242, "99001")], listening=False)
    assert tt.listening_pids(tt.PORT, proc=other) == []
    # an unreadable or absent /proc is an empty answer, never a guess
    assert tt.listening_pids(tt.PORT, proc=tmp_path / "nowhere") == []


def test_stop_falls_back_to_the_port_when_there_is_no_pid_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(56) The jar outlives its launcher, so with no pid file the port names the target;
    stop signals it and returns only once the port is closed."""
    tools = tmp_path / "tools"
    tools.mkdir()
    proc = fake_proc(tmp_path, tt.PORT, [(4242, "99001")])
    sent: list[tuple[int, int]] = []
    states = iter([True, False])  # answering, then closed after the signal

    def kill(pid: int, sig: int) -> None:
        sent.append((pid, sig))

    def is_open() -> bool:
        return next(states, False)

    assert tt.stop(tools=tools, wait=5.0, proc=proc, kill=kill, is_open=is_open) == 0
    assert sent == [(4242, tt.signal.SIGTERM)]
    out = capsys.readouterr().out
    assert "4242" in out and "found through the port" in out and "closed" in out


def test_stop_signals_the_pid_file_and_the_port_holder_together(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(56) The launcher the pid file names and the JVM holding the port are two processes;
    both are signalled, and the pid file goes only once the port is closed."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "terminal.pid").write_text("4200\n")
    proc = fake_proc(tmp_path, tt.PORT, [(4242, "99001")])
    sent: list[int] = []
    states = iter([True, False])
    assert tt.stop(tools=tools, wait=5.0, proc=proc,
                   kill=lambda pid, sig: sent.append(pid), is_open=lambda: next(states, False)) == 0
    assert sent == [4200, 4242]
    assert not (tools / "terminal.pid").exists()
    assert "found through the pid file" in capsys.readouterr().out


def test_stop_reports_a_survivor_and_leaves_the_pid_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(56) A port still answering at the deadline is a failure, said so, and the pid file
    stays: the caller has not got what it asked for."""
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "terminal.pid").write_text("4200\n")
    proc = fake_proc(tmp_path, tt.PORT, [(4242, "99001")])
    assert tt.stop(tools=tools, wait=0.0, proc=proc, kill=lambda pid, sig: None, is_open=lambda: True) == 1
    assert (tools / "terminal.pid").exists()
    assert "still answering" in capsys.readouterr().err


def test_stop_on_a_terminal_that_is_not_running(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(56) Nothing to signal and a closed port is success: the caller wanted it stopped."""
    tools = tmp_path / "tools"
    tools.mkdir()
    proc = fake_proc(tmp_path, tt.PORT, [])
    assert tt.stop(tools=tools, proc=proc, kill=lambda pid, sig: None, is_open=lambda: False) == 0
    assert "not running" in capsys.readouterr().out
    # but a port that answers with no findable holder is not success
    assert tt.stop(tools=tools, proc=proc, kill=lambda pid, sig: None, is_open=lambda: True) == 1
    assert "no process holding it could be found" in capsys.readouterr().err
