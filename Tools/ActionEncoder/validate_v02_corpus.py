"""Validate an LLM-generated or human-exported action-config.v0.2 JSONL corpus before training."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from action_config_schema import CONFIG_VERSION, RESOURCE_SPECS, canonicalize_config


def load_channels_map() -> dict[str, set[str]]:
    catalog_path = Path(__file__).resolve().parents[2] / "Docs" / "ActionLanguage" / "profiles" / "yukikaze-resources.v0.2.json"
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    return {rid: set(spec["channels"]) for rid, spec in data["resources"].items()}


def validate_file(path: Path) -> tuple[int, list[str]]:
    channels_map = load_channels_map()
    errors: list[str] = []
    valid = 0

    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
            text = (row.get("raw_text") or "").strip()
            if not text:
                raise ValueError("empty raw_text")
            if not row.get("group_id"):
                raise ValueError("missing group_id")
            cfg = row.get("config") if isinstance(row.get("config"), dict) else json.loads(row["config_json"])
            if cfg.get("version") != CONFIG_VERSION:
                raise ValueError(f"version must be {CONFIG_VERSION}")

            # Validate parameter ranges and parallel channel conflicts
            if cfg.get("decision") == "execute":
                for step in cfg.get("steps") or []:
                    used_channels: set[str] = set()
                    for act in step.get("actions") or []:
                        rid = act["resource_id"]
                        spec = RESOURCE_SPECS[rid]
                        overlap = used_channels & channels_map[rid]
                        if overlap:
                            raise ValueError(f"parallel channel conflict on {sorted(overlap)}")
                        used_channels |= channels_map[rid]
                        for cyc in act.get("cycles") or []:
                            dur = int(cyc["duration_ms"])
                            if not spec["min_dur"] <= dur <= spec["max_dur"]:
                                raise ValueError(f"{rid} duration_ms={dur} out of [{spec['min_dur']}, {spec['max_dur']}]")
                            ctrls = cyc.get("controls") or {}
                            if not spec["supports_amp"] and "amplitude_scale" in ctrls:
                                raise ValueError(f"{rid} must not include amplitude_scale")
                            if spec["supports_amp"]:
                                amp = float(ctrls["amplitude_scale"])
                                if not spec["min_amp"] <= amp <= spec["max_amp"]:
                                    raise ValueError(f"{rid} amplitude_scale={amp} out of [{spec['min_amp']}, {spec['max_amp']}]")
                            if spec["supports_hold"]:
                                hold = float(ctrls["hold_ratio"])
                                if not spec["min_hold"] <= hold <= spec["max_hold"]:
                                    raise ValueError(f"{rid} hold_ratio={hold} out of [{spec['min_hold']}, {spec['max_hold']}]")

            canonicalize_config(cfg)
            valid += 1
        except Exception as exc:
            errors.append(f"Line {line_no}: {exc}")
    return valid, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    valid, errs = validate_file(args.corpus)
    print(f"Valid samples: {valid}, Errors: {len(errs)}")
    for e in errs[:20]:
        print("  ERR:", e)
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    main()
