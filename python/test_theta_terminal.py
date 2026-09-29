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


def test_missing_credentials_name_the_variables_only(tmp_path: Path) -> None:
    # dotenv points at nothing: the test never reads the operator's own env file
    with pytest.raises(SystemExit) as e:
        tt.credentials({"THETADATA_EMAIL": FAKE_EMAIL}, dotenv=tmp_path / "absent")
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


def test_start_without_the_jar_and_without_a_download_writes_no_creds_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(71) The jar is fetched before the credentials step, so a download that fails leaves
    no creds file behind and names the jar, never a value."""

    def failing(url: str) -> list[bytes]:
        raise OSError("no route")

    with pytest.raises(SystemExit) as e:
        tt.start({"THETADATA_EMAIL": FAKE_EMAIL, "THETADATA_PASSWORD": FAKE_PASSWORD}, tools=tmp_path, port=1, wait=1.0, fetch=failing)
    out, _ = capsys.readouterr()
    assert tt.JAR_NAME in str(e.value) and "download failed" in str(e.value)
    for text in (str(e.value), out):
        assert FAKE_EMAIL not in text and FAKE_PASSWORD not in text
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


# --- (71) the jar fetched on first start, and the env-file fallback for the login ------------


def jar_bytes(n: int = tt.JAR_MIN_BYTES) -> bytes:
    """A stand-in for a real jar: the zip magic and enough bytes to pass the size check."""
    return tt.ZIP_MAGIC + b"\0" * (n - len(tt.ZIP_MAGIC))


def fake_java(tmp_path: Path) -> Path:
    """A stand-in for java that records the creds file's mode and line count, then fails."""
    java = tmp_path / "java"
    java.write_text("#!/bin/sh\nstat -c %a \"$4\" > \"$(dirname \"$4\")/mode.txt\"\nwc -l < \"$4\" > \"$(dirname \"$4\")/lines.txt\"\nexit 3\n")
    java.chmod(0o755)
    return java


