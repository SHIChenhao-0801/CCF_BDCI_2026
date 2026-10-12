"""Portable stdlib replay of the conditional375 followup; zero network/model calls."""
import argparse,hashlib,importlib.util,json,socket,sys
from decimal import Decimal
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
load=lambda path:json.loads(path.read_text(encoding='utf-8-sig'))
def reject_network(*args,**kwargs):
    raise RuntimeError('Network is forbidden in this public replay')
socket.create_connection=reject_network
socket.socket.connect=reject_network
socket.socket.connect_ex=reject_network
socket.getaddrinfo=reject_network

def verify_manifest(bundle):
    manifest=load(bundle/'public-manifest.json')
    assert all((bundle/name).resolve().is_relative_to(bundle.resolve()) for name in manifest['files']),'Manifest path leaves public bundle'
    assert all(sha(bundle/name)==digest for name,digest in manifest['files'].items()),'Public payload hash mismatch'
    return manifest

def module_from(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

class PortableRecordedRoot:
    def __init__(self,root):self.root=root
    def __truediv__(self,recorded):return self.root/str(recorded).replace('\\','/')

def replay(bundle=ROOT):
    manifest=verify_manifest(bundle)
    sys.path.insert(0,str(bundle/'historical600'))
    historical=module_from(bundle/'historical600/replay.py','historical600_public_replay')
    history=historical.replay(bundle/'historical600')
    assert history['status']=='PASS' and history['complete_items']==592 and history['missing_items']==8
    old_rows=load(bundle/'historical600/history/replication600-resume-20261008/results.json')['rows']
    old_errors={row['id'] for row in old_rows if not row['initial']['correct']}
    assert len(old_errors)==375
    study=bundle/'process/tokenmatched-followup-20261008'
    ready=load(study/'ready.json')
    projection=ready['public_projection']
    assert projection['kind']=='SCIENTIFIC_READY_EXCLUDES_FOUR_INTERNAL_TEST_LOGS'
    omitted=projection['omitted_internal_test_logs_sha256']
    assert set(omitted)=={'offline-tests.log','operational-v2-green.log','operational-v2-red-verified.log','operational-v2-red.log'}
    assert len(ready['sha256'])==projection['retained_public_frozen_file_count']==21
    assert not any((study/name).exists() for name in omitted)
    reconstructed={key:value for key,value in ready.items() if key!='public_projection'}
    hashes={**ready['sha256'],**omitted}
    order=projection['original_sha256_key_order']
    assert len(order)==len(set(order))==projection['original_frozen_file_count']==25 and set(order)==set(hashes)
    reconstructed['sha256']={name:hashes[name] for name in order}
    original_bytes=(json.dumps(reconstructed,indent=2)+'\n').replace('\n','\r\n').encode('utf8')
    assert hashlib.sha256(original_bytes).hexdigest()==projection['source_sha256']=='931c85207cb6d22f798a453e43cf73058d9a575f40b6d8b3cc9eec90cd2f09dd','Original scientific freeze registration changed'
    data=load(study/'cases.json')
    assert {case['task']['id'] for case in data['cases']}==old_errors
    original_data=load(bundle/'process/run14-input/dataset.json')
    historic_known={}
    for source in sorted((bundle/'historical600/history').rglob('calls.jsonl')):
        for line in source.read_text(encoding='utf-8').splitlines():
            row=json.loads(line)
            if row['status']=='ok':
                assert row['call_key'] not in historic_known or row==historic_known[row['call_key']]
                historic_known[row['call_key']]=row
    for row in original_data['raw_records']:
        if row['status']=='ok':
            assert row==historic_known[row['call_key']],'Selection source raw differs from independently replayed historical600'
    independent=module_from(bundle/'audit/independent_raw_auditor.py','followup_public_independent_auditor')
    independent.PROJECT=PortableRecordedRoot(bundle)
    result=independent.audit(study,budget_after=study/'full_followup-budget-settled.json')
    expected=load(bundle/'analysis/expected-independent-summary.json')
    for key,value in expected.items():
        if key!='source_independent_terminal_audit_sha256':assert json.loads(json.dumps(result[key]))==value,'Derived summary disagreement: '+key
    identities=load(bundle/'copy-identity.json')['source_role_to_public_relative']
    assert all(sha(bundle/item['public_relative'])==item['public_sha256'] for item in identities)
    assert all(item['source_sha256']==item['public_sha256'] for item in identities if item['copy_mode']=='EXACT_BYTES')
    settlement=load(bundle/'analysis/settlement-receipt.public.json')
    for filename,source_key in [('full_followup-budget-before.json','before_sha256'),('full_followup-budget-after.json','original_client_exit_after_sha256'),('full_followup-budget-settled.json','source_sha256')]:
        value=load(study/filename)
        assert value['public_projection']['source_sha256']==settlement[source_key]
    assert result['budget']['global_unknown_before']==13 and result['budget']['global_unknown_after']==14
    assert result['budget']['control_delta_CNY']=='3.105112' and result['budget']['residual_control_CNY']=='2.359296'
    helper=module_from(bundle/'bootstrap/paired_bootstrap.py','public_paired_bootstrap')
    summary=load(bundle/'analysis/full-v2-bootstrap-input.json')
    primary=result['primary']
    assert summary['n']==primary['valid'] and summary['planned_n']==primary['planned']
    assert summary['contrasts']==[{'name':'full_vs_neutral','b':primary['full_only_correct'],'w':primary['control_only_correct']}]
    assert summary['independent_raw_audit_sha256']==expected['source_independent_terminal_audit_sha256']
    bootstrap=helper.analyze_cohort(summary)
    archived_bootstrap=load(bundle/'analysis/full-v2-bootstrap-supplement.json')
    assert bootstrap['contrasts']==archived_bootstrap['contrasts']
    assert archived_bootstrap['summary_sha256']==sha(bundle/'analysis/full-v2-bootstrap-input.json')
    assert archived_bootstrap['scoped_plan_sha256']==sha(bundle/'bootstrap/PLAN.md')
    pilot_before=load(study/'calibration_only-budget-before.json');pilot_after=load(study/'calibration_only-budget-after.json')
    pilot_delta=pilot_after['charged_micro_cny']-pilot_before['charged_micro_cny']
    assert pilot_delta==12748
    return {'status':'PASS','kind':'DERIVED_PORTABLE_CONDITIONAL375_REPLAY','not_new_independent_samples':True,'historical600_replayed':True,'historical_observed':592,'historical_initial_errors_selected':375,
        'source_independent_audit_sha256':expected['source_independent_terminal_audit_sha256'],'frozen_original25_checked':False,'original25_registration_identity_reconstructed':True,'retained_public_frozen21_checked':True,'omitted_four_internal_test_logs':True,'source_selection_raw_exact_checked':True,
        **{key:result[key] for key in ('phase_state_counts','actual_request_starts','actual_successful_responses','raw_terminal_request_states','usage','usage_by_request_phase','primary','exploratory_SAT_ablation','outcome')},
        'budget':{key:result['budget'][key] for key in ('status','control_delta_CNY','attributable_known_successful_control_CNY','residual_control_CNY','known_successful_calls_in_interval','reserved_delta','settled_delta','global_unknown_delta','global_unknown_before','global_unknown_after','globally_known_calls_without_raw_in_interval','late_global_usage_promoted_to_scientific_success','original_after_had_active_reservations')},
        'pilot_control_CNY':str(Decimal(pilot_delta)/1000000),'combined_control_CNY':str(Decimal(result['budget']['control_delta_CNY'])+Decimal(pilot_delta)/1000000),
        'bootstrap_posthoc_conditional':bootstrap['contrasts'][0],'budget_projection_not_vendor_invoice':True,'owner_IDs_omitted':True,'all_paths_relative':True,'live_ledger_access':False,'network_requests':0,'model_api_calls':0}

if __name__=='__main__':
    assert sys.version_info>=(3,12)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'replay-result.json')
    args=parser.parse_args()
    result=replay()
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','phase_state_counts','actual_request_starts','actual_successful_responses','model_api_calls','network_requests')}))
