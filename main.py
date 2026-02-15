"""HHAT — HI Horn Antenna Analysis Tool
우리은하 중성수소(21cm) 관측 데이터 분석 GUI
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from src.app import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HHAT")
    app.setApplicationDisplayName("HHAT — HI Horn Antenna Analysis Tool")

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
