import asyncio
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

HTML = "<html><body><script type='application/ld+json'>{\"@context\":\"https://schema.org\",\"@type\":\"Product\",\"name\":\"Probe Item\",\"sku\":\"P1\",\"offers\":{\"price\":\"10\",\"priceCurrency\":\"USD\"}} </script></body></html>"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass


def main():
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    port = srv.server_port
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        import app.knowledge.crawler as c
        async def fetch():
            body, status = await c.WebsiteCrawler(max_pages=1, max_depth=1, concurrency=1, requests_per_second=1.0).fetch(f'http://public-example.test:{port}/')
            print('status', status)
            print(body[:200])
        asyncio.run(fetch())
    finally:
        srv.shutdown(); srv.server_close()


if __name__ == '__main__':
    main()
