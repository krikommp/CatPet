"""Build exhaustive observation artifacts from completed real capture batches.

This performs physical evidence validation and deterministic video extraction only.
It neither observes/approves semantics nor writes review scores or training admission.
Existing completed or incomplete outputs are never overwritten.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROUND = Path(__file__).resolve().parents[1]
ROOT = ROUND.parents[1]
sys.path.insert(0, str(ROOT / "Tools/ActionEncoder"))

from review_evidence import (EvidenceError, canonical_hash, file_hash, find_ffmpeg,
                             require, strict_json, validate_capture_only)
from action_config_schema import RESOURCE_CHANNELS


def pillow_modules():
    """Allow the installed base interpreter's Pillow without altering the venv."""
    try:
        import PIL
    except ModuleNotFoundError as error:
        if error.name != "PIL":
            raise
        base_sites = Path(sys.base_prefix) / "Lib/site-packages"
        require((base_sites / "PIL/__init__.py").is_file(),
                "Pillow is unavailable in the venv and its base interpreter")
        sys.path.insert(0, str(base_sites))
        try:
            PIL = importlib.import_module("PIL")
        finally:
            sys.path.remove(str(base_sites))
    from PIL import Image, ImageDraw, ImageFont
    return PIL, Image, ImageDraw, ImageFont


def read_json(path):
    return strict_json(Path(path).read_text(encoding="utf-8-sig"))


def read_jsonl(path):
    return [strict_json(line) for line in Path(path).read_text(encoding="utf-8-sig").splitlines()
            if line.strip()]


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def resolved(path, base):
    path = Path(path)
    return (path if path.is_absolute() else base / path).resolve()


def artifact(path, published_path=None):
    return {"path": str((published_path or path).resolve()),
            "sha256": file_hash(path), "bytes": path.stat().st_size}


