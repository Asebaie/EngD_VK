# Команды ДЗ 2

## Запуск RustFS на четырёх папках-дисках

```bash
mkdir -p ~/rustfs-lab/disk{0..3}
```

```bash
rustfs_up() {
  docker run -d --name rustfs \
    -p 127.0.0.1:9000:9000 -p 127.0.0.1:9001:9001 \
    -v "$HOME/rustfs-lab/disk0:/data/rustfs0" \
    -v "$HOME/rustfs-lab/disk1:/data/rustfs1" \
    -v "$HOME/rustfs-lab/disk2:/data/rustfs2" \
    -v "$HOME/rustfs-lab/disk3:/data/rustfs3" \
    -e RUSTFS_VOLUMES="/data/rustfs{0...3}" \
    -e RUSTFS_UNSAFE_BYPASS_DISK_CHECK=true \
    -e RUSTFS_ADDRESS=":9000" \
    -e RUSTFS_CONSOLE_ADDRESS=":9001" \
    -e RUSTFS_CONSOLE_ENABLE=true \
    -e RUSTFS_ACCESS_KEY=rustfsadmin \
    -e RUSTFS_SECRET_KEY=rustfsadmin \
    rustfs/rustfs:latest
}
rustfs_up
```

```bash
docker ps --filter name=rustfs; docker logs rustfs 2>&1 | grep -v WARNING; du -sh ~/rustfs-lab/disk*
```

## Загрузка данных

```bash
mc alias set rustfs http://127.0.0.1:9000 rustfsadmin rustfsadmin
mc mb rustfs/vacancies-csv && mc mb rustfs/vacancies-json && mc mb rustfs/write-test
mc cp ~/rustfs-lab/source/it_vacancies_2024.csv rustfs/vacancies-csv/
mc cp --recursive ~/rustfs-lab/source/hh_sample/ rustfs/vacancies-json/ > /dev/null
mc ls --recursive --summarize rustfs/vacancies-json | tail -3
```

## Размеры папок и фрагменты

```bash
du -sh ~/rustfs-lab/source/it_vacancies_2024.csv ~/rustfs-lab/disk*/vacancies-csv ~/rustfs-lab/source/hh_sample ~/rustfs-lab/disk*/vacancies-json
ls -l ~/rustfs-lab/disk0/vacancies-csv/it_vacancies_2024.csv/*/ | head -6
cd ~/rustfs-lab; for d in 0 1 2 3; do echo "disk$d part.1:"; dd if=$(echo disk$d/vacancies-csv/it_vacancies_2024.csv/*/part.1) bs=1 skip=32 count=70 2>/dev/null | LC_ALL=C tr -c '[:print:]' '.'; echo; done
ls -l ~/rustfs-lab/source/hh_sample/100595731.json ~/rustfs-lab/disk*/vacancies-json/100595731.json/
shasum -a 256 ~/rustfs-lab/source/it_vacancies_2024.csv; mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256
```

## Способ A: папка заменена пустой

Потеряна 1 папка из 4:

```bash
docker rm -f rustfs && mv ~/rustfs-lab/disk3 ~/rustfs-lab/disk3.lost && rustfs_up
stat -f '%SB  %N' ~/rustfs-lab/disk*; du -sh ~/rustfs-lab/disk*
mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256; mc cp ~/rustfs-lab/source/hh_sample/100595731.json rustfs/write-test/s1.json
cmp ~/rustfs-lab/disk3/vacancies-csv/it_vacancies_2024.csv/*/part.1 ~/rustfs-lab/disk3.lost/vacancies-csv/it_vacancies_2024.csv/*/part.1 && echo "part.1: restored == lost"
```

Потеряны 2 папки из 4:

```bash
docker rm -f rustfs && mv ~/rustfs-lab/disk2 ~/rustfs-lab/disk2.lost && mv ~/rustfs-lab/disk3 ~/rustfs-lab/disk3.healed && rustfs_up
du -sh ~/rustfs-lab/disk*; curl -s -w '\n[http %{http_code}]\n' http://127.0.0.1:9000/health/ready
mc ls rustfs; mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256
```

Потеряны 3 папки из 4:

```bash
docker rm -f rustfs && mv ~/rustfs-lab/disk1 ~/rustfs-lab/disk1.lost && rustfs_up
du -sh ~/rustfs-lab/disk*; curl -s -w '\n[http %{http_code}]\n' http://127.0.0.1:9000/health/ready
mc ls rustfs; mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256
```

Возврат исходных папок:

```bash
docker rm -f rustfs && mkdir ~/rustfs-lab/blank && mv ~/rustfs-lab/disk{1,2,3} ~/rustfs-lab/blank/ && mv ~/rustfs-lab/disk1.lost ~/rustfs-lab/disk1 && mv ~/rustfs-lab/disk2.lost ~/rustfs-lab/disk2 && mv ~/rustfs-lab/disk3.lost ~/rustfs-lab/disk3 && rustfs_up
mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256; du -sh ~/rustfs-lab/disk?
```

## Способ B: папка недоступна

Закрыта 1 папка, затем 2:

```bash
chmod 000 ~/rustfs-lab/disk3; ls ~/rustfs-lab/disk3
mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256; mc cp ~/rustfs-lab/source/hh_sample/100595731.json rustfs/write-test/o1.json
chmod 000 ~/rustfs-lab/disk1
mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256; mc cp ~/rustfs-lab/source/hh_sample/100595731.json rustfs/write-test/o2.json
chmod 755 ~/rustfs-lab/disk1 ~/rustfs-lab/disk3
```

Закрыты 3 папки:

```bash
chmod 000 ~/rustfs-lab/disk1 ~/rustfs-lab/disk2 ~/rustfs-lab/disk3; ls -ld ~/rustfs-lab/disk?
mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256; mc ls rustfs
chmod 755 ~/rustfs-lab/disk1 ~/rustfs-lab/disk2 ~/rustfs-lab/disk3; mc cat rustfs/vacancies-csv/it_vacancies_2024.csv | shasum -a 256
```
