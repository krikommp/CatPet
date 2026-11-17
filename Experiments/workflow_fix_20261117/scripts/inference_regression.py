"""Regression against the actual HTTP handler, LocalEncoder and strict decoder.
The neural head is deterministic test data; no checkpoint is trained or replaced.
"""
import contextlib,copy,io,json,sys,tempfile,threading,urllib.request,urllib.error,unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from http.server import HTTPServer
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Tools/ActionEncoder'))
import torch
from action_config_schema import RESOURCE_IDS,RESOURCE_TO_ID,INPUT_POLICY_VERSION,ModelOutputError,canonicalize_config,decode_config,norm_log_duration,RESOURCE_SPECS
from input_constraints import validate_instruction_constraints
from encoder import LocalEncoder
from server import make_handler

def config(rid='nod.basic',durations=(600,),amps=None):
 if amps is None: amps=[1.0]*len(durations)
 return {'version':'action-config.v0.2','decision':'execute','steps':[{'actions':[{'resource_id':rid,'cycles':[{'duration_ms':d,'controls':{'hold_ratio':.2,**({'amplitude_scale':a} if rid!='blink.full' else {})}} for d,a in zip(durations,amps)]}]}]}

class Tokenizer:
 def __init__(self):self.seen=[]
 def encode(self,text,**kwargs):self.seen.append(text);return [1,2,3]
 def __call__(self,texts,**kwargs):self.seen.extend(texts);return {'input_ids':torch.ones(1,3,dtype=torch.long),'attention_mask':torch.ones(1,3,dtype=torch.long)}
class Backbone:
 def __call__(self,**kwargs):return SimpleNamespace(last_hidden_state=torch.zeros(1,3,256))
class Head:
 def __init__(self):self.scenario='normal';self.conditioned=None
 def forward_discrete(self,pooled):
  r=['blink.full','PAD'];st=[0,2];cnt=[1,0]
  if self.scenario=='conflict':r=['smile.basic','blink.full'];st=[0,0];cnt=[1,1]
  if self.scenario=='empty':r=['PAD','PAD']
  if self.scenario=='stage':st=[1,2]
  if self.scenario=='count':cnt=[0,0]
  out={'decision':torch.tensor([[9.,0,0,0]]),'resource_id':torch.zeros(1,2,len(RESOURCE_IDS)),'stage':torch.zeros(1,2,3),'cycle_count':torch.zeros(1,2,4),'h':torch.zeros(1,256)}
  for i in range(2):out['resource_id'][0,i,RESOURCE_TO_ID[r[i]]]=9;out['stage'][0,i,st[i]]=9;out['cycle_count'][0,i,cnt[i]]=9
  return out
 def forward_params(self,h,rids):
  self.conditioned=rids.tolist();out=torch.full((1,2,3,3),.5);out[0,0,:,0]=norm_log_duration(600,RESOURCE_SPECS['blink.full']);out[0,0,:,2]=.4
  if self.scenario=='nonfinite':out[0,0,0,0]=float('nan')
  return out

def fixture():
 e=LocalEncoder.__new__(LocalEncoder);e.torch=torch;e.config_head=Head();e.config_head_manifest={'capability_profile':'yukikaze.v1','resource_catalog_version':'yukikaze-resources.v0.2','parameter_schema_version':'action-config.v0.2','label_policy_version':'action-config-labels.v0.2','max_length':128,'model_version':'test-fixture'};e.tokenizer=Tokenizer();e.config_backbone=Backbone();e.model=e.config_backbone;return e

