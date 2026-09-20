"""The pre-commit hook's name-specific rules (36): a ThetaData login, a FRED key with any
value, or an SEC identity that is not the example.com placeholder is refused in any file,
.env.example included; the empty placeholders commit."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-commit"


def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_bytes(HOOK.read_bytes())
    (hooks / "pre-commit").chmod(0o755)
    for k, v in (("user.email", "t@example.com"), ("user.name", "t"), ("core.hooksPath", "hooks"), ("commit.gpgsign", "false")):
        subprocess.run(["git", "-C", str(tmp_path), "config", k, v], check=True)
    return tmp_path


def commit(path: Path, name: str, content: str) -> subprocess.CompletedProcess[str]:
    (path / name).write_text(content)
    subprocess.run(["git", "-C", str(path), "add", name], check=True)
    return subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", "x"], capture_output=True, text=True)


# Built by concatenation so this file never carries an assignment the hook would refuse.
CASES = [
    ("THETADATA_" + "EMAIL=" + "someone@example.org", "named credential"),
    ("THETADATA_" + "PASSWORD=" + "short", "named credential"),
    ("FRED_API_" + "KEY=" + "abc123", "named credential"),
    ("SEC_EDGAR_" + "IDENTITY=" + '"A Person a.person@corp.net"', "not the example.com placeholder"),
]


@pytest.mark.parametrize(("line", "message"), CASES)
def test_named_rules_refuse(tmp_path: Path, line: str, message: str) -> None:
    r = commit(repo(tmp_path), "notes.md", f"# notes\n{line}\n")
    assert r.returncode != 0 and message in r.stderr


def test_placeholders_commit(tmp_path: Path) -> None:
    text = (ROOT / ".env.example").read_text()
    r = commit(repo(tmp_path), ".env.example", text)
    assert r.returncode == 0, r.stderr
