"""MAJIMeeting Windows desktop entrypoint."""
import sys

from PySide6.QtWidgets import QApplication, QLabel, QMainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("MAJIMeeting")
    window = QMainWindow()
    window.setWindowTitle("MAJIMeeting — Prototype initial")
    window.resize(1000, 650)
    label = QLabel(
        "MAJIMeeting\n\n"
        "Socle de l'application initialisé.\n"
        "Enregistrement, transcription et rapports : en développement."
    )
    label.setStyleSheet("font-size: 18px; padding: 32px;")
    window.setCentralWidget(label)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
