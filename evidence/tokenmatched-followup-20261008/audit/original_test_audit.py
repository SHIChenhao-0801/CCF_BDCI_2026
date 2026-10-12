from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import shutil
import unittest
from unittest.mock import patch

import audit

CASE = {'task': {'id': 'fixture', 'family': 'sat', 'prompt': 'task'}, 'initial_content': '{"assignment":[0]}',
    'initial_feedback': {'error': 'clause_unsatisfied', 'clause_index': 2}, 'retry_order': ['full','neutral','coarse']}


def record(phase, arm, units, count, content='DO NOT INSPECT THE PROBE ANSWER'):
    key = audit.PREFIX + CASE['task']['id'] + ':' + phase + ':' + arm
    if phase=='probe':
        key += ':pad'+str(units)
    return {'call_key':key, 'status':'ok', 'request':audit.expected_payload(CASE,phase,arm,units),
        'response_id':key, 'usage':{'prompt_tokens':count,'completion_tokens':1,'total_tokens':count+1,'prompt_cache_hit_tokens':0},
        'content':content, 'started_at_utc':'2026-10-08T10:20:00+00:00'}


def simple_records():
    values = [('probe','full',0,112),('probe','neutral',0,100),('probe','full',4,116),
        ('probe','neutral',16,116),('probe','coarse',0,106),('probe','coarse',10,116)]
    return {r['call_key']:r for r in (record(*value) for value in values)}