def check_batch(batch):
    done_path = ROUND / f"{batch}_done.json"
    require(done_path.is_file(), f"Batch report is absent: {done_path}")
    done = read_json(done_path)
    items = done.get("items")
    require(done.get("finished") is True, "Batch is not finished; no observation artifacts created")
    require(isinstance(items, list) and bool(items), "Finished batch has no items")
    require(done.get("failed") == 0 and done.get("total") == done.get("completed") == len(items),
            "Batch completion counts disagree or contain failed items")
    require(all(item.get("ok") is True and not item.get("error") for item in items),
            "Every item must have ok=true and no error")
    # The teacher may have corrected an unrecorded queue into a new immutable v2 file.
    queues = [path for path in ROUND.glob(f"{batch}_queue*.jsonl")
              if file_hash(path) == done.get("queue_sha256")]
    require(len(queues) == 1, "Cannot uniquely identify the actual queue by done.queue_sha256")
    queue_path = queues[0]
    queue = read_jsonl(queue_path)
    require(len(queue) == len(items), "Actual queue and done report have different lengths")
    snapshot_root = resolved(done["snapshot_root"], ROUND)
    require(snapshot_root.is_relative_to(ROUND) and snapshot_root.is_dir(),
            "Snapshot root is absent or outside this experiment")
    ids = set()
    for item, queued in zip(items, queue):
        cid = item.get("candidate_id")
        require(isinstance(cid, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", cid),
                "Invalid candidate id")
        require(cid not in ids, "Duplicate candidate id")
        ids.add(cid)
        require(cid == queued.get("candidate_id") and item.get("raw_text") == queued.get("raw_text"),
                "Done item does not bind to its actual queue entry")
        evidence_path = resolved(item["evidence_path"], ROUND)
        require(evidence_path.parent == snapshot_root / cid and evidence_path.is_file(),
                "Evidence is not in the candidate's actual snapshot directory")
        target = ROUND / "observations" / cid
        staging = target.with_name(f".{cid}.incomplete")
        require(not target.exists() and not staging.exists(),
                f"Refusing to overwrite existing observation output: {target} / {staging}")
    return done_path, done, queue_path, queue


def build_candidate(item, queued, done_path, queue_path, ffmpeg, modules):
    PIL, Image, ImageDraw, ImageFont = modules
    cid = item["candidate_id"]
    evidence_path = resolved(item["evidence_path"], ROUND)
    evidence = read_json(evidence_path)
    metadata_path = evidence_path.parent / "meta.json"
    metadata = read_json(metadata_path)
    config = strict_json(evidence["config_json"])
    require(canonical_hash(config) == canonical_hash(strict_json(queued["plan_json"])),
            "Captured config does not match actual queue config")
    for key in ("candidate_id", "parent_candidate_id", "input_role", "raw_text"):
        require(metadata.get(key, "") == queued.get(key, ""), f"Metadata/queue {key} mismatch")
    video_path = resolved(evidence["video_file"], evidence_path.parent)
    trajectory_path = resolved(evidence["trajectory_file"], evidence_path.parent)
    require(resolved(item["video_path"], ROUND) == video_path, "Done video path mismatch")
    persona_path = resolved(evidence["persona_path"], ROOT)
    integrity = validate_capture_only(
        evidence_path, metadata_path=metadata_path, ffmpeg_path=ffmpeg,
        persona_file=persona_path,
        compiler_file=ROOT / "Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs",
        resource_file=ROOT / "Assets/Scripts/ActionLanguage/ActionResourceCatalog.cs",
        native_profile_file=ROOT / "Assets/Scripts/ActionLanguage/YukikazeActionCatalog.cs")
    require(integrity["valid"] is True and integrity["ai_reviewed"] is False and
            integrity["training_eligible"] is False, "Unexpected capture-only result")
    trajectory = read_jsonl(trajectory_path)
    frame_count = evidence["frame_count"]
    require(len(trajectory) == frame_count == integrity["decoded_frames"], "Source frame counts disagree")
    resources = sorted({action["resource_id"] for step in config["steps"] for action in step["actions"]})
    channels = sorted(set().union(*(RESOURCE_CHANNELS[rid] for rid in resources)))
    focus = []
    for index, frame in enumerate(trajectory):
        require(frame["frame_index"] == index, "Noncontiguous trajectory")
        params = frame["parameters"]
        values = {param["id"]: param["value"] for param in params}
        require(len(values) == len(params), "Duplicate trajectory parameter id")
        require(set(channels).issubset(values), f"Frame {index} omits required resource channels")
        focus.append({"frame_index": index, "video_time_ms": frame["video_time_ms"],
                      "player_time_ms": frame["player_time_ms"], "state": frame.get("state"),
                      "parameters": [{"id": key, "value": values[key]} for key in channels]})
    watched_sources = {Path(entry["source_path"]): entry["sha256"] for entry in integrity["artifacts"]}
    watched_sources.update({done_path: file_hash(done_path), queue_path: file_hash(queue_path),
                            ffmpeg: file_hash(ffmpeg), Path(__file__).resolve(): file_hash(__file__)})
    target = ROUND / "observations" / cid
    staging = target.with_name(f".{cid}.incomplete")
    staging.mkdir(parents=True, exist_ok=False)
    (staging / "frames").mkdir()
    (staging / "contact_sheets").mkdir()
    command = [str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
               "-err_detect", "explode", "-i", str(video_path), "-map", "0:v:0", "-vsync", "0",
               "-start_number", "0", "-n", str(staging / "frames/frame_%06d.png")]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    require(result.returncode == 0 and not result.stderr.strip(),
            "Full-resolution frame extraction failed: " + result.stderr[:500])
    frames = sorted((staging / "frames").glob("frame_*.png"))
    require(len(frames) == frame_count and
            [path.name for path in frames] == [f"frame_{index:06d}.png" for index in range(frame_count)],
            "Extracted frames do not exactly cover the source video")
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font = ImageFont.truetype(str(font_path), 14) if font_path.is_file() else ImageFont.load_default()
    heading_font = ImageFont.truetype(str(font_path), 18) if font_path.is_file() else font
    with Image.open(frames[0]) as first:
        width, height = first.size
    # Preserve the ENTIRE frame; choose dimensions with both minima satisfied.
    scale = max(180 / width, 210 / height)
    thumb_width, thumb_height = math.ceil(width * scale), math.ceil(height * scale)
    label_height, header_height = 42, 52
    tile_height = thumb_height + label_height
    page_specs = []
    frame_specs = []
    for page_index, start in enumerate(range(0, frame_count, 36)):
        end = min(start + 36, frame_count)
        sheet = Image.new("RGB", (6 * thumb_width, header_height + 6 * tile_height), "#d7d7d7")
        draw = ImageDraw.Draw(sheet)
        draw.text((8, 5), f"{cid} | page {page_index + 1} | EVERY frame {start}..{end - 1}",
                  fill="black", font=heading_font)
        draw.text((8, 29), f"video {trajectory[start]['video_time_ms']:.1f}..{trajectory[end - 1]['video_time_ms']:.1f} ms | no frames skipped",
                  fill="black", font=font)
        for index in range(start, end):
            path = frames[index]
            with Image.open(path) as original:
                original.load()
                require(original.size == (width, height), "Video frame dimensions changed")
                thumb = original.convert("RGB").resize((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            local = index - start
            x, y = (local % 6) * thumb_width, header_height + (local // 6) * tile_height
            sheet.paste(thumb, (x, y))
            draw.text((x + 4, y + thumb_height + 3), f"frame {index:04d} | v={trajectory[index]['video_time_ms']:.1f}ms",
                      fill="black", font=font)
            draw.text((x + 4, y + thumb_height + 22), f"player={trajectory[index]['player_time_ms']:.1f}ms",
                      fill="black", font=font)
            frame_specs.append({**artifact(path, target / "frames" / path.name), "frame_index": index,
                                "video_time_ms": trajectory[index]["video_time_ms"],
                                "player_time_ms": trajectory[index]["player_time_ms"]})
        page_name = f"page_{page_index + 1:03d}.png"
        page_path = staging / "contact_sheets" / page_name
        sheet.save(page_path, format="PNG")
        page_specs.append({**artifact(page_path, target / "contact_sheets" / page_name),
                           "page_index": page_index, "first_frame_index": start,
                           "last_frame_index": end - 1, "frame_count": end - start,
                           "video_time_start_ms": trajectory[start]["video_time_ms"],
                           "video_time_end_ms": trajectory[end - 1]["video_time_ms"],
                           "player_time_start_ms": trajectory[start]["player_time_ms"],
                           "player_time_end_ms": trajectory[end - 1]["player_time_ms"]})
    focus_path = staging / "trajectory_focus.jsonl"
    with focus_path.open("x", encoding="utf-8") as stream:
        for frame in focus:
            stream.write(json.dumps(frame, ensure_ascii=False, allow_nan=False) + "\n")
    integrity_path = staging / "physical_integrity_report.json"
    write_json(integrity_path, integrity)
    require(all(file_hash(path) == digest for path, digest in watched_sources.items()),
            "Source evidence/bindings changed while building observations")
    manifest = {
        "schema_version": "teacher-observation-artifacts.v1", "candidate_id": cid,
        "stage": "observation_artifacts_only", "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "ai_reviewed": False, "training_eligible": False, "release_approved": False,
        "raw_text": metadata["raw_text"], "input_role": metadata["input_role"], "config": config,
        "config_sha256": canonical_hash(config), "source_frame_count": frame_count,
        "decoded_frame_count": integrity["decoded_frames"], "extracted_frame_count": len(frames),
        "trajectory_frame_count": len(trajectory), "focused_trajectory_frame_count": len(focus),
        "contact_sheet_frame_count": sum(page["frame_count"] for page in page_specs),
        "every_frame_included": True, "resource_ids": resources, "focused_parameter_ids": channels,
        "source_dimensions": {"width": width, "height": height},
        "thumbnail_dimensions": {"width": thumb_width, "height": thumb_height},
        "sheet_layout": {"columns": 6, "rows": 6, "cropping": False, "timestamp_unit": "ms"},
        "evidence": artifact(evidence_path), "video": artifact(video_path),
        "full_trajectory": artifact(trajectory_path), "metadata": artifact(metadata_path),
        "done_report": artifact(done_path), "queue": artifact(queue_path),
        "physical_integrity_report": artifact(integrity_path, target / integrity_path.name),
        "trajectory_focus": artifact(focus_path, target / focus_path.name),
        "contact_sheets": page_specs, "full_resolution_frames": frame_specs,
        "tooling": {"builder": artifact(Path(__file__).resolve()), "ffmpeg": artifact(ffmpeg),
                    "pillow_version": PIL.__version__, "pillow_module": str(Path(PIL.__file__).resolve())},
        "limitations": ["These artifacts do not establish actual AI observation or acceptance.",
                        "Contact sheets retain all frames at reduced resolution; full-resolution frames and full trajectory are available."]}
    write_json(staging / "observation_manifest.json", manifest)
    require(not target.exists(), "Target appeared during processing; refusing replacement")
    staging.rename(target)
    return {"candidate_id": cid, "frames": frame_count, "pages": len(page_specs),
            "observation_manifest": str(target / "observation_manifest.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", choices=("pilot", "main", "revision", "fixpilot", "fixmain"), required=True)
    parser.add_argument("--ffmpeg", type=Path)
    args = parser.parse_args()
    done_path, done, queue_path, queue = check_batch(args.batch)
    ffmpeg = find_ffmpeg(args.ffmpeg)
    modules = pillow_modules()
    for item, queued in zip(done["items"], queue):
        report = build_candidate(item, queued, done_path, queue_path, ffmpeg, modules)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    print(json.dumps({"batch": args.batch, "complete": True, "candidates": len(queue),
                      "ai_reviewed": False, "training_eligible": False}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (EvidenceError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"complete": False, "error": str(error), "ai_reviewed": False,
                          "training_eligible": False}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
