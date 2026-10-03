"""fetch_all's guard on data/financials: a real directory there stops the run."""

from pathlib import Path

import pytest

import fetch_all


def test_a_real_directory_at_the_latest_path_is_refused_and_never_replaced(tmp_path: Path) -> None:
    latest = tmp_path / "financials"
    assert fetch_all.stale_latest(latest) is None
    latest.mkdir()
    (latest / "OLD.json").write_text("{}")
    reason = fetch_all.stale_latest(latest)
    assert reason is not None and "real directory" in reason
    with pytest.raises(FileExistsError):
        fetch_all.point_latest(tmp_path / "snapshots" / "new", latest)
    assert (latest / "OLD.json").exists()


def test_a_symlink_is_repointed_and_an_absent_path_is_created(tmp_path: Path) -> None:
    latest = tmp_path / "financials"
    first, second = tmp_path / "snapshots" / "a", tmp_path / "snapshots" / "b"
    first.mkdir(parents=True)
    second.mkdir()
    fetch_all.point_latest(first, latest)
    assert latest.is_symlink() and latest.resolve() == first and fetch_all.stale_latest(latest) is None
    fetch_all.point_latest(second, latest)
    assert latest.resolve() == second


def test_main_stops_before_any_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    latest = tmp_path / "financials"
    latest.mkdir()
    universe = tmp_path / "universe.json"
    universe.write_text((Path(__file__).resolve().parent.parent / "reference" / "universe.json").read_text())
    monkeypatch.setattr(fetch_all, "LATEST", latest)

    def no_fetch(argv: list[str]) -> int:
        raise AssertionError("fetched")

    monkeypatch.setattr(fetch_all.fetch, "main", no_fetch)
    assert fetch_all.main(["--universe", str(universe)]) == 2
    assert "real directory" in capsys.readouterr().err
