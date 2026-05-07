import argparse
import random
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Operation:
    kind: str
    key: int
    value: int


class FakeDB:
    def __init__(self, initial_data: Dict[int, int], read_delay: float, write_delay: float) -> None:
        self.storage = dict(initial_data)
        self.read_delay = read_delay
        self.write_delay = write_delay
        self.read_count = 0
        self.write_count = 0

    def read(self, key: int) -> int:
        self.read_count += 1
        time.sleep(self.read_delay)
        return self.storage.get(key, 0)

    def write(self, key: int, value: int) -> None:
        self.write_count += 1
        time.sleep(self.write_delay)
        self.storage[key] = value


class Cache:
    def __init__(self) -> None:
        self.storage: Dict[int, int] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: int) -> Tuple[bool, int]:
        if key in self.storage:
            self.hits += 1
            return True, self.storage[key]
        self.misses += 1
        return False, 0

    def set(self, key: int, value: int) -> None:
        self.storage[key] = value

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


class Strategy:
    name = "base"

    def read(self, key: int) -> int:
        raise NotImplementedError

    def write(self, key: int, value: int) -> None:
        raise NotImplementedError

    def finalize(self) -> Dict[str, float]:
        return {}


class CacheAsideStrategy(Strategy):
    name = "cache_aside"

    def __init__(self, db: FakeDB, cache: Cache) -> None:
        self.db = db
        self.cache = cache

    def read(self, key: int) -> int:
        found, value = self.cache.get(key)
        if found:
            return value
        value = self.db.read(key)
        self.cache.set(key, value)
        return value

    def write(self, key: int, value: int) -> None:
        self.db.write(key, value)


class WriteThroughStrategy(Strategy):
    name = "write_through"

    def __init__(self, db: FakeDB, cache: Cache) -> None:
        self.db = db
        self.cache = cache

    def read(self, key: int) -> int:
        found, value = self.cache.get(key)
        if found:
            return value
        value = self.db.read(key)
        self.cache.set(key, value)
        return value

    def write(self, key: int, value: int) -> None:
        self.cache.set(key, value)
        self.db.write(key, value)


class WriteBackStrategy(Strategy):
    name = "write_back"

    def __init__(self, db: FakeDB, cache: Cache, flush_every_ops: int = 100) -> None:
        self.db = db
        self.cache = cache
        self.flush_every_ops = flush_every_ops
        self.pending: Dict[int, int] = {}
        self.op_count = 0
        self.max_pending = 0
        self.flush_count = 0

    def read(self, key: int) -> int:
        found, value = self.cache.get(key)
        if found:
            return value
        value = self.db.read(key)
        self.cache.set(key, value)
        return value

    def write(self, key: int, value: int) -> None:
        self.cache.set(key, value)
        self.pending[key] = value
        self.op_count += 1
        self.max_pending = max(self.max_pending, len(self.pending))
        if self.op_count % self.flush_every_ops == 0:
            self.flush()

    def flush(self) -> None:
        if not self.pending:
            return
        for key, value in list(self.pending.items()):
            self.db.write(key, value)
        self.pending.clear()
        self.flush_count += 1

    def finalize(self) -> Dict[str, float]:
        self.flush()
        return {
            "max_pending_writes": float(self.max_pending),
            "flush_count": float(self.flush_count),
        }


def generate_operations(
    seed: int,
    total_requests: int,
    read_ratio: float,
    keyspace: int,
    value_min: int = 1,
    value_max: int = 100_000,
) -> List[Operation]:
    rng = random.Random(seed)
    ops: List[Operation] = []
    for _ in range(total_requests):
        key = rng.randint(1, keyspace)
        if rng.random() < read_ratio:
            ops.append(Operation(kind="read", key=key, value=0))
        else:
            value = rng.randint(value_min, value_max)
            ops.append(Operation(kind="write", key=key, value=value))
    return ops


def run_benchmark(strategy: Strategy, operations: List[Operation]) -> Dict[str, float]:
    latencies_ms: List[float] = []
    start_all = time.perf_counter()

    for op in operations:
        started = time.perf_counter()
        if op.kind == "read":
            strategy.read(op.key)
        else:
            strategy.write(op.key, op.value)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies_ms.append(elapsed_ms)

    extra = strategy.finalize()
    total_s = time.perf_counter() - start_all
    throughput = len(operations) / total_s if total_s > 0 else 0.0

    metrics = {
        "throughput_req_sec": throughput,
        "avg_latency_ms": statistics.fmean(latencies_ms) if latencies_ms else 0.0,
    }
    metrics.update(extra)
    return metrics


