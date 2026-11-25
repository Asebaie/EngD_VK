# ДЗ 5. Менеджеры ресурсов YARN и Mesos

Kubernetes 1.37 в kind на одном узле. Программа расчёта пар навыков из ДЗ 3 собрана в образ и запущена как задание Kubernetes с заявками и пределами ресурсов: остановка по памяти (OOMKilled), замер пика и предел по нему, RustFS из ДЗ 2 внутри кластера, расчёт по четырём частям файла, ожидание при нехватке процессора, вытеснение по приоритету и квота пространства имён. Топ-10 пар совпадает с ДЗ 3.

| Путь | Что это |
|---|---|
| [`ИнжД_лаб5.pdf`](ИнжД_лаб5.pdf) | Отчёт |
| [`kind-config.yaml`](kind-config.yaml) | Кластер kind |
| [`Dockerfile`](Dockerfile) | Образ `hw5-pairs:1` |
| [`pairs.py`](pairs.py) | Расчёт пар навыков: весь файл, часть файла, объединение частей |
| [`k8s/`](k8s) | Манифесты заданий, RustFS и квоты |
| [`logs/`](logs) | Журналы запусков |

## Запуск

RustFS из ДЗ 2 запущен в Docker как контейнер `rustfs`, в нём бакет `hh-lake` с датасетом и результатами ДЗ 3. Команды выполняются из папки `hw5`, журналы пишутся в `logs/`.

Кластер, образ, ключи S3:

```bash
kind create cluster --config kind-config.yaml && kubectl wait --for=condition=Ready node --all --timeout=120s && kubectl get nodes -o wide
```

```bash
docker build -t hw5-pairs:1 . && kind load docker-image hw5-pairs:1 --name hw5 && docker network connect kind rustfs && kubectl create namespace hw5 && kubectl create secret generic s3 -n hw5 --from-literal=AWS_ACCESS_KEY_ID=rustfsadmin --from-literal=AWS_SECRET_ACCESS_KEY=rustfsadmin
```

Остановка по памяти:

```bash
kubectl apply -f k8s/pairs-oom.yaml && kubectl wait -n hw5 --for=condition=failed job/pairs-oom --timeout=300s && kubectl get pods -n hw5 -l job-name=pairs-oom -o 'custom-columns=POD:.metadata.name,MEMORY_LIMIT:.spec.containers[0].resources.limits.memory,STATUS:.status.phase,REASON:.status.containerStatuses[0].state.terminated.reason,EXIT_CODE:.status.containerStatuses[0].state.terminated.exitCode' | tee logs/pairs-oom.txt && kubectl describe job -n hw5 pairs-oom | sed -n '/^Events/,$p' | tee -a logs/pairs-oom.txt
```

Замер пика и подобранный предел:

```bash
kubectl apply -f k8s/pairs-measure.yaml && kubectl wait -n hw5 --for=condition=complete job/pairs-measure --timeout=600s && kubectl logs -n hw5 job/pairs-measure | tee logs/pairs-measure.txt
```

```bash
kubectl apply -f k8s/pairs-fit.yaml && kubectl wait -n hw5 --for=condition=complete job/pairs-fit --timeout=600s && kubectl get pods -n hw5 -l job-name=pairs-fit -o 'custom-columns=POD:.metadata.name,MEMORY_LIMIT:.spec.containers[0].resources.limits.memory,STATUS:.status.phase' | tee logs/pairs-fit.txt && kubectl logs -n hw5 job/pairs-fit | tee -a logs/pairs-fit.txt
```

RustFS внутри кластера и перенос бакета:

```bash
kubectl apply -f k8s/rustfs.yaml && kubectl rollout status -n hw5 deploy/rustfs --timeout=300s && kubectl get deploy/rustfs pvc/rustfs svc/s3 -n hw5 && kubectl get pods -n hw5 -l app=rustfs
```

```bash
kubectl port-forward -n hw5 svc/s3 9100:9000 >/dev/null & sleep 3; mc alias set k8s http://127.0.0.1:9100 rustfsadmin rustfsadmin && mc mb k8s/hh-lake && mc mirror --quiet rustfs/hh-lake k8s/hh-lake | tail -4 && for a in rustfs k8s; do echo "$a: $(mc du $a/hh-lake)"; done | tee logs/mirror.txt && kubectl exec -n hw5 deploy/rustfs -- du -sh /data/rustfs0 /data/rustfs1 /data/rustfs2 /data/rustfs3 | tee -a logs/mirror.txt; kill %1
```

