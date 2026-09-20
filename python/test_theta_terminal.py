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
