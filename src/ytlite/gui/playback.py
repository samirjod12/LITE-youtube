"""Qt wrapper that runs mpv as a separate process and talks to it over JSON IPC.

No continuous polling: a 1.5-3 s timer exists ONLY while mpv is running and is
stopped the moment it exits.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QObject, QProcess, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

from ..formats import StreamOption
from ..mpvconf import conf_args
from ..player import (POLL_PROPERTIES, IpcProtocol, PlaybackHealth, build_mpv_command,
                      exit_message, ipc_endpoint)
from ..winjob import assign_pid, create_kill_on_close_job


class PlayerController(QObject):
    stateChanged = Signal(str, str)        # state: launching|playing|stopped|error, message
    statsUpdated = Signal(dict, object)    # raw mpv sample, HealthReport

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.proc: QProcess | None = None
        self.sock: QLocalSocket | None = None
        self.ipc = IpcProtocol()
        self.health = PlaybackHealth()
        self.sample: dict = {}
        self.last_pos = 0.0
        self.video_id = ""
        self.option: StreamOption | None = None
        self._pending: dict[int, str] = {}
        self._stderr = ""
        self._user_stop = False
        self._ipc_name = ""
        self._tries = 0
        self._job = create_kill_on_close_job()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._connect_timer = QTimer(self)
        self._connect_timer.setInterval(400)
        self._connect_timer.timeout.connect(self._try_connect)

    # -- state -------------------------------------------------------------
    def is_running(self) -> bool:
        return self.proc is not None and self.proc.state() != QProcess.ProcessState.NotRunning

    # -- launch / stop -----------------------------------------------------
    def launch(self, video_id: str, option: StreamOption, title: str, start_seconds: float = 0.0) -> bool:
        self.stop()
        exe = self.ctx.mpv_exe()
        if exe is None:
            self.stateChanged.emit("error", "mpv was not found. Put mpv.exe in the 'mpv' folder "
                                   "next to YouTube-Lite.exe (see README).")
            return False
        s = self.ctx.settings
        info = self.ctx.mpv_info()
        supported = (info.options if info else set()) or None
        hwdecs = info.hwdecs if info else None
        args, skipped = conf_args(self.ctx.paths.mpv_conf, supported)
        if skipped:
            self.ctx.logger.warning("mpv.conf options skipped (unsupported by this mpv): %s", skipped)
        ipc_value, self._ipc_name = ipc_endpoint(os.getpid())
        if os.name != "nt":
            try:
                os.unlink(ipc_value)
            except OSError:
                pass
        cmd = build_mpv_command(
            exe, option, title, ipc_value, conf_args=args, hwdec=s["hwdec"], speed=s["speed"],
            volume=s["volume"], fullscreen=s["fullscreen"], decoder_threads=s["decoder_threads"],
            sw_assist=s["sw_assist"], start_seconds=start_seconds, supported=supported, hwdecs=hwdecs)

        self.video_id, self.option = video_id, option
        self.health = PlaybackHealth(height=option.height)
        self.sample, self._pending, self._stderr = {}, {}, ""
        self._user_stop = False
        self.ipc = IpcProtocol()

        self.proc = QProcess(self)
        self.proc.setProgram(cmd[0])
        self.proc.setArguments(cmd[1:])
        self.proc.readyReadStandardError.connect(self._on_stderr)
        self.proc.readyReadStandardOutput.connect(self._on_stderr)
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)
        self.proc.started.connect(self._on_started)
        self.stateChanged.emit("launching", f"Starting mpv at {option.title}...")
        self.proc.start()
        return True

    def stop(self) -> None:
        proc = self.proc
        if proc is None:
            return
        self._user_stop = True
        if proc.state() != QProcess.ProcessState.NotRunning:
            self.command("quit")
            proc.terminate()
            if not proc.waitForFinished(1500):
                proc.kill()
                proc.waitForFinished(1000)
        # _on_finished normally cleans up; make sure of it
        if self.proc is proc:
            self._cleanup()

    # -- IPC ---------------------------------------------------------------
    def command(self, *args) -> None:
        if self.sock is not None and self.sock.state() == QLocalSocket.LocalSocketState.ConnectedState:
            _rid, raw = self.ipc.command(*args)
            self.sock.write(raw)

    def _try_connect(self):
        self._tries += 1
        if self._tries > 25 or self.proc is None:
            self._connect_timer.stop()
            return
        if self.sock is None:
            self.sock = QLocalSocket(self)
            self.sock.connected.connect(self._on_connected)
            self.sock.readyRead.connect(self._on_ipc_data)
        if self.sock.state() == QLocalSocket.LocalSocketState.UnconnectedState:
            self.sock.connectToServer(self._ipc_name)

    def _on_connected(self):
        self._connect_timer.stop()
        self.stateChanged.emit("playing", "Playing")
        self._poll_timer.start(self.ctx.settings.profile.poll_ms)
        self._poll()

    def _poll(self):
        if self.sock is None or self.sock.state() != QLocalSocket.LocalSocketState.ConnectedState:
            return
        self._pending.clear()
        for prop in POLL_PROPERTIES:
            rid, raw = self.ipc.command("get_property", prop)
            self._pending[rid] = prop
            self.sock.write(raw)

    def _on_ipc_data(self):
        if self.sock is None:
            return
        for msg in self.ipc.feed(bytes(self.sock.readAll())):
            rid = msg.get("request_id")
            prop = self._pending.pop(rid, None) if rid is not None else None
            if prop is None:
                continue
            self.sample[prop] = msg.get("data") if msg.get("error") == "success" else None
            if not self._pending:
                pos = self.sample.get("time-pos")
                if isinstance(pos, (int, float)):
                    self.last_pos = float(pos)
                rep = self.health.assess(self.sample)
                self.statsUpdated.emit(dict(self.sample), rep)

    # -- process events ----------------------------------------------------
    def _on_started(self):
        if self.proc is not None:
            assign_pid(self._job, int(self.proc.processId()))
        self._tries = 0
        self._connect_timer.start()

    def _on_stderr(self):
        if self.proc is None:
            return
        chunk = bytes(self.proc.readAllStandardError()).decode("utf-8", "replace")
        chunk += bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._stderr = (self._stderr + chunk)[-2000:]

    def _on_error(self, err):
        if err == QProcess.ProcessError.FailedToStart:
            self.stateChanged.emit("error", "mpv could not be started. The file may be damaged, "
                                   "blocked by antivirus, or not a 64-bit build.")
            self._cleanup()

    def _on_finished(self, code, _status):
        user = self._user_stop
        self._on_stderr()
        stderr = self._stderr
        self._cleanup()
        if user or code in (0, 4):
            self.stateChanged.emit("stopped", "Stopped")
        else:
            self.stateChanged.emit("error", exit_message(int(code), stderr))

    def _cleanup(self):
        self._poll_timer.stop()
        self._connect_timer.stop()
        if self.sock is not None:
            self.sock.abort()
            self.sock.deleteLater()
            self.sock = None
        if self.proc is not None:
            proc, self.proc = self.proc, None
            proc.deleteLater()
        self._pending.clear()
