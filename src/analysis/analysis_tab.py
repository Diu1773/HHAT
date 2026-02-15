"""분석 탭 — Step 네비게이션 + 파이프라인 관리

레이아웃:
  ┌──────────────────────────────────────────────────────────────┐
  │  Progress: 3/13 단계 완료                                     │
  ├──────────────┬───────────────────────────────────────────────┤
  │              │                                               │
  │  Step 1  ✓  │                                               │
  │  Step 2  ✓  │        현재 Step 위젯                          │
  │  Step 3  ✓  │                                               │
  │  Step 4  ○  │                                               │
  │  Step 5  🔒 │                                               │
  │  ...        │                                               │
  │  Step 13 🔒 │                                               │
  │              │                                               │
  │  [리셋]      │                                               │
  └──────────────┴───────────────────────────────────────────────┘
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPushButton, QLabel, QStackedWidget, QFrame,
    QScrollArea, QMessageBox,
)

from src.models.observation import Observation
from src.models.project_state import ProjectState
from src.core.fits_io import scan_folder
from src.core.metadata import load_meta_json
from src.core.cache import load_cache

# Step 임포트
from src.analysis.step1_file_selection import Step1FileSelection
from src.analysis.step2_type_classification import Step2TypeClassification
from src.analysis.step3_metadata import Step3Metadata
from src.analysis.step4_qc import Step4QC
from src.analysis.step5_preprocessing import Step5Preprocessing
from src.analysis.step6_baseline import Step6Baseline
from src.analysis.step7_velocity import Step7Velocity
from src.analysis.step8_lsr_correction import Step8LSRCorrection
from src.analysis.step9_peak_detection import Step9PeakDetection
from src.analysis.step10_gaussian_fitting import Step10GaussianFitting
from src.analysis.step11_physics import Step11Physics
from src.analysis.step12_export import Step12Export
from src.analysis.step13_batch import Step13Batch
from src.analysis.step_base import StepBase


STEP_CLASSES = [
    Step1FileSelection,
    Step2TypeClassification,
    Step3Metadata,
    Step4QC,
    Step5Preprocessing,
    Step6Baseline,
    Step7Velocity,
    Step8LSRCorrection,
    Step9PeakDetection,
    Step10GaussianFitting,
    Step11Physics,
    Step12Export,
    Step13Batch,
]

STEP_LABELS = [
    "데이터 로딩",
    "타입 분류",
    "메타데이터",
    "QC 품질점검",
    "전처리",
    "Baseline",
    "속도 변환",
    "LSR 보정",
    "피크 검출",
    "프로파일 피팅",
    "물리량 환산",
    "자동 저장",
    "은하지도 맵",
]


class StepButton(QPushButton):
    """Step 네비게이션 버튼"""

    def __init__(self, step_number: int, step_name: str, parent=None):
        super().__init__(parent)
        self.step_number = step_number
        self.step_name = step_name
        self._completed = False
        self._accessible = False
        self._current = False
        self.setFixedHeight(36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def set_state(self, completed: bool, accessible: bool, current: bool = False):
        self._completed = completed
        self._accessible = accessible
        self._current = current
        self.setEnabled(accessible)
        self._update_style()

    def _update_style(self):
        num = self.step_number + 1
        name = self.step_name

        if self._current:
            icon = "▶"
            bg = "#3a7bd5"
            fg = "white"
            border = "2px solid #66ccff"
        elif self._completed:
            icon = "✓"
            bg = "#1b5e20"
            fg = "#a5d6a7"
            border = "1px solid #388e3c"
        elif self._accessible:
            icon = "○"
            bg = "#2a2a3e"
            fg = "white"
            border = "1px solid #555"
        else:
            icon = "🔒"
            bg = "#1a1a2a"
            fg = "#555"
            border = "1px solid #333"

        self.setText(f" {icon}  Step {num}: {name}")
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {fg};
                border: {border}; border-radius: 4px;
                text-align: left; padding-left: 10px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {'#4a8be5' if self._current else '#3a3a5e'}; }}
        """)


