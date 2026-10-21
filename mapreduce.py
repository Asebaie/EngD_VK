import csv
import io
import os
import resource
import sys
import time
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from itertools import combinations

import boto3

BUCKET = "hh-lake"
KEY = "it_vacancies_2024.csv"
RESULTS = "results/mapreduce"
CHUNK_BYTES = 32 * 1024 * 1024
BATCH_ROWS = 20000
WORKERS = 4
ROLE = "Программист, разработчик"
FRONTEND = ("frontend", "front-end", "front end", "фронтенд")

s3 = boto3.client("s3", endpoint_url=f"http://{os.environ['S3_ENDPOINT']}")


def read_lines() -> Iterator[str]:
    size = s3.head_object(Bucket=BUCKET, Key=KEY)["ContentLength"]
    tail = b""
    chunks = 0
    for start in range(0, size, CHUNK_BYTES):
        end = min(start + CHUNK_BYTES, size) - 1
        data = tail + s3.get_object(Bucket=BUCKET, Key=KEY, Range=f"bytes={start}-{end}")["Body"].read()
        chunks += 1
        *complete, tail = data.split(b"\n")
        for line in complete:
            yield line.decode() + "\n"
    print(f"read {size} bytes in {chunks} chunks of {CHUNK_BYTES // 2**20} MiB")
    if tail:
        yield tail.decode()


def is_variant(row: dict[str, str]) -> bool:
    name = row["name"].lower()
    return row["role"] == ROLE and any(word in name for word in FRONTEND)


def map_task(task_id: int, attempt: int, fail_task: int, rows: list[dict[str, str]]) -> tuple[int, list[Counter]]:
    if task_id == fail_task and attempt == 0:
        raise RuntimeError(f"mapper {task_id} crashed")
    counts = [Counter(), Counter(), Counter()]
    vacancies = 0
    for row in rows:
        if not is_variant(row):
            continue
        vacancies += 1
        skills = sorted({s.strip(" ") for s in row["key_skills"].split(";") if s.strip(" ")})
        for k in (1, 2, 3):
            counts[k - 1].update(combinations(skills, k))
    return vacancies, counts


def batches() -> Iterator[list[dict[str, str]]]:
    batch = []
    for row in csv.DictReader(read_lines()):
        batch.append({"role": row["role"], "name": row["name"], "key_skills": row["key_skills"]})
        if len(batch) == BATCH_ROWS:
            yield batch
            batch = []
    if batch:
        yield batch


def save(k: int, counter: Counter) -> None:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["skills", "count"])
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        writer.writerow([" + ".join(key), count])
    s3.put_object(Bucket=BUCKET, Key=f"{RESULTS}/k{k}.csv", Body=out.getvalue().encode())


def main() -> None:
    fail_task = int(sys.argv[1]) if len(sys.argv) > 1 else -1
    started = time.perf_counter()
    totals = [Counter(), Counter(), Counter()]
    vacancies = 0
    with ProcessPoolExecutor(WORKERS) as pool:
        pending = {}
        for task_id, rows in enumerate(batches()):
            pending[pool.submit(map_task, task_id, 0, fail_task, rows)] = (task_id, rows)
        tasks = len(pending)
        while pending:
            future, (task_id, rows) = pending.popitem()
            try:
                found, counts = future.result()
            except RuntimeError as error:
                print(f"task {task_id} failed: {error}, restarting")
                pending[pool.submit(map_task, task_id, 1, fail_task, rows)] = (task_id, rows)
                continue
            vacancies += found
            for total, part in zip(totals, counts):
                total.update(part)
    print(f"map tasks: {tasks}, workers: {WORKERS}")
    print(f"frontend vacancies: {vacancies}")
    for k, counter in enumerate(totals, start=1):
        save(k, counter)
        print(f"k={k}: unique {len(counter)}, total {sum(counter.values())} -> s3://{BUCKET}/{RESULTS}/k{k}.csv")
        print("   top:", "; ".join(f"{' + '.join(key)}={count}" for key, count in counter.most_common(3)))
    driver = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    workers = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 2**20
    print(f"time {time.perf_counter() - started:.1f} s, peak rss driver {driver:.0f} MiB, worker {workers:.0f} MiB")


if __name__ == "__main__":
    main()
