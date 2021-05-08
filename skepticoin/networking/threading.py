import threading

from skepticoin.coinstate import CoinState

from .params import PORT
from .peer import DiskInterface, LocalPeer


class NetworkingThread(threading.Thread):
    def __init__(
        self, coinstate: CoinState, port: int = PORT, disk_interface=DiskInterface()
    ):
        super().__init__(name="NetworkingThread")
        self.port = port

        self.local_peer = LocalPeer(disk_interface=disk_interface)
        self.local_peer.chain_manager.set_coinstate(coinstate)

    def run(self):
        if self.port is not None:
            self.local_peer.start_listening(self.port)
        self.local_peer.run()

    def stop(self):
        self.local_peer.stop()
