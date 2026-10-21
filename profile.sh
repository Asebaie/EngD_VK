#!/bin/bash
set -e

run() {
  for i in 1 2 3; do
    /usr/bin/time -l "$@" > run.log 2> time.log
    awk -v name="$*" -v i="$i" '/ real /{t=$1} /maximum resident set size/{m=$1/1048576} END{printf "%-40s run %d  %6.1f s  %5.0f MiB\n", name, i, t, m}' time.log
  done
}

run .venv/bin/python mapreduce.py
run .venv/bin/python duckdb_counts.py csv
run .venv/bin/python duckdb_counts.py parquet
