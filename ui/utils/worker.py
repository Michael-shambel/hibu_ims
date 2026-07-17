from PySide6.QtCore import QObject, QThread, Signal
import traceback

class Worker(QObject):
    finished = Signal(object)   # emits the result
    error = Signal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            traceback.print_exc()
            self.error.emit(str(e))
        finally:
            self.deleteLater()