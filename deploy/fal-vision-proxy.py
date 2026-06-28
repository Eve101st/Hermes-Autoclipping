#!/usr/bin/env python3
"""Loopback auth-rewriting reverse proxy: Hermes (Bearer) -> fal (Key).

Why: Hermes' vision aux uses an OpenAI client that sends
``Authorization: Bearer <FAL_KEY>``, but fal's OpenAI-compatible endpoint
(`https://fal.run/openrouter/router/openai/v1`) requires
``Authorization: Key <FAL_KEY>``. The main model still needs Bearer (OpenRouter),
so a global header override won't do — this proxy fixes the scheme for the vision
calls only.

It is a stateless, key-less scheme-rewriter: it swaps `Bearer ` -> `Key ` on the
Authorization header of whatever passes through and forwards to fal.run. Stdlib
only; binds loopback. Point Hermes' auxiliary.vision.base_url at
http://127.0.0.1:<port>/openrouter/router/openai/v1 with api_key=<FAL_KEY>.
"""
import http.client
import http.server
import os
import ssl

UPSTREAM = os.environ.get("FAL_PROXY_UPSTREAM", "fal.run")
PORT = int(os.environ.get("FAL_PROXY_PORT", "8089"))
_HOP = {"host", "content-length", "connection", "transfer-encoding", "keep-alive"}


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length) if length else b""
        headers = {}
        for k, v in self.headers.items():
            if k.lower() in _HOP:
                continue
            if k.lower() == "authorization" and v.lower().startswith("bearer "):
                v = "Key " + v[7:]
            headers[k] = v
        conn = http.client.HTTPSConnection(UPSTREAM, timeout=180,
                                           context=ssl.create_default_context())
        try:
            conn.request(self.command, self.path, body=body, headers=headers)
            resp = conn.getresponse()
            data = resp.read()
            self.send_response(resp.status)
            for k, v in resp.getheaders():
                if k.lower() in _HOP:
                    continue
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:  # noqa: BLE001 - return a gateway error to the client
            self.send_error(502, f"fal-vision-proxy: {e}")
        finally:
            conn.close()

    do_POST = _forward
    do_GET = _forward

    def log_message(self, *a):  # silence per-request stderr noise
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
