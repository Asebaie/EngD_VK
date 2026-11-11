# ДЗ 4. Обеспечение отказоустойчивости средствами Apache ZooKeeper

Вариант 8: «Программист, разработчик Frontend». Ансамбль из трёх серверов ZooKeeper 3.9.6 и два координатора расчёта пар навыков из ДЗ 3.

| Путь | Что это |
|---|---|
| `zk1/conf/zoo.cfg`, `zk2/conf/zoo.cfg`, `zk3/conf/zoo.cfg` | Конфигурации серверов: общие строки `server.N`, свои порты и `dataDir` |
| `zk1/data/myid`, `zk2/data/myid`, `zk3/data/myid` | Номера серверов |
| `coordinator.py` | Координатор: выбор лидера и эпоха через ZooKeeper, расчёт пар из RustFS с чекпоинтами, публикация результата. `FENCING=1` включает проверку эпохи |
| `failover.py` | Приостанавливает лидера посреди расчёта, замеряет смену лидера, возобновляет его после публикации запасным |
| `check.py` | Указатель на результат и сверка пар с ДЗ 3 |
| `logs/` | Журналы координаторов и `failover.py` |
| `outputs/` | Выводы команд текстом |
| `ИнжД_лаб4.pdf` | Отчёт |

Запуск:

```bash
uv venv .venv && uv pip install --python .venv/bin/python kazoo boto3
export JAVA_HOME=... S3_ENDPOINT=127.0.0.1:9000 AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_DEFAULT_REGION=us-east-1
for n in 1 2 3; do zk$n/bin/zkServer.sh start; done
FENCING=0 .venv/bin/python coordinator.py A run1
FENCING=0 .venv/bin/python coordinator.py B run1
.venv/bin/python failover.py run1
.venv/bin/python check.py run1
```

Для запуска с защитой те же команды с `FENCING=1` и именем запуска `run2`.
