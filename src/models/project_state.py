"""프로젝트 상태 관리 — 분석 파이프라인 진행 추적"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class ProjectState:
    """분석 파이프라인의 단계별 완료 상태를 추적한다."""

    TOTAL_STEPS = 13

    def __init__(self, state_dir: Path | None = None):
        self.state: dict[str, Any] = {
            "project_name": "",
            "created": datetime.now().isoformat(),
            "last_modified": datetime.now().isoformat(),
            "current_step": 0,
            "completed_steps": [],
            "step_data": {},
        }
        self._state_file: Path | None = None

        if state_dir is not None:
            state_dir = Path(state_dir)
            state_dir.mkdir(parents=True, exist_ok=True)
            self._state_file = state_dir / "project_state.json"
            if self._state_file.exists():
                self._load()

    # ── 단계 상태 ──

    def is_step_completed(self, step_index: int) -> bool:
        return step_index in self.state["completed_steps"]

    def is_step_accessible(self, step_index: int) -> bool:
        """이전 단계가 완료되어야 접근 가능. Step 0은 항상 접근 가능."""
        if step_index == 0:
            return True
        return self.is_step_completed(step_index - 1)

    def mark_step_completed(self, step_index: int):
        if step_index not in self.state["completed_steps"]:
            self.state["completed_steps"].append(step_index)
            self.state["completed_steps"].sort()
        self.state["current_step"] = step_index
        self.state["last_modified"] = datetime.now().isoformat()
        self._save()

    def unmark_step(self, step_index: int):
        """단계 완료를 취소하고, 이후 단계도 모두 리셋한다."""
        self.state["completed_steps"] = [
            s for s in self.state["completed_steps"] if s < step_index
        ]
        self.state["last_modified"] = datetime.now().isoformat()
        self._save()

    def reset(self):
        self.state["completed_steps"] = []
        self.state["current_step"] = 0
        self.state["step_data"] = {}
        self.state["last_modified"] = datetime.now().isoformat()
        self._save()

    # ── 단계별 데이터 ──

    def store_step_data(self, step_key: str, data: dict):
        if step_key not in self.state["step_data"]:
            self.state["step_data"][step_key] = {}
        self.state["step_data"][step_key].update(data)
        self._save()

    def get_step_data(self, step_key: str) -> dict:
        return self.state["step_data"].get(step_key, {})

    # ── 영속성 ──

    def save(self):
        """외부에서 상태를 강제 저장할 때 사용."""
        self._save()

    def _save(self):
        if self._state_file is None:
            return
        with open(self._state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def _load(self):
        if self._state_file is None or not self._state_file.exists():
            return
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.state.update(loaded)
        except (json.JSONDecodeError, IOError):
            pass

    @property
    def progress_text(self) -> str:
        done = len(self.state["completed_steps"])
        return f"{done}/{self.TOTAL_STEPS} 단계 완료"