class AnalysisTab(QWidget):
    """분석 탭: Step 네비게이션 + 파이프라인"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 상태 디렉토리
        state_dir = Path.home() / ".hhat" / "state"
        self.project_state = ProjectState(state_dir)

        self._observations: list[Observation] = []
        self._current_step: int = 0

        self._setup_ui()
        self._create_steps()
        self._restore_observations_from_state()
        self._restore_navigation_state()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 프로그레스 바
        progress_bar = QFrame()
        progress_bar.setStyleSheet("QFrame { background: #16162a; border-bottom: 1px solid #333; }")
        pbl = QHBoxLayout(progress_bar)
        pbl.setContentsMargins(12, 6, 12, 6)

        self.lbl_progress = QLabel("")
        self.lbl_progress.setStyleSheet("color: #66ccff; font-size: 12px; font-weight: bold;")
        pbl.addWidget(self.lbl_progress)
        pbl.addStretch()

        self.btn_reset = QPushButton("파이프라인 리셋")
        self.btn_reset.setStyleSheet(
            "QPushButton { color: #f44336; background: transparent; border: 1px solid #f44336; "
            "padding: 4px 10px; border-radius: 3px; font-size: 10px; }"
        )
        self.btn_reset.clicked.connect(self._on_reset)
        pbl.addWidget(self.btn_reset)

        main_layout.addWidget(progress_bar)

        # 메인: 좌(버튼) / 우(Step 위젯)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 좌: Step 버튼 리스트
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setMinimumWidth(220)
        nav_scroll.setMaximumWidth(260)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)

        nav_widget = QWidget()
        self.nav_layout = QVBoxLayout(nav_widget)
        self.nav_layout.setContentsMargins(6, 6, 6, 6)
        self.nav_layout.setSpacing(3)

        self.step_buttons: list[StepButton] = []
        for i, name in enumerate(STEP_LABELS):
            btn = StepButton(i, name)
            btn.clicked.connect(lambda checked, idx=i: self._go_to_step(idx))
            self.step_buttons.append(btn)
            self.nav_layout.addWidget(btn)

        # MVP / 2차 / 고급 구분선
        self._add_separator("MVP (Step 1~7, 12)")
        self._add_separator("2차 완성 (Step 9~10, 13)", after_idx=7)
        self._add_separator("고급 (Step 8, 11)", after_idx=10)

        self.nav_layout.addStretch()
        nav_scroll.setWidget(nav_widget)
        splitter.addWidget(nav_scroll)

        # 우: Step 위젯 스택
        self.stack = QStackedWidget()
        splitter.addWidget(self.stack)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)

    def _add_separator(self, text: str, after_idx: int = None):
        """구분선 (nav_layout에 직접 추가됨 — 위치는 addWidget 순서에 따름)"""
        # 구분선은 나중에 UI에서 볼 수 있도록 라벨로 추가
        pass  # 현재는 스킵. 필요시 QLabel 삽입

    def _create_steps(self):
        """Step 위젯들을 생성하고 스택에 추가한다."""
        self.steps: list[StepBase] = []
        for StepClass in STEP_CLASSES:
            step = StepClass(self.project_state)
            step.step_completed.connect(self._on_step_completed)
            step.go_to_step.connect(self._go_to_step)
            self.steps.append(step)
            self.stack.addWidget(step)

        # Step 1 data_loaded → 다른 Step들에 전파
        if isinstance(self.steps[0], Step1FileSelection):
            self.steps[0].data_loaded.connect(self._on_data_loaded)

    def _restore_observations_from_state(self):
        """project_state의 step1 정보로 관측 파일 목록을 복원한다."""
        step1_data = self.project_state.get_step_data("step1")
        folder = step1_data.get("folder")
        if not folder:
            return

        root = Path(folder).expanduser()
        if not root.is_dir():
            return

        observations = scan_folder(root)
        if not observations:
            return

        for obs in observations:
            obs.metadata = load_meta_json(obs)
            load_cache(obs)
        self._observations = observations

    def _restore_navigation_state(self):
        """마지막으로 보던 step으로 이동한다."""
        raw_idx = self.project_state.state.get("current_step", 0)
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            idx = 0

        idx = max(0, min(idx, len(self.steps) - 1))

        if idx > 0 and not self._observations:
            idx = 0

        while idx > 0 and not self.project_state.is_step_accessible(idx):
            idx -= 1

        self._go_to_step(idx)

    def _update_buttons(self):
        """버튼 상태를 갱신한다."""
        for i, btn in enumerate(self.step_buttons):
            completed = self.project_state.is_step_completed(i)
            accessible = self.project_state.is_step_accessible(i)
            current = (i == self._current_step)
            btn.set_state(completed, accessible, current)

        self.lbl_progress.setText(self.project_state.progress_text)

    def _go_to_step(self, idx: int):
        """Step으로 이동한다."""
        if not self.project_state.is_step_accessible(idx):
            QMessageBox.information(
                self, "접근 불가",
                f"Step {idx + 1}은 이전 단계를 완료해야 접근할 수 있습니다."
            )
            return

        self._current_step = idx
        self.stack.setCurrentIndex(idx)

        # Step에 데이터 전달 & on_enter 호출
        step = self.steps[idx]
        step.set_observations(self._observations, 0 if self._observations else -1)
        step.on_enter()

        self._update_buttons()

        # 현재 step 기억
        self.project_state.state["current_step"] = idx
        self.project_state.save()

    @Slot(int)
    def _on_step_completed(self, step_index: int):
        """Step 완료 시 호출"""
        self._update_buttons()

    @Slot(list)
    def _on_data_loaded(self, observations: list):
        """Step 1에서 데이터 로드 완료 시"""
        self._observations = observations

    def _on_reset(self):
        reply = QMessageBox.question(
            self, "파이프라인 리셋",
            "모든 단계의 완료 상태를 초기화하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.project_state.reset()
            self._update_buttons()
            self._go_to_step(0)

    def set_observations(self, observations: list[Observation]):
        """외부에서 관측 데이터를 주입한다."""
        self._observations = observations

    def load_observation_folder(self, folder: str):
        """관측 완료 후 외부에서 호출 — 폴더를 스캔하여 데이터를 로드하고 Step 1로 이동."""
        root = Path(folder).expanduser()
        if not root.is_dir():
            # 개별 폴더가 아니라 부모 폴더일 수 있음
            root = root.parent
            if not root.is_dir():
                return

        observations = scan_folder(root)
        if not observations:
            return

        for obs in observations:
            obs.metadata = load_meta_json(obs)
            load_cache(obs)

        self._observations = observations

        # Step 1에 상태 저장
        self.project_state.store_step_data("step1", {
            "folder": str(root),
            "count": len(observations),
        })

        # Step 1의 data_loaded 시그널을 수동으로 트리거하지 않고 직접 반영
        self._go_to_step(0)