def test_start_downloads_a_missing_jar_before_the_credentials_step(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(71) A fresh clone has no jar: start fetches it, checks it, renames it into place and
    prints its size and sha256, and does so before it reads a credential, so a missing login
    is reported against a jar that is already there."""
    tools = tmp_path / "thetaterminal"
    asked: list[str] = []

    def fetch(url: str) -> list[bytes]:
        asked.append(url)
        return [jar_bytes()[:1000], jar_bytes()[1000:]]

    with pytest.raises(SystemExit) as e:  # no login anywhere: the credentials step refuses
        tt.start({}, tools=tools, port=1, wait=1.0, dotenv=tmp_path / "absent", fetch=fetch)
    assert "THETADATA_EMAIL" in str(e.value)
    assert asked == [tt.JAR_URL]
    assert (tools / tt.JAR_NAME).read_bytes() == jar_bytes()
    assert not list(tools.glob("*.part")) and not list(tools.glob(".*"))
    out = capsys.readouterr().out
    assert f"{tt.JAR_MIN_BYTES} bytes" in out and "sha256 " in out


def test_a_corrupt_download_is_removed_and_reported(tmp_path: Path) -> None:
    """(71) An error page, or a truncated jar, never lands as the jar: the partial file is
    removed and the exit is non-zero with the reason."""
    tools = tmp_path / "thetaterminal"
    with pytest.raises(SystemExit, match="not a jar") as e:
        tt.download_jar(tools / tt.JAR_NAME, fetch=lambda url: [b"<html>not found</html>"])
    assert "no zip magic" in str(e.value)
    assert not (tools / tt.JAR_NAME).exists() and not list(tools.iterdir())
    with pytest.raises(SystemExit, match="not a jar"):  # the magic alone is not enough
        tt.download_jar(tools / tt.JAR_NAME, fetch=lambda url: [tt.ZIP_MAGIC + b"\0" * 10])
    assert not list(tools.iterdir())

    def failing(url: str) -> list[bytes]:
        raise OSError("connection reset")

    with pytest.raises(SystemExit, match="download failed: OSError"):
        tt.download_jar(tools / tt.JAR_NAME, fetch=failing)
    assert not list(tools.iterdir())


def test_an_existing_jar_is_never_replaced_without_the_flag(tmp_path: Path) -> None:
    """(71) A jar already there is left alone; --update-jar is the one way to replace it."""
    tools = tmp_path / "thetaterminal"
    tools.mkdir()
    (tools / tt.JAR_NAME).write_bytes(b"the jar that was there")
    env = {"PATH": os.environ.get("PATH", ""), "THETADATA_EMAIL": FAKE_EMAIL, "THETADATA_PASSWORD": FAKE_PASSWORD}

    def refuse(url: str) -> list[bytes]:
        raise AssertionError("the download was asked for")

    assert tt.start(env, tools=tools, java=str(fake_java(tmp_path)), port=1, wait=5.0, fetch=refuse) == 1
    assert (tools / tt.JAR_NAME).read_bytes() == b"the jar that was there"
    assert tt.start(env, tools=tools, java=str(fake_java(tmp_path)), port=1, wait=5.0,
                    update_jar=True, fetch=lambda url: [jar_bytes()]) == 1
    assert (tools / tt.JAR_NAME).read_bytes() == jar_bytes()


def test_credentials_fall_back_to_the_env_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """(71) Variables absent from the environment but present in the env file at the repo
    root: start proceeds, the values travel by the mode-600 creds file only, and nothing
    printed carries either."""
    dotenv = tmp_path / "env-file"
    dotenv.write_text(f"SOME_OTHER_NAME=ignored\n{tt.VARS[0]}={FAKE_EMAIL}\n{tt.VARS[1]}='{FAKE_PASSWORD}'\n")
    assert tt.credentials({}, dotenv=dotenv) == (FAKE_EMAIL, FAKE_PASSWORD)
    # the environment wins where it is set; the file fills only what it lacks
    assert tt.credentials({tt.VARS[0]: "other@example.org"}, dotenv=dotenv) == ("other@example.org", FAKE_PASSWORD)
    tools = tmp_path / "thetaterminal"
    tools.mkdir()
    (tools / tt.JAR_NAME).write_bytes(b"not a jar")
    rc = tt.start({"PATH": os.environ.get("PATH", "")}, tools=tools, java=str(fake_java(tmp_path)), port=1, wait=5.0, dotenv=dotenv)
    out, err = capsys.readouterr()
    assert rc == 1 and "exited with code 3" in err
    assert (tools / "lines.txt").read_text().strip() == "2" and (tools / "mode.txt").read_text().strip() == "600"
    for text in (out, err, (tools / "terminal.log").read_text()):
        assert FAKE_EMAIL not in text and FAKE_PASSWORD not in text
    assert not (tools / "creds.txt").exists()
    # absent from both: the error names the variables and no value
    with pytest.raises(SystemExit) as e:
        tt.credentials({}, dotenv=tmp_path / "absent")
    assert tt.VARS[0] in str(e.value) and tt.VARS[1] in str(e.value) and FAKE_EMAIL not in str(e.value)


def test_status_says_the_jar_is_missing_and_that_start_will_download_it(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert tt.status(tools=tmp_path, port=1) == 1
    assert "jar: missing (start will download it)" in capsys.readouterr().out
    (tmp_path / tt.JAR_NAME).write_bytes(b"x" * 7)
    tt.status(tools=tmp_path, port=1)
    assert "jar: present (7 bytes)" in capsys.readouterr().out


def test_main_takes_update_jar_on_start_only(capsys: pytest.CaptureFixture[str]) -> None:
    assert tt.main([]) == 2 and tt.main(["stop", "--update-jar"]) == 2 and tt.main(["start", "--bogus"]) == 2
    assert "--update-jar" in capsys.readouterr().err
