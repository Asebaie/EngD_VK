import csv
import io
import json
import logging
import os
import sys
import time
from collections import Counter
from collections.abc import Iterator
from itertools import combinations

import boto3
from kazoo.client import KazooClient

HOSTS = "127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183"
SESSION_TIMEOUT = 10.0
BUCKET = "hh-lake"
KEY = "it_vacancies_2024.csv"
CHUNK_BYTES = 8 * 1024 * 1024
BATCH_ROWS = 10000
ROLE = "Программист, разработчик"
FRONTEND = ("frontend", "front-end", "front end", "фронтенд")

name, run = sys.argv[1], sys.argv[2]
fencing = os.environ.get("FENCING") == "1"
root = f"/hw4/{run}"
s3 = boto3.client("s3", endpoint_url=f"http://{os.environ['S3_ENDPOINT']}")
zk = KazooClient(hosts=HOSTS, timeout=SESSION_TIMEOUT)

os.makedirs("logs", exist_ok=True)
log = logging.getLogger("coordinator")
log.setLevel(logging.INFO)
for handler in (logging.FileHandler(f"logs/{run}-{name}.log"), logging.StreamHandler()):
    handler.setFormatter(logging.Formatter(f"%(asctime)s.%(msecs)03d {name} %(message)s", "%H:%M:%S"))
    log.addHandler(handler)

header = s3.get_object(Bucket=BUCKET, Key=KEY, Range="bytes=0-65535")["Body"].read().split(b"\n")[0].decode()
COLUMNS = next(csv.reader([header]))
ROLE_I, NAME_I, SKILLS_I = COLUMNS.index("role"), COLUMNS.index("name"), COLUMNS.index("key_skills")


def lines(start: int, position: list[int]) -> Iterator[str]:
    size = s3.head_object(Bucket=BUCKET, Key=KEY)["ContentLength"]
    tail = b""
    for begin in range(start, size, CHUNK_BYTES):
        end = min(begin + CHUNK_BYTES, size) - 1
        data = tail + s3.get_object(Bucket=BUCKET, Key=KEY, Range=f"bytes={begin}-{end}")["Body"].read()
        *complete, tail = data.split(b"\n")
        for line in complete:
            position[0] += len(line) + 1
            yield line.decode() + "\n"
    if tail:
        position[0] += len(tail)
        yield tail.decode()


def tasks(offset: int) -> Iterator[tuple[list[list[str]], int]]:
    position = [offset]
    reader = csv.reader(lines(offset, position))
    if offset == 0:
        next(reader)
    batch = []
    for row in reader:
        batch.append(row)
        if len(batch) == BATCH_ROWS:
            yield batch, position[0]
            batch = []
    if batch:
        yield batch, position[0]


def count_pairs(batch: list[list[str]], counter: Counter) -> None:
    for row in batch:
        if row[ROLE_I] == ROLE and any(word in row[NAME_I].lower() for word in FRONTEND):
            skills = sorted({s.strip(" ") for s in row[SKILLS_I].split(";") if s.strip(" ")})
            counter.update(" + ".join(pair) for pair in combinations(skills, 2))


def save_checkpoint(task: int, offset: int, counter: Counter, epoch: int) -> None:
    key = f"hw4/{run}/checkpoint-{task}-{name}.json"
    s3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(counter).encode())
    state = {"task": task, "offset": offset, "key": key, "by": name, "epoch": epoch}
    zk.retry(zk.set, f"{root}/checkpoint", json.dumps(state).encode())


def result_csv(counter: Counter) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["skills", "count"])
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        writer.writerow([key, count])
    return out.getvalue().encode()


def publish(counter: Counter, epoch: int) -> None:
    key = f"hw4/{run}/pairs-epoch{epoch}-{name}.csv"
    s3.put_object(Bucket=BUCKET, Key=key, Body=result_csv(counter))
    pointer = json.dumps({"key": key, "by": name, "epoch": epoch, "unique": len(counter), "total": sum(counter.values())})
    if fencing:
        transaction = zk.transaction()
        transaction.check(f"{root}/epoch", epoch)
        transaction.set_data(f"{root}/result", pointer.encode())
        check, stat = transaction.commit()
        if isinstance(check, Exception):
            log.info(f"запись результата отклонена: {type(check).__name__}, эпоха {epoch} устарела")
            return
    else:
        stat = zk.retry(zk.set, f"{root}/result", pointer.encode())
    log.info(f"записал результат: пар уникальных {len(counter)}, всего {sum(counter.values())}, s3://{BUCKET}/{key}")
    log.info(f"указатель {root}/result: версия {stat.version}")


def lead() -> None:
    epoch = zk.retry(zk.set, f"{root}/epoch", name.encode()).version
    log.info(f"стал лидером, эпоха {epoch}")
    if zk.retry(zk.get, f"{root}/result")[0]:
        log.info("результат уже опубликован, завершаю")
        return
    data = zk.retry(zk.get, f"{root}/checkpoint")[0]
    if data:
        state = json.loads(data)
        counter = Counter(json.loads(s3.get_object(Bucket=BUCKET, Key=state["key"])["Body"].read()))
        task, offset = state["task"] + 1, state["offset"]
        log.info(f"продолжаю с чекпоинта: задача {task}, байт {offset}, чекпоинт записал {state['by']}")
    else:
        log.info("чекпоинта нет, жду запасного координатора")
        while len(election.contenders()) < 2:
            time.sleep(0.5)
        counter, task, offset = Counter(), 0, 0
        log.info("запасной координатор на месте, начинаю с начала")
    for batch, offset in tasks(offset):
        count_pairs(batch, counter)
        save_checkpoint(task, offset, counter, epoch)
        log.info(f"задача {task} готова, байт {offset}, пар уникальных {len(counter)}")
        task += 1
    publish(counter, epoch)


def on_state(state: str) -> None:
    log.info(f"состояние сессии ZooKeeper: {state}")


zk.add_listener(on_state)
zk.start()
for node in ("epoch", "checkpoint", "result"):
    zk.ensure_path(f"{root}/{node}")
log.info(f"запущен: pid {os.getpid()}, сессия 0x{zk.client_id[0]:x}, тайм-аут {SESSION_TIMEOUT:.0f} с, FENCING={int(fencing)}")
election = zk.Election(f"{root}/election", f"{name}:{os.getpid()}")
election.run(lead)
log.info("завершил работу")
zk.remove_listener(on_state)
zk.stop()
