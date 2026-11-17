"""Summarize real artifacts; no synthetic results, model selection or promotion."""
import collections,datetime as dt,json,sys,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[1];ROOT=R.parents[1];sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
from review_evidence import file_hash,canonical_hash
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def jl(p):return [json.loads(x) for x in p.read_text(encoding='utf-8-sig').splitlines() if x.strip()]
def write(p,x):
    with p.open('x',encoding='utf-8') as f:json.dump(x,f,ensure_ascii=False,indent=2)
checkpoint=R/'checkpoint_epoch80';manifest=read(checkpoint/'manifest.json')
epochs=jl(checkpoint/'epoch_metrics.jsonl');assert len(epochs)==80
selected=epochs[manifest['best_epoch']-1]
evaluation=read(R/'reports/new_checkpoint_fixed_test.json')
prior=read(ROOT/'Experiments/teacher_round_20261117_184246/reports/completion_summary.json')
admission=read(R/'reports/admission_accepted_records.json')
protected=read(R/'protected_before.json')
after=[{'path':p,'before':h,'after':file_hash(p),'unchanged':file_hash(p)==h} for p,h in protected.items()]
assert all(x['unchanged'] for x in after)
rows=jl(R/'accepted_records.jsonl');old=jl(ROOT/'Experiments/teacher_round_20261117_184246/accepted_records.jsonl')
assert [r for r in rows if r['split']!='train']==[r for r in old if r['split']!='train']
health=json.load(urllib.request.urlopen('http://localhost:8765/health',timeout=10))
assert health['action_config_head']['checkpoint_id']=='838f2c1ac110'
comparison=prior['fixed_test_comparison']+[{'model':'teacher_round2','checkpoint_id':manifest['checkpoint_id'],**evaluation['metrics'],'raw_false_execution':evaluation['raw_prediction_metrics'].get('false_execution',0)}]
report={'completed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'training_completed':True,'epochs':80,'selected_epoch':manifest['best_epoch'],'optimizer_updates_total':manifest['optimizer_updates_total'],'selected_epoch_optimizer_updates':manifest['selected_epoch_optimizer_updates'],'checkpoint_id':manifest['checkpoint_id'],'checkpoint_dir':str(checkpoint.resolve()),'checkpoint_hashes':{n:file_hash(checkpoint/n) for n in ['manifest.json','config_head.pt','backbone_state.pt']},'admission':admission,'fixed_heldout_unchanged':True,'fixed_test_comparison':comparison,'new_test_raw_metrics':evaluation['raw_prediction_metrics'],'selected_epoch_train_fit':selected['predicted_resource_train_fit'],'selected_epoch_validation':selected['predicted_resource_validation'],'last_epoch_train_fit':epochs[-1]['predicted_resource_train_fit'],'protected_inputs':after,'service_health':health,'preview_isolation_check':read(R/'reports/preview_isolation_check.json'),'capture_quarantine':read(R/'reports/capture_quarantine.json'),'release_approved':False,'limitations':['Small 7-row fixed test; structure correctness is not visual naturalness or complete numeric correctness.','Only the new teacher demonstrations received independent visual review; model outputs are diagnostic predictions, not fresh video acceptance.','Exact duration binding deliberately accepts a small positive grammar and rejects other numeric contexts.','Round9 comparison is diagnostic, not proof of independence from its historical training set.','Default live service still uses round9; no automatic promotion.']}
write(R/'reports/completion_summary.json',report)
from retrain_and_eval import structure
failures=[r for r in evaluation['predictions'] if r.get('technical_error') or structure(r['predicted'])!=structure(r['expected'])]
with (R/'reports/fixed_test_failures.jsonl').open('x',encoding='utf-8') as f:
    for r in failures:f.write(json.dumps(r,ensure_ascii=False)+'\n')
m=evaluation['metrics'];raw=evaluation['raw_prediction_metrics'];train=selected['predicted_resource_train_fit']
text=f'''# 第二轮训练结果

本轮已完成80轮训练。训练、代码修复、录像问题和失败结果全部保留；本轮结束按用户要求提交 Git。

- 新教材接受 {admission['new_accepted']} 条，连同上一轮42条，共 {admission['accepted']} 条。训练 {manifest['train_count']} 条，验证8条，测试7条，旧验证/测试内容完全未改。
- 总共更新权重 {manifest['optimizer_updates_total']} 次；仅看验证集选择第 {manifest['best_epoch']} 轮（当时累计 {manifest['selected_epoch_optimizer_updates']} 次更新）。新模型 `{manifest['checkpoint_id']}`。
- 同样7道测试题：本轮动作/顺序/次数结构正确 {m.get('structure_correct',0)}/7；其中动作题 {m.get('execute_structure_correct',0)}/4。上一轮分别0/7、0/4；旧第9轮分别3/7、1/4。
- 不该执行的3题：原始模型误选执行 {raw.get('false_execution',0)}/3；最终放行的错误执行 {sum(m.get('false_execute_'+d,0) for d in ['none','unsupported','ambiguous'])}/3。技术拒绝 {m.get('technical_errors',0)}/7，单列，不当作理解正确。
- 选中模型在训练题上结构正确 {train.get('structure_correct',0)}/{train['total']}；这是背熟教材情况，不是泛化成绩。

## 本轮修复

1. 停顿单独学习“零停顿/有停顿”，有停顿只从引擎允许的范围产生；张望固定不增加中间停顿。
2. 明确的时长只在严格识别的肯定句式内绑定原文数字，并记录来源。模糊、否定或无关的数字拒绝，动作种类、顺序、次数仍由模型预测，不会为了凑答案替换。
3. 窗口预览和录像原来各放一个人物在同一位置，导致重影。改成每个预览有自己的独立场景和摄像机。真实双预览像素检查通过，创建/移动另一副本不会改变本摄像机画面。
4. 初始36段录像全部技术隔离；同样文字/动作创建新子版本，重新录制36段，并独立重新审核。72段及所有失败/修改关系都保留。

## 结果边界

只有7道重复使用的比较题，不能据此声称已经可靠，也不当作一套全新盲测。结构正确不等于每个动作幅度、时长和视觉效果都完美。本轮模型输出尚未逐条做新的视觉验收。详细错误见 reports/fixed_test_failures.jsonl，逐轮训练/验证记录在 checkpoint_epoch80。

本轮的挥手教材因“右臂”侧别不明确全部未获准入，训练仍只覆盖9种资源；挥手、欢呼、鞠躬仍缺合格训练教材。单独的“害羞三次”和“同时微笑张望”也未通过视觉审核，没有为凑数量降低标准。严格时长语法还有覆盖不足，具体见 reports/authored_train_representation.json。

窗口的默认服务仍是第9轮 `{health['action_config_head']['checkpoint_id']}`；新模型单独保存，没有自动替换。旧模型、旧测试、旧语料哈希均未改变。
'''
with (R/'ROUND_REPORT.md').open('x',encoding='utf-8') as f:f.write(text)
with (R/'PROGRESS.md').open('a',encoding='utf-8') as f:f.write(f"\n## Completed\n\n80 epochs finished; checkpoint {manifest['checkpoint_id']}, selected epoch {manifest['best_epoch']}; fixed-test structure {m.get('structure_correct',0)}/7. Full outcome in ROUND_REPORT.md. Git commit is the final requested step.\n")
print(json.dumps({k:report[k] for k in ['training_completed','selected_epoch','checkpoint_id','optimizer_updates_total']},ensure_ascii=False))
