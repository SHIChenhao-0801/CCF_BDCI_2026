"""Default verifies preparation; paid flags require explicit root preflight and unpaused shared policy."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import time

from study import calibrate, calibrate_coarse, execute_case, MissingPair
from transport import Caller, LocalStop
from analysis import summarize

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
load = lambda path: json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--run-eval', action='store_true')
    modes.add_argument('--calibration-only', action='store_true')
    args = parser.parse_args()
    ready = load(ROOT / 'ready.json')
    assert all(hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == sha for name, sha in ready['sha256'].items())
    dataset = load(ROOT / 'cases.json')
    assert all(hashlib.sha256((PROJECT / name).read_bytes()).hexdigest() == sha
               for name, sha in dataset['source_sha256'].items()), 'Historical source provenance changed'
    if not args.run_eval and not args.calibration_only:
        print(json.dumps({'status': 'OFFLINE_READY_NO_API', 'cases': len(dataset['cases']), 'model_calls': 0,
                          'live_feasibility_unproven': True}))
        return
    preflight = load(ROOT / 'execution-preflight.json')
    scope = 'calibration_only' if args.calibration_only else 'full_followup'
    assert preflight['root_authorized_paid_start'] is True and preflight['authorized_scope'] == scope
    assert preflight['request_policy_tests'] == 'PASS' and preflight['ledger_reset'] is False
    assert load(PROJECT / 'process/request-policy.json')['paused'] is False
    before = load(PROJECT / 'process/model-budget.json')
    assert not before['active_reservations']
    cap_micro = int(preflight['additional_settled_control_cap_micro_CNY'])
    assert 0 < cap_micro <= 5_000_000
    result_path = ROOT / (scope + '-result.json')
    marker = ROOT / (scope + '-started.json')
    assert not marker.exists() and not result_path.exists(), 'No automatic restart'
    marker.write_text(json.dumps({'started_at_utc': datetime.now(timezone.utc).isoformat(), 'scope': scope}) + '\n', encoding='utf-8')
    shutil.copyfile(PROJECT / 'process/model-budget.json', ROOT / (scope + '-budget-before.json'))
    # Root must preserve the cumulative study baseline when promoting a paid6case probe
    # to the full phase. Otherwise this guard would incorrectly reset the5CNYallocation.
    baseline = int(preflight['study_baseline_charged_micro_CNY'])
    assert baseline <= before['charged_micro_cny']
    transport = None
    def caller(key, request):
        current = load(PROJECT / 'process/model-budget.json')
        # Keep room for the same proxy's worst-case next reservation.
        if current['charged_micro_cny'] - baseline + 2_359_296 > cap_micro:
            raise LocalStop('FOLLOWUP_SETTLED_CONTROL_CAP_REACHED')
        return transport(key, request)
    cases = dataset['cases']
    if args.calibration_only:
        cases = [next(case for case in cases if case['task']['family'] + ':' + case['task']['difficulty'] == cell)
                 for cell in sorted(dataset['cells'])]
    results, stopped, failure_type, started = [], None, None, time.perf_counter()
    try:
        transport = Caller(ROOT / 'calls.jsonl', ROOT / 'model_calls.jsonl')
        for case in cases:
            if args.calibration_only:
                try:
                    value = calibrate(case, caller)
                    if 'coarse' in case['retry_order']:
                        value['coarse'] = calibrate_coarse(case, value['target_prompt_tokens'], caller)
                    result = {'id': case['task']['id'], 'status': 'matched_probe_only', 'calibration': value}
                except MissingPair as error:
                    result = {'id': case['task']['id'], 'status': 'missing', 'reason': str(error)}
            else:
                result = execute_case(case, caller)
            results.append(result)
            (ROOT / (scope + '-rows.json')).write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            print(json.dumps({'processed': len(results), 'id': case['task']['id'], 'status': result['status']}), flush=True)
    except LocalStop as error:
        stopped = str(error)
    except BaseException as error:
        failure_type = type(error).__name__
        raise
    finally:
        shutil.copyfile(PROJECT / 'process/model-budget.json', ROOT / (scope + '-budget-after.json'))
        status = 'FAILED_LOCAL_ERROR' if failure_type else ('STOPPED_PARTIAL' if stopped else 'ALL_SELECTED_CASES_PROCESSED')
        result = {'status': status, 'stop_code': stopped, 'failure_type': failure_type,
                  'scope': scope, 'selected_cases': len(cases), 'processed_cases': len(results),
                  'unattempted_or_interrupted_cases': len(cases) - len(results), 'elapsed_seconds': time.perf_counter() - started,
                  'no_correctness_or_significance_used_for_stopping': True, 'automatic_restart': False}
        if not args.calibration_only:
            source = PROJECT / 'process/run14-input/run.py'
            spec = importlib.util.spec_from_file_location('frozen_followup_scorer', source)
            scorer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(scorer)
            result['science'] = summarize(results, dataset['cases'], scorer.score)
        result_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
