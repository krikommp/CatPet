"""Read-only compact display of every actual focused trajectory frame for review B."""
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
for cid in sys.argv[1:]:
    path = root / 'observations' / cid / 'observation_manifest.json'
    m = json.loads(path.read_text(encoding='utf-8-sig'))
    print(json.dumps({k: m[k] for k in ('candidate_id','raw_text','input_role','config','source_frame_count','every_frame_included','contact_sheets')}, ensure_ascii=False))
    frames = [json.loads(x) for x in Path(m['trajectory_focus']['path']).read_text(encoding='utf-8-sig').splitlines() if x.strip()]
    print('FRAME,VIDEO_MS,PLAYER_MS,STATE,' + ','.join(x['id'] for x in frames[0]['parameters']))
    for f in frames:
        print(','.join([str(f['frame_index']),f"{f['video_time_ms']:.2f}",f"{f['player_time_ms']:.2f}",str(f['state'])] + [f"{p['value']:.5g}" for p in f['parameters']]))
