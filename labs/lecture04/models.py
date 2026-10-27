"""Paper-and-pencil models for parallel programming basics."""
from math import isclose


def amdahl(serial_fraction, processors):
    return 1/(serial_fraction+(1-serial_fraction)/processors)


def initial(n):
    a = [[0.0]*(n+2) for _ in range(n+2)]
    a[0] = [1.0]*(n+2)
    return a


def value(a, i, j):
    return .2*(a[i][j]+a[i-1][j]+a[i+1][j]+a[i][j-1]+a[i][j+1])


def sweep(a, scheme):
    n = len(a)-2
    out = [row[:] for row in a]
    for color in ([0, 1] if scheme == 'redblack' else [None]):
        for i in range(1, n+1):
            for j in range(1, n+1):
                if color is None or (i+j) % 2 == color:
                    source = a if scheme == 'jacobi' else out
                    out[i][j] = value(source, i, j)
    return [row[1:-1] for row in out[1:-1]]


def check_assignments():
    for n in [1, 2, 3, 5, 8]:
        for workers in [1, 2, 4, 8]:
            groups = [list(range(1+p*n//workers, 1+(p+1)*n//workers))
                      for p in range(workers)]
            assert sorted(i for g in groups for i in g) == list(range(1, n+1))
        for color in [0, 1]:
            cells = {(i, j) for i in range(1, n+1) for j in range(1, n+1)
                     if (i+j) % 2 == color}
            for i, j in cells:
                assert not ({(i-1,j),(i+1,j),(i,j-1),(i,j+1)} & cells)


def main():
    for fraction in [.01, .1]:
        print(f'S={fraction:.2f} P=64 speedup={amdahl(fraction,64):.3f}')
    assert isclose(amdahl(.001, 10**9), 1000, rel_tol=1e-5)
    expected = {
        'rowmajor': [[.2, .24], [.04, .056]],
        'jacobi': [[.2, .2], [0., 0.]],
        'redblack': [[.2, .24], [.04, 0.]],
    }
    for scheme in expected:
        result = sweep(initial(2), scheme)
        assert all(isclose(x,y,abs_tol=1e-12)
                   for r,s in zip(result,expected[scheme]) for x,y in zip(r,s))
        print(scheme + ': ' + repr([[round(x,3) for x in r] for r in result]))
    first = [9, 2, 7, 1, 4, 3, 8, 6, 5, 10]
    partials = [sum(first[p::4]) for p in range(4)]
    assert partials == [18, 15, 15, 7] and sum(partials) == 55
    print(f'partials={partials} sum={sum(partials)}')
    check_assignments()
    print('row_coverage=pass color_independence=pass all_checks=pass')


if __name__ == '__main__':
    main()
