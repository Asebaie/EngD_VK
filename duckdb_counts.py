import os
import resource
import sys
import time

import duckdb

SOURCES = {
    "csv": "read_csv('s3://hh-lake/it_vacancies_2024.csv', header = true, all_varchar = true)",
    "parquet": "read_parquet('s3://hh-lake/it_vacancies_2024.parquet')",
}

VARIANT = """
CREATE TABLE frontend AS
SELECT vacancy_id,
       list_sort(list_distinct(list_filter(list_transform(string_split(key_skills, ';'), s -> trim(s)), s -> s <> ''))) AS skills
FROM {source}
WHERE role = 'Программист, разработчик'
  AND regexp_matches(lower(name), 'frontend|front-end|front end|фронтенд')
"""

COUNTS = {
    1: """
        SELECT s1 AS skills, count(*) AS count
        FROM (SELECT unnest(skills) AS s1 FROM frontend)
        GROUP BY 1""",
    2: """
        WITH e AS (SELECT vacancy_id, unnest(skills) AS s FROM frontend)
        SELECT a.s || ' + ' || b.s AS skills, count(*) AS count
        FROM e a JOIN e b ON a.vacancy_id = b.vacancy_id AND a.s < b.s
        GROUP BY 1""",
    3: """
        WITH e AS (SELECT vacancy_id, unnest(skills) AS s FROM frontend)
        SELECT a.s || ' + ' || b.s || ' + ' || c.s AS skills, count(*) AS count
        FROM e a
        JOIN e b ON a.vacancy_id = b.vacancy_id AND a.s < b.s
        JOIN e c ON a.vacancy_id = c.vacancy_id AND b.s < c.s
        GROUP BY 1""",
}


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs")
    con.execute(f"""CREATE SECRET (TYPE s3, KEY_ID '{os.environ["AWS_ACCESS_KEY_ID"]}',
        SECRET '{os.environ["AWS_SECRET_ACCESS_KEY"]}', ENDPOINT '{os.environ["S3_ENDPOINT"]}',
        URL_STYLE 'path', USE_SSL false)""")
    return con


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else "csv"
    started = time.perf_counter()
    con = connect()
    con.execute(VARIANT.format(source=SOURCES[source]))
    print(f"source: {source}")
    print("frontend vacancies:", con.execute("SELECT count(*) FROM frontend").fetchone()[0])
    for k, query in COUNTS.items():
        con.execute(f"CREATE TABLE k{k} AS {query}")
        target = f"s3://hh-lake/results/duckdb/k{k}.csv"
        con.execute(f"COPY (SELECT * FROM k{k} ORDER BY count DESC, skills) TO '{target}' (HEADER)")
        unique, total = con.execute(f"SELECT count(*), sum(count) FROM k{k}").fetchone()
        print(f"k={k}: unique {unique}, total {total} -> {target}")
        top = con.execute(f"SELECT skills, count FROM k{k} ORDER BY count DESC, skills LIMIT 3").fetchall()
        print("   top:", "; ".join(f"{skills}={count}" for skills, count in top))
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20
    print(f"time {time.perf_counter() - started:.1f} s, peak rss {peak:.0f} MiB")


if __name__ == "__main__":
    main()
