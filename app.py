import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self._send_json(200, {"message": "Hello World from Cloud Run!"})
            return

        if self.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return

        self._send_json(404, {"error": "not found"})

    def _send_json(self, status_code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Listening on port {port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
