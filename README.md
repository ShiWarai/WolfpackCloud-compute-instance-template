# WolfpackCloud-compute-instance-template

Шаблон вычислительного модуля WolfpackCloud: образ ROS 2 Humble с **RMW Zenoh**, симметричная нода **`wolfpackcloud_peer`**.

## Поведение

- Два пода обмениваются сообщениями **`wolfpackcloud_peer_interfaces/msg/RttPacket`** по парам топиков (по умолчанию `/topic_a` ↔ `/topic_b`).
- Каждая нода периодически шлёт **пинг** (`is_reply=false`), удалённая сторона отражает пакет (**эхо**, `is_reply=true`) с теми же `correlation_id` и `stamp_sent`, обновляя `counter_value`.
- **Круговая задержка** (отправка → обработка на peer → ответ → приём на своей стороне) измеряется по **монотонным** часам через таблицу `pending` для собственных `correlation_id`.
- В **`/rosout`** уходит агрегат через `rclpy` logging: раз в `log_period_sec` логируется **медиана** RTT по скользящему окну последних измерений (**не** среднее арифметическое).
- При переполнении ожидаемых ответов (`pending` ≥ `pending_cap`) или при превышении порога счётчика сбрасываются соответствующие состояния (очередь измерений / pending / счётчик — см. параметры в коде).

Идентификаторы заявок: `correlation_id = (peer_shard << 32) | seq`. Параметр **`peer_shard`** (по умолчанию `0` → авто из имени хоста) задайте явно, если нужно гарантировать уникальность между однотипными окружениями.

## Запуск

Внутри образа:

```bash
ros2 launch wolfpackcloud_peer peer.launch.py publish_topic:=/topic_a subscribe_topic:=/topic_b
```

Аргументы `pulse_period_sec`, `log_period_sec` задают период пингов и период сводки в rosout. **`peer_shard`** (целое, по умолчанию `0`): старшие 32 бита `correlation_id`; `0` означает авто из SHA256(hostname). В Kubernetes для двух подов задайте разные значения (см. `deploy/k3s/wolfpackcloud-control-peers/`).

## Сборка образа (wolfpack-registry)

Из корня репозитория `WolfpackCloud-kubernetes` (нужны `kubectl`, `buildctl`, BuildKit в namespace `wolfpack-build`):

```bash
./scripts/build-with-buildkit.sh amd64 WolfpackCloud-compute-instance-template \
  10.43.50.10:5000/wolfpackcloud-compute-instance-peer:humble-amd64
```

```bash
./scripts/build-with-buildkit.sh arm64 WolfpackCloud-compute-instance-template \
  10.43.50.10:5000/wolfpackcloud-compute-instance-peer:humble-arm64
```

## Деплой peer-подов

```bash
cd deploy/k3s
kubectl apply -k zenoh/
kubectl apply -k wolfpackcloud-control-peers/
```

Подробности: [deploy/k3s/README.md](../deploy/k3s/README.md).

## Лицензия и автор

MIT, правообладатель и сопровождение: **ShiWarai** `<zhuravliov.pav@yandex.ru>` (см. `LICENSE` и `package.xml`).
