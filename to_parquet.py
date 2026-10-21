import time

from duckdb_counts import connect

started = time.perf_counter()
connect().execute(
    "COPY (SELECT * FROM read_csv('s3://hh-lake/it_vacancies_2024.csv', header = true, all_varchar = true)) "
    "TO 's3://hh-lake/it_vacancies_2024.parquet' (FORMAT parquet)"
)
print(f"s3://hh-lake/it_vacancies_2024.parquet written in {time.perf_counter() - started:.1f} s")
