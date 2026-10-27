#!/usr/bin/env python3
"""Real PySpark local RDD checks, including one deliberately retried task."""
import os
from pathlib import Path
import sys
import tempfile
from operator import add

from pyspark import SparkConf, SparkContext, StorageLevel, TaskContext


# Synthetic TSV: event ID, device, browser. Repeated IDs remain separate events.
LINES = ["1\tmobile\tsafari", "2\tdesktop\tchrome",
         "3\tmobile\tchrome", "4\tmobile\tsafari",
         "5\ttablet\tchrome", "6\tmobile\tchrome", "broken"]


def parse(line):
    fields = line.split("\t")
    if (len(fields) != 3 or not fields[0].isdigit()
            or fields[1] not in {"mobile", "desktop", "tablet"}
            or fields[2] not in {"safari", "chrome"}):
        return []
    return [(int(fields[0]), fields[1], fields[2])]


def retry_partition(index, rows):
    context = TaskContext.get()
    attempt = context.attemptNumber()
    if index == 1 and attempt == 0:
        raise RuntimeError("CS149 intentional first-attempt failure")
    # Attempt number is diagnostic metadata; the numeric subtotal is deterministic.
    yield (index, attempt, sum(rows))


def main():
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    with tempfile.TemporaryDirectory(prefix="cs149-spark-") as directory:
        root = Path(directory)
        input_file = root / "events.tsv"
        input_file.write_text("\n".join(LINES) + "\n", encoding="utf-8")
        conf = (SparkConf().setMaster("local[2,2]")
                .setAppName("CS149 lecture09")
                .set("spark.ui.enabled", "false")
                .set("spark.ui.showConsoleProgress", "false")
                .set("spark.driver.host", "127.0.0.1")
                .set("spark.driver.bindAddress", "127.0.0.1")
                .set("spark.local.dir", str(root / "scratch")))
        sc = SparkContext(conf=conf)
        sc.setLogLevel("ERROR")
        try:
            print(f"Spark {sc.version}, Python {sys.version.split()[0]}")
            rows = sc.textFile(input_file.as_uri(), minPartitions=3).flatMap(parse)
            mobile = rows.filter(lambda row: row[1] == "mobile")
            counts = mobile.map(lambda row: (row[2], 1)).reduceByKey(add, 3)
            assert rows.count() == 6 and mobile.count() == 4
            actual = sorted(counts.collect())
            assert actual == [("chrome", 2), ("safari", 2)]
            assert sc.parallelize([], 3).map(lambda x: (x, 1)).reduceByKey(add).collect() == []
            print(f"mobile browser counts: {actual}; malformed=1; empty input PASS")

            # Diagnostic only. Transformation accumulators may overcount on retries.
            calls = sc.accumulator(0)

            def observe(value):
                calls.add(1)
                return value * 2

            doubled = sc.parallelize(range(12), 4).map(observe)
            assert calls.value == 0
            assert doubled.count() == 12 and calls.value == 12
            assert doubled.count() == 12 and calls.value == 24
            doubled.persist(StorageLevel.MEMORY_ONLY)
            assert calls.value == 24  # persist itself runs no tasks.
            assert doubled.count() == 12 and calls.value == 36
            assert doubled.count() == 12 and calls.value == 36
            doubled.unpersist(blocking=True)
            assert doubled.count() == 12 and calls.value == 48
            print("lazy/cache/recompute: observed map calls 0,12,24,24,36,36,48")

            keyed = sc.parallelize([(i, i * 10) for i in range(8)], 4).partitionBy(3)
            placement = keyed.mapPartitionsWithIndex(
                lambda index, it: [(index, key) for key, _ in it]).collect()
            assert len(placement) == 8
            assert all(index == key % 3 for index, key in placement)
            assert keyed.partitioner is not None
            assert keyed.mapValues(lambda value: value + 1).partitioner == keyed.partitioner
            print("partitionBy: 8 integer keys correctly assigned to 3 partitions")

            left = sc.parallelize([("a", 1), ("a", 2), ("b", 3)], 2)
            right = sc.parallelize([("a", "x"), ("a", "y"), ("c", "z")], 2)
            joined = sorted(left.join(right, 3).collect())
            assert joined == [("a", (1, "x")), ("a", (1, "y")),
                              ("a", (2, "x")), ("a", (2, "y"))]
            print("inner join: duplicate key produces 2 x 2 = 4 records")

            sc.setCheckpointDir((root / "checkpoint").as_uri())
            checkpointed = sc.parallelize(range(10), 3).map(lambda x: x + 1)
            checkpointed.persist(StorageLevel.MEMORY_AND_DISK)
            checkpointed.checkpoint()
            assert not checkpointed.isCheckpointed()
            assert checkpointed.count() == 10
            assert checkpointed.isCheckpointed() and checkpointed.getCheckpointFile()
            checkpointed.unpersist(blocking=True)
            assert checkpointed.sum() == 55
            print("checkpoint: materialized locally; sum remains 55 after unpersist")

            output_dir = root / "result"
            counts.saveAsTextFile(output_dir.as_uri())
            saved = sorted(line for file in output_dir.glob("part-*")
                           for line in file.read_text(encoding="utf-8").splitlines())
            assert saved == sorted(repr(pair) for pair in actual)
            print("saveAsTextFile: partition files verified in temporary directory")

            # local[2,2]: two threads; allow two attempts per task before aborting.
            recovered = sorted(sc.parallelize(range(12), 4)
                               .mapPartitionsWithIndex(retry_partition).collect())
            assert [index for index, _, _ in recovered] == list(range(4))
            assert [attempt for _, attempt, _ in recovered] == [0, 1, 0, 0]
            assert sum(subtotal for _, _, subtotal in recovered) == sum(range(12)) == 66
            print("retry: attempts [0,1,0,0], recovered sum=66")
            print("ALL LOCAL SPARK CHECKS PASS")
        finally:
            sc.stop()


if __name__ == "__main__":
    main()
