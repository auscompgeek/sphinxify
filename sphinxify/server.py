import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from sphinxify.from_java import process, process_raw


class SphinxifyServer(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    index_html = b"""
        <!DOCTYPE html>
        <html>
            <head></head>
            <body>
            In: doxygen contents<br/>
            <textarea id="inbox" rows="20" cols="100"></textarea><br/>
            Out: python docstring<br/>
            <textarea id="outbox" rows="20" cols="100"></textarea><br/>
            Out: raw<br/>
            <textarea id="rawbox" rows="20" cols="100"></textarea>

            <script>

            function xfer() {
                let data = {inbox: inbox.value}
                fetch("/sphinxify", {
                    method: "POST",
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data),
                }).then(res => {
                    res.json().then(res => {
                        outbox.value = res.outbox;
                        rawbox.value = res.rawbox;
                    })
                });
            }

            inbox.oninput = inbox.onpropertychange = inbox.onpaste = xfer;
            xfer();

            </script>
        </html>
        """

    @classmethod
    def run(cls, port: int = 5678) -> None:
        server = HTTPServer(("127.0.0.1", port), cls)
        url = f"http://127.0.0.1:{port}/"
        print("Sphinxify server listening at", url)

        webbrowser.open(url)
        server.serve_forever()

    def do_GET(self) -> None:
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(self.index_html)))
            self.end_headers()
            self.wfile.write(self.index_html)
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/sphinxify":
            length = int(self.headers["content-length"])
            postdata = json.loads(self.rfile.read(length).decode("utf-8"))
            docstring = process(postdata["inbox"])
            raw = process_raw(postdata["inbox"])
            response = json.dumps({"outbox": docstring, "rawbox": raw})

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response.encode("utf-8"))
        else:
            self.send_error(404)


if __name__ == "__main__":
    SphinxifyServer.run()
