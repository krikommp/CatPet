"""Serialize 54 individual root Codex teacher choices; no random label generation."""
import datetime as dt,json,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1]
sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from action_config_schema import validate_training_config
from input_constraints import validate_instruction_constraints
from review_evidence import file_hash
def a(r,ds,amp=1.,hold=0.):
    if not isinstance(ds,list):ds=[ds]
    amps=amp if isinstance(amp,list) else [amp]*len(ds)
    return {'resource_id':r+'.full' if r=='blink' else r+'.basic','cycles':[{'duration_ms':d,'controls':dict(hold_ratio=hold,**({} if r=='blink' else {'amplitude_scale':amps[i]}))} for i,d in enumerate(ds)]}
def ex(*steps):return {'version':'action-config.v0.2','decision':'execute','steps':[{'actions':s} for s in steps]}
def no(d):return {'version':'action-config.v0.2','decision':d,'steps':[]}
authored=[
('用眨眼发送短暗号：眨眼三次，每次450毫秒。',ex([a('blink',[450]*3)])),
('跟着节拍点头三次，每次700毫秒，每次都回正。',ex([a('nod',[700]*3)])),
('表达反对，摇头三次，每次750毫秒。',ex([a('shake_head',[750]*3,.85)])),
('歪头三次，每次800毫秒，幅度越来越小。',ex([a('tilt_head',[800]*3,[.9,.75,.55])])),
('巡视走廊，左右张望三次，每次900毫秒。',ex([a('look_around',[900]*3)])),
('拍三张表情练习照，微笑三次，每次900毫秒，中间恢复正常。',ex([a('smile',[900]*3,.98,.35)])),
('排练抗议表情，生气三次，每次1100毫秒，中间收起表情。',ex([a('angry',[1100]*3,.98,.35)])),
('练习不好意思的神态，害羞三次，每次1000毫秒。',ex([a('shy',[1000]*3,1.05,.35)])),
('排练听见警报的反应，惊讶三次，每次900毫秒。',ex([a('surprise',[900]*3,1.05,.35)])),
('发出手臂信号：挥手三次，每次750毫秒，右臂侧抬并张开手掌，再放回。',ex([a('wave',[750]*3,.8)])),
('让眼睛休息一下，眨眼一次，持续1200毫秒，闭上后停一会儿再睁开。',ex([a('blink',1200,hold=.4)])),
('轻轻表示确认，点头一次，持续1100毫秒，幅度小一些。',ex([a('nod',1100,.55)])),
('摇头两次，第一次600毫秒，第二次1100毫秒，后一次慢一些。',ex([a('shake_head',[600,1100],.85)])),
('歪头两次，每次900毫秒，幅度越来越大。',ex([a('tilt_head',[900,900],[.55,1.05])])),
('左右张望两次，第一次1000毫秒，第二次1600毫秒。',ex([a('look_around',[1000,1600])])),
('示范侧抬右臂并张开手掌的挥手动作一次，持续900毫秒，随后放回。',ex([a('wave',900,.7)])),
('收到好消息先点头两次，再露出微笑。',ex([a('nod',[600,600],.9)],[a('smile',1200,.98,.4)])),
('感谢鼓励，先微笑，再点头两次。',ex([a('smile',1200,.98,.4)],[a('nod',[600,600],.9)])),
('醒来突然听见警报：先眨眼两次，再露出惊讶表情。',ex([a('blink',[450,450])],[a('surprise',1100,1.05,.4)])),
('从震惊中缓过来，先惊讶，再眨眼两次。',ex([a('surprise',1100,1.05,.4)],[a('blink',[450,450])])),
('先摇头否认，再歪头思考。',ex([a('shake_head',850,.9)],[a('tilt_head',1100,1.,.3)])),
('先歪头思考，再摇头给出否定答案。',ex([a('tilt_head',1100,1.,.3)],[a('shake_head',850,.9)])),
('先露出生气表情，再左右张望寻找捣乱的人。',ex([a('angry',1300,.98,.4)],[a('look_around',1300)])),
('先左右张望检查周围，再露出生气表情。',ex([a('look_around',1300)],[a('angry',1300,.98,.4)])),
('先表演害羞，再眨眼两次调整心情。',ex([a('shy',1300,1.05,.4)],[a('blink',[450,450])])),
('先眨眼两次，再切换成害羞的表情。',ex([a('blink',[450,450])],[a('shy',1300,1.05,.4)])),
('先挥手，右臂侧抬、张开手掌再放回，随后点头确认。',ex([a('wave',900,.8)],[a('nod',800,.9)])),
('先点头确认，再挥手，右臂侧抬、张开手掌后放回。',ex([a('nod',800,.9)],[a('wave',900,.8)])),
('做个俏皮练习：眨眼和歪头同时开始，各做一次。',ex([a('blink',1000,hold=.3),a('tilt_head',1000,.9,.3)])),
('做眼睛与头部的配合练习，眨眼和摇头同时开始，各做两次。',ex([a('blink',[650,650]),a('shake_head',[650,650],.85)])),
('开心地赞同，点头和微笑同时开始。',ex([a('nod',1000,.9),a('smile',1300,.98,.4)])),
('带着笑意寻找朋友，左右张望和微笑同时开始。',ex([a('look_around',1400),a('smile',1400,.98,.4)])),
('惊讶地琢磨这个问题，歪头和惊讶表情同时开始。',ex([a('tilt_head',1300,.9,.35),a('surprise',1300,1.05,.35)])),
('带着害羞表情示范挥手，两者同时开始，右臂侧抬、张开手掌再放回。',ex([a('shy',1400,1.,.4),a('wave',1000,.8)])),
('用动作表示拒绝：摇头和挥手同时开始，挥手时右臂侧抬、张开手掌再放回。',ex([a('shake_head',1000,.9),a('wave',1000,.8)])),
('微笑着示范挥手，两者同时开始，右臂侧抬、张开手掌再放回。',ex([a('smile',1400,.98,.4),a('wave',1000,.8)])),
('接下来只听我说话，保持静止。',no('none')),
('刚才屏幕里的角色点了头，这是对录像的描述。',no('none')),
('现在不要微笑，保持原样就好。',no('none')),
('不要摇头，也不需要别的动作。',no('none')),
('监控面板显示连接状态正常。',no('none')),
('我在整理“点头”和“眨眼”这两个动作词的释义。',no('none')),
('请整个身体转过去，背对着我。',no('unsupported')),
('只闭左眼，右眼保持睁开，给我一个单眼眨眼。',no('unsupported')),
('请连续眨眼五次。',no('unsupported')),
('请点头与鞠躬同时开始并各自完整执行。',no('unsupported')),
('请眨眼和微笑同时开始并各自完整执行。',no('unsupported')),
('跳起来并在空中转身。',no('unsupported')),
('按这个节奏连续做，但我还没告诉你做哪个动作。',no('ambiguous')),
('第二个动作换一下。',no('ambiguous')),
('表情换成另一种情绪。',no('ambiguous')),
('照着上次那个示范再来。',no('ambiguous')),
('反应再有精神一点。',no('ambiguous')),
('做成我指的那个样子。',no('ambiguous'))]
plan=json.loads((R/'scenario_plan.json').read_text(encoding='utf-8'));assert len(authored)==len(plan['candidates'])==54
rows=[];audits=[]
for p,(text,config) in zip(plan['candidates'],authored):
    assert p['planned_decision']==config['decision'];validate_training_config(config)
    audit=validate_instruction_constraints(text,config);audits.append({'candidate_id':p['candidate_id'],**audit})
    rows.append({**p,'raw_text':text,'input_role':'instruction','config':config,'generation':{'provider':'OpenAI / Codex desktop','model':'Codex (exact backend model identifier not exposed)','context_id':'codex-desktop:/root:teacher_round2_20261117_192708','prompt_version':'codex-teacher-round2.v1','generated_at':dt.datetime.now(dt.timezone.utc).isoformat(),'prompt_sha256':file_hash(R/'prompts/generation_v1.md')},'provenance':{'source_split':'train','scenario_plan_sha256':file_hash(R/'scenario_plan.json'),'generation_source_file':str(Path(__file__).resolve()),'generation_source_sha256':file_hash(__file__)},'admission_status':'pending_independent_review','training_eligible':False})
for name,value in [('candidates.jsonl',rows),('reports/initial_constraint_audit.jsonl',audits)]:
    with (R/name).open('x',encoding='utf-8') as f:
        for row in value:f.write(json.dumps(row,ensure_ascii=False)+'\n')
issues=[a for a in audits if a['violations'] or a['unresolved']]
assert not issues,json.dumps(issues,ensure_ascii=False)
for batch,selected in [('pilot',rows[:2]),('main',rows[2:36])]:
    with (R/f'{batch}_queue.jsonl').open('x',encoding='utf-8') as f:
        for r in selected:f.write(json.dumps({k:r[k] for k in ('candidate_id','parent_candidate_id','raw_text','input_role')}|{'decision':'execute','plan_json':json.dumps(r['config'],ensure_ascii=False,separators=(',',':'))},ensure_ascii=False)+'\n')
print(json.dumps({'candidates':len(rows),'execute':36,'issues':issues},ensure_ascii=False))
