"""Portable three-segment fixed240 pure audit replay; stdlib and no network."""
import argparse,hashlib,importlib.util,json,socket
from pathlib import Path
ROOT=Path(__file__).resolve().parent
load=lambda p:json.loads(p.read_text(encoding='utf-8-sig'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def no_network(*a,**k):raise RuntimeError('Network forbidden in scientific replay')
socket.create_connection=no_network
socket.socket.connect=no_network
socket.socket.connect_ex=no_network
socket.getaddrinfo=no_network

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def replay():
    manifest=load(ROOT/'public-manifest.json')
    for name,value in manifest['files'].items():
        path=(ROOT/name).resolve()
        assert path.is_relative_to(ROOT.resolve()) and sha(path)==value
    original=module(ROOT/'process/tokenmatched-holdout240-20261008-independent-audit/audit.py','original_fixed240_audit')
    tasks=load(ROOT/'protocol/dataset.json')
    regenerated,seeds=original.regenerated(load(ROOT/'protocol/excluded756.json'))
    assert tasks==regenerated and seeds==load(ROOT/'protocol/manifest.json')['seeds']
    for task in tasks:
        assert original.ORACLE.initial_prompt(task)==task['prompt']
        assert original.ORACLE.fingerprint(task)==task['instance_sha256']
        assert original.ORACLE.score(task,json.dumps(task['oracle']))==(True,None)
    paths=[ROOT/f'raw/segment{i}-calls.jsonl' for i in (1,2,3)]
    assert (ROOT/'raw/combined-three-segments.jsonl').read_bytes()==b''.join(p.read_bytes() for p in paths)
    records,starts,ids={},[],set()
    segments=[]
    for path in paths:
        local,order=original.BASE.parse_journal([json.loads(line) for line in path.read_text(encoding='utf8').splitlines()])
        assert records.keys().isdisjoint(local)
        response_ids={r['response_id'] for r in local.values() if r['status']=='ok'}
        assert ids.isdisjoint(response_ids)
        records.update(local);starts.extend(order);ids.update(response_ids);segments.append(local)
    attempted={k[len(original.PREFIX):].split(':',1)[0] for k in set(segments[0])|set(segments[1])}
    eligible=[t['id'] for t in tasks if t['id'] not in attempted]
    assert len(attempted)==105 and len(eligible)==135 and eligible==load(ROOT/'protocol/eligible-ids.json')
    assert all(k[len(original.PREFIX):].split(':',1)[0] in eligible for k in segments[2])
    items=[original.inspect_item(task,records) for task in tasks]
    assert {k for item in items for k in item['checked_keys']}==records.keys()
    assert starts==[k for item in items for k in item['checked_keys']]
    science=original.estimands(tasks,items)
    expected=load(ROOT/'expected-summary.json')
    for key,value in science.items():assert value==expected[key],key
    pairs=[item['primary_pair'] for item in items if 'primary_pair' in item]
    counts={'full_correct':sum(p[0] for p in pairs),'neutral_correct':sum(p[1] for p in pairs)}
    assert counts==expected['primary_correct_counts']=={'full_correct':104,'neutral_correct':93}
    bootstrap=module(ROOT/'bootstrap/paired_bootstrap.py','registered_bootstrap')
    registration=load(ROOT/'bootstrap/registration.json')
    assert registration['replicates']==10000 and registration['seed']==20261008
    assert registration['holdout_files']['dataset.json']['sha256']==sha(ROOT/'protocol/dataset.json')
    primary=science['primary_overall240']
    interval=bootstrap.paired_percentile_interval(primary['full_only_correct'],primary['control_only_correct'],primary['valid'],240)
    assert interval==expected['supplementary_primary_paired_bootstrap']
    assert len(starts)==expected['combined_starts'] and len(ids)==expected['combined_successful_responses']
    assert sum(r['status']=='ok' for r in segments[2].values())==expected['new135_successful_responses']==753
    return {'status':'PASS_PORTABLE_THREE_SEGMENT240_RAW_ORACLE_INPUT_TOKEN_MATCHING_AND_ORDER','registered_N':240,'primary_correct_counts':counts,**science,'supplementary_primary_paired_bootstrap':interval,'administrative_amendment_after_observed_prior_results':True,'original_hypothesis_protocol_N_unchanged':True,'complete_study':False,'missing_three_retained':True,'all_raw_requests_and_calibration_padding_checked':True,'duplicate_request_or_response_ids':False,'model_calls':0,'network_requests':0}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    result=replay();args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps({'status':result['status'],'valid':result['primary_overall240']['valid'],'missing':result['primary_overall240']['not_complete'],'model_calls':0,'network_requests':0}))
