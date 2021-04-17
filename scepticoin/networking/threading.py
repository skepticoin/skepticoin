import threading

from .peer import local_peer
from .params import PORT


class NetworkingThread(threading.Thread):

    def __init__(self, coinstate, port=PORT):
        super().__init__(name="NetworkingThread")
        self.port = port

        self.local_peer = local_peer
        local_peer.chain_manager.set_coinstate(coinstate)

    def run(self):
        self.local_peer.start_listening(self.port)
        self.local_peer.run()

    def stop(self):
        self.local_peer.stop()
