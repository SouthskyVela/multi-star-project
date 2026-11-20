import http.server
import os
import re
import socketserver

ROOT = r"H:\pass_project\multi_star_project\slides\dist"
os.chdir(ROOT)

RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


class Handler(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            self.path = "/index.html"
            path = self.translate_path(self.path)

        if os.path.isfile(path):
            size = os.path.getsize(path)
            range_header = self.headers.get("Range")
            start, end = 0, size - 1
            partial = False
            if range_header:
                match = RANGE_RE.match(range_header.strip())
                if match:
                    first, last = match.groups()
                    if first:
                        start = int(first)
                        end = int(last) if last else size - 1
                    elif last:
                        start = max(size - int(last), 0)
                    end = min(end, size - 1)
                    if start <= end:
                        partial = True

            length = end - start + 1
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", self.guess_type(path))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(path, "rb") as handle:
                handle.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    remaining -= len(chunk)
            return

        return super().do_GET()

    def log_message(self, *args):
        pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


with Server(("127.0.0.1", 8091), Handler) as httpd:
    httpd.serve_forever()