def warm_cache(strategy: Strategy, keys: List[int]) -> None:
    for key in keys:
        strategy.read(key)


def format_num(value: float) -> str:
    return f"{value:.2f}"


def build_strategies(
    initial_data: Dict[int, int],
    db_read_delay: float,
    db_write_delay: float,
) -> List[Tuple[str, Strategy, FakeDB, Cache]]:
    db1 = FakeDB(initial_data, db_read_delay, db_write_delay)
    cache1 = Cache()
    s1 = CacheAsideStrategy(db1, cache1)

    db2 = FakeDB(initial_data, db_read_delay, db_write_delay)
    cache2 = Cache()
    s2 = WriteThroughStrategy(db2, cache2)

    db3 = FakeDB(initial_data, db_read_delay, db_write_delay)
    cache3 = Cache()
    s3 = WriteBackStrategy(db3, cache3, flush_every_ops=100)

    return [
        (s1.name, s1, db1, cache1),
        (s2.name, s2, db2, cache2),
        (s3.name, s3, db3, cache3),
    ]


def print_report_line(profile: str, name: str, results: Dict[str, float]) -> None:
    line = (
        f"[{profile}] {name}: "
        f"throughput={format_num(results['throughput_req_sec'])} req/s, "
        f"avg_latency={format_num(results['avg_latency_ms'])} ms, "
        f"db_reads={int(results['db_reads'])}, "
        f"db_writes={int(results['db_writes'])}, "
        f"cache_hit_rate={format_num(results['cache_hit_rate'] * 100)}%"
    )
    if "max_pending_writes" in results:
        line += (
            f", write_back_max_pending={int(results['max_pending_writes'])}, "
            f"flush_count={int(results['flush_count'])}"
        )
    print(line)


def run_profile(
    profile_name: str,
    read_ratio: float,
    operations_count: int,
    keyspace: int,
    warmup_keys: int,
    db_read_delay: float,
    db_write_delay: float,
    seed: int,
) -> List[Dict[str, float]]:
    initial_data = {k: k * 10 for k in range(1, keyspace + 1)}
    operations = generate_operations(
        seed=seed,
        total_requests=operations_count,
        read_ratio=read_ratio,
        keyspace=keyspace,
    )

    rows: List[Dict[str, float]] = []
    for strategy_name, strategy, db, cache in build_strategies(initial_data, db_read_delay, db_write_delay):
        warm_cache(strategy, list(range(1, warmup_keys + 1)))
        metrics = run_benchmark(strategy, operations)

        result_row: Dict[str, float] = {
            "profile": profile_name,
            "strategy": strategy_name,
            "throughput_req_sec": metrics["throughput_req_sec"],
            "avg_latency_ms": metrics["avg_latency_ms"],
            "db_reads": float(db.read_count),
            "db_writes": float(db.write_count),
            "cache_hit_rate": cache.hit_rate,
        }
        if "max_pending_writes" in metrics:
            result_row["max_pending_writes"] = metrics["max_pending_writes"]
            result_row["flush_count"] = metrics["flush_count"]

        rows.append(result_row)
        print_report_line(profile_name, strategy_name, result_row)

    return rows


