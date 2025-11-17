from __future__ import annotations

from datetime import datetime, timedelta

from kimi_cli.ui.shell.task_manager import (
    ColorMode,
    TaskBanner,
    TaskBannerSettings,
    TaskStateStore,
    TaskStatus,
)


class _StubConsole:
    def __init__(self, color_system: str | None, no_color: bool = False):
        self.color_system = color_system
        self.no_color = no_color

    def print(self, *args, **kwargs):  # noqa: D401, ANN001
        """No-op printer for banner tests."""
        return None


def _make_task(store: TaskStateStore, command: str) -> int:
    task = store.create_task(command_text=command, user_input=command, thinking=None)
    return task.id


def test_task_banner_limits_visible_tasks():
    store = TaskStateStore()
    t1 = _make_task(store, "run tests")
    t2 = _make_task(store, "lint")
    t3 = _make_task(store, "docs")
    t4 = _make_task(store, "deploy")
    store.mark_running(t1)
    store.mark_running(t2)
    store.mark_running(t3)
    store.mark_succeeded(t3)
    store.mark_running(t4)
    store.mark_succeeded(t4)

    banner = TaskBanner(store, TaskBannerSettings(visible_slots=2, refresh_interval=1.0))
    visible, hidden, _ = banner._visible_tasks_for_render(datetime.now())
    assert len(visible) == 2
    assert {task.status for task in visible} == {TaskStatus.RUNNING}
    assert hidden >= 2


def test_task_banner_filters_faded_completed_tasks():
    store = TaskStateStore()
    now = datetime.now()
    t1 = _make_task(store, "run")
    t2 = _make_task(store, "finish")
    store.mark_running(t1)
    store.mark_running(t2)
    store.mark_succeeded(t2)
    task = store.get(t2)
    assert task is not None
    task.fade_deadline = now - timedelta(seconds=1)

    banner = TaskBanner(store, TaskBannerSettings(visible_slots=4, refresh_interval=1.0))
    visible, hidden, _ = banner._visible_tasks_for_render(now)
    ids = [task.id for task in visible]
    assert t2 not in ids
    assert hidden == 0


def test_task_banner_detects_truecolor(monkeypatch):
    monkeypatch.setattr(
        "kimi_cli.ui.shell.task_manager.console",
        _StubConsole(color_system="truecolor", no_color=False),
    )
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    banner = TaskBanner(TaskStateStore(), TaskBannerSettings())
    assert banner._color_mode == ColorMode.TRUECOLOR


def test_task_banner_detects_limited_color(monkeypatch):
    monkeypatch.setattr(
        "kimi_cli.ui.shell.task_manager.console",
        _StubConsole(color_system="eight_bit", no_color=False),
    )
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.delenv("TERM", raising=False)
    banner = TaskBanner(TaskStateStore(), TaskBannerSettings())
    assert banner._color_mode == ColorMode.LIMITED


def test_task_banner_prefers_mono_when_no_color(monkeypatch):
    monkeypatch.setattr(
        "kimi_cli.ui.shell.task_manager.console",
        _StubConsole(color_system="truecolor", no_color=False),
    )
    monkeypatch.setenv("NO_COLOR", "1")
    banner = TaskBanner(TaskStateStore(), TaskBannerSettings())
    assert banner._color_mode == ColorMode.MONO


def test_task_banner_uses_ascii_spinner_in_mono(monkeypatch):
    monkeypatch.setattr(
        "kimi_cli.ui.shell.task_manager.console",
        _StubConsole(color_system=None, no_color=True),
    )
    monkeypatch.setenv("TERM", "dumb")
    store = TaskStateStore()
    task_id = _make_task(store, "long run")
    store.mark_running(task_id)
    banner = TaskBanner(store, TaskBannerSettings())
    task = store.get(task_id)
    assert task is not None
    spinner = banner._spinner_for(task)
    assert spinner in banner.ASCII_SPINNER
