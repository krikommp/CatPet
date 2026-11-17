from pathlib import Path
import subprocess,json,hashlib,re,concurrent.futures,shutil,datetime
from PIL import Image,ImageDraw,ImageFont
ROOT=Path.cwd(); RUN=ROOT/'Experiments/teacher_video_20261117_01'; FF=Path(r'C:\Users\chenyifei\.codex\visualizations\2026\10\15\01a13f3f-3806-7061-aa03-4c3dfa56b899\Pets\Xuetuan\tools\python-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe')
SELECT='r1-002 r1-005 r1-006 r1-007 r2-001 r2-004 r2-005 r2-006 r2-007 r2-008 r4-001 r4-003 r4-007 r4-008 r6-006 r7-002 r7-004 r7-005 r7-006 r8-001 r8-003 r8-005 autovid-1 autovid-2'.split()
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
events=[json.loads(x) for x in (RUN/'input/Dataset/ActionCards/evaluations.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
completed={x['candidate_id'] for x in events if x.get('event_type')=='playback_completed'}
resource_hashes={str(p.relative_to(RUN)):sha(p) for p in (RUN/'input').rglob('*') if p.is_file() and (p.name in ['ActionResourceCatalog.cs','ActionConfigCompiler.cs','PreviewSession.cs'] or p.name=='yukikaze-resources.v0.2.json')}
def inspect(d):
 r={'candidate_id':d.name,'meta_present':(d/'meta.json').exists(),'video_present':(d/'preview.mp4').exists(),'completion_event_in_snapshot':d.name in completed}
 if r['meta_present']:
  m=json.loads((d/'meta.json').read_text(encoding='utf-8-sig')); r['meta_sha256']=sha(d/'meta.json'); r['raw_text']=m.get('raw_text'); r['meta_candidate_matches_dir']=m.get('candidate_id')==d.name
  for k in ['plan_json','native_json']:
   try: r[k.replace('_json','')]=json.loads(m.get(k,''))
   except: r[k.replace('_json','')]=None
  r['config_sha256']=hashlib.sha256(m.get('plan_json','').encode()).hexdigest();r['native_sha256']=hashlib.sha256(m.get('native_json','').encode()).hexdigest()
  r['metadata_playback_completed']=m.get('playback_completed');r['generator_source']={k:m.get(k) for k in ['provider_kind','provider_version','model_version','text_source']}; r['historical_resource_content_hash_present']=any(k in m for k in ['resource_hash','resource_catalog_hash','resource_catalog_sha256'])
 if r['video_present']:
  v=d/'preview.mp4';before=sha(v)
  p=subprocess.run([str(FF),'-hide_banner','-i',str(v),'-map','0:v:0','-f','null','-','-progress','pipe:1','-nostats'],capture_output=True,text=True)
  vals=dict(re.findall(r'^(\w+)=(.*)$',p.stdout,re.M));r.update(video_sha256=before,video_bytes=v.stat().st_size,stable_during_decode=before==sha(v),decode_returncode=p.returncode,decoded_frames=int(vals.get('frame',0)),decoded_duration_ms=int(vals.get('out_time_us',0))/1000)
  fps=re.search(r'(\d+(?:\.\d+)?) fps',p.stderr);r['fps']=float(fps.group(1)) if fps else None
  r['decode_error_lines']=[x for x in p.stderr.splitlines() if any(s in x.lower() for s in ['error','invalid','corrupt'])]
  expected=(r.get('native') or {}).get('duration_ms');r['native_duration_ms']=expected;r['duration_difference_ms']=r['decoded_duration_ms']-expected if expected is not None else None
  r['duration_plausible']=expected is not None and abs(r['decoded_duration_ms']-expected)<=200
 r['historical_binding_status']='unverifiable_resource_content_hash_missing'
 r['selected_for_visual_review']=d.name in SELECT
 return r
rows=list(concurrent.futures.ThreadPoolExecutor(max_workers=4).map(inspect,sorted((ROOT/'Dataset/ActionCards/snapshots').iterdir())))
(RUN/'reports/video_inventory.json').write_text(json.dumps({'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'ffmpeg':str(FF),'current_resource_hashes_for_comparison_only':resource_hashes,'rows':rows},ensure_ascii=False,indent=2),encoding='utf-8')
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
for cid in SELECT:
 d=ROOT/'Dataset/ActionCards/snapshots'/cid; out=RUN/'frames'/cid;out.mkdir(parents=True,exist_ok=True)
 evidence=RUN/'evidence'/cid;evidence.mkdir(parents=True,exist_ok=True)
 for name in ['meta.json','preview.mp4']:shutil.copy2(d/name,evidence/name)
 subprocess.run([str(FF),'-v','error','-i',str(evidence/'preview.mp4'),'-vsync','0',str(out/'f_%04d.png')],check=True)
 fs=list(sorted(out.glob('f_*.png')));cols=6;w=200;h=260
 sheet=Image.new('RGB',(cols*w,((len(fs)+cols-1)//cols)*h),(238,238,238));draw=ImageDraw.Draw(sheet)
 for i,f in enumerate(fs):
  im=Image.open(f).convert('RGB');im.thumbnail((200,233));x=(i%cols)*w;y=(i//cols)*h
  sheet.paste(im,(x+(w-im.width)//2,y));draw.text((x+3,y+235),f'{cid} f{i} {i/12:.3f}s',font=font,fill='black')
 sheet.save(RUN/'frames'/f'{cid}_all.png')
summary={'directories':len(rows),'meta':sum(r['meta_present'] for r in rows),'videos':sum(r['video_present'] for r in rows),'decode_ok':sum(r.get('decode_returncode')==0 for r in rows),'duration_plausible':sum(r.get('duration_plausible',False) for r in rows),'completion_events':sum(r['completion_event_in_snapshot'] for r in rows),'selected':len(SELECT)}
(RUN/'reports/video_inventory_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(summary)
print([(r['candidate_id'],r.get('decoded_frames'),r.get('duration_difference_ms'),r['completion_event_in_snapshot']) for r in rows if r['selected_for_visual_review']])
