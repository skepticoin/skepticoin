from threading import Thread
from typing import Optional

from skepticoin.coinstate import CoinState
from skepticoin.networking.params import PORT
from skepticoin.networking.peer import DiskInterface, LocalPeer


class NetworkingThread(Thread):
    def __init__(
        self,
        coinstate: CoinState,
        port: Optional[int] = PORT,
        disk_interface: DiskInterface = DiskInterface(),
    ):
        super().__init__(name="NetworkingThread")
        self.port = port

        self.local_peer = LocalPeer(disk_interface=disk_interface)
        self.local_peer.chain_manager.set_coinstate(coinstate)

    def run(self) -> None:
        if self.port is not None:
            self.local_peer.start_listening(self.port)
        self.local_peer.run()

    def stop(self) -> None:
        self.local_peer.stop()
