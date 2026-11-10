"""YouTube Lite entry point."""
import os
import sys
import traceback

if not getattr(sys, "frozen", False):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))


def _fix_std_streams() -> None:
    """A windowed (no-console) Windows program has sys.stdout/sys.stderr == None.
    Libraries such as yt-dlp and Qt then crash on print/flush, so give them a sink."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


_fix_std_streams()


def _app_root() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


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


def _excepthook(exc_type, exc, tb) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        logs = os.path.join(_app_root(), "logs")
        os.makedirs(logs, exist_ok=True)
        with open(os.path.join(logs, "crash.log"), "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    except OSError:
        pass
    _fatal("YouTube Lite hit an unexpected error but tried to continue.\n\n"
           f"{exc_type.__name__}: {exc}\n\nDetails were saved to logs\\crash.log")


def main() -> int:
    sys.excepthook = _excepthook
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        _fatal(f"The Qt GUI component (PySide6) is missing or cannot load:\n{exc}\n\n"
               "YouTube Lite needs 64-bit Windows 10. See README.txt > Troubleshooting.")
        return 2

    from ytlite import APP_NAME
    from ytlite.app import AppContext
    from ytlite.gui.mainwindow import MainWindow
    from ytlite.gui.theme import app_icon, stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")               # light-weight, consistent with the flat stylesheet
    app.setStyleSheet(stylesheet())
    app.setWindowIcon(app_icon())

    ctx = AppContext()
    try:
        win = MainWindow(ctx)
    except Exception as exc:
        ctx.logger.exception("startup failed")
        _fatal(f"YouTube Lite could not start:\n{exc}")
        return 1
    win.show()
    code = app.exec()
    # Worker threads may still be inside a network call; leave without waiting for them.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