def save_markdown_report(path: str, rows: List[Dict[str, float]]) -> None:
    lines = [
        "# Отчет по сравнению стратегий кеширования",
        "",
        "| Профиль | Стратегия | Throughput (req/sec) | Средняя задержка (ms) | Обращения в БД (read/write) | Hit Rate кеша | Параметры Write-Back |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        wb = "-"
        if "max_pending_writes" in row:
            wb = f"max_pending={int(row['max_pending_writes'])}, flush_count={int(row['flush_count'])}"
        lines.append(
            "| "
            + f"{row['profile']} | {row['strategy']} | {format_num(row['throughput_req_sec'])} | "
            + f"{format_num(row['avg_latency_ms'])} | {int(row['db_reads'])}/{int(row['db_writes'])} | "
            + f"{format_num(row['cache_hit_rate'] * 100)}% | {wb} |"
        )

    lines.extend(
        [
            "",
            "## Выводы",
            "",
            *build_conclusions(rows),
            "",
            "## Примечания",
            "",
            "- Все профили выполнены на одинаковом наборе операций (для конкретного профиля).",
            "- Для стратегии write-back отдельно зафиксированы размер накопления незаписанных данных и число flush.",
        ]
    )

    with open(path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сравнение стратегий кеширования.")
    parser.add_argument("--requests", type=int, default=6000, help="Число запросов на профиль.")
    parser.add_argument("--keyspace", type=int, default=800, help="Размер пространства ключей.")
    parser.add_argument("--warmup-keys", type=int, default=200, help="Размер прогрева кеша перед тестом.")
    parser.add_argument("--db-read-ms", type=float, default=1.0, help="Задержка чтения БД в миллисекундах.")
    parser.add_argument("--db-write-ms", type=float, default=2.5, help="Задержка записи БД в миллисекундах.")
    parser.add_argument("--seed", type=int, default=42, help="Базовый seed для генерации нагрузки.")
    parser.add_argument("--report", default="REPORT.md", help="Путь к итоговому markdown-отчету.")
    parser.add_argument("--console-log", default="CONSOLE_LOG.txt", help="Файл для сохранения консольных логов.")
    return parser.parse_args()


class Tee:
    def __init__(self, *streams) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def pick_best(rows: List[Dict[str, float]], profile: str, key: str, reverse: bool) -> str:
    profile_rows = [row for row in rows if row["profile"] == profile]
    best = sorted(profile_rows, key=lambda row: row[key], reverse=reverse)[0]
    return str(best["strategy"])


def build_conclusions(rows: List[Dict[str, float]]) -> List[str]:
    conclusions: List[str] = []
    for profile in ["read-heavy", "balanced", "write-heavy"]:
        best_throughput = pick_best(rows, profile, "throughput_req_sec", reverse=True)
        best_latency = pick_best(rows, profile, "avg_latency_ms", reverse=False)
        min_writes = pick_best(rows, profile, "db_writes", reverse=False)
        conclusions.append(
            f"- Профиль `{profile}`: лучший throughput — `{best_throughput}`, "
            f"лучшая задержка — `{best_latency}`, меньше всего write в БД — `{min_writes}`."
        )

    overall_read = pick_best(rows, "read-heavy", "throughput_req_sec", reverse=True)
    overall_write = pick_best(rows, "write-heavy", "throughput_req_sec", reverse=True)
    overall_mix = pick_best(rows, "balanced", "throughput_req_sec", reverse=True)
    conclusions.append("")
    conclusions.append(f"- Для чтения оптимальна стратегия `{overall_read}`.")
    conclusions.append(f"- Для записи оптимальна стратегия `{overall_write}`.")
    conclusions.append(f"- Для смешанной нагрузки оптимальна стратегия `{overall_mix}`.")
    return conclusions


def main() -> None:
    args = parse_args()
    db_read_delay = args.db_read_ms / 1000.0
    db_write_delay = args.db_write_ms / 1000.0

    profiles = [
        ("read-heavy", 0.80),
        ("balanced", 0.50),
        ("write-heavy", 0.20),
    ]

    original_stdout = sys.stdout
    with open(args.console_log, "w", encoding="utf-8") as log_file:
        sys.stdout = Tee(original_stdout, log_file)
        try:
            print("=== Старт тестов кеширования ===")
            all_rows: List[Dict[str, float]] = []
            for idx, (name, read_ratio) in enumerate(profiles):
                print(f"--- Профиль: {name} ({int(read_ratio * 100)}% read / {int((1 - read_ratio) * 100)}% write) ---")
                rows = run_profile(
                    profile_name=name,
                    read_ratio=read_ratio,
                    operations_count=args.requests,
                    keyspace=args.keyspace,
                    warmup_keys=args.warmup_keys,
                    db_read_delay=db_read_delay,
                    db_write_delay=db_write_delay,
                    seed=args.seed + idx,
                )
                all_rows.extend(rows)

            save_markdown_report(args.report, all_rows)
            print(f"=== Готово. Отчет сохранен: {args.report} ===")
            print(f"=== Логи сохранены: {args.console_log} ===")
        finally:
            sys.stdout = original_stdout


if __name__ == "__main__":
    main()
