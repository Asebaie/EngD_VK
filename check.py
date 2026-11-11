import csv
import io
import json
import os
import sys

import boto3
from kazoo.client import KazooClient

HOSTS = "127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183"
HW3_PAIRS = "results/mapreduce/k2.csv"

run = sys.argv[1]
s3 = boto3.client("s3", endpoint_url=f"http://{os.environ['S3_ENDPOINT']}")
zk = KazooClient(hosts=HOSTS)


def load(key: str) -> dict[str, int]:
    body = s3.get_object(Bucket="hh-lake", Key=key)["Body"].read().decode()
    return {row["skills"]: int(row["count"]) for row in csv.DictReader(io.StringIO(body))}


zk.start()
data, stat = zk.get(f"/hw4/{run}/result")
zk.stop()
pointer = json.loads(data)
print(f"указатель /hw4/{run}/result: версия {stat.version}, записал {pointer['by']}, эпоха {pointer['epoch']}")
objects = s3.list_objects_v2(Bucket="hh-lake", Prefix=f"hw4/{run}/pairs-")["Contents"]
print("объекты результата в хранилище:", ", ".join(item["Key"] for item in objects))
mine, hw3 = load(pointer["key"]), load(HW3_PAIRS)
print(f"по указателю: пар уникальных {len(mine)}, всего {sum(mine.values())}")
print(f"ДЗ 3 ({HW3_PAIRS}): пар уникальных {len(hw3)}, всего {sum(hw3.values())}")
print("совпадает с ДЗ 3" if mine == hw3 else "НЕ совпадает с ДЗ 3")
