import json, hashlib, statistics, importlib.util
from collections import Counter
from math import comb
from pathlib import Path

O = Path(__file__).resolve().parent
P = O.parent
load = lambda p: json.loads(p.read_text(encoding='utf-8-sig'))
# The existing frozen replay checks source hashes, all requests, matching,
# scientific denominators, and forbids socket/network access before extraction.
spec = importlib.util.spec_from_file_location('portable_fixed240', P/'replay.py')
portable = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portable)
base_proof = portable.replay()
original = portable.module(P/'process/tokenmatched-holdout240-20261008-independent-audit/audit.py', 'posthoc_original_audit')
tasks = load(P/'protocol/dataset.json')
events = [json.loads(line) for line in (P/'raw/combined-three-segments.jsonl').read_text(encoding='utf8').splitlines()]
records, starts = original.BASE.parse_journal(events)
rows = [original.inspect_item(task, records) for task in tasks]
# Response records remain in the unchanged journal; strip their duplicate
# working references exactly as in the original independent per-item export.
rows = [{k:v for k,v in row.items() if k not in ('primary_records','coarse_record')} for row in rows]
rows = json.loads(json.dumps(rows))
byid = {t['id']: t for t in tasks}
oracle = original.ORACLE
assert len(starts) == 1317
assert len([e for e in records.values() if e['status'] == 'ok']) == 1314

def comparison(rs):
    pairs = [(True, True) if r['status'] == 'initial_correct' else tuple(r['primary_pair']) for r in rs if r['status'] in ('initial_correct', 'complete_primary_pair')]
    b = sum(a and not c for a,c in pairs)
    c = sum(d and not a for a,d in pairs)
    return {'planned': len(rs), 'valid': len(pairs), 'missing': len(rs)-len(pairs), 'full_correct':sum(a for a,d in pairs),'neutral_correct':sum(d for a,d in pairs),'b': b,'c':c,'p_exact_two_sided': min(1,2*sum(comb(b+c,k) for k in range(min(b,c)+1))/2**(b+c)) if b+c else 1.0,'difference':(b-c)/len(pairs)}

cells=[]
for family in ('arithmetic','graph','sat'):
    for difficulty in ('easy','hard'):
        selected=[r for r in rows if byid[r['id']]['family']==family and byid[r['id']]['difficulty']==difficulty]
        cells.append({'family':family,'difficulty':difficulty,**comparison(selected)})
assert sum(c['b'] for c in cells)==12 and sum(c['c'] for c in cells)==1
phase = {}
for name in ('initial','probe','final'):
    es=[e for e in records.values() if e['status']=='ok' and e['call_key'].split(':')[2]==name]
    phase[name]={'successful_calls':len(es),'input':sum(e['usage']['prompt_tokens'] for e in es),'output':sum(e['usage']['completion_tokens'] for e in es),'cache_hit':sum(e['usage'].get('prompt_cache_hit_tokens',0) for e in es)}

prefix='tokenmatched-holdout240-20261008:'
paired=[]
for r in rows:
    if r['status'] != 'complete_primary_pair': continue
    fs=records[prefix+r['id']+':final:full']; ns=records[prefix+r['id']+':final:neutral']
    assert fs['status']==ns['status']=='ok'
    assert fs['usage']['prompt_tokens']==ns['usage']['prompt_tokens']==r['target_prompt_tokens']
    assert [oracle.score(byid[r['id']], fs['content'])[0], oracle.score(byid[r['id']], ns['content'])[0]] == r['primary_pair']
    paired.append({'id':r['id'],'family':byid[r['id']]['family'],'difficulty':byid[r['id']]['difficulty'],'full_output':fs['usage']['completion_tokens'],'neutral_output':ns['usage']['completion_tokens'],'output_difference':fs['usage']['completion_tokens']-ns['usage']['completion_tokens'],'input_each':fs['usage']['prompt_tokens'],'full_correct':r['primary_pair'][0],'neutral_correct':r['primary_pair'][1]})

