"""Deterministic teaching models, not MPI or a hardware performance simulator."""
from collections import OrderedDict
from math import isclose


def rendezvous(p, parity):
    programs = [[] for _ in range(p)]
    def pair(a, b, first):
        programs[a].extend([(first, b), ('R' if first == 'S' else 'S', b)])
    for rank in range(p):
        if not parity:
            peers = [q for q in (rank-1, rank+1) if 0 <= q < p]
            programs[rank] = [('S', q) for q in peers] + [('R', q) for q in peers]
        elif rank % 2 == 0:
            for q in (rank+1, rank-1):
                if 0 <= q < p: pair(rank, q, 'S')
        else:
            for q in (rank-1, rank+1):
                if 0 <= q < p: pair(rank, q, 'R')
    pos = [0]*p
    while True:
        if all(pos[r] == len(programs[r]) for r in range(p)): return True
        progress = False
        for r in range(p):
            if pos[r] == len(programs[r]): continue
            op, q = programs[r][pos[r]]
            if pos[q] == len(programs[q]): continue
            other, peer = programs[q][pos[q]]
            if peer == r and op != other:
                pos[r] += 1
                pos[q] += 1
                progress = True
        if not progress: return False


def grid(n):
    a = [[0.0]*(n+2) for _ in range(n+2)]
    a[0] = [1.0]*(n+2)
    return a


def update(a, i, j):
    return 0.2*(a[i][j]+a[i-1][j]+a[i+1][j]+a[i][j-1]+a[i][j+1])


def halo_case(n, p, sweeps):
    # p <= n: each rank owns at least one row. lo is a zero-based interior offset.
    reference = grid(n)
    ranks = []
    for r in range(p):
        lo, hi = r*n//p, (r+1)*n//p
        local = [row[:] for row in reference[lo:hi+2]]
        ranks.append((lo, hi-lo, local))
    total_values = 0
    for _ in range(sweeps):
        for color in (0, 1):
            # Snapshot every sender before delivering: this models a completed exchange.
            outgoing = [(a[1][:], a[h][:]) for lo, h, a in ranks]
            for r, (lo, h, a) in enumerate(ranks):
                if r > 0:
                    a[0] = outgoing[r-1][1][:]
                    total_values += n+2
                if r+1 < p:
                    a[h+1] = outgoing[r+1][0][:]
                    total_values += n+2
            for lo, h, a in ranks:
                for i in range(1, h+1):
                    for j in range(1, n+1):
                        if (lo+i+j) % 2 == color: a[i][j] = update(a, i, j)
            for i in range(1, n+1):
                for j in range(1, n+1):
                    if (i+j) % 2 == color: reference[i][j] = update(reference, i, j)
            for lo, h, a in ranks:
                assert a[1:h+1] == reference[lo+1:lo+h+1]
                assert all(a[i][0] == a[i][-1] == 0 for i in range(1, h+1))
            assert ranks[0][2][0] == [1.0]*(n+2)
            assert ranks[-1][2][-1] == [0.0]*(n+2)
    assert total_values == 4*(p-1)*(n+2)*sweeps
    return total_values


def remote_values(n, rows, cols):
    # Directed halo payload across all internal rectangular partition interfaces.
    return 2*n*(rows-1) + 2*n*(cols-1)


def cache_misses(n, width):
    # Only input reads of a double-buffered stencil; output has a separate cache.
    # Fully associative LRU, 6 lines, 4 scalar elements/line, stride n+2.
    cache = OrderedDict()
    misses = 0
    for jj in range(1, n+1, width):
        for i in range(1, n+1):
            for j in range(jj, min(jj+width, n+1)):
                for x, y in [(i,j),(i-1,j),(i+1,j),(i,j-1),(i,j+1)]:
                    line = (x*(n+2)+y)//4
                    if line not in cache:
                        misses += 1
                        if len(cache) == 6: cache.popitem(last=False)
                    cache[line] = None
                    cache.move_to_end(line)
    return misses


def main():
    for p in range(2, 10):
        assert not rendezvous(p, False)
        assert rendezvous(p, True)
    print('rendezvous: 8 send-first deadlocks detected; 8 parity schedules complete')
    cases = 0
    for n in [1, 2, 3, 5, 8, 11]:
        for p in range(1, min(n, 4)+1):
            for sweeps in [1, 2, 7]:
                halo_case(n, p, sweeps)
                cases += 1
    print(f'halo: cases={cases} every_color=pass boundaries=pass payload=pass')
    assert halo_case(8, 2, 1) == 40
    n, p = 1024, 16
    strip, tile = remote_values(n, p, 1), remote_values(n, 4, 4)
    assert (strip, tile) == (30720, 12288)
    print(f'partition N=1024 P=16: strip={strip} tile={tile} values/exchange')
    row, blocked = cache_misses(30, 30), cache_misses(30, 4)
    assert blocked < row
    print(f'LRU input-only N=30: row={row} strip_width4={blocked} misses')
    f, q1, q2 = 3, 36, 20
    assert isclose((f/q2)/(f/q1), 1.8)
    peak, bandwidth = 1000, 100  # GFLOP/s and GB/s; decimal prefixes cancel.
    assert peak/bandwidth == 10
    for intensity in [0.25, 1, 4, 10, 20]:
        print(f'roofline I={intensity:g}: {min(peak, bandwidth*intensity):g} GFLOP/s')
    assert 258*258/32 == 2080.125
    print('fusion: 36 -> 20 logical bytes/element; ideal bandwidth-only speedup=1.8')
    print('all_checks=pass')


if __name__ == '__main__':
    main()
