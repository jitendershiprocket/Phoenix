"""Phoenix Dashboard - Progress store for real-time UI."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Literal

StepStatus = Literal["pending", "running", "done", "failed"]


@dataclass
class StepInfo:
    name: str
    label: str
    status: StepStatus = "pending"
    duration_sec: float | None = None
    message: str = ""
    started_at: float | None = None


class ProgressStore:
    """Thread-safe progress store for Phoenix agent steps."""

    _instance: "ProgressStore | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "ProgressStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized") and self._initialized:
            return
        self._initialized = True
        self._lock = threading.Lock()
        self._steps: list[StepInfo] = [
            StepInfo("fetch", "Fetch bug from Sentry"),
            StepInfo("clone", "Clone repo & create fix branch"),
            StepInfo("fix", "AI fix + apply edits"),
            StepInfo("validate", "ng build & lint (may take 2–4 min)"),
            StepInfo("pr", "Create PR"),
        ]
        self._current_step: str | None = None
        self._last_log: str = ""
        self._bug_summary: str = ""
        self._bug_details: dict = {}
        self._overall_status: StepStatus = "pending"
        self._finished_at: float | None = None
        self._run_started_at: float = 0
        self._pr_url: str = ""

    def reset(self, bug_summary: str = "") -> None:
        with self._lock:
            self._run_started_at = time.time()
            for s in self._steps:
                s.status = "pending"
                s.duration_sec = None
                s.message = ""
                s.started_at = None
            self._current_step = None
            self._last_log = ""
            self._bug_summary = bug_summary
            self._bug_details = {}
            self._overall_status = "pending"
            self._finished_at = None
            self._pr_url = ""

    def set_pr_url(self, url: str) -> None:
        with self._lock:
            self._pr_url = (url or "")[:500]

    def step_start(self, name: str, message: str = "") -> None:
        with self._lock:
            self._current_step = name
            for s in self._steps:
                if s.name == name:
                    s.status = "running"
                    s.started_at = time.time()
                    s.message = (message or "")[:150]
                    break

    def step_end(
        self,
        name: str,
        duration_sec: float,
        message: str = "",
        success: bool = True,
    ) -> None:
        with self._lock:
            for s in self._steps:
                if s.name == name:
                    s.status = "done" if success else "failed"
                    s.duration_sec = duration_sec
                    s.message = (message or "")[:200]
                    s.started_at = None
                    break
            if self._current_step == name:
                self._current_step = None
            self._last_log = message or ""

    def set_overall_done(self, success: bool = True) -> None:
        with self._lock:
            self._overall_status = "done" if success else "failed"
            self._finished_at = time.time()

    def add_log(self, msg: str) -> None:
        with self._lock:
            self._last_log = (msg or "")[-500:]

    def set_bug_summary(self, summary: str) -> None:
        with self._lock:
            self._bug_summary = (summary or "")[:200]

    def set_bug_details(self, details: dict) -> None:
        with self._lock:
            self._bug_details = {k: (str(v) or "")[:300] for k, v in (details or {}).items()}

    def to_dict(self) -> dict:
        with self._lock:
            now = time.time()
            run_start = self._run_started_at or 0
            steps_out = []
            for s in self._steps:
                elapsed = None
                if (
                    s.started_at is not None
                    and s.name == self._current_step
                    and s.started_at >= run_start - 1
                ):
                    elapsed = round(now - s.started_at, 1)
                steps_out.append({
                    "name": s.name,
                    "label": s.label,
                    "status": s.status,
                    "duration_sec": s.duration_sec,
                    "elapsed_sec": elapsed,
                    "message": (s.message or "")[:150],
                })
            return {
                "steps": steps_out,
                "current_step": self._current_step,
                "last_log": self._last_log,
                "bug_summary": self._bug_summary,
                "bug_details": dict(self._bug_details),
                "overall_status": self._overall_status,
                "finished_at": self._finished_at,
                "pr_url": (self._pr_url or "").strip() or None,
            }


progress = ProgressStore()
