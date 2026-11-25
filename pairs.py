import csv
import io
import json
import os
import resource
import sys
import time
from collections import Counter
from collections.abc import Iterator
from itertools import combinations
from pathlib import Path

import boto3

BUCKET = "hh-lake"
KEY = "it_vacancies_2024.csv"
HW3_PAIRS = "results/mapreduce/k2.csv"
RESULTS = "results/k8s"
CHUNK_BYTES = 32 * 1024 * 1024
ROLE = "Программист, разработчик"
FRONTEND = ("frontend", "front-end", "front end", "фронтенд")

s3 = boto3.client("s3", endpoint_url=f"http://{os.environ['S3_ENDPOINT']}")
size = s3.head_object(Bucket=BUCKET, Key=KEY)["ContentLength"]
header = s3.get_object(Bucket=BUCKET, Key=KEY, Range="bytes=0-65535")["Body"].read().split(b"\n")[0].decode()
COLUMNS = next(csv.reader([header]))
ROLE_I, NAME_I, SKILLS_I = COLUMNS.index("role"), COLUMNS.index("name"), COLUMNS.index("key_skills")


def lines(start: int, end: int) -> Iterator[str]:
    position = max(start - 1, 0)
    line_start = position
    tail = b""
    skip = True
    while position < size:
        stop = min(position + CHUNK_BYTES, size)
        data = tail + s3.get_object(Bucket=BUCKET, Key=KEY, Range=f"bytes={position}-{stop - 1}")["Body"].read()
        position = stop
        *complete, tail = data.split(b"\n")
        for line in complete:
            if line_start >= end:
                return
            if not skip:
                yield line.decode()
            skip = False
            line_start += len(line) + 1
    if tail and line_start < end:
        yield tail.decode()


def count_pairs(start: int, end: int) -> Counter:
    counter = Counter()
    for row in csv.reader(lines(start, end)):
        if row[ROLE_I] == ROLE and any(word in row[NAME_I].lower() for word in FRONTEND):
            skills = sorted({s.strip(" ") for s in row[SKILLS_I].split(";") if s.strip(" ")})
            counter.update(" + ".join(pair) for pair in combinations(skills, 2))
    return counter


def ranked(counter: Counter) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))


def save(counter: Counter, key: str) -> None:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["skills", "count"])
    writer.writerows(ranked(counter))
    s3.put_object(Bucket=BUCKET, Key=key, Body=out.getvalue().encode())


def report(counter: Counter, key: str) -> None:
    save(counter, key)
    body = s3.get_object(Bucket=BUCKET, Key=HW3_PAIRS)["Body"].read().decode()
    hw3 = Counter({row["skills"]: int(row["count"]) for row in csv.DictReader(io.StringIO(body))})
    print(f"пар уникальных {len(counter)}, всего {sum(counter.values())} -> s3://{BUCKET}/{key}")
    print("топ-10 пар:")
    for place, (pair, count) in enumerate(ranked(counter)[:10], start=1):
        print(f"{place:>2}. {pair} = {count}")
    print(f"топ-10 совпадает с ДЗ 3: {'да' if ranked(counter)[:10] == ranked(hw3)[:10] else 'нет'}")
    print(f"все пары совпадают с ДЗ 3: {'да' if counter == hw3 else 'нет'}")


def memory() -> str:
    process = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    container = int(Path("/sys/fs/cgroup/memory.peak").read_text()) / 2**20
    return f"пик памяти: процесс {process:.0f} МБ, контейнер {container:.0f} МБ"


started = time.perf_counter()
mode = sys.argv[1]
if mode == "full":
    report(count_pairs(0, size), f"{RESULTS}/pairs-full.csv")
elif mode == "part":
    index, parts = int(os.environ["JOB_COMPLETION_INDEX"]), int(os.environ["PARTS"])
    start, end = size * index // parts, size * (index + 1) // parts
    counter = count_pairs(start, end)
    s3.put_object(Bucket=BUCKET, Key=f"{RESULTS}/parts/part-{index}.json", Body=json.dumps(counter).encode())
    print(f"часть {index} из {parts}: байты {start}-{end}, пар уникальных {len(counter)}, всего {sum(counter.values())}")
elif mode == "merge":
    parts = int(os.environ["PARTS"])
    counter = Counter()
    for index in range(parts):
        counter.update(json.loads(s3.get_object(Bucket=BUCKET, Key=f"{RESULTS}/parts/part-{index}.json")["Body"].read()))
    print(f"объединил частей: {parts}")
    report(counter, f"{RESULTS}/pairs-parallel.csv")
print(f"время {time.perf_counter() - started:.1f} с, {memory()}")
