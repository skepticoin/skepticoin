from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import traceback
from typing import Callable, Dict


class HttpHandler(BaseHTTPRequestHandler):

    actions: Dict[str, Callable] = {}

    server_address = ('127.0.0.1', 2411)

    def do_GET(self):  # type: ignore
        try:
            if self.path in HttpHandler.actions:
                action = HttpHandler.actions[self.path]
                (response_code, content_type, body) = action(self)
            else:
                (response_code, content_type, body) = (404, 'text/plain', 'NOT FOUND')

        except Exception:
            print(traceback.format_exc())
            (response_code, content_type, body) = (500, "text/plain", traceback.format_exc())

        self.send_response(response_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body.encode())

    @staticmethod
    def serverLoop() -> None:
        httpd = ThreadingHTTPServer(HttpHandler.server_address, HttpHandler)
        httpd.serve_forever()
