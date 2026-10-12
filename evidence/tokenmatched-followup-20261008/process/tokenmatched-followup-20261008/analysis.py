"""Separate conditional primary/SAT-ablation denominators; never a stopping rule."""
from math import comb


def comparison(pairs, planned):
    n = len(pairs)
    better = sum(full and not control for full, control in pairs)
    worse = sum(control and not full for full, control in pairs)
    discordant, missing = better + worse, planned - n
    p = min(1.0, 2 * sum(comb(discordant, k) for k in range(min(better, worse) + 1)) / 2 ** discordant) if discordant else 1.0
    return {'planned': planned, 'valid': n, 'not_complete': missing, 'full_only_correct': better,
            'control_only_correct': worse, 'difference': (better - worse) / n if n else None,
            'exact_McNemar_two_sided': p if n else None,
            'planned_possible_outcome_difference_bounds_not_CI': [(better - worse - missing) / planned, (better - worse + missing) / planned]}


def summarize(results, cases, score):
    tasks = {case['task']['id']: case['task'] for case in cases}
    primary, ablation = [], []
    for result in results:
        if result['status'] != 'complete_primary_pair':
            continue
        task = tasks[result['id']]
        correct = {arm: score(task, response['content'])[0] for arm, response in result['responses'].items()}
        primary.append((correct['full'], correct['neutral']))
        if result['SAT_ablation_status'] == 'complete':
            ablation.append((correct['full'], correct['coarse']))
    return {'primary_full_vs_neutral': comparison(primary, 375),
            'exploratory_SAT_full_vs_coarse': comparison(ablation, 166),
            'scope': 'conditional followup on reused historical initial-error cases; no pooled or overall592 accuracy'}