Расчёт по частям и объединение:

```bash
kubectl apply -f k8s/pairs-parts.yaml && kubectl wait -n hw5 --for=condition=complete job/pairs-parts --timeout=600s && kubectl get pods -n hw5 -l job-name=pairs-parts -o 'custom-columns=POD:.metadata.name,STATUS:.status.phase,START:.status.containerStatuses[0].state.terminated.startedAt,END:.status.containerStatuses[0].state.terminated.finishedAt' | tee logs/pairs-parts.txt && for i in 0 1 2 3; do kubectl logs -n hw5 -l job-name=pairs-parts,batch.kubernetes.io/job-completion-index=$i; done | tee -a logs/pairs-parts.txt
```

```bash
kubectl apply -f k8s/pairs-merge.yaml && kubectl wait -n hw5 --for=condition=complete job/pairs-merge --timeout=300s && kubectl logs -n hw5 job/pairs-merge | tee logs/pairs-merge.txt
```

Нехватка процессора:

```bash
kubectl describe node hw5-control-plane | sed -n '/Allocated resources/,/memory/p' | tee logs/pairs-cpu.txt && kubectl apply -f k8s/pairs-cpu.yaml && sleep 1 && kubectl get pods -n hw5 -l job-name=pairs-cpu | tee -a logs/pairs-cpu.txt && kubectl wait -n hw5 --for=condition=complete job/pairs-cpu --timeout=600s && kubectl get pods -n hw5 -l job-name=pairs-cpu -o 'custom-columns=POD:.metadata.name,CPU_REQUEST:.spec.containers[0].resources.requests.cpu,STATUS:.status.phase,CREATED:.metadata.creationTimestamp,START:.status.containerStatuses[0].state.terminated.startedAt' | tee -a logs/pairs-cpu.txt && kubectl get events -n hw5 --field-selector reason=FailedScheduling -o custom-columns=POD:.involvedObject.name,MESSAGE:.message | tee -a logs/pairs-cpu.txt
```

Вытеснение по приоритету:

```bash
kubectl get pods -n hw5 -l 'job-name in (pairs-low,pairs-high)' -w | tee logs/priority.txt & sleep 1; kubectl apply -f k8s/pairs-low.yaml && kubectl wait -n hw5 --for=condition=Ready pod -l job-name=pairs-low --timeout=60s && kubectl apply -f k8s/pairs-high.yaml && kubectl wait -n hw5 --for=condition=complete job/pairs-high job/pairs-low --timeout=600s; sleep 1; kill %1
```

```bash
kubectl get events -n hw5 --field-selector reason=Preempted -o custom-columns=POD:.involvedObject.name,MESSAGE:.message | tee -a logs/priority.txt && kubectl get pods -n hw5 -l job-name=pairs-high -o custom-columns=POD:.metadata.name,UID:.metadata.uid | tee -a logs/priority.txt && kubectl get jobs -n hw5 pairs-low pairs-high -o 'custom-columns=JOB:.metadata.name,PRIORITY:.spec.template.spec.priorityClassName,CPU_REQUEST:.spec.template.spec.containers[0].resources.requests.cpu,FAILED:.status.failed,SUCCEEDED:.status.succeeded' | tee -a logs/priority.txt
```

Квота пространства имён:

```bash
kubectl apply -f k8s/quota.yaml && kubectl create secret generic s3 -n hw5-quota --from-literal=AWS_ACCESS_KEY_ID=rustfsadmin --from-literal=AWS_SECRET_ACCESS_KEY=rustfsadmin && kubectl apply -f k8s/pairs-quota.yaml && sleep 2 && kubectl get pods -n hw5-quota | tee logs/quota.txt && kubectl describe resourcequota -n hw5-quota | tee -a logs/quota.txt && kubectl wait -n hw5-quota --for=condition=complete job/pairs-quota --timeout=600s && kubectl get pods -n hw5-quota -o 'custom-columns=POD:.metadata.name,MEMORY_REQUEST:.spec.containers[0].resources.requests.memory,STATUS:.status.phase,CREATED:.metadata.creationTimestamp' | tee -a logs/quota.txt && kubectl get events -n hw5-quota --field-selector reason=FailedCreate -o custom-columns=MESSAGE:.message | head -2 | tee -a logs/quota.txt
```

Удаление кластера:

```bash
kind delete cluster --name hw5 && docker network disconnect kind rustfs
```