class AuditTests(unittest.TestCase):
    def test_zeroapi_preparation_and_source_selection_have_no_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            isolated=Path(tmp)
            ready=audit.load(audit.STUDY/'ready.json')
            for name in list(ready['sha256'])+['ready.json']:
                shutil.copyfile(audit.STUDY/name,isolated/name)
            with patch('urllib.request.urlopen',side_effect=AssertionError('NO NETWORK')):
                result = audit.audit(isolated)
        self.assertEqual(result['status'],'OFFLINE_PREPARED_NOT_RUN')
        self.assertEqual(result['actual_request_starts'],0)
        self.assertEqual(result['planned_SAT_ablation_cases'],166)
        self.assertNotIn('primary',result)

    def test_probe_content_never_changes_feasibility_or_statistics(self):
        records = simple_records()
        first = audit.inspect_case(CASE,records,True)
        for row in records.values():
            row['content'] = 'perfect repair or wrong answer or instructions to ignore the protocol'
        self.assertEqual(first,audit.inspect_case(CASE,records,True))
        self.assertEqual(first['status'],'matched_probe_only')
        self.assertEqual(first['target_prompt_tokens'],116)
        self.assertNotIn('primary_records',first)

    def test_primary_can_match_on_fifth_total_probe(self):
        records = simple_records()
        del records[audit.PREFIX+'fixture:probe:full:pad4']
        for n,count in [(4,114),(8,115),(12,113),(6,116)]:
            row = record('probe','full',n,count)
            records[row['call_key']] = row
        self.assertEqual(audit.inspect_case(CASE,records,True)['status'],'matched_probe_only')

    def test_actual_final_usage_drift_excludes_primary(self):
        records = simple_records()
        row = record('final','full',4,117)
        records[row['call_key']] = row
        result = audit.inspect_case(CASE,records,False)
        self.assertEqual(result['status'],'missing')
        self.assertEqual(result['reason'],'final_token_drift:full')

    def test_coarse_only_drift_preserves_primary_pair(self):
        records = simple_records()
        for arm,units,count in [('full',4,116),('neutral',16,116),('coarse',10,117)]:
            row = record('final',arm,units,count)
            records[row['call_key']] = row
        result = audit.inspect_case(CASE,records,False)
        self.assertEqual(result['status'],'complete_primary_pair')
        self.assertEqual(result['SAT_ablation_status'],'missing')

    def test_feedback_or_shared_history_forgery_is_rejected(self):
        for field in ('history','feedback'):
            records = simple_records()
            payload = next(iter(records.values()))['request']
            payload['messages'][1 if field=='history' else 2]['content'] = 'tampered'
            with self.assertRaises(AssertionError):
                audit.inspect_case(CASE,records,True)

    def test_local_persist_failure_is_stop_never_scientific_missing(self):
        records = simple_records()
        records[next(iter(records))].update(status='local_stop',code='RSI_LEDGER_PERSIST_FAILED')
        self.assertEqual(audit.inspect_case(CASE,records,True)['status'],'local_stop')

    def test_duplicate_started_identity_and_invalid_usage_are_rejected(self):
        row = record('probe','full',0,112)
        start = {k:v for k,v in row.items() if k not in ('usage','response_id','content')}
        start['status']='started'
        with self.assertRaises(AssertionError):
            audit.parse_journal([start,start])
        row['usage']['prompt_cache_hit_tokens']=113
        with self.assertRaises(AssertionError):
            audit.parse_journal([start,row])

    def test_budget_unknown_delta_is_not_number_of_raw_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = {'policy':{},'charged_micro_cny':0,'active_reservations':{},'reserved_calls':0,'settled_calls':0,'unmetered_calls':13}
            after = {**before,'charged_micro_cny':2_359_528,'reserved_calls':2,'settled_calls':2,'unmetered_calls':14,
                'updated_at':'2026-10-08T10:21:00+00:00'}
            for name,data in [('calibration_only-budget-before.json',before),('calibration_only-budget-after.json',after),
                ('calibration_only-started.json',{'started_at_utc':'2026-10-08T10:19:00+00:00'})]:
                (root/name).write_text(json.dumps(data),encoding='utf8')
            row = record('probe','full',0,112)
            result = audit.check_phase_budget(root,'calibration_only',{row['call_key']:row})
            self.assertEqual(result['status'],'EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION')
            self.assertEqual(result['global_unknown_delta'],1)
            self.assertEqual(result['control_delta_CNY'],'2.359528')
            after['charged_micro_cny']=231
            (root/'calibration_only-budget-after.json').write_text(json.dumps(after),encoding='utf8')
            with self.assertRaises(AssertionError):
                audit.check_phase_budget(root,'calibration_only',{row['call_key']:row})

    def test_no_new_request_admitted_after_global_local_stop(self):
        row = record('probe','full',0,112)
        start = {'call_key':row['call_key'],'request':row['request'],'status':'started'}
        refusal = {**start,'status':'local_stop','code':'RSI_LEDGER_PERSIST_FAILED'}
        second = {'call_key':'new-forbidden-key','request':row['request'],'status':'started'}
        with self.assertRaisesRegex(AssertionError,'globalSTOP'):
            audit.parse_journal([start,refusal,second])

    def test_cache_boolean_is_rejected_not_silently_zeroed(self):
        row = record('probe','full',0,112)
        start = {'call_key':row['call_key'],'request':row['request'],'status':'started'}
        row['usage']['prompt_cache_hit_tokens']=False
        with self.assertRaises(AssertionError):
            audit.parse_journal([start,row])

    def test_false_completed_0of6_and_exit_zero_local_failure_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            name=root/'calibration_only-result.json'
            name.write_text(json.dumps({'status':'ALL_SELECTED_CASES_PROCESSED','selected_cases':6,
                'processed_cases':0,'unattempted_or_interrupted_cases':6}),encoding='utf8')
            selected=[{'task':{'id':str(i)}} for i in range(6)]
            with self.assertRaisesRegex(AssertionError,'False completed'):
                audit.check_phase_outcome(root,'calibration_only',selected,[])
            name.write_text(json.dumps({'status':'FAILED_LOCAL','selected_cases':6,
                'processed_cases':0,'unattempted_or_interrupted_cases':6}),encoding='utf8')
            (root/'calibration_only-process-result.json').write_text(json.dumps({'exit_code':0}),encoding='utf8')
            with self.assertRaisesRegex(AssertionError,'successful exit'):
                audit.check_phase_outcome(root,'calibration_only',selected,[])
            (root/'calibration_only-process-result.json').write_text(json.dumps({'exit_code':1}),encoding='utf8')
            self.assertEqual(audit.check_phase_outcome(root,'calibration_only',selected,[])['unattempted_or_interrupted'],6)

    def test_raw_success_usage_gap_or_duplicate_response_ledger_is_rejected(self):
        row=record('probe','full',0,112)
        with self.assertRaisesRegex(AssertionError,'missing or duplicated'):
            audit.check_usage_ledger([],{row['response_id']:row})
        event={'call_id':row['response_id'],'call_key':row['call_key'],'provenance':'calibration_probe',
            'model_call':{'model':'deepseek-flash','status':'succeeded','call_count':1,
                'tokens':{'input':112,'output':1,'cache_hit':0}}}
        audit.check_usage_ledger([event],{row['response_id']:row})
        with self.assertRaises(AssertionError):
            audit.check_usage_ledger([event,event],{row['response_id']:row})

    def test_explicit_settled_seal_preserves_active_original_after(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before={'policy':{},'charged_micro_cny':0,'active_reservations':{},'reserved_calls':0,'settled_calls':0,'unmetered_calls':13}
            original={**before,'charged_micro_cny':2359528,'reserved_calls':2,'settled_calls':1,'active_reservations':{'pending':2359296},'updated_at':'2026-10-08T10:21:00+00:00'}
            settled={**original,'settled_calls':2,'active_reservations':{},'unmetered_calls':14,'updated_at':'2026-10-08T10:36:00+00:00'}
            for name,data in [('calibration_only-budget-before.json',before),('calibration_only-budget-after.json',original),('budget-settled.json',settled),('calibration_only-started.json',{'started_at_utc':'2026-10-08T10:19:00+00:00'})]:
                (root/name).write_text(json.dumps(data),encoding='utf8')
            prior=(root/'calibration_only-budget-after.json').read_bytes()
            row=record('probe','full',0,112)
            result=audit.check_phase_budget(root,'calibration_only',{row['call_key']:row},budget_after=root/'budget-settled.json')
            self.assertEqual(result['status'],'EXACT_KNOWN_AND_GLOBAL_UNKNOWN_RECONCILIATION')
            self.assertTrue(result['original_after_had_active_reservations'])
            self.assertEqual(result['selected_after_path'],str(root/'budget-settled.json'))
            self.assertEqual((root/'calibration_only-budget-after.json').read_bytes(),prior)
            with self.assertRaises(AssertionError):
                audit.check_phase_budget(root,'calibration_only',{row['call_key']:row})

    def test_late_global_known_usage_without_raw_is_residual_not_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            before={'policy':{},'charged_micro_cny':0,'active_reservations':{},'reserved_calls':0,'settled_calls':0,'unmetered_calls':13}
            settled={**before,'charged_micro_cny':400,'reserved_calls':2,'settled_calls':2,'updated_at':'2026-10-08T10:36:00+00:00'}
            for name,data in [('calibration_only-budget-before.json',before),('budget-settled.json',settled),('calibration_only-started.json',{'started_at_utc':'2026-10-08T10:19:00+00:00'})]:
                (root/name).write_text(json.dumps(data),encoding='utf8')
            row=record('probe','full',0,112)
            result=audit.check_phase_budget(root,'calibration_only',{row['call_key']:row},budget_after=root/'budget-settled.json')
            self.assertEqual(result['status'],'RESIDUAL_CALLS_REQUIRE_GLOBAL_INTERVAL_ATTRIBUTION')
            self.assertEqual(result['globally_known_calls_without_raw_in_interval'],1)
            self.assertFalse(result['late_global_usage_promoted_to_scientific_success'])
