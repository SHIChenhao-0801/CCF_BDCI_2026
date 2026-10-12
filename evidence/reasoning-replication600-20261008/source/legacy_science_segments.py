"""Frozen legacy scoring segments; host/model caller intentionally omitted."""
import heapq,json,operator

def shortest(spec):
    queue, visited = [(0, [spec['source']])], set()
    while queue:
        cost, path = heapq.heappop(queue)
        node = path[-1]
        if node in visited:
            continue
        visited.add(node)
        if node == spec['target']:
            return {'path': path, 'cost': cost}
        for a, b, weight in spec['edges']:
            neighbor = b if a == node else a if b == node else None
            if neighbor is not None and neighbor not in visited:
                heapq.heappush(queue, (cost + weight, path + [neighbor]))
    raise ValueError('Disconnected generated graph')


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON key')
        obj[key] = value
    return obj


def check(task, text):
    try:
        answer = json.loads(text, object_pairs_hook=unique_object)
        spec, family = task['spec'], task['family']
        if not isinstance(answer, dict):
            return False, {'error': 'json_object_required'}
        if family == 'arithmetic':
            if set(answer) != {'answer'} or type(answer['answer']) is not int:
                return False, {'error': 'integer_answer_schema'}
            expected = spec['start']
            for op, value in spec['ops']:
                expected = expected + value if op == '+' else expected - value if op == '-' else expected * value
            if answer['answer'] != expected:
                return False, {'error': 'sequential_arithmetic_mismatch'}
        elif family == 'sat':
            bits = answer.get('assignment')
            if set(answer) != {'assignment'} or not isinstance(bits, list) or len(bits) != spec['n'] or any(type(b) is not int or b not in [0, 1] for b in bits):
                return False, {'error': 'binary_assignment_schema'}
            for i, clause in enumerate(spec['clauses'], 1):
                if not any(bits[abs(v)-1] == (v > 0) for v in clause):
                    return False, {'error': 'clause_unsatisfied', 'clause_index': i}
        else:
            path = answer.get('path')
            if set(answer) != {'path', 'cost'} or not isinstance(path, list) or len(path) < 2 or any(type(v) is not int or v not in range(spec['n']) for v in path) or type(answer.get('cost')) is not int:
                return False, {'error': 'path_schema'}
            if path[0] != spec['source'] or path[-1] != spec['target'] or len(set(path)) != len(path):
                return False, {'error': 'path_endpoints_or_repetition'}
            edges = {(a, b): w for a, b, w in spec['edges']}
            edges.update({(b, a): w for a, b, w in spec['edges']})
            if any((a, b) not in edges for a, b in zip(path, path[1:])):
                return False, {'error': 'nonexistent_edge'}
            cost = sum(edges[a, b] for a, b in zip(path, path[1:]))
            if answer['cost'] != cost:
                return False, {'error': 'path_cost_mismatch'}
            if cost != shortest(spec)['cost']:
                return False, {'error': 'path_not_shortest'}
        return True, None
    except (ValueError, TypeError, KeyError):
        return False, {'error': 'invalid_json_or_schema'}
