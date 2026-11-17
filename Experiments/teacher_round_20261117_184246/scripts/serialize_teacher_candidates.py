"""Serialize individually authored Codex choices; no random/template generation."""
import datetime as dt,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]; ROOT=R.parents[1]
sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from action_config_schema import validate_training_config
from input_constraints import validate_instruction_constraints
from review_evidence import file_hash,canonical_hash
def a(r,ds,amp=1.0,hold=0.0):
    if not isinstance(ds,list): ds=[ds]
    amps=amp if isinstance(amp,list) else [amp]*len(ds)
    return {'resource_id':r+'.full' if r=='blink' else r+'.basic','cycles':[{'duration_ms':d,'controls':dict(hold_ratio=hold,**({} if r=='blink' else {'amplitude_scale':amps[i]}))} for i,d in enumerate(ds)]}
def ex(*steps):return {'version':'action-config.v0.2','decision':'execute','steps':[{'actions':s} for s in steps]}
def no(d):return {'version':'action-config.v0.2','decision':d,'steps':[]}
authored={
'train':[
('请眨眼两次，每次500毫秒，闭合后就睁开。',ex([a('blink',[500,500])])),
('表示答应，点头两次，每次720毫秒，动作干脆。',ex([a('nod',[720,720],1.1)])),
('用摇头表示拒绝，摇头一次，持续900毫秒。',ex([a('shake_head',900,1.0)])),
('摆出疑惑的样子，歪头一次，持续1200毫秒，中间稍作停留。',ex([a('tilt_head',1200,1.1,.35)])),
('寻找机房里的声音来源，左右张望一次，持续1300毫秒，连贯地看完再回正。',ex([a('look_around',1300,1.0,0)])),
('拍照时露出明显的微笑，微笑一次，持续1400毫秒。',ex([a('smile',1400,.98,.45)])),
('表演气呼呼地抗议，生气一次，持续1500毫秒。',ex([a('angry',1500,.98,.45)])),
('表演被戳穿后不好意思的神态，害羞一次，持续1600毫秒。',ex([a('shy',1600,1.1,.45)])),
('听到突如其来的警报，惊讶一次，持续1200毫秒。',ex([a('surprise',1200,1.1,.4)])),
('向刚来的朋友挥手打招呼，挥手两次，每次800毫秒。',ex([a('wave',[800,800],1.0)])),
('任务成功后举手欢呼一次，持续1400毫秒，举起后停留片刻。',ex([a('cheer',1400,1.05,.35)])),
('向前辈郑重行礼，鞠躬一次，持续1500毫秒。',ex([a('bow',1500,1.1,.38)])),
('刚睡醒确认消息：先眨眼一次，再点头一次。',ex([a('blink',600)],[a('nod',800,1.0)])),
('表现和好的情绪转折：先露出生气的表情，再微笑。',ex([a('angry',1400,.98,.4)],[a('smile',1400,.98,.45)])),
('先左右张望寻找朋友，找到后再挥手。',ex([a('look_around',1300,1.0)],[a('wave',900,1.05)])),
('道歉时先鞠躬，再露出害羞的神态。',ex([a('bow',1500,1.1,.35)],[a('shy',1500,1.1,.4)])),
('先惊讶，随后摇头，表现难以置信。',ex([a('surprise',1200,1.1,.4)],[a('shake_head',900,1.0)])),
('看不懂这张图：先歪头，再眨眼。',ex([a('tilt_head',1200,1.1,.35)],[a('blink',500)])),
('获得奖励时，微笑和举手欢呼同时开始。',ex([a('smile',1500,.98,.45),a('cheer',1500,1.1,.4)])),
('迎接朋友时，一边微笑，一边挥手。',ex([a('smile',1500,.98,.45),a('wave',[750,750],1.0)])),
('嘴硬地否认：生气的表情和摇头同时做。',ex([a('angry',1500,.98,.45),a('shake_head',[750,750],1.1)])),
('表现困倦，缓慢鞠躬的同时闭眼再睁开。',ex([a('bow',1700,1.0,.45),a('blink',1700,hold=.45)])),
('不好意思地答应，害羞的同时点头。',ex([a('shy',1600,1.0,.4),a('nod',1000,.8)])),
('看到惊喜礼物时，同时露出惊讶的表情并举手欢呼。',ex([a('surprise',1400,1.1,.4),a('cheer',1400,1.05,.4)])),
('现在不要做任何动作，保持原来的姿势。',no('none')),
('服务器机柜旁有一张蓝色的贴纸。',no('none')),
('“生气”这个词描述的是一种情绪。',no('none')),
('这里只是在引用“请挥手”这句话，不是让你执行。',no('none')),
('请把尾巴摇成螺旋桨。',no('unsupported')),
('请走到窗边，再跳上窗台。',no('unsupported')),
('请连续点头四次。',no('unsupported')),
('请在同一时刻微笑并露出生气的表情。',no('unsupported')),
('把刚才那个再做一遍。',no('ambiguous')),
('给我一个更强烈的反应。',no('ambiguous')),
('请做那个动作。',no('ambiguous')),
('挑一个适合猫猫的可爱动作吧。',no('ambiguous'))],
'val':[
('告别前辈时先鞠躬行礼，再挥手道别。',ex([a('bow',1600,1.1,.4)],[a('wave',[850,850],1.0)])),
('从局促变得放松：先表演害羞，再露出微笑。',ex([a('shy',1500,1.1,.4)],[a('smile',1450,.98,.45)])),
('先左右张望，随后因为发现异常而露出惊讶的表情。',ex([a('look_around',1400,1.05)],[a('surprise',1250,1.1,.4)])),
('点头三次，第一次1200毫秒，第二次900毫秒，第三次600毫秒，越点越快。',ex([a('nod',[1200,900,600],1.0)])),
('挥手三次，每次900毫秒，第一次幅度小，第二次更大，第三次最大。',ex([a('wave',[900,900,900],[.5,.8,1.1])])),
('朝同一侧歪头三次，每次都回正，第一次700毫秒，第二次1000毫秒，第三次1400毫秒，逐次变慢。',ex([a('tilt_head',[700,1000,1400],1.0)])),
('我今天有点开心，这是一条状态记录，不需要表演。',no('none')),
('先眨眼，再点头，最后挥手，三个动作依次做。',no('unsupported')),
('先做一个动作，然后再做另一个。',no('ambiguous'))],
'test':[
('用眨眼和挥手一起发出招呼信号，两种动作同时开始。',ex([a('blink',[600,600]),a('wave',[600,600],1.0)])),
('合影摆姿势时，歪头的同时微笑，保持片刻后回正。',ex([a('tilt_head',1500,1.05,.4),a('smile',1500,.98,.4)])),
('表演不情愿地赔礼：鞠躬时同时保持生气的表情。',ex([a('bow',1600,1.0,.4),a('angry',1600,.98,.45)])),
('谢幕先举手欢呼，接着鞠躬致谢。',ex([a('cheer',1500,1.1,.4)],[a('bow',1600,1.1,.4)])),
('先露出微笑，接着收起笑容左右张望，像是要去找人。',ex([a('smile',1400,.98,.4)],[a('look_around',1300,1.0)])),
('表现改口：先点头，回正后再摇头。',ex([a('nod',900,1.0)],[a('shake_head',1000,1.05)])),
('不要眨眼，也不要鞠躬，停在原位即可。',no('none')),
('请让身体朝左、朝右交替摇摆，不是反复朝同一侧歪头。',no('unsupported')),
('幅度改小一点，速度再慢一些。',no('ambiguous'))]}
plan=json.loads((R/'scenario_plan.json').read_text(encoding='utf-8'));rows=[];audits=[]
for split, data in authored.items():
    allocated=[p for p in plan['candidates'] if p['split']==split]
    assert len(allocated)==len(data)
    for p,(text,config) in zip(allocated,data):
        assert p['planned_decision']==config['decision'];validate_training_config(config)
        audit=validate_instruction_constraints(text,config);audits.append({'candidate_id':p['candidate_id'],**audit})
        rows.append({**p,'raw_text':text,'input_role':'instruction','config':config,'generation':{'provider':'OpenAI / Codex desktop','model':'Codex (exact backend model identifier not exposed)','context_id':'codex-desktop:/root:teacher_round_20261117_184246','prompt_version':'codex-teacher-round1.v1','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'prompt_sha256':file_hash(R/'prompts/generation_v1.md')},'provenance':{'source_split':split,'scenario_plan_sha256':file_hash(R/'scenario_plan.json'),'generation_source_file':str(Path(__file__).resolve()),'generation_source_sha256':file_hash(__file__)},'admission_status':'pending_independent_review','training_eligible':False})
with (R/'candidates.jsonl').open('x',encoding='utf-8') as f:
    for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
with (R/'reports/initial_constraint_audit.json').open('x',encoding='utf-8') as f:json.dump(audits,f,ensure_ascii=False,indent=2)
for name,selected in [('pilot',rows[:2]),('main',[r for r in rows[2:] if r['config']['decision']=='execute'])]:
    with (R/f'{name}_queue.jsonl').open('x',encoding='utf-8') as f:
        for r in selected:f.write(json.dumps({k:r[k] for k in ('candidate_id','parent_candidate_id','raw_text','input_role')}|{'decision':r['config']['decision'],'plan_json':json.dumps(r['config'],ensure_ascii=False,separators=(',',':'))},ensure_ascii=False)+'\n')
print(json.dumps({'candidates':len(rows),'issues':[a for a in audits if a['violations'] or a['unresolved']]},ensure_ascii=False,indent=2))
