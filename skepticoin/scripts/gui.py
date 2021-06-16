from skepticoin.gui.services import StatefulServices
import webbrowser
from threading import Thread
from time import sleep

from skepticoin.gui.http_handler import HttpHandler


def main() -> None:

    services = StatefulServices()
    HttpHandler.actions = services.actions

    print('Starting local GUI server...')
    serverThread = Thread(target=HttpHandler.serverLoop)
    serverThread.start()

    print('Sleeping')
    sleep(2)

    print('Starting browser...')
    webbrowser.open('http://%s:%d' % HttpHandler.server_address)

    print('Waiting...')
    # serverThread.stop() ???
    serverThread.join()
