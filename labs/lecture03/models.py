"""Deterministic teaching models, not a CPU performance simulator."""
from math import ceil


def utilization(compute, latency, threads, cycles=3000):
    ready = [0] * threads
    remaining = [compute] * threads
    current = None
    cursor = 0
    busy = 0
    for tick in range(cycles):
        if current is None:
            for offset in range(threads):
                candidate = (cursor + offset) % threads
                if ready[candidate] <= tick:
                    current = candidate
                    break
        if current is None:
            continue
        busy += 1
        remaining[current] -= 1
        if remaining[current] == 0:
            ready[current] = tick + 1 + latency
            remaining[current] = compute
            cursor = (current + 1) % threads
            current = None
    return busy / cycles


def assignment(n, width, blocked=False):
    groups = []
    for instance in range(width):
        if blocked:
            groups.append(list(range(instance*n//width, (instance+1)*n//width)))
        else:
            groups.append(list(range(instance, n, width)))
    assert sorted(i for group in groups for i in group) == list(range(n))
    return groups


def main():
    for count, expected in [(1, .2), (2, .4), (5, 1.), (8, 1.)]:
        value = utilization(3, 12, count)
        assert abs(value-expected) < 1e-12
        print(f'C=3 L=12 threads={count} utilization={value:.1%}')
    assert utilization(6, 12, 3) == 1
    assert ceil((3+12)/3) == 5
    for blocked in [False, True]:
        groups = assignment(19, 8, blocked)
        print(('blocked' if blocked else 'interleaved') + ': ' + str(groups))
    for n in [0, 1, 3, 7, 8, 9, 19, 32, 33]:
        for width in [1, 4, 8, 16]:
            assignment(n, width)
            assignment(n, width, True)
    compute_peak = 5120 * 1.6e9
    bandwidth = 900e9
    performance = bandwidth / 12
    assert abs(performance / compute_peak * 100 - .91552734375) < 1e-10
    print(f'bandwidth_bound={performance/1e9:.1f} Gop/s')
    print(f'fraction_of_mul_peak={performance/compute_peak:.3%}')
    washed = dried = folded = 0
    ends = []
    for _ in range(3):
        washed += 45
        dried = max(washed, dried) + 60
        folded = max(dried, folded) + 15
        ends.append(folded)
    assert ends == [120, 180, 240]
    print('laundry_finish_minutes=' + str(ends))
    print('all_checks=pass')


if __name__ == '__main__':
    main()
