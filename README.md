# ДЗ 3. Технология MapReduce

Вариант 8: «Программист, разработчик Frontend». Данные: `it_vacancies_2024.csv` в бакете `hh-lake` локального RustFS.

| Файл | Что делает |
|---|---|
| `mapreduce.py` | Свой MapReduce: читает объект из RustFS частями по 32 МБ, считает навыки, пары и тройки, пишет результаты в `hh-lake/results/mapreduce` |
| `duckdb_counts.py` | Тот же расчёт SQL-запросом в DuckDB, результаты в `hh-lake/results/duckdb` |
| `verify.py` | Сверка результатов двух способов |
| `analysis.py` | Влияние пар и троек навыков на медианную зарплату и сравнение трёх регионов |
| `to_parquet.py` | Копия данных в Parquet для оптимизации |
| `profile.sh` | По три запуска каждого способа с временем и пиком памяти |

Запуск:

```bash
uv venv .venv && uv pip install --python .venv/bin/python duckdb boto3
export S3_ENDPOINT=127.0.0.1:9000 AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=us-east-1
.venv/bin/python mapreduce.py
.venv/bin/python duckdb_counts.py csv
.venv/bin/python verify.py
.venv/bin/python analysis.py
.venv/bin/python mapreduce.py 5
.venv/bin/python to_parquet.py
./profile.sh
```

`mapreduce.py 5` имитирует отказ маппера с номером задачи 5: задача падает и перезапускается.
