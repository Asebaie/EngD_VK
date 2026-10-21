from duckdb_counts import connect

MIN_PAIR = 30
MIN_TRIPLE = 20
TOP = 10

BASE = """
CREATE TABLE fv AS
SELECT vacancy_id, area, schedule,
       list_sort(list_distinct(list_filter(list_transform(string_split(key_skills, ';'), s -> trim(s)), s -> s <> ''))) AS skills,
       CASE WHEN currency = 'RUR' THEN coalesce(
           (try_cast(salary_from AS DOUBLE) + try_cast(salary_to AS DOUBLE)) / 2,
           try_cast(salary_from AS DOUBLE), try_cast(salary_to AS DOUBLE)) END AS salary
FROM read_csv('s3://hh-lake/it_vacancies_2024.csv', header = true, all_varchar = true)
WHERE role = 'Программист, разработчик'
  AND regexp_matches(lower(name), 'frontend|front-end|front end|фронтенд');

CREATE TABLE e AS SELECT vacancy_id, area, salary, unnest(skills) AS s FROM fv;

CREATE TABLE single AS
SELECT s, count(*) AS freq, count(salary) AS n, median(salary) AS med FROM e GROUP BY s;

CREATE TABLE pair AS
SELECT a.s AS a, b.s AS b, count(*) AS freq, count(a.salary) AS n, median(a.salary) AS med
FROM e a JOIN e b ON a.vacancy_id = b.vacancy_id AND a.s < b.s
GROUP BY 1, 2;

CREATE TABLE triple AS
SELECT a.s AS a, b.s AS b, c.s AS c, count(a.salary) AS n, median(a.salary) AS med
FROM e a
JOIN e b ON a.vacancy_id = b.vacancy_id AND a.s < b.s
JOIN e c ON a.vacancy_id = c.vacancy_id AND b.s < c.s
WHERE a.salary IS NOT NULL
GROUP BY 1, 2, 3
HAVING count(*) >= {min_triple};
"""

PAIR_UPLIFT = """
SELECT p.a || ' + ' || p.b AS pair, p.n, round(p.med) AS pair_median,
       CASE WHEN sa.freq >= sb.freq THEN p.a ELSE p.b END AS base,
       round(CASE WHEN sa.freq >= sb.freq THEN sa.med ELSE sb.med END) AS base_median,
       CASE WHEN sa.freq >= sb.freq THEN p.b ELSE p.a END AS added,
       round(p.med - CASE WHEN sa.freq >= sb.freq THEN sa.med ELSE sb.med END) AS uplift
FROM pair p JOIN single sa ON sa.s = p.a JOIN single sb ON sb.s = p.b
WHERE p.n >= {min_pair}
ORDER BY uplift {order}, pair
LIMIT {top}
"""

TRIPLE_UPLIFT = """
WITH t AS (
    SELECT t.*, ab.freq AS f_ab, ac.freq AS f_ac, bc.freq AS f_bc, ab.med AS m_ab, ac.med AS m_ac, bc.med AS m_bc
    FROM triple t
    JOIN pair ab ON ab.a = t.a AND ab.b = t.b
    JOIN pair ac ON ac.a = t.a AND ac.b = t.c
    JOIN pair bc ON bc.a = t.b AND bc.b = t.c
)
SELECT a || ' + ' || b || ' + ' || c AS triple, n, round(med) AS triple_median,
       CASE WHEN f_ab >= greatest(f_ac, f_bc) THEN a || ' + ' || b
            WHEN f_ac >= f_bc THEN a || ' + ' || c ELSE b || ' + ' || c END AS base,
       round(CASE WHEN f_ab >= greatest(f_ac, f_bc) THEN m_ab WHEN f_ac >= f_bc THEN m_ac ELSE m_bc END) AS base_median,
       CASE WHEN f_ab >= greatest(f_ac, f_bc) THEN c WHEN f_ac >= f_bc THEN b ELSE a END AS added,
       round(med - CASE WHEN f_ab >= greatest(f_ac, f_bc) THEN m_ab WHEN f_ac >= f_bc THEN m_ac ELSE m_bc END) AS uplift
FROM t
ORDER BY uplift {order}, triple
LIMIT {top}
"""

REGION_SUMMARY = """
SELECT area, count(*) AS vacancies, round(100 * count(*) / (SELECT count(*) FROM fv), 1) AS share_pct,
       count(salary) AS with_salary, round(median(salary)) AS median,
       round(quantile_cont(salary, 0.25)) AS q25, round(quantile_cont(salary, 0.75)) AS q75,
       round(100 * avg((schedule = 'Удаленная работа')::INT), 1) AS remote_pct
FROM fv WHERE area IN {regions} GROUP BY area ORDER BY vacancies DESC
"""

REGION_SKILLS = """
WITH r AS (SELECT * FROM fv WHERE area = '{region}'),
     total AS (SELECT count(*) AS n FROM r),
     re AS (SELECT vacancy_id, salary, unnest(skills) AS s FROM r),
     combos AS (
         SELECT 1 AS k, s AS combo, count(*) AS c, median(salary) AS med FROM re GROUP BY s
         UNION ALL
         SELECT 2, a.s || ' + ' || b.s, count(*), median(a.salary)
         FROM re a JOIN re b ON a.vacancy_id = b.vacancy_id AND a.s < b.s GROUP BY 2
         UNION ALL
         SELECT 3, a.s || ' + ' || b.s || ' + ' || c.s, count(*), median(a.salary)
         FROM re a JOIN re b ON a.vacancy_id = b.vacancy_id AND a.s < b.s
         JOIN re c ON a.vacancy_id = c.vacancy_id AND b.s < c.s GROUP BY 2
     )
SELECT k, combo, c, round(100 * c / n, 1) AS share_pct, round(med) AS median
FROM combos, total
QUALIFY row_number() OVER (PARTITION BY k ORDER BY c DESC, combo) <= {top}
ORDER BY k, c DESC, combo
"""


def show(title: str, cursor: object) -> None:
    rows = cursor.fetchall()
    names = [d[0] for d in cursor.description]
    print(f"\n== {title}")
    print(" | ".join(names))
    for row in rows:
        print(" | ".join(str(value) for value in row))


def main() -> None:
    con = connect()
    con.execute(BASE.format(min_triple=MIN_TRIPLE))
    show(
        "Frontend: вакансий, с зарплатой в рублях, медиана",
        con.execute("SELECT count(*), count(salary), round(median(salary)) FROM fv"),
    )
    for order, title in (("DESC", "повышают"), ("ASC", "понижают")):
        show(
            f"Пары, которые сильнее всего {title} медиану (n >= {MIN_PAIR}, база - более частый навык пары)",
            con.execute(PAIR_UPLIFT.format(min_pair=MIN_PAIR, order=order, top=TOP)),
        )
        show(
            f"Тройки, которые сильнее всего {title} медиану (n >= {MIN_TRIPLE}, база - самая частая пара тройки)",
            con.execute(TRIPLE_UPLIFT.format(order=order, top=TOP)),
        )
    regions = [r[0] for r in con.execute("SELECT area FROM fv GROUP BY area ORDER BY count(*) DESC LIMIT 3").fetchall()]
    show("Регионы: вакансии и зарплаты", con.execute(REGION_SUMMARY.format(regions=tuple(regions))))
    for region in regions:
        show(f"{region}: топ навыков, пар и троек", con.execute(REGION_SKILLS.format(region=region, top=5)))


if __name__ == "__main__":
    main()
