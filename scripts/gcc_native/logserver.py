#!/usr/bin/env python3
"""Local server of gcc-native-calib-v1 (a copy of realtel_e2e/logserver.py with another description): serves page_gcc.html from this
directory, appends every POST /log line to OUT and writes a DONE marker when it receives done. Usage: logserver.py PORT OUT
"""
import http.server, os, sys
PORT, OUT = int(sys.argv[1]), sys.argv[2]; os.chdir(os.path.dirname(os.path.abspath(__file__)))
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        with open(OUT, "a") as f: f.write(b + "\n")
        if '"done":true' in b.replace(" ", ""): open(OUT + ".DONE", "w").write("1")
        self.send_response(204); self.end_headers()
http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
