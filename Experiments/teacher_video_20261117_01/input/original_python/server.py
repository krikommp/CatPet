"""Loopback-only MiniRBT HTTP service; start with the project Python environment."""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys

from encoder import (
    ActionHeadNotTrainedError,
    ConfigHeadNotTrainedError,
    DEFAULT_ACTION_HEAD_DIR,
    DEFAULT_CONFIG_HEAD_DIR,
    DEFAULT_MODEL_DIR,
    InputTooLongError,
    LocalEncoder,
    VersionMismatchError,
)

MAX_BODY_BYTES = 65536


def strict_json(raw: bytes) -> object:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key.")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite JSON values are forbidden.")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=invalid_constant)


def make_handler(encoder):
    class Handler(BaseHTTPRequestHandler):
        server_version = "PetLocalEncoder/1.0"

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def log_message(self, fmt, *args):
            # Do not log request bodies or text contents.
            sys.stderr.write("[action-encoder] " + fmt % args + "\n")

        def send_json(self, status, data):
            payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

        def error(self, status, code, message):
            self.send_json(status, {"error": {"code": code, "message": message}})

        def allowed_origin(self):
            # No browser cross-origin requests; native Unity/Python clients omit Origin.
            if self.headers.get("Origin"):
                self.error(403, "origin_forbidden", "Use the native local client.")
                return False
            return True

        def do_GET(self):
            if not self.allowed_origin():
                return
            if self.path == "/health":
                self.send_json(200, encoder.health())
            else:
                self.error(404, "not_found", "Available endpoints: GET /health, POST /encode.")

        def do_POST(self):
            if not self.allowed_origin():
                return
            if self.path not in ("/encode", "/plan", "/configure"):
                self.error(404, "not_found", "Available endpoints: GET /health, POST /encode, POST /plan, POST /configure.")
                return
            if self.headers.get_content_type() != "application/json":
                self.error(415, "content_type", "Use Content-Type: application/json.")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY_BYTES:
                    self.error(413, "body_size", "JSON body must be 1 to 65536 bytes.")
                    return
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("Incomplete request body.")
                data = strict_json(raw)
                if self.path == "/plan":
                    result = encoder.plan(data)
                elif self.path == "/configure":
                    result = encoder.configure(data)
                else:
                    result = encoder.encode(data)
            except ActionHeadNotTrainedError as exc:
                self.error(409, "action_head_not_trained", str(exc))
                return
            except ConfigHeadNotTrainedError as exc:
                self.error(409, "config_head_not_trained", str(exc))
                return
            except InputTooLongError as exc:
                self.error(400, "input_too_long", str(exc))
                return
            except VersionMismatchError as exc:
                self.error(400, "version_mismatch", str(exc))
                return
            except (ValueError, UnicodeDecodeError) as exc:
                self.error(400, "invalid_request", str(exc))
                return
            except TimeoutError:
                self.error(408, "request_timeout", "Request body timed out.")
                return
            except Exception as exc:
                sys.stderr.write(f"[action-encoder] inference failed: {type(exc).__name__}\n")
                self.error(500, "inference_failed", "Local inference failed; check service logs.")
                return
            self.send_json(200, result)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--action-head-dir", type=Path, default=DEFAULT_ACTION_HEAD_DIR)
    parser.add_argument("--config-head-dir", type=Path, default=DEFAULT_CONFIG_HEAD_DIR)
    parser.add_argument("--threads", type=int, choices=range(1, 17), default=2)
    args = parser.parse_args()
    encoder = LocalEncoder(
        args.model_dir, args.threads,
        action_head_dir=args.action_head_dir,
        config_head_dir=args.config_head_dir,
    )
    httpd = HTTPServer(("127.0.0.1", args.port), make_handler(encoder))
    print(json.dumps({"url": f"http://127.0.0.1:{args.port}", **encoder.health()}, ensure_ascii=False), flush=True)
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