class Regression(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.encoder=fixture();cls.httpd=HTTPServer(('127.0.0.1',0),make_handler(cls.encoder));cls.url='http://127.0.0.1:'+str(cls.httpd.server_port)+'/configure';cls.thread=threading.Thread(target=cls.httpd.serve_forever,daemon=True);cls.thread.start()
 @classmethod
 def tearDownClass(cls):cls.httpd.shutdown();cls.httpd.server_close();cls.thread.join()
 def setUp(self):self.encoder.config_head.scenario='normal';self.encoder.config_head_manifest.pop('input_policy',None);self.encoder.tokenizer.seen.clear()
 def post(self,text='眨一次眼',role='instruction',extra=None):
  body={'request_id':'regression','text':text,'input_role':role,**{k:self.encoder.config_head_manifest[k] for k in ('capability_profile','resource_catalog_version','parameter_schema_version','label_policy_version')}};body.update(extra or {})
  req=urllib.request.Request(self.url,data=json.dumps(body,ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
  try:
   with urllib.request.urlopen(req,timeout=5) as response:return response.status,json.loads(response.read())
  except urllib.error.HTTPError as e:return e.code,json.loads(e.read())
 def test_http_legacy_unprefixed_echo_role(self):
  status,data=self.post();self.assertEqual(status,200);self.assertEqual(data['input_role'],'instruction');self.assertEqual(set(self.encoder.tokenizer.seen),{'眨一次眼'});self.assertEqual(self.encoder.config_head.conditioned,[[1,0]])
 def test_http_new_role_policy_prefix(self):
  self.encoder.config_head_manifest['input_policy']=INPUT_POLICY_VERSION;status,data=self.post('我再眨两次眼喵','dialogue');self.assertEqual(status,200);self.assertEqual(data['input_role'],'dialogue');self.assertEqual(set(self.encoder.tokenizer.seen),{'角色台词表演：我再眨两次眼喵'})
 def test_http_instruction_count_violation_is_422(self):
  status,data=self.post('眨两次眼');self.assertEqual(status,422);self.assertEqual(data['error']['code'],'model_output_invalid');self.assertTrue(data['constraint_audit']['violations']);self.assertEqual(data['raw_config']['steps'][0]['actions'][0]['resource_id'],'blink.full');self.assertEqual(len(data['raw_config']['steps'][0]['actions'][0]['cycles']),1);self.assertNotIn('config',data)
 def test_http_invalid_role_is_request_400(self):
  status,data=self.post(role='invalid');self.assertEqual(status,400);self.assertEqual(data['error']['code'],'invalid_request')
 def test_http_conflict_is_422_without_substitution(self):
  self.encoder.config_head.scenario='conflict';status,data=self.post(role='dialogue');self.assertEqual(status,422);self.assertEqual(data['error']['code'],'model_output_invalid');self.assertIn('conflict',data['error']['message']);self.assertEqual(self.encoder.config_head.conditioned,[[6,1]])
 def test_http_internal_invalid_predictions_never_none(self):
  for scenario in ('empty','stage','count','nonfinite'):
   with self.subTest(scenario=scenario):
    self.encoder.config_head.scenario=scenario;status,data=self.post(role='dialogue');self.assertEqual(status,422);self.assertEqual(data['error']['code'],'model_output_invalid');self.assertNotIn('config',data)
 def test_http_exact_duration_mismatch(self):
  status,data=self.post('眨一次眼，持续1秒钟');self.assertEqual(status,422);self.assertEqual(data['constraint_audit']['violations'][0]['expected'],1000)
 def test_http_unresolved_duration_scope(self):
  status,data=self.post('第二次用0.6秒');self.assertEqual(status,422);self.assertTrue(data['constraint_audit']['unresolved'])
 def test_http_dialogue_skips_instruction_numeric_guard(self):
  status,data=self.post('再来十二次喵','dialogue');self.assertEqual(status,200);self.assertIsNone(data['constraint_audit'])
 def test_http_idioms_are_not_numeric_quantities(self):
  for text in ('一边眨眼一边卖萌','轻一点眨眼','一起眨眼','稍等一下，眨眼'):
   with self.subTest(text=text):self.assertEqual(self.post(text)[0],200)
 def test_explicit_numeric_and_relative_regressions(self):
  rows=[('点头十二次',config()),('点头1.5次',config()),('点头一次，持续半秒',config()),('点头一次，持续六百毫秒',config(durations=(900,))),('点头两次，第二次幅度为0.5',config(durations=(600,600))),('点头两次，第二次用第一下的一半幅度',config(durations=(600,600))),('点头三次，第三次比第一次更慢',config(durations=(1200,600,900))),('点头三次，第二次比第三次慢一点',config(durations=(600,1000,1500))),('点头两次，第二次不要比第一次更重',config(durations=(600,600),amps=(.5,1))),('点头两次，不要越来越重',config(durations=(600,600),amps=(.5,1))),('只点头一次，第二次不要做',config(durations=(600,600))),('点头一次，持续-1秒',config(durations=(1000,)))]
  for text,c in rows:
   with self.subTest(text=text):
    r=validate_instruction_constraints(text,c);self.assertTrue(r['violations'] or r['unresolved'],r)
 def test_relative_explicit_reference_valid(self):
  r=validate_instruction_constraints('点头三次，第三次比第一次更慢',config(durations=(600,1200,900)));self.assertFalse(r['violations'] or r['unresolved']);self.assertEqual(r['checks'][-1]['reference_cycle_index'],0)
 def test_count_cannot_be_exempted_by_other_action_ordinal(self):
  c=config(durations=(600,600));c['steps'][0]['actions']+=config('wave.basic',durations=(600,900))['steps'][0]['actions'];r=validate_instruction_constraints('点头一次，同时挥手两次，第二次挥手更慢',c);self.assertEqual(r['violations'][0]['kind'],'cycle_count')
 def test_first_event_scope_and_monotonic_relations(self):
  for text,c in [('先用力点头一下，第二下轻一点',config(durations=(600,600),amps=(1,.5))),('连续点头三次，越来越慢',config(durations=(600,800,1000)))]:
   with self.subTest(text=text):
    r=validate_instruction_constraints(text,c);self.assertFalse(r['violations'] or r['unresolved'],r)
  for text,c in [('不要点头两次',config(durations=(600,600))),('点头一次，不要用0.6秒',config()),('点头两次，第二次比第一次轻',config(durations=(600,600),amps=(.5,1))),('先重后轻地点头两次',config(durations=(600,600),amps=(.5,1))),('连续点头三次，越来越慢',config(durations=(1000,800,600)))]:
   with self.subTest(text=text):
    r=validate_instruction_constraints(text,c);self.assertTrue(r['violations'] or r['unresolved'],r)
 def test_schema_rejects_invalid_labels(self):
  c=config(durations=(600,),amps=(2,));self.assertRaises(ValueError,canonicalize_config,c)
 def test_numeric_ordinals_bounds_and_approximations(self):
  for text in ('点头两次，第三次温柔些','点头两次以上','点头两次左右','大约点头两次','点头两次半','点头两次，每次600毫秒左右','点头两次，每次大约600毫秒','点头两次，每次600毫秒以下','点头两次，每次600毫秒半','点头两次，每次一分半','点头两次，频率五赫兹'):
   with self.subTest(text=text):
    r=validate_instruction_constraints(text,config(durations=(600,600)));self.assertTrue(r['violations'] or r['unresolved'],r)
  for text in ('一边点头一边微笑','点头时轻一点','一起点头','点头两次，第二次温柔些'):
   with self.subTest(text=text):
    r=validate_instruction_constraints(text,config(durations=(600,600)));self.assertFalse(r['violations'] or r['unresolved'],r)
 def test_legacy_diagnostic_roles_and_separate_technical_errors(self):
  import model_test
  e=fixture();e.config_head_manifest['checkpoint_id']='test-fixture';e.config_head_info={'can_generate_configs':True}
  with tempfile.TemporaryDirectory(dir=ROOT/'Experiments/workflow_fix_20261117') as temporary:
   p=Path(temporary);checkpoint=p/'checkpoint';checkpoint.mkdir();(checkpoint/'manifest.json').write_text(json.dumps(e.config_head_manifest),encoding='utf-8')
   rows=[{'raw_text':'眨十二次眼','input_role':role,'config':config('blink.full')} for role in ('instruction','dialogue')]
   dataset=p/'data.jsonl';dataset.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows),encoding='utf-8');report=p/'report.json'
   with patch.object(sys,'argv',['model_test.py','--checkpoint-dir',str(checkpoint),'--dataset',str(dataset),'--report',str(report)]),patch.object(model_test,'LocalEncoder',return_value=e),patch.object(model_test,'http_checks',return_value=[]),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(model_test.main(),1)
   result=json.loads(report.read_text(encoding='utf-8'));self.assertEqual(result['stage'],'legacy_diagnostic_only');self.assertEqual(len(result['technical_errors']),1);self.assertEqual(result['technical_errors'][0]['code'],'model_output_invalid');self.assertEqual(result['technical_errors'][0]['input_role'],'instruction');self.assertEqual(result['technical_errors'][0]['raw_config']['decision'],'execute');self.assertEqual(result['metrics']['decision']['confusion']['execute'],{'execute':1});self.assertFalse(result['assessment']['release_approved']);self.assertFalse(result['training_admission'])
  self.assertEqual(model_test.configure_request('你好',e.config_head_manifest,'role-test','dialogue')['input_role'],'dialogue');self.assertRaises(ValueError,model_test.configure_request,'你好',e.config_head_manifest,'role-test',None)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(Regression);result=unittest.TextTestRunner(verbosity=2).run(suite)
 report={'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),'real_http':True,'port_policy':'OS-assigned loopback; existing service untouched','neural_head':'deterministic fixture; actual LocalEncoder, decoder, guard and handler','trained':False}
 (ROOT/'Experiments/workflow_fix_20261117/reports/inference_regression.json').write_text(json.dumps(report,indent=2),encoding='utf-8');sys.exit(0 if result.wasSuccessful() else 1)
