import http.server
import os
import socketserver

ROOT = r"H:\pass_project\multi_star_project\slides\dist"
os.chdir(ROOT)


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.translate_path(self.path)
        if not os.path.exists(path) or os.path.isdir(path):
            self.path = "/index.html"
        return super().do_GET()

    def log_message(self, *args):
        pass


with socketserver.TCPServer(("127.0.0.1", 8091), Handler) as httpd:
    httpd.serve_forever()
