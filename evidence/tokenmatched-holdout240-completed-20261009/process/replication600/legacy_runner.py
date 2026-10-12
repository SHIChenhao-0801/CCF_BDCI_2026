"""Historical generator pure functions only; no paid runner."""
import random,heapq,json

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

def make_dataset():
    rng, tasks = random.Random(SEED), []
    for family in ['arithmetic', 'sat', 'graph']:
        for i in range(12):
            hard = i % 2 == 1
            split = 'development' if i < 2 else 'pilot' if i < 4 else 'eval'
            if family == 'arithmetic':
                start = rng.randint(20, 150)
                ops = [[rng.choice(['+', '-', '*']), rng.randint(2, 9)] for _ in range(8 if hard else 4)]
                spec, answer = {'start': start, 'ops': ops}, start
                for op, value in ops:
                    answer = answer + value if op == '+' else answer - value if op == '-' else answer * value
                oracle = {'answer': answer}
                instruction = 'Apply ops sequentially to start, using exact integer arithmetic. Return {"answer": integer}.'
            elif family == 'sat':
                n = 10 if hard else 6
                bits = [rng.randrange(2) for _ in range(n)]
                clauses = []
                while len(clauses) < (28 if hard else 12):
                    clause = [v if rng.randrange(2) else -v for v in rng.sample(range(1, n+1), 3)]
                    if any(bits[abs(v)-1] == (v > 0) for v in clause) and clause not in clauses:
                        clauses.append(clause)
                spec, oracle = {'n': n, 'clauses': clauses}, {'assignment': bits}
                instruction = 'Find any satisfying assignment for this CNF. Each clause is OR, clauses combine by AND, positive literals mean x_i and negative literals mean NOT x_i. Return {"assignment": [0 or 1 for x_1 through x_n]}. All instances are satisfiable.'
            else:
                n = 10 if hard else 6
                edges = [[v, v+1, rng.randint(1, 15)] for v in range(n-1)]
                while len(edges) < (17 if hard else 9):
                    a, b = sorted(rng.sample(range(n), 2))
                    if not any(x == a and y == b for x, y, _ in edges):
                        edges.append([a, b, rng.randint(1, 15)])
                spec = {'n': n, 'edges': sorted(edges), 'source': 0, 'target': n-1}
                oracle = shortest(spec)
                instruction = 'Find a shortest simple path from source to target in this undirected positive-weight graph. Each edge is [a,b,weight]. Return {"path": [integer vertices], "cost": integer total weight}. Any tied optimum is accepted.'
            prompt = instruction + '\nInput: ' + json.dumps(spec, separators=(',', ':')) + '\nOutput only the requested JSON object, without code fences or other keys.'
            tasks.append({'id': family+'-'+str(i+1).zfill(2), 'family': family, 'difficulty': 'hard' if hard else 'easy', 'split': split, 'spec': spec, 'oracle': oracle, 'prompt': prompt})
    return tasks
