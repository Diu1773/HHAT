"""분석 파이프라인 — Step 베이스 클래스

모든 분석 단계 위젯의 공통 인터페이스를 정의한다.
참고: Aperture_Photometry 프로젝트의 StepWindowBase 패턴

하단 네비게이션: [◀ 이전] ─── [완료로 표시] ─── [다음 ▶]
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

from src.models.observation import Observation
from src.models.project_state import ProjectState
from src.core.cache import save_cache


TOTAL_STEPS = ProjectState.TOTAL_STEPS


class StepBase(QWidget):
    """분석 파이프라인 단일 Step 위젯의 베이스 클래스.

    서브클래스에서 반드시 구현할 것:
        setup_ui()       — Step 고유 UI를 self.content_layout에 추가
        validate_step()  — 완료 가능 여부 반환
        on_enter()       — Step 활성화 시 호출 (데이터 로드 등)

    선택적 오버라이드:
        save_state()     — Step 결과를 project_state에 저장
        restore_state()  — 저장된 상태 복원
    """

    step_completed = Signal(int)            # step_index
    step_status_changed = Signal(int, str)  # (step_index, status_msg)
    go_to_step = Signal(int)                # 이동할 step_index

    def __init__(
        self,
        step_index: int,
        step_name: str,
        step_description: str,
        project_state: ProjectState,
        parent=None,
    ):
        super().__init__(parent)
        self.step_index = step_index
        self.step_name = step_name
        self.step_description = step_description
        self.project_state = project_state
        self.completed = project_state.is_step_completed(step_index)

        self._observations: list[Observation] = []
        self._current_idx: int = -1

        self._build_base_ui()
        self.setup_ui()
        self.restore_state()

    def _build_base_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── 헤더 ──
        header = QFrame()
        header.setStyleSheet("QFrame { background: #16162a; border-bottom: 2px solid #3a7bd5; }")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        step_num = QLabel(f"Step {self.step_index + 1}")
        step_num.setStyleSheet("color: #3a7bd5; font-size: 18px; font-weight: bold; margin-right: 8px;")
        header_layout.addWidget(step_num)

        title = QLabel(self.step_name)
        title.setStyleSheet("color: white; font-size: 15px; font-weight: bold;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("font-size: 11px;")
        header_layout.addWidget(self.lbl_status)

        outer.addWidget(header)

        # ── 설명 ──
        desc = QLabel(self.step_description)
        desc.setStyleSheet("color: #888; font-size: 11px; padding: 6px 12px;")
        desc.setWordWrap(True)
        outer.addWidget(desc)

        # ── 컨텐츠 영역 ──
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        outer.addWidget(self.content_widget, stretch=1)

        # ── 하단 네비게이션: [◀ 이전] ─── [완료로 표시] ─── [다음 ▶] ──
        nav = QFrame()
        nav.setStyleSheet("QFrame { background: #16162a; border-top: 1px solid #333; }")
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(12, 8, 12, 8)

        # 이전 버튼
        self.btn_prev = QPushButton("◀  이전 단계")
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background: #2e7d32; color: white; font-weight: bold;
                padding: 8px 18px; border-radius: 4px;
            }
            QPushButton:hover { background: #388e3c; }
            QPushButton:disabled { background: #333; color: #666; }
        """)
        self.btn_prev.clicked.connect(self._on_prev)
        if self.step_index == 0:
            self.btn_prev.setEnabled(False)
        nav_layout.addWidget(self.btn_prev)

        nav_layout.addStretch()

        # 완료 버튼
        self.btn_mark_complete = QPushButton("완료로 표시")
        self.btn_mark_complete.setStyleSheet("""
            QPushButton {
                background: #1565c0; color: white; font-weight: bold;
                padding: 8px 24px; border-radius: 4px; font-size: 12px;
            }
            QPushButton:hover { background: #1976d2; }
            QPushButton:disabled { background: #555; color: #999; }
        """)
        self.btn_mark_complete.clicked.connect(self._on_mark_complete)
        nav_layout.addWidget(self.btn_mark_complete)

        nav_layout.addStretch()

        # 다음 버튼
        self.btn_next = QPushButton("다음 단계  ▶")
        self.btn_next.setStyleSheet("""
            QPushButton {
                background: #c62828; color: white; font-weight: bold;
                padding: 8px 18px; border-radius: 4px;
            }
            QPushButton:hover { background: #e53935; }
            QPushButton:disabled { background: #333; color: #666; }
        """)
        self.btn_next.clicked.connect(self._on_next)
        if self.step_index >= TOTAL_STEPS - 1:
            self.btn_next.setEnabled(False)
        nav_layout.addWidget(self.btn_next)

        outer.addWidget(nav)

        self._update_nav_state()

    def _update_nav_state(self):
        """완료 상태에 따라 버튼 텍스트/활성 상태를 갱신한다."""
        self.completed = self.project_state.is_step_completed(self.step_index)

        if self.completed:
            self.lbl_status.setText("완료됨")
            self.lbl_status.setStyleSheet("color: #4caf50; font-size: 11px; font-weight: bold;")
            self.btn_mark_complete.setText("완료됨 ✓")
            self.btn_mark_complete.setEnabled(False)
            # 완료 후 다음 버튼 활성화 (녹색)
            if self.step_index < TOTAL_STEPS - 1:
                self.btn_next.setEnabled(True)
                self.btn_next.setStyleSheet("""
                    QPushButton {
                        background: #2e7d32; color: white; font-weight: bold;
                        padding: 8px 18px; border-radius: 4px;
                    }
                    QPushButton:hover { background: #388e3c; }
                """)
        else:
            self.lbl_status.setText("진행 중")
            self.lbl_status.setStyleSheet("color: #ff9800; font-size: 11px;")
            self.btn_mark_complete.setText("완료로 표시")
            self.btn_mark_complete.setEnabled(True)
            # 미완료 시 다음 버튼 비활성
            if self.step_index < TOTAL_STEPS - 1:
                self.btn_next.setEnabled(False)
                self.btn_next.setStyleSheet("""
                    QPushButton {
                        background: #c62828; color: white; font-weight: bold;
                        padding: 8px 18px; border-radius: 4px;
                    }
                    QPushButton:hover { background: #e53935; }
                    QPushButton:disabled { background: #333; color: #666; }
                """)

    def _on_mark_complete(self):
        if not self.validate_step():
            return

        # 단계 완료 시점에 현재 관측 상태를 모두 디스크에 동기화한다.
        for obs in self._observations:
            try:
                save_cache(obs)
            except Exception:
                pass

        # 각 관측 폴더에 결과 자동 저장 (CSV, fit.json, meta.json)
        try:
            from src.core.export import export_autosave
            for obs in self._observations:
                try:
                    export_autosave(obs)
                except Exception:
                    pass
        except ImportError:
            pass

        self.save_state()
        self.project_state.mark_step_completed(self.step_index)
        self.completed = True
        self._update_nav_state()
        self.step_completed.emit(self.step_index)

    def _on_prev(self):
        if self.step_index > 0:
            self.go_to_step.emit(self.step_index - 1)

    def _on_next(self):
        if self.step_index < TOTAL_STEPS - 1 and self.completed:
            self.go_to_step.emit(self.step_index + 1)

    # ── 서브클래스 인터페이스 ──

    def setup_ui(self):
        pass

    def validate_step(self) -> bool:
        return True

    def on_enter(self):
        """Step 활성화 시 호출. _update_nav_state도 같이 갱신."""
        self._update_nav_state()

    def save_state(self):
        pass

    def restore_state(self):
        pass

    # ── 데이터 접근 ──

    def set_observations(self, observations: list[Observation], current_idx: int = -1):
        self._observations = observations
        self._current_idx = current_idx

    @property
    def observations(self) -> list[Observation]:
        return self._observations

    @property
    def current_obs(self) -> Observation | None:
        if 0 <= self._current_idx < len(self._observations):
            return self._observations[self._current_idx]
        return None

    def set_current_index(self, idx: int):
        self._current_idx = idx
