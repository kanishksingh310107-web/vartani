from pathlib import Path
import socket

import pytest

from launcher import (
    ProfilePaths,
    SetupError,
    _choose_port,
    copy_existing_profile,
    ensure_bundle,
    ensure_profile,
    resolve_profile_paths,
)


def test_packaged_profile_uses_windows_user_data_not_install_dir(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path / "Local")}
    paths = resolve_profile_paths(env, frozen=True, script_root=tmp_path / "install")
    assert paths.home == tmp_path / "Local" / "Vartani"
    assert paths.data == paths.home / "data"
    assert paths.logs == paths.home / "logs"


def test_profile_setup_is_repeatable_and_preserves_saved_settings(tmp_path):
    paths = ProfilePaths(tmp_path / "profile", tmp_path / "profile" / "data", tmp_path / "profile" / "logs")
    ensure_profile(paths)
    settings = paths.data / "user" / "models.json"
    settings.write_text('{"models":["kept"]}', encoding="utf-8")
    ensure_profile(paths)
    assert settings.read_text(encoding="utf-8") == '{"models":["kept"]}'
    assert (paths.data / "runs").is_dir()


def test_storage_error_is_actionable_and_retryable(tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x", encoding="utf-8")
    paths = ProfilePaths(blocker, blocker / "data", blocker / "logs")
    with pytest.raises(SetupError, match="writable VARTANI_HOME"):
        ensure_profile(paths)
    blocker.unlink()
    ensure_profile(paths)
    assert paths.data.is_dir()


def test_import_copies_old_profile_without_overwriting_or_deleting_source(tmp_path):
    source = tmp_path / "old" / "data"
    target = tmp_path / "profile" / "data"
    (source / "user").mkdir(parents=True)
    (source / "runs" / "run1").mkdir(parents=True)
    (source / "user" / "models.json").write_text("old settings", encoding="utf-8")
    (source / "runs" / "run1" / "meta.json").write_text("old run", encoding="utf-8")
    (target / "user").mkdir(parents=True)
    (target / "user" / "models.json").write_text("newer settings", encoding="utf-8")

    copied, skipped = copy_existing_profile(source, target)
    assert (copied, skipped) == (1, 1)
    assert (target / "user" / "models.json").read_text(encoding="utf-8") == "newer settings"
    assert (target / "runs" / "run1" / "meta.json").read_text(encoding="utf-8") == "old run"
    assert (source / "user" / "models.json").read_text(encoding="utf-8") == "old settings"
    assert copy_existing_profile(source, target) == (0, 2)


def test_missing_bundle_reports_reextract_instructions(tmp_path):
    with pytest.raises(SetupError, match="Re-extract the full Windows package"):
        ensure_bundle(tmp_path)


def test_busy_default_port_falls_back_but_explicit_port_is_not_changed():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        busy = sock.getsockname()[1]
        assert _choose_port("127.0.0.1", busy, explicit=False) != busy
        with pytest.raises(SetupError, match="already using that port"):
            _choose_port("127.0.0.1", busy, explicit=True)
