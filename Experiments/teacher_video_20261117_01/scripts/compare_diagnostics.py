"""Compare saved predictions only. Does not run inference, train, or deploy."""
from pathlib import Path
import collections,hashlib,json,subprocess
R=Path(__file__).resolve().parents[1]
names=['baseline_legacy_fixed_eval','round9_legacy_fixed_eval','round9_strict_fixed_eval']
reports=[json.loads((R/f'reports/{n}.json').read_text(encoding='utf-8')) for n in names]
dataset_hash=hashlib.sha256((R/'data/fixed_eval.jsonl').read_bytes()).hexdigest()
assert all(x['dataset_sha256']==dataset_hash for x in reports),'Reports must use the final same frozen evaluation file.'
def stats(x):
    m=x['metrics'];return {'checkpoint':x['checkpoint_id'],'total':m['total'],
      'decision_correct':m.get('decision_correct',0),'execute_structure_correct':m.get('execute_structure_correct',0),'execute_total':m['gold_execute'],
      'none_false_execution':m.get('false_execute_none',0),'none_total':m['gold_none'],
      'unsupported_false_execution':m.get('false_execute_unsupported',0),'unsupported_total':m['gold_unsupported'],
      'ambiguous_false_execution':m.get('false_execute_ambiguous',0),'ambiguous_total':m['gold_ambiguous'],
      'technical_rejections':m.get('technical_errors',0),'objective_constraints_passed':m.get('objective_constraints_passed',0),
      'objective_constraints_total':m.get('objective_constraints_total',0),'unresolved_gold_rows':m.get('gold_scope_unresolved_rows',0)}
out={'dataset_sha256':dataset_hash,'runs':{n:stats(x) for n,x in zip(names,reports)},'model_trained_by_this_session':False,
     'warnings':['Small diagnostic sample; both checkpoints may have seen the semantic families.',
                 'Strict decoder is a behavior guard comparison, not a model quality improvement.',
                 'Rejections include conservative grammar limits and actual violations; inspect per-row evidence.',
                 'No new Unity playback or model-specific video score was obtained.',
                 'No deployment or ready designation.']}
native_checks={}
for name,report in zip(names[:2],reports[:2]):
    rows=report['predictions'];configs=R/f'reports/{name}_configs.jsonl'
    configs.write_text(''.join(json.dumps(x['predicted'],ensure_ascii=False)+'\n' for x in rows),encoding='utf-8')
    native_checks[name]={}
    for version in ('baseline','patched'):
        output=subprocess.run([str(R/f'scripts/compiler_{version}.exe'),str(configs)],capture_output=True,text=True,encoding='utf-8',check=True).stdout
        result=[json.loads(x) for x in output.splitlines() if x.strip()]
        native_checks[name][version]={'passed':sum(x['compile_ok'] for x in result),'total':len(result),'errors':dict(collections.Counter(x['error'] for x in result if not x['compile_ok']))}
        (R/f'reports/{name}_native_{version}.jsonl').write_text(''.join(json.dumps({**r,'raw_text':x['raw_text']},ensure_ascii=False)+'\n' for r,x in zip(result,rows)),encoding='utf-8')
out['actual_predicted_config_CSharp_checks']=native_checks
(R/'reports/round9_comparison.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
a,b,c=[stats(x) for x in reports]
kind_report=json.loads((R/'reports/code_audit_comparison.json').read_text(encoding='utf-8'))
assert kind_report['fixed_eval_sha256']==dataset_hash
def ratio(name,kinds):
    groups=kind_report[name]['constraints_by_kind']
    return str(sum(groups.get(k,{}).get('passed',0) for k in kinds))+'/'+str(sum(groups.get(k,{}).get('total',0) for k in kinds))
text=f'''# 第 9 轮辅助预测诊断

两个实际checkpoint：冻结基线 `{a['checkpoint']}` 与 Gemini 第9轮 `{b['checkpoint']}`。本会话未训练任何模型，未切换服务。三份结果使用同一最终28条文件，SHA256 `{dataset_hash}`。

| 指标 | 上一版，原解码器 | 第9轮，原解码器 | 第9轮，严格解码/指令检查 |
|---|---:|---:|---:|
| decision正确 | {a['decision_correct']}/28 | {b['decision_correct']}/28 | {c['decision_correct']}/28 |
| 执行结构正确 | {a['execute_structure_correct']}/14 | {b['execute_structure_correct']}/14 | {c['execute_structure_correct']}/14 |
| none误执行 | {a['none_false_execution']}/4 | {b['none_false_execution']}/4 | {c['none_false_execution']}/4 |
| unsupported误执行 | {a['unsupported_false_execution']}/6 | {b['unsupported_false_execution']}/6 | {c['unsupported_false_execution']}/6 |
| ambiguous误执行 | {a['ambiguous_false_execution']}/4 | {b['ambiguous_false_execution']}/4 | {c['ambiguous_false_execution']}/4 |
| 技术拒绝 | {a['technical_rejections']} | {b['technical_rejections']} | {c['technical_rejections']} |
| 已建立归属的客观约束通过 | {a['objective_constraints_passed']}/{a['objective_constraints_total']} | {b['objective_constraints_passed']}/{b['objective_constraints_total']} | {c['objective_constraints_passed']}/{c['objective_constraints_total']} |
| 精确时长约束 | {ratio(names[0],['exact_duration_ms'])} | {ratio(names[1],['exact_duration_ms'])} | {ratio(names[2],['exact_duration_ms'])} |
| 逐次/渐变关系约束 | {ratio(names[0],['relative','gradual_relative'])} | {ratio(names[1],['relative','gradual_relative'])} | {ratio(names[2],['relative','gradual_relative'])} |

第9轮在本小样本上的执行结构比上一版多对 {b['execute_structure_correct']-a['execute_structure_correct']} 条，仍有明确不支持动作被执行。严格版本的拒绝是保守检查结果，**不是模型准确率提升**；其中包括不满足明确数字/次数/关系、资源hold映射不足和语法作用域未覆盖。逐条保留拒绝前的预测及原因。严格版本不能据此直接替换在线行为。

该集合没有证明对已训练基线语义独立。文本新不代表语义族新；两版均可能见过这些族。1条固定题的跨分句数字作用域仍待解析。未被文本约束的时长/幅度不计参数MAE。没有新模型对应的Unity录像，不能从此结果声称视觉或自然度改善。

完整证据：`baseline_legacy_fixed_eval.json`、`round9_legacy_fixed_eval.json`、`round9_strict_fixed_eval.json`。各报告记录实际源码hash与限制。复现预测命令见 `code_audit.md`；仅重生成此比较表可运行 `scripts/compare_diagnostics.py`。

原始预测还逐条送入真实C#编译器（PreviewCandidate），原/修复编译结果保存在 `*_native_baseline.jsonl`、`*_native_patched.jsonl`，汇总见 `round9_comparison.json`。该项是离线编译检查，不能冒称Unity完整播放通过。
'''
(R/'reports/round9_comparison.md').write_text(text,encoding='utf-8')
print(json.dumps(out['runs'],ensure_ascii=False))
