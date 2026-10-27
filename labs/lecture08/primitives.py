"""Deterministic data-parallel algorithms executed sequentially on the CPU."""
from collections import Counter
from random import Random


def serial_exclusive(xs, op, identity):
    out, acc = [], identity
    for x in xs:
        out.append(acc)
        acc = op(acc, x)
    return out


def tree_reduce(xs, op, identity):
    level = list(xs)
    while len(level) > 1:
        level = [op(level[i],level[i+1]) if i+1 < len(level) else level[i]
                 for i in range(0,len(level),2)]
    return level[0] if level else identity


def hillis_inclusive(xs, op):
    out, distance, work, rounds = list(xs), 1, 0, 0
    while distance < len(out):
        old = out[:]
        for i in range(distance, len(out)):
            out[i] = op(old[i-distance], old[i])
            work += 1
        distance *= 2
        rounds += 1
    return out, work, rounds


def blelloch_exclusive(xs, op, identity):
    n = len(xs)
    if n == 0: return [], 0, 0
    m = 1 << (n-1).bit_length()
    a = list(xs)+[identity]*(m-n)
    width, work, rounds = 2, 0, 0
    while width <= m:
        for right in range(width-1, m, width):
            left = right-width//2
            a[right] = op(a[left], a[right])
            work += 1
        width *= 2
        rounds += 1
    a[m-1] = identity
    width = m
    while width >= 2:
        for right in range(width-1, m, width):
            left = right-width//2
            left_total, incoming = a[left], a[right]
            a[left] = incoming
            a[right] = op(incoming, left_total)  # prefix BEFORE left subtree
            work += 1
        width //= 2
        rounds += 1
    return a[:n], work, rounds


def compact(xs, predicate):
    flags = [int(predicate(x)) for x in xs]
    positions, _, _ = blelloch_exclusive(flags, lambda a,b:a+b, 0)
    count = positions[-1]+flags[-1] if flags else 0
    out, writes = [None]*count, [0]*count
    for i, keep in enumerate(flags):
        if keep:
            out[positions[i]] = xs[i]
            writes[positions[i]] += 1
    assert writes == [1]*count
    return out


def segmented_inclusive(xs, heads, op, identity):
    if len(xs) != len(heads) or (xs and not heads[0]):
        raise ValueError('heads must match data and mark the first element')
    def combine(left, right):
        a, ha = left
        b, hb = right
        return (b if hb else op(a,b), ha or hb)
    pairs = list(zip(xs, map(bool, heads)))
    prefix, _, _ = blelloch_exclusive(pairs, combine, (identity, False))
    return [combine(p,x)[0] for p,x in zip(prefix,pairs)]


def gather(xs, indices):
    if any(i < 0 or i >= len(xs) for i in indices): raise ValueError('bad gather index')
    return [xs[i] for i in indices]


def scatter_unique(xs, indices, size):
    if len(xs) != len(indices) or len(set(indices)) != len(indices):
        raise ValueError('scatter requires one value per unique destination')
    if any(i < 0 or i >= size for i in indices): raise ValueError('bad scatter index')
    out = [None]*size
    for i,x in zip(indices,xs): out[i] = x
    return out


def spmv(values, columns, rowptr, x):
    if not rowptr or rowptr[0] != 0 or rowptr[-1] != len(values):
        raise ValueError('bad row pointers')
    if len(values) != len(columns) or any(a > b for a,b in zip(rowptr,rowptr[1:])):
        raise ValueError('bad CSR lengths or row order')
    products = [a*b for a,b in zip(values,gather(x,columns))]
    heads = [False]*len(values)
    for lo,hi in zip(rowptr,rowptr[1:]):
        if lo < hi: heads[lo] = True
    prefix = segmented_inclusive(products,heads,lambda a,b:a+b,0)
    return [prefix[hi-1] if lo < hi else 0 for lo,hi in zip(rowptr,rowptr[1:])]


def cell_ids(points, nx, ny):
    if nx < 1 or ny < 1: raise ValueError('bad grid dimensions')
    if any(not (0 <= x < 1 and 0 <= y < 1) for x,y in points):
        raise ValueError('points must lie in the half-open unit square')
    return [int(y*ny)*nx+int(x*nx) for x,y in points]


def bin_ranges(keys, bins):
    if bins < 1 or any(k < 0 or k >= bins for k in keys): raise ValueError('bad bin')
    pairs = sorted((k,i) for i,k in enumerate(keys))
    starts, ends = [0]*bins, [0]*bins
    for j,(key,_) in enumerate(pairs):
        if j == 0 or key != pairs[j-1][0]: starts[key] = j
        if j+1 == len(pairs) or key != pairs[j+1][0]: ends[key] = j+1
    return [i for k,i in pairs], starts, ends


def scatter_sum(values, keys, bins):
    if len(values) != len(keys): raise ValueError('length mismatch')
    order, _, _ = bin_ranges(keys,bins)
    sorted_keys = [keys[i] for i in order]
    heads = [i == 0 or k != sorted_keys[i-1] for i,k in enumerate(sorted_keys)]
    prefix = segmented_inclusive([values[i] for i in order],heads,lambda a,b:a+b,0)
    out = [0]*bins
    for i,k in enumerate(sorted_keys):
        if i+1 == len(order) or k != sorted_keys[i+1]: out[k] = prefix[i]
    return out


