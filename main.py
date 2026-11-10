"""YouTube Lite entry point."""
import os
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def _fatal(message: str) -> None:
    """Show a message even if Qt itself cannot start."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "YouTube Lite", 0x10)
            return
        except Exception:
            pass
    sys.stderr.write(message + "\n")


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        _fatal(f"The Qt GUI component (PySide6) is missing or cannot load:\n{exc}\n\n"
               "YouTube Lite needs 64-bit Windows 10. See README.txt > Troubleshooting.")
        return 2

    from ytlite import APP_NAME
    from ytlite.app import AppContext
    from ytlite.gui.mainwindow import MainWindow
    from ytlite.gui.theme import stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")               # light-weight, consistent with the flat stylesheet
    app.setStyleSheet(stylesheet())

    ctx = AppContext()
    try:
        win = MainWindow(ctx)
    except Exception as exc:             # pragma: no cover
        ctx.logger.exception("startup failed")
        _fatal(f"YouTube Lite could not start:\n{exc}")
        return 1
    win.show()
    code = app.exec()
    # Worker threads may still be inside a network call; leave without waiting for them.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
