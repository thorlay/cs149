"""Deterministic scheduling exercises; all times are abstract cost units."""
from collections import deque
from heapq import heappop, heappush


def static_loads(costs, workers, cyclic=False):
    groups = [list(range(p, len(costs), workers)) if cyclic else
              list(range(p*len(costs)//workers, (p+1)*len(costs)//workers))
              for p in range(workers)]
    assert sorted(i for g in groups for i in g) == list(range(len(costs)))
    return [sum(costs[i] for i in g) for g in groups]


def dynamic(costs, workers, chunk=1):
    ready = [(0, p) for p in range(workers)]
    visited = []
    while len(visited) < len(costs):
        start = len(visited)
        end = min(start+chunk, len(costs))
        time, p = heappop(ready)
        visited.extend(range(start, end))
        heappush(ready, (time+sum(costs[start:end]), p))
    assert visited == list(range(len(costs)))
    return max(time for time, _ in ready)


def dag_schedule(durations, parents, workers):
    pending = set(durations)
    done = set()
    running = []
    now = 0
    order = []
    while pending or running:
        for task in sorted(pending):
            if len(running) == workers:
                break
            if set(parents[task]) <= done:
                pending.remove(task)
                order.append((task, now))
                heappush(running, (now+durations[task], task))
        if not running:
            raise ValueError('Cycle or unsatisfied dependency')
        now = running[0][0]
        while running and running[0][0] == now:
            _, task = heappop(running)
            done.add(task)
    return now, order


def steal_trace(n, workers, cutoff):
    queues = [deque() for _ in range(workers)]
    queues[0].append((0, n))
    visits = []
    steals = 0
    while any(queues):
        for p in range(workers):
            if queues[p]:
                lo, hi = queues[p].pop()
            else:
                victim = next((q for q in range(workers) if queues[q]), None)
                if victim is None:
                    continue
                lo, hi = queues[victim].popleft()
                steals += 1
            if hi-lo <= cutoff:
                visits.extend(range(lo, hi))
            else:
                mid = lo+(hi-lo)//2
                queues[p].append((mid, hi))
                queues[p].append((lo, mid))
    assert sorted(visits) == list(range(n))
    return steals


def check_buffer_reuse():
    # After barrier t-1, nobody still needs to read the sum from t-2.
    for t in range(1, 20):
        assert (t+1) % 3 != (t-1) % 3
        assert (t+1) % 2 == (t-1) % 2


def main():
    costs = [9]*4 + [1]*12
    block = static_loads(costs, 4)
    cyclic = static_loads(costs, 4, True)
    assert block == [36, 4, 4, 4]
    assert cyclic == [12]*4
    print(f'static_block={block} static_cyclic={cyclic}')
    tail = [1]*15 + [13]
    late = dynamic(tail, 4)
    early = dynamic(sorted(tail, reverse=True), 4)
    assert (late, early) == (16, 13)
    print(f'long_task_last={late} long_task_first={early}')
    durations = dict(A=2, B=3, C=5, D=1)
    parents = dict(A=[], B=['A'], C=['A'], D=['B', 'C'])
    assert dag_schedule(durations, parents, 1)[0] == 11
    assert dag_schedule(durations, parents, 2)[0] == 8
    print('dag_work=11 dag_span=8 two_worker_time=8')
    try:
        dag_schedule(dict(A=1, B=1), dict(A=['B'], B=['A']), 2)
    except ValueError:
        pass
    else:
        raise AssertionError('Cycle was not detected')
    for n in [0, 1, 3, 19, 32, 257]:
        for p in [1, 2, 4, 8]:
            for chunk in [1, 4, 16]:
                assert dynamic([1]*n, p, chunk) >= n/p
                steal_trace(n, p, chunk)
    example_steals = steal_trace(32, 4, 4)
    assert example_steals > 0
    print('steal_trace_coverage=pass cycle_detection=pass')
    check_buffer_reuse()
    print('buffer_slot_arithmetic=pass all_checks=pass')


if __name__ == '__main__':
    main()