def main():
    add = lambda a,b:a+b
    scan_cases = 0
    def check_scan(xs, identity):
        expected = serial_exclusive(xs,add,identity)
        got, work, rounds = blelloch_exclusive(xs,add,identity)
        inc, hwork, hrounds = hillis_inclusive(xs,add)
        assert got == expected
        assert tree_reduce(xs,add,identity) == (add(expected[-1],xs[-1]) if xs else identity)
        assert inc == [add(p,x) for p,x in zip(expected,xs)]
        if xs:
            m = 1 << (len(xs)-1).bit_length()
            assert work == 2*(m-1) and rounds == 2*(m.bit_length()-1)
        else: assert (work,rounds) == (0,0)
        assert hwork == sum(len(xs)-(1<<k) for k in range(hrounds))
    for n in list(range(66))+[127,128,129,257]:
        check_scan([(i%13)-6 for i in range(n)],0)
        check_scan([chr(97+i%4) for i in range(n)],'')
        scan_cases += 2
    rng = Random(149)
    for _ in range(200):
        xs = [rng.randrange(-9,10) for _ in range(rng.randrange(130))]
        check_scan(xs,0)
        scan_cases += 1
        assert compact(xs,lambda x:x%3 != 0) == [x for x in xs if x%3 != 0]
        assert compact(xs,lambda x:False) == []
        assert compact(xs,lambda x:True) == xs
        heads = [i == 0 or rng.random() < .3 for i in range(len(xs))]
        expected, acc = [], 0
        for x,h in zip(xs,heads):
            acc = x if h else acc+x
            expected.append(acc)
        assert segmented_inclusive(xs,heads,add,0) == expected
        keys = [rng.randrange(16) for x in xs]
        order,starts,ends = bin_ranges(keys,16)
        assert sorted(order) == list(range(len(xs)))
        for k in range(16):
            assert order[starts[k]:ends[k]] == [i for i,x in enumerate(keys) if x == k]
        assert [b-a for a,b in zip(starts,ends)] == [Counter(keys)[k] for k in range(16)]
        expected = [sum(x for x,k in zip(xs,keys) if k == b) for b in range(16)]
        assert scatter_sum(xs,keys,16) == expected
    for _ in range(100):
        rows, cols = rng.randrange(12), rng.randrange(1,9)
        dense = [[rng.choice([0,0,0,-2,1,3]) for c in range(cols)] for r in range(rows)]
        x = [rng.randrange(-4,5) for c in range(cols)]
        values,columns,rowptr = [],[],[0]
        for row in dense:
            for c,v in enumerate(row):
                if v: values.append(v);columns.append(c)
            rowptr.append(len(values))
        assert spmv(values,columns,rowptr,x) == [sum(a*b for a,b in zip(row,x)) for row in dense]
    assert spmv([],[],[0],[]) == []
    assert spmv([],[],[0,0,0],[]) == [0,0]
    assert spmv([3,1,2,4,2,6,8],[0,2,1,2,1,2,3],[0,2,2,3,4,7,7],[1,2,3,4]) == [6,0,4,12,54,0]
    assert segmented_inclusive(['a','b','c','d'],[1,0,1,0],add,'') == ['a','ab','c','cd']
    points = [(.6,.4),(.3,.1),(.55,.5),(.1,.1),(.99,.99),(.4,.1)]
    assert cell_ids(points,4,3) == [6,1,6,0,11,1]
    assert bin_ranges(cell_ids(points,4,3),12)[0] == [3,1,5,0,2,4]
    assert bin_ranges([],16) == ([],[0]*16,[0]*16)
    assert scatter_sum([1]*10,[5]*10,16) == [0]*5+[10]+[0]*10
    assert scatter_unique(['A','B','C'],[2,0,1],3) == ['B','C','A']
    for action in [lambda:gather([1],[-1]),lambda:scatter_unique([1,2],[0,0],1),
                   lambda:spmv([],[],[1],[]),lambda:bin_ranges([16],16),lambda:cell_ids([(1.0,0.5)],4,3)]:
        try: action()
        except ValueError: pass
        else: raise AssertionError('invalid input accepted')
    a = [2,1,3,4]
    print('exclusive=',blelloch_exclusive(a,add,0)[0], 'inclusive=',hillis_inclusive(a,add)[0])
    print(f'scan_cases={scan_cases} integer_and_noncommutative_strings=pass')
    print('random_pipelines=200 compact_three_predicates=pass segmented=pass bins=pass scatter_sum=pass')
    print('spmv_random=100 empty_rows_example=[6, 0, 4, 12, 54, 0] invalid_inputs=pass')
    print('N=8: Hillis combines=17 rounds=3; Blelloch combines=14 rounds=6')
    print('all_checks=pass')


if __name__ == '__main__': main()
