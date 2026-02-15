"""Step 12: 결과 내보내기 — 저장 상태 확인 + 사용자 지정 폴더 내보내기."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QTextEdit, QFileDialog, QTreeWidget, QTreeWidgetItem,
)

from src.analysis.step_base import StepBase
from src.core.cache import save_cache
from src.core.export import export_package, export_autosave
from src.models.project_state import ProjectState
from src.widgets.obs_list import ObsListWidget


class Step12Export(StepBase):
    """각 관측의 자동 저장 상태를 확인하고, 원하는 폴더로 내보낼 수 있다.

    자동 저장은 매 Step 완료 시 관측 폴더/exports/latest에 저장된다.
    이 Step에서는 그 결과를 확인하고, 추가로 사용자가 원하는 위치에 내보낼 수 있다.
    """

    def __init__(self, project_state: ProjectState, parent=None):
        super().__init__(
            step_index=11,
            step_name="결과 내보내기",
            step_description=(
                "각 단계 완료 시 관측 폴더에 결과가 자동 저장됩니다. "
                "여기서 저장 상태를 확인하고, 별도 폴더로 내보낼 수 있습니다."
            ),
            project_state=project_state,
            parent=parent,
        )

    def setup_ui(self):
        layout = QHBoxLayout()

        # 관측 리스트
        self.obs_list = ObsListWidget()
        self.obs_list.btn_open.hide()
        self.obs_list.setMaximumWidth(260)
        self.obs_list.observation_selected.connect(self._on_select)
        layout.addWidget(self.obs_list)

        # 상태 + 버튼
        right = QVBoxLayout()

        # 자동 저장 상태
        status_group = QGroupBox("자동 저장 상태")
        sl = QVBoxLayout(status_group)

        self.lbl_target = QLabel("대상: -")
        self.lbl_target.setStyleSheet("color: #66ccff;")
        sl.addWidget(self.lbl_target)

        self.lbl_path = QLabel("경로: -")
        self.lbl_path.setStyleSheet("color: #aaa; font-size: 11px;")
        self.lbl_path.setWordWrap(True)
        sl.addWidget(self.lbl_path)

        self.tree_files = QTreeWidget()
        self.tree_files.setHeaderLabels(["파일", "크기", "수정 시각"])
        self.tree_files.setRootIsDecorated(False)
        self.tree_files.setStyleSheet("""
            QTreeWidget { background: #1e1e2e; color: white; border: 1px solid #444; }
            QHeaderView::section { background: #2a2a3e; color: white;
                                   border: 1px solid #444; padding: 3px; }
        """)
        sl.addWidget(self.tree_files)

        right.addWidget(status_group)

        # 버튼들
        btn_row = QHBoxLayout()

        self.btn_refresh = QPushButton("전체 갱신 저장")
        self.btn_refresh.setStyleSheet(
            "QPushButton { background: #1565c0; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_refresh.clicked.connect(self._on_refresh_all)
        btn_row.addWidget(self.btn_refresh)

        self.btn_export_folder = QPushButton("폴더로 내보내기...")
        self.btn_export_folder.setStyleSheet(
            "QPushButton { background: #2e7d32; color: white; font-weight: bold; padding: 8px; }"
        )
        self.btn_export_folder.clicked.connect(self._on_export_folder)
        btn_row.addWidget(self.btn_export_folder)

        right.addLayout(btn_row)

        self.lbl_status = QLabel("")
        right.addWidget(self.lbl_status)

        layout.addLayout(right, stretch=1)
        self.content_layout.addLayout(layout, stretch=1)

    def on_enter(self):
        super().on_enter()
        self.obs_list.set_observations(self._observations)
        if self._observations:
            idx = self._current_idx if 0 <= self._current_idx < len(self._observations) else 0
            self._on_select(idx)

    def _on_select(self, idx: int):
        self._current_idx = idx
        obs = self.current_obs
        if obs is None:
            self.lbl_target.setText("대상: -")
            self.lbl_path.setText("경로: -")
            self.tree_files.clear()
            return

        self.lbl_target.setText(f"대상: {obs.display_name}")
        export_dir = obs.path / "exports" / "latest"
        self.lbl_path.setText(f"경로: {export_dir}")
        self._refresh_file_tree(export_dir)

    def _refresh_file_tree(self, export_dir: Path):
        self.tree_files.clear()
        if not export_dir.exists():
            return

        for p in sorted(export_dir.glob("*")):
            if not p.is_file():
                continue
            size = p.stat().st_size
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            if size < 1024:
                size_str = f"{size} B"
            else:
                size_str = f"{size / 1024:.1f} KB"
            QTreeWidgetItem(self.tree_files, [p.name, size_str, mtime])

    def _on_refresh_all(self):
        success = 0
        fail = 0
        for obs in self._observations:
            try:
                save_cache(obs)
                export_autosave(obs)
                success += 1
            except Exception:
                fail += 1

        color = "#4caf50" if fail == 0 else "#ff9800"
        self.lbl_status.setText(f"전체 저장: 성공 {success}, 실패 {fail}")
        self.lbl_status.setStyleSheet(f"color: {color};")

        # 현재 선택된 관측의 파일 목록 갱신
        obs = self.current_obs
        if obs:
            self._refresh_file_tree(obs.path / "exports" / "latest")

    def _on_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "내보낼 폴더 선택")
        if not folder:
            return

        out = Path(folder)
        success = 0
        fail = 0
        for obs in self._observations:
            try:
                obs_dir = out / obs.display_name
                export_package(obs, obs_dir)
                success += 1
            except Exception:
                fail += 1

        color = "#4caf50" if fail == 0 else "#ff9800"
        self.lbl_status.setText(f"내보내기 완료: {out} (성공 {success}, 실패 {fail})")
        self.lbl_status.setStyleSheet(f"color: {color};")

    def save_state(self):
        pass

    def restore_state(self):
        pass

    def validate_step(self) -> bool:
        return True
