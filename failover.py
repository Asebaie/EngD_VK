import json
import logging
import os
import signal
import sys
import time

from kazoo.client import KazooClient

HOSTS = "127.0.0.1:2181,127.0.0.1:2182,127.0.0.1:2183"
PAUSE_AT_TASK = 10

run = sys.argv[1]
root = f"/hw4/{run}"
zk = KazooClient(hosts=HOSTS)

os.makedirs("logs", exist_ok=True)
log = logging.getLogger("failover")
log.setLevel(logging.INFO)
for handler in (logging.FileHandler(f"logs/{run}-failover.log"), logging.StreamHandler()):
    handler.setFormatter(logging.Formatter("%(asctime)s.%(msecs)03d failover %(message)s", "%H:%M:%S"))
    log.addHandler(handler)


def wait(condition: object) -> None:
    while not condition():
        time.sleep(0.1)


def checkpoint_task() -> int:
    data = zk.get(f"{root}/checkpoint")[0]
    return json.loads(data)["task"] if data else -1


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


zk.start()
election = zk.Election(f"{root}/election")
wait(lambda: zk.exists(f"{root}/checkpoint") and checkpoint_task() >= PAUSE_AT_TASK)
leader = election.contenders()[0]
leader_name, pid = leader.split(":")[0], int(leader.split(":")[1])
os.kill(pid, signal.SIGSTOP)
paused = time.time()
log.info(f"приостановил лидера {leader_name} (pid {pid}) после задачи {checkpoint_task()}")
wait(lambda: election.contenders()[:1] != [leader])
log.info(f"лидер сменился через {time.time() - paused:.1f} с: новый лидер {election.contenders()[0].split(':')[0]}")
wait(lambda: zk.get(f"{root}/result")[0])
log.info(f"запасной координатор опубликовал результат через {time.time() - paused:.1f} с после приостановки")
os.kill(pid, signal.SIGCONT)
log.info(f"возобновил {leader_name} через {time.time() - paused:.1f} с после приостановки")
wait(lambda: not alive(pid))
data, stat = zk.get(f"{root}/result")
log.info(f"{leader_name} завершился, указатель {root}/result: версия {stat.version}, {data.decode()}")
zk.stop()