def output_summary(ps):
    return {'pairs':len(ps),'full_output_sum':sum(r['full_output'] for r in ps),'neutral_output_sum':sum(r['neutral_output'] for r in ps),'full_output_mean':statistics.mean(r['full_output'] for r in ps),'neutral_output_mean':statistics.mean(r['neutral_output'] for r in ps),'paired_output_difference_mean':statistics.mean(r['output_difference'] for r in ps),'paired_output_difference_median':statistics.median(r['output_difference'] for r in ps),'output_difference_range':[min(r['output_difference'] for r in ps),max(r['output_difference'] for r in ps)],'total_input_each_arm':sum(r['input_each'] for r in ps)}
output = output_summary(paired)
output['by_cell']=[{'family':f,'difficulty':d,**output_summary([r for r in paired if r['family']==f and r['difficulty']==d])} for f in ('arithmetic','graph','sat') for d in ('easy','hard')]
equal_output = [r for r in paired if r['output_difference']==0]
output['post_hoc_equal_output_subset'] = {'pairs':len(equal_output),'b':sum(r['full_correct'] and not r['neutral_correct'] for r in equal_output),'c':sum(r['neutral_correct'] and not r['full_correct'] for r in equal_output),'scope':'Post-hoc conditioning on an outcome-related variable; descriptive sensitivity only, not a controlled causal estimate.'}
example_row=next(r for r in rows if r['status']=='complete_primary_pair' and r['primary_pair']==[True,False] and byid[r['id']]['family']=='sat')
eid=example_row['id']
example={'id':eid,'task':byid[eid],'independent_calibration':example_row,'initial':records[prefix+eid+':initial'],'full':records[prefix+eid+':final:full'],'neutral':records[prefix+eid+':final:neutral']}
# These scientific records contain no credentials; preserve exact messages and returned usage.
result={'status':'RAW240_INDEPENDENT_EXTRACTION_PASS','overall':comparison(rows),'six_cells':cells,'phase_success_usage':phase,'raw_started_calls':1317,'raw_successful_calls':1314,'paired_retry_output_tokens':output,'missing_cases':[{'id':r['id'],'status':r['status'],'details':r} for r in rows if r['status'] not in ('initial_correct','complete_primary_pair')],'source_sha256':{p.relative_to(P).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (P/'raw/combined-three-segments.jsonl',P/'protocol/dataset.json',P/'protocol/study.py',P/'replay.py',P/'process/tokenmatched-holdout240-20261008-independent-audit/audit.py')}}
# Check every numerical field, all missing-case classifications, and the exact
# selected task/prompt/request/response against the independently saved export.
expected = load(O/'evidence.json')
assert {k:v for k,v in result.items() if k != 'source_sha256'} == {k:v for k,v in expected.items() if k != 'source_sha256'}
assert example == load(O/'exact-prompt-example.json')
assert paired == load(O/'paired-output-tokens.json')
assert output['pairs'] == 150
assert (output['full_output_sum'], output['neutral_output_sum'], output['total_input_each_arm']) == (2608,2616,33512)
assert eid == 'sat-holdout240-easy-35'
assert sum(v['input'] for v in phase.values()) == 288383
assert sum(v['output'] for v in phase.values()) == 11438
assert sum(v['cache_hit'] for v in phase.values()) == 43120
proof = {'status':'PASS_PORTABLE_POSTHOC_ALL_NUMBERS_AND_EXACT_PROMPTS',
         'model_calls':0,'network_requests':0,'pairs':150,
         'full_output_sum':2608,'neutral_output_sum':2616,'input_each_arm':33512,
         'started_calls':1317,'successful_calls':1314,'six_cells':cells,
         'example_id':eid,'source_sha256':result['source_sha256'],
         'existing_public_replay_status':base_proof['status'],
         'saved_export_sha256':{name:hashlib.sha256((O/name).read_bytes()).hexdigest() for name in
                               ('evidence.json','exact-prompt-example.json','paired-output-tokens.json','six-cells.tex','evidence-notes.md')}}
(O/'replay-proof.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf8')
print(json.dumps({'status':proof['status'],'pairs':150,'started_calls':1317,'successful_calls':1314,'model_calls':0,'network_requests':0}))
