# Практика: сравнение типов кеширования

Проект реализует три стратегии кеширования одной и той же системы:

- `cache_aside` (Lazy Loading / Cache-Aside / Write-Around),
- `write_through`,
- `write_back`.

## Быстрый старт

```bash
python main.py
```

После запуска:

- в консоль выводятся логи по каждому профилю и стратегии;
- генерируется файл `REPORT.md` с таблицей метрик и блоком выводов;
- генерируется файл `CONSOLE_LOG.txt` с логом тестового прогона.

## Профили нагрузки

- `read-heavy` (80/20),
- `balanced` (50/50),
- `write-heavy` (20/80).

## Что измеряется

- `throughput (req/sec)`,
- `avg latency`,
- обращения в БД (`read/write`),
- `cache hit rate`,
- для `write_back`: накопление буфера и число `flush`.

