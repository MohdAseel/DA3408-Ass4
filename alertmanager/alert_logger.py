import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        for alert in body.get("alerts", []):
            labels, notes = alert.get("labels", {}), alert.get("annotations", {})
            print(f"[{alert.get('status', '?').upper():8}] {labels.get('alertname')} "
                  f"severity={labels.get('severity')} :: {notes.get('summary', '')} "
                  f"(since {alert.get('startsAt')})", flush=True)
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print("alert-logger listening on :5001", flush=True)
    HTTPServer(("0.0.0.0", 5001), Handler).serve_forever()
