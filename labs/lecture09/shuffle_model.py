#!/usr/bin/env python3
"""Paper-scale model: deterministic shuffle, combining, skew, recovery costs."""
from collections import Counter
from fractions import Fraction
import random


def shuffle(parts, reducers, combine):
    if reducers <= 0:
        raise ValueError("reducers must be positive")
    buckets = [[] for _ in range(reducers)]
    sent = 0
    for part in parts:
        items = Counter()
        if combine:
            for key, value in part:
                items[key] += value
            records = list(items.items())
        else:
            records = part
        for key, value in records:
            # Integer keys make partition placement reproducible across processes.
            buckets[key % reducers].append((key, value))
            sent += 1
    totals = {}
    for bucket in buckets:
        local = Counter()
        for key, value in bucket:
            local[key] += value
        totals.update(local)
    return totals, sent, [len(b) for b in buckets]


def recovery_inputs(lost_children, dependencies, available_parents):
    """Parents that must be regenerated, not a real Spark scheduler."""
    needed = set()
    for child in lost_children:
        needed.update(dependencies[child])
    return needed - set(available_parents)


def main():
    parts = [[(0, 1), (0, 1), (1, 1)],
             [(0, 1), (2, 1), (2, 1)], [(1, 1), (2, 1)]]
    raw, raw_sent, raw_load = shuffle(parts, 2, False)
    combined, combined_sent, combined_load = shuffle(parts, 2, True)
    assert raw == combined == {0: 3, 1: 2, 2: 3}
    assert (raw_sent, combined_sent) == (8, 6)
    assert raw_load == [6, 2] and combined_load == [4, 2]
    print(f"shuffle: raw={raw_sent}, combined={combined_sent}, totals={raw}")

    rng = random.Random(149)
    for _ in range(200):
        records = [(rng.randrange(8), rng.randrange(-5, 6))
                   for _ in range(rng.randrange(101))]
        count = rng.randrange(1, 9)
        parts = [records[i::count] for i in range(count)]
        reference = Counter()
        for key, value in records:
            reference[key] += value
        reducers = rng.randrange(1, 10)
        direct, n1, _ = shuffle(parts, reducers, False)
        merged, n2, _ = shuffle(parts, reducers, True)
        # Keep zero totals: a present key whose sum is zero still exists.
        assert dict(reference) == direct == merged
        assert n2 <= n1
        assert sum(merged.values()) == sum(v for _, v in records)
    print("random shuffle: 200 cases PASS")

    parts = [[(0, 1)] * 100 + [(i + 1, 1)] for i in range(4)]
    _, sent, load = shuffle(parts, 8, False)
    assert sent == 404 and max(load) == 400
    _, sent_combined, _ = shuffle(parts, 8, True)
    assert sent_combined == 8
    print("skew: 400 hot-key records share one reducer; combining sends 8 records")

    narrow = {i: {i} for i in range(4)}
    wide = {i: set(range(4)) for i in range(4)}
    assert recovery_inputs({2}, narrow, set()) == {2}
    assert recovery_inputs({2}, wide, set()) == {0, 1, 2, 3}
    assert recovery_inputs({2}, wide, {0, 1, 3}) == {2}
    print("recovery model: narrow=1 parent, wide<=4 parents; reuse survives")

    serial_seconds = Fraction(100 * 10**12, 50 * 10**6)
    parallel_minutes = serial_seconds / 1000 / 60
    hours = Fraction(25 * 365 * 24, 1000)
    assert serial_seconds == 2_000_000 and hours == 219
    print(f"scan: {float(serial_seconds / 86400):.3f} days, "
          f"{float(parallel_minutes):.3f} minutes on 1000 ideal nodes")
    print(f"failure model: 25-year mean / 1000 nodes = {float(hours):.0f} hours")
    print("ALL MODEL CHECKS PASS")


if __name__ == "__main__":
    main()
