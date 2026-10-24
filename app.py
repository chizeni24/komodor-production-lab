import os
import socket
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logging.basicConfig(level=logging.INFO)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = 6379

def check_redis():
    with socket.create_connection(
        (REDIS_HOST, REDIS_PORT), timeout=2
    ) as connection:
        connection.sendall(b"*1\r\n$4\r\nPING\r\n")
        response = connection.recv(128)
        if response != b"+PONG\r\n":
            raise RuntimeError(f"Unexpected Redis response: {response!r}")
        return "PONG"

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.respond(200, "API process healthy")
            return

        if self.path in ("/", "/readyz"):
            try:
                result = check_redis()
                self.respond(200, f"API connected to Redis: {result}")
            except Exception as error:
                logging.exception("Redis connection failed")
                self.respond(503, f"Redis unavailable: {error}")
            return

        self.respond(404, "Not found")

    def respond(self, status, message):
        body = (message + "\n").encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    logging.info("API started; Redis readiness checked per request")
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
