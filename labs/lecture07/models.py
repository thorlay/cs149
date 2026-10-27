"""CPU semantic models: not a CUDA emulator, compiler, or GPU benchmark."""
from collections import Counter
from math import ceil, isclose


def tiled_avg(x, threads, reverse=False):
    n = len(x)
    out = [None]*n
    visits = [0]*n
    blocks = list(range((n+threads-1)//threads))
    if reverse: blocks.reverse()
    for block in blocks:
        base = block*threads
        shared = [None]*(threads+2)
        writes = [0]*(threads+2)
        # Complete all cooperative loads before any output reads (barrier phase).
        for t in range(threads):
            for q in range(t, threads+2, threads):
                g = base+q-1
                shared[q] = x[g] if 0 <= g < n else 0.0
                writes[q] += 1
        assert writes == [1]*(threads+2)
        for t in range(threads):
            i = base+t
            if i < n:
                assert all(shared[q] is not None for q in (t,t+1,t+2))
                out[i] = (shared[t]+shared[t+1]+shared[t+2])/3
                visits[i] += 1
    assert visits == [1]*n
    return out


def reference(x):
    padded = [0.0]+x+[0.0]
    return [sum(padded[i:i+3])/3 for i in range(len(x))]


def matrix_coverage(nx, ny, bx, by):
    count = Counter()
    launched = 0
    for yb in range((ny+by-1)//by):
        for xb in range((nx+bx-1)//bx):
            for ty in range(by):
                for tx in range(bx):
                    launched += 1
                    x, y = xb*bx+tx, yb*by+ty
                    if x < nx and y < ny: count[(x,y)] += 1
    assert count == Counter({(x,y):1 for y in range(ny) for x in range(nx)})
    return launched


def sectors(offset, stride):
    # 32 lanes, each loading 4 bytes; abstract aligned 32-byte sectors.
    touched = set()
    for lane in range(32):
        address = 4*(offset+stride*lane)
        touched.update(range(address//32, (address+3)//32+1))
    return len(touched)


def resident_blocks(threads, shared, registers_per_thread,
                    max_threads, shared_bytes, registers, max_blocks, max_warps):
    # No allocation granularity, partitioning, or reserved resources modeled.
    return min(max_threads//threads, shared_bytes//shared,
               registers//(threads*registers_per_thread), max_blocks,
               max_warps//ceil(threads/32))


def flag_order(order):
    # One resident block, no preemption. Block 1 waits; block 0 produces flag.
    flag = 0
    for block in order:
        if block == 1 and flag == 0: return False
        if block == 0: flag = 1
    return True


def main():
    sizes = [0,1,2,3,5,31,32,33,127,128,129,257]
    blocks = [1,2,7,32,64,128,256]
    cases = 0
    for n in sizes:
        x = [(i%17-8)*0.25 for i in range(n)]
        want = reference(x)
        for t in blocks:
            for reverse in (False, True):
                got = tiled_avg(x,t,reverse)
                assert all(isclose(a,b,rel_tol=0,abs_tol=1e-12) for a,b in zip(got,want))
            cases += 1
    assert tiled_avg([1,2,3,4,5],2) == [1,2,3,4,3]
    print(f'avg3: cases={cases} two_block_orders=pass tile_writers=pass outputs=pass')
    matrix_cases = 0
    for nx,ny in [(0,0),(1,1),(11,5),(12,6),(17,9),(31,33)]:
        for bx,by in [(4,3),(8,4),(16,16)]:
            matrix_coverage(nx,ny,bx,by)
            matrix_cases += 1
    assert matrix_coverage(11,5,4,3) == 72
    print(f'matrix: cases={matrix_cases} exact_once=pass 11x5_launch=72 valid=55')
    for n in sizes:
        for launched in [1,7,32,128]:
            visits = [0]*n
            for tid in range(launched):
                for i in range(tid,n,launched): visits[i] += 1
            assert visits == [1]*n
    print('grid_stride: cases=48 exact_once=pass')
    # Thread 0 tries to read neighbors before other producers have run.
    shared = [None]*6
    for q in range(0,6,4): shared[q] = 1
    assert shared[1] is None
    print('missing_barrier: uninitialized_neighbor_counterexample=detected')
    assert [sectors(0,1),sectors(1,1),sectors(0,32)] == [4,5,32]
    print('sector_model: aligned=4 offset_one_float=5 stride32=32')
    count = resident_blocks(128,520,1,384,1536,65536,32,12)
    assert count == 2
    assert resident_blocks(256,520,64,2048,98304,65536,32,64) == 4
    assert resident_blocks(256,520,32,2048,98304,65536,32,64) == 8
    print('residency: toy_blocks_per_SM=2; register32=8 register64=4')
    assert flag_order([0,1]) and not flag_order([1,0])
    bins = [i%10 for i in range(101)]
    assert Counter(bins) == Counter(reversed(bins))
    print('cross_block: producer_first=complete consumer_first=deadlock; histogram_order=pass')
    assert 130*4 == 520 and 3*520 > 1536
    assert 80*64*32 == 163840
    assert isclose(80*4*16*1.245e9*2/1e12,12.7488)
    print('all_checks=pass')


if __name__ == '__main__':
    main()
