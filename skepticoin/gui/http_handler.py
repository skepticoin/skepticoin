from typing import Dict, Tuple
from flask import Flask
from .services import SkepticoinService
from .web_app_loader import WEB_APP_LOADER


app = Flask(__name__)
skeptis = SkepticoinService()


@app.route("/")
def webRoot() -> str:
    return WEB_APP_LOADER  # type: ignore #  mypy bug!?


@app.route('/event-stream')
def event_stream() -> Tuple[str, int, Dict[str, str]]:
    msg = skeptis.event_queue.pop() if skeptis.event_queue else 'Nothing Is Happening'
    return ('data: %s\n\n' % msg, 200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache'
    })


@app.route('/wallet')
def get_wallet() -> Dict[str, int]:
    return {'size': len(skeptis.wallet.keypairs)}


@app.route('/height')
def get_height() -> Dict[str, int]:
    height = len(skeptis.thread.local_peer.chain_manager.coinstate.block_by_hash)
    return {'height': height}


class HttpHandler:

    @staticmethod
    def server_loop() -> None:
        app.run()

    server_address = ('127.0.0.1', 5000)  # this is the flask default
