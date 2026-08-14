import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import app


class UpdaterTests(unittest.TestCase):
    def setUp(self) -> None:
        app._RESTART_PENDING = False

    def tearDown(self) -> None:
        app._RESTART_PENDING = False

    def test_untracked_venv_does_not_dirty_tracked_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            repo = Path(raw_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Updater Test"], cwd=repo, check=True)
            (repo / "tracked.txt").write_text("tracked\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=repo, check=True)
            (repo / ".venv").mkdir()
            (repo / ".venv" / "pyvenv.cfg").write_text("home = test\n", encoding="utf-8")
            with mock.patch.object(app, "_repo_root", return_value=repo):
                self.assertTrue(app._tracked_worktree_is_clean())

    def test_tracked_edit_still_blocks_update(self) -> None:
        with tempfile.TemporaryDirectory() as raw_dir:
            repo = Path(raw_dir)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
            subprocess.run(["git", "config", "user.name", "Updater Test"], cwd=repo, check=True)
            tracked = repo / "tracked.txt"
            tracked.write_text("before\n", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-qm", "initial"], cwd=repo, check=True)
            tracked.write_text("after\n", encoding="utf-8")
            with mock.patch.object(app, "_repo_root", return_value=repo):
                self.assertFalse(app._tracked_worktree_is_clean())

    def test_windows_helper_failure_keeps_current_app_alive(self) -> None:
        with mock.patch.object(app, "_is_windows", return_value=True), mock.patch.object(
            app, "_start_windows_restart_helper", side_effect=RuntimeError("boom")
        ), mock.patch.object(app, "_append_update_log") as log_mock:
            self.assertFalse(app._schedule_self_restart())
        self.assertFalse(app._RESTART_PENDING)
        log_mock.assert_called_once()

    def test_windows_restart_defers_dependency_install(self) -> None:
        helper = mock.Mock()
        with mock.patch.object(app, "_is_windows", return_value=True), mock.patch.object(
            app, "_start_windows_restart_helper", return_value=helper
        ) as start_mock, mock.patch.object(app.threading, "Thread") as thread_mock:
            self.assertTrue(app._schedule_self_restart(install_deps_after_exit=True))
        start_mock.assert_called_once_with(install_deps_after_exit=True)
        thread_mock.assert_called_once()

    def test_windows_update_does_not_run_pip_inside_live_process(self) -> None:
        old_sha = "a" * 40
        new_sha = "b" * 40

        def git_output(args, **_kwargs):
            values = {
                ("rev-parse", "--abbrev-ref", "HEAD"): "main",
                ("rev-parse", "HEAD"): old_sha,
                ("rev-parse", "origin/main"): new_sha,
            }
            return values[tuple(args)]

        ok_result = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(app, "_is_windows", return_value=True), mock.patch.object(
            app, "_tracked_worktree_is_clean", return_value=True
        ), mock.patch.object(app, "_git_output", side_effect=git_output), mock.patch.object(
            app, "_git_run", return_value=ok_result
        ), mock.patch.object(app, "_schedule_self_restart", return_value=True) as restart_mock, mock.patch.object(
            app.subprocess, "run"
        ) as subprocess_run_mock:
            result = app._perform_app_update(install_deps=True)

        self.assertTrue(result["ok"])
        self.assertTrue(result["updated"])
        subprocess_run_mock.assert_not_called()
        restart_mock.assert_called_once_with(delay_seconds=1.0, install_deps_after_exit=True)


if __name__ == "__main__":
    unittest.main()
