"""CLI for local text encoding; --direct runs without the HTTP service."""
import argparse
import json
from pathlib import Path
import urllib.request

from encoder import DEFAULT_MODEL_DIR, LocalEncoder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("texts", nargs="+", help="One or more action phrases")
    parser.add_argument("--direct", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = {"texts": args.texts, "max_length": args.max_length}
    if args.direct:
        result = LocalEncoder(args.model_dir).encode(data)
    else:
        req = urllib.request.Request(f"http://127.0.0.1:{args.port}/encode",
                                     data=json.dumps(data, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.load(response)
    output = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
        print(f"Wrote {len(result['embeddings'])} x {result['hidden_size']} features to {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
