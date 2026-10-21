import csv
import io
import os

import boto3

s3 = boto3.client("s3", endpoint_url=f"http://{os.environ['S3_ENDPOINT']}")


def load(engine: str, k: int) -> dict[str, int]:
    body = s3.get_object(Bucket="hh-lake", Key=f"results/{engine}/k{k}.csv")["Body"].read().decode()
    return {row["skills"]: int(row["count"]) for row in csv.DictReader(io.StringIO(body))}


for k in (1, 2, 3):
    mapreduce, duck = load("mapreduce", k), load("duckdb", k)
    differ = sum(mapreduce.get(key) != duck.get(key) for key in mapreduce.keys() | duck.keys())
    print(
        f"k={k}: MapReduce unique {len(mapreduce)} total {sum(mapreduce.values())} | "
        f"DuckDB unique {len(duck)} total {sum(duck.values())} | different keys: {differ} | "
        f"{'MATCH' if mapreduce == duck else 'MISMATCH'}"
    )
