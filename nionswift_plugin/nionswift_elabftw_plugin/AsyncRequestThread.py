import threading

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