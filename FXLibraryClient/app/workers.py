# app/workers.py -- QThread workers that run the UE headless bridge off the UI thread.

from PySide6.QtCore import QThread, Signal

from app import ue_bridge


class BridgeWorker(QThread):
    log_line = Signal(str)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, ue_editor, project, command, params, bridge_dir=None,
                 timeout=600.0):
        super().__init__()
        self.ue_editor = ue_editor
        self.project = project
        self.command = command
        self.params = params
        self.bridge_dir = bridge_dir
        self.timeout = timeout

    def run(self):
        try:
            result = ue_bridge.run_bridge(
                self.ue_editor, self.project, self.command, self.params,
                bridge_dir=self.bridge_dir,
                log_cb=lambda s: self.log_line.emit(s),
                timeout=self.timeout,
            )
            if result.get("ok"):
                self.finished.emit(result)
            else:
                self.failed.emit(result.get("error") or "Bridge returned ok=false")
        except Exception as e:
            self.failed.emit(str(e))
