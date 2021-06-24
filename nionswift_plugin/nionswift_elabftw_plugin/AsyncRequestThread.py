from PyQt5.QtCore import QThread, pyqtSignal
import threading

class AsyncRequestThread_QT(QThread):
    signal = pyqtSignal(object)

    def __init__(self, target, *args):
        QThread.__init__(self)
        self.target = target
        self.args = args

    def run(self):
        try:
            self.signal.emit(self.target(*self.args) if self.args else self.target())
        except Exception as ex:
            print(ex)

    # a class method to reduce no. of lines of code to make async requests
    @classmethod
    def asyncrequest(cls, target, callback, *args):
        self = cls(target, *args)
        def do_nothing(arg):
            pass
        self.signal.connect(do_nothing) if callback is None else self.signal.connect(callback)
        self.start()
        return self

class AsyncRequestThread_threading:
    
    def __init__(self, target, *args):
        self.thread = threading.Thread(name = 'eln api comm.', target=self.run)
        self.target = target
        self.args = args
    
    def run(self):
        try:
            self.target(*self.args)
        except Exception as e:
            print(e)
    
    @classmethod
    def asyncrequest(cls, target, *args):
        self = cls(target, *args)
        self.thread.start()
        return self