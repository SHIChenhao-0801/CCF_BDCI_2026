"""Exact sealed Oct8 monetary audit functions; no live ledger access."""
from decimal import Decimal

def totals(calls):
    calls = tuple(calls)
    return {'input_tokens': sum(c['usage']['prompt_tokens'] for c in calls),
            'output_tokens': sum(c['usage']['completion_tokens'] for c in calls),
            'cache_hit_tokens': sum(c['usage'].get('prompt_cache_hit_tokens') or 0 for c in calls)}


def check_budget(before, after, usage, successes, final):
    assert before['policy'] == after['policy']
    assert before['unmetered_calls'] == 13
    for name in ('charged_micro_cny', 'reserved_calls', 'settled_calls', 'unmetered_calls'):
        assert after[name] >= before[name], 'Historical accounting was refunded or reset'
    assert not before['active_reservations']
    policy = before['policy']
    reserve = int(Decimal(policy['input_cny_per_million']) * policy['max_input_tokens']
                  + Decimal(policy['output_cny_per_million']) * policy['max_output_tokens'])
    assert reserve == 2359296
    unknown = after['unmetered_calls'] - before['unmetered_calls']
    control = usage['input_tokens'] * 2 + usage['output_tokens'] * 8
    peak = Decimal(usage['cache_hit_tokens']) * Decimal('0.04') + (usage['input_tokens'] - usage['cache_hit_tokens']) * 2 + usage['output_tokens'] * 8
    delta = after['charged_micro_cny'] - before['charged_micro_cny']
    active = sum(after['active_reservations'].values())
    if final:
        assert not active
        assert delta == control + unknown * reserve, 'Global charge delta disagrees with raw usage/unknown accounting'
        assert after['reserved_calls'] - before['reserved_calls'] == successes + unknown
        assert after['settled_calls'] - before['settled_calls'] == successes + unknown
    cap = int(Decimal(policy['budget_cny']) * 1_000_000)
    assert after['charged_micro_cny'] <= cap
    safe = Decimal('31.676218') + (peak + unknown * reserve + active) / 1_000_000
    safe_control = Decimal('31.676218') + Decimal(control + unknown * reserve + active) / 1_000_000
    assert safe_control <= Decimal(40)
    return {'historical_unknown_calls_retained': before['unmetered_calls'], 'new_global_unknown_calls': unknown,
        'global_unknown_calls_final_or_snapshot': after['unmetered_calls'], 'new_unknown_reserve_CNY': str(Decimal(unknown * reserve) / 1_000_000),
        'new_known_conservative_peak_usage_CNY': str(peak / 1_000_000), 'new_control_usage_CNY': str(Decimal(control) / 1_000_000),
        'new_active_reserve_CNY': str(Decimal(active) / 1_000_000), 'control_charge_delta_CNY': str(Decimal(delta) / 1_000_000),
        'expected_final_control_delta_CNY': str(Decimal(control + unknown * reserve) / 1_000_000),
        'cumulative_safe_upper_CNY': str(safe), 'cumulative_safe_control_upper_CNY': str(safe_control),
        'prior_safe_upper_CNY': '31.676218', 'authorized_actual_total_CNY': '40',
        'active_reservations': len(after['active_reservations']), 'global_charge_delta_exact': final,
        'unknown_charges_are_not_invoices': True, 'historical_unknown_refund_CNY': '0', 'second_paid_ledger': False}
