from collections import OrderedDict

def simulate(addresses, line_bytes=4, capacity_lines=2):
    resident = OrderedDict()
    seen = set()
    hits = misses = 0
    log = []

    for address in addresses:
        line = (address // line_bytes) * line_bytes
        if line in resident:
            hits += 1
            kind = "hit"
            resident.move_to_end(line)
        else:
            misses += 1
            kind = "cold miss" if line not in seen else "miss after eviction"
            if len(resident) == capacity_lines:
                resident.popitem(last=False)
            resident[line] = None
        seen.add(line)
        log.append((address, kind, list(resident.keys())))
    return hits, misses, log

case_a = [0, 1, 2, 3, 2, 1, 4, 1]
case_b = list(range(16)) + [0]
for name, case, expected in [
    ("A", case_a, (6, 2)),
    ("B", case_b, (12, 5)),
]:
    hit, miss, log = simulate(case)
    assert (hit, miss) == expected
    print(f"{name}: hits={hit}, misses={miss}")
    for address, kind, lines in log:
        print(f"  addr={address:>2} | {kind:<19} | lines={lines}")
