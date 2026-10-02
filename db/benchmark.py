#!/usr/bin/env python3
"""
LogPulse Index Benchmark
Measures the impact of adding idx_service_ts (service, ts) on all analytics queries.
Workflow: confirm row count, BEFORE timings, CREATE INDEX + ANALYZE, AFTER timings,
write raw EXPLAIN ANALYZE to docs/benchmarks/raw/, write summary to docs/benchmarks/index-benchmark.md.
Safety guard: only connects to 127.0.0.1/localhost:3307 (local container).
"""
import datetime, re, statistics, sys, time
from pathlib import Path
import pymysql

REPO_ROOT    = Path(__file__).resolve().parent.parent
RAW_DIR      = REPO_ROOT / "docs" / "benchmarks" / "raw"
SUMMARY_FILE = REPO_ROOT / "docs" / "benchmarks" / "index-benchmark.md"

QUERIES = [
    {
        "id": "q1_error_rate_5min",
        "label": "Q1 - Error rate per 5-min window (payment-service, last 24 h of data)",
        "sql": (
            "SELECT service,\n"
            "       FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(ts) / 300) * 300) AS window_start,\n"
            "       COUNT(*) AS total_events,\n"
            "       SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) AS error_events,\n"
            "       ROUND(SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS error_rate_pct\n"
            "FROM events\n"
            "WHERE service = 'payment-service'\n"
            "  AND ts >= '2026-10-02 00:00:00'\n"
            "  AND ts <  '2026-10-03 00:00:00'\n"
            "GROUP BY service, window_start\n"
            "ORDER BY window_start ASC"
        ),
    },
    {
        "id": "q2_p95_latency",
        "label": "Q2 - p95 latency per service (order-service, full 7-day window)",
        "sql": (
            "WITH ranked_events AS (\n"
            "    SELECT service, latency_ms,\n"
            "           ROW_NUMBER() OVER (PARTITION BY service ORDER BY latency_ms) AS rn,\n"
            "           COUNT(*) OVER (PARTITION BY service) AS cnt\n"
            "    FROM events\n"
            "    WHERE service = 'order-service'\n"
            "      AND ts >= '2026-09-26 00:00:00'\n"
            "      AND ts <  '2026-10-03 00:00:00'\n"
            ")\n"
            "SELECT service, latency_ms AS p95_latency_ms\n"
            "FROM ranked_events\n"
            "WHERE rn = CEIL(0.95 * cnt)"
        ),
    },
    {
        "id": "q3_top10_slow_endpoints",
        "label": "Q3 - Top 10 slowest endpoints (auth-service, full 7-day window)",
        "sql": (
            "WITH endpoint_stats AS (\n"
            "    SELECT service, endpoint,\n"
            "           COUNT(*) AS call_count,\n"
            "           ROUND(AVG(latency_ms), 2) AS avg_latency_ms,\n"
            "           MAX(latency_ms) AS max_latency_ms\n"
            "    FROM events\n"
            "    WHERE service = 'auth-service'\n"
            "      AND ts >= '2026-09-26 00:00:00'\n"
            "      AND ts <  '2026-10-03 00:00:00'\n"
            "    GROUP BY service, endpoint\n"
            "),\n"
            "ranked_endpoints AS (\n"
            "    SELECT *,\n"
            "           DENSE_RANK() OVER (PARTITION BY service ORDER BY avg_latency_ms DESC) AS rnk\n"
            "    FROM endpoint_stats\n"
            ")\n"
            "SELECT service, endpoint, call_count, avg_latency_ms, max_latency_ms, rnk AS latency_rank\n"
            "FROM ranked_endpoints\n"
            "WHERE rnk <= 10\n"
            "ORDER BY avg_latency_ms DESC"
        ),
    },
    {
        "id": "q4_point_lookup",
        "label": "Q4 - Point lookup: inventory-service, 2-hour window",
        "sql": (
            "SELECT id, trace_id, service, level, ts, latency_ms, endpoint\n"
            "FROM events\n"
            "WHERE service = 'inventory-service'\n"
            "  AND ts >= '2026-10-01 12:00:00'\n"
            "  AND ts <  '2026-10-01 14:00:00'\n"
            "LIMIT 100"
        ),
    },
    {
        "id": "q5_error_lookup",
        "label": "Q5 - Filtered ERROR lookup: notification-service, 1-day window",
        "sql": (
            "SELECT id, trace_id, service, level, ts, latency_ms, endpoint, message\n"
            "FROM events\n"
            "WHERE service = 'notification-service'\n"
            "  AND ts >= '2026-10-01 00:00:00'\n"
            "  AND ts <  '2026-10-02 00:00:00'\n"
            "  AND level = 'ERROR'\n"
            "LIMIT 100"
        ),
    },
]


def load_env() -> dict:
    env_file = REPO_ROOT / ".env"
    env: dict = {}
    if env_file.exists():
        with open(env_file) as fh:
            for line in fh:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def connect(env: dict):
    host = env.get("DB_HOST", "127.0.0.1")
    port = int(env.get("DB_PORT", 3307))
    if host not in ("127.0.0.1", "localhost") or port != 3307:
        sys.exit(f"Safety error: restricted to local container 127.0.0.1:3307, got {host}:{port}")
    return pymysql.connect(
        host=host, port=port,
        user=env.get("DB_USER", "logpulse_user"),
        password=env.get("DB_PASSWORD", "logpulse_password"),
        database=env.get("DB_NAME", "logpulse"),
        charset="utf8mb4", autocommit=True,
        read_timeout=600, write_timeout=600,
    )


def confirm_row_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM events")
        count = cur.fetchone()[0]
    print(f"\n{'='*60}")
    print(f"  Row count (SELECT COUNT(*)): {count:,}")
    print(f"{'='*60}\n")
    if count < 1_000_000:
        print(f"WARNING: only {count:,} rows. Target is 1 M+.", file=sys.stderr)
    return count


def parse_explain_metrics(text: str) -> dict:
    m = {"actual_time_ms": "N/A", "rows_examined": "N/A", "access_type": "N/A"}
    time_matches = re.findall(r"actual time=([\d.]+)\.\.([\d.]+)", text)
    if time_matches:
        m["actual_time_ms"] = f"{float(time_matches[-1][1]):.3f}"
    rows_matches = re.findall(r"\brows=(\d+)", text)
    if rows_matches:
        m["rows_examined"] = max(int(r) for r in rows_matches)
    type_m = re.search(
        r"(Table scan|Index lookup|Index range scan|Single-row index lookup"
        r"|Covering index scan|Rows fetched before execution|Filter"
        r"|Nested loop|Sort|Aggregate)",
        text,
    )
    if type_m:
        m["access_type"] = type_m.group(1)
    return m


def run_explain_analyze(conn, sql: str) -> str:
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN ANALYZE\n{sql}")
        rows = cur.fetchall()
    return "\n".join(str(r[0]) for r in rows)


def time_query(conn, sql: str, runs: int = 3) -> list:
    times = []
    with conn.cursor() as cur:
        for _ in range(runs):
            t0 = time.perf_counter()
            cur.execute(sql)
            cur.fetchall()
            times.append((time.perf_counter() - t0) * 1000)
    return times


def save_raw(phase: str, query_id: str, text: str) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{phase}_{query_id}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"    [raw] -> {path.relative_to(REPO_ROOT)}")


def benchmark_phase(conn, phase: str, results: dict) -> None:
    print(f"\n{'-'*60}")
    print(f"  PHASE: {phase.upper()}")
    print(f"{'-'*60}")
    results[phase] = {}
    for q in QUERIES:
        qid, label, sql = q["id"], q["label"], q["sql"]
        print(f"\n  {label}")
        print("    -> EXPLAIN ANALYZE ...", end=" ", flush=True)
        explain_text = run_explain_analyze(conn, sql)
        print("done")
        save_raw(phase, qid, explain_text)
        metrics = parse_explain_metrics(explain_text)
        print("    -> Timing 3 runs ...", end=" ", flush=True)
        times_ms = time_query(conn, sql, runs=3)
        med = statistics.median(times_ms)
        print(f"  {[f'{t:.1f}ms' for t in times_ms]}  median={med:.1f}ms")
        results[phase][qid] = {
            "label": label, "times_ms": times_ms,
            "median_ms": med, "explain_metrics": metrics,
        }


def build_summary_markdown(row_count: int, results: dict) -> str:
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = []
    L += [
        "# LogPulse Index Benchmark Report", "",
        f"_Generated: {now}_", "",
        "## Environment", "",
        "| Key | Value |",
        "|:----|:------|",
        "| MySQL version | 8.0 (Docker, host port 3307) |",
        f"| Total rows | {row_count:,} |",
        "| Table | `logpulse.events` |",
        "| Index added | `idx_service_ts (service, ts)` |",
        "| Runs per query | 3 (first run may be cold cache) |",
        "| Timing | Wall-clock via `time.perf_counter()` |",
        "",
        "> **Cold-cache note:** The first timed run may be slower because InnoDB buffer",
        "> pool pages are not yet loaded. The median of 3 runs is the canonical figure.",
        "",
        "## Summary Table", "",
        "| Query | Before (ms) | After (ms) | Speed-up | Rows examined (before) | Rows examined (after) | Access type (before) | Access type (after) |",
        "|:------|------------:|-----------:|--------:|----------------------:|---------------------:|:---------------------|:--------------------|",
    ]
    for q in QUERIES:
        qid = q["id"]
        bd = results.get("before", {}).get(qid, {})
        ad = results.get("after", {}).get(qid, {})
        bmed = bd.get("median_ms")
        amed = ad.get("median_ms")
        label = bd.get("label") or ad.get("label") or qid
        speedup = f"{bmed / amed:.2f}x" if bmed and amed and amed > 0 else "N/A"
        bm = bd.get("explain_metrics", {})
        am = ad.get("explain_metrics", {})
        L.append(
            f"| {label} | {bmed:.1f} | {amed:.1f} | {speedup} | "
            f"{bm.get('rows_examined','N/A')} | {am.get('rows_examined','N/A')} | "
            f"{bm.get('access_type','N/A')} | {am.get('access_type','N/A')} |"
        )
    L += ["", "## Per-Query Detail", ""]
    for q in QUERIES:
        qid = q["id"]
        L.append(f"### {qid.replace('_', ' ').title()}")
        L.append("")
        for phase in ("before", "after"):
            data = results.get(phase, {}).get(qid)
            if not data:
                continue
            t = data["times_ms"]
            em = data["explain_metrics"]
            L += [
                f"**{phase.capitalize()}**", "",
                f"- Run 1: {t[0]:.1f} ms",
                f"- Run 2: {t[1]:.1f} ms",
                f"- Run 3: {t[2]:.1f} ms",
                f"- **Median: {data['median_ms']:.1f} ms**",
                f"- Rows examined: {em['rows_examined']}",
                f"- Access type: {em['access_type']}",
                f"- EXPLAIN actual time (ms): {em['actual_time_ms']}",
                f"- Raw: [raw/{phase}_{qid}.txt](raw/{phase}_{qid}.txt)",
                "",
            ]
        bd = results.get("before", {}).get(qid, {})
        ad = results.get("after", {}).get(qid, {})
        bmed = bd.get("median_ms")
        amed = ad.get("median_ms")
        if bmed and amed:
            if amed < bmed * 0.9:
                L.append(f"> **Index helped.** Median {bmed:.1f} ms -> {amed:.1f} ms ({bmed/amed:.2f}x speed-up). The (service, ts) index enables an index range scan instead of a full partition scan.")
            elif amed <= bmed * 1.1:
                L.append(f"> **Index had minimal effect** ({bmed:.1f} ms -> {amed:.1f} ms). Partition pruning alone may be sufficient, or result set size makes both plans equivalent.")
            else:
                L.append(f"> **Index did not improve this query** ({bmed:.1f} ms -> {amed:.1f} ms). See raw EXPLAIN ANALYZE for details.")
        L.append("")
    L += [
        "## Methodology", "",
        "- Timings: wall-clock via `time.perf_counter()` (Python).",
        "- `EXPLAIN ANALYZE` forces full execution; `actual time` is server-side only.",
        "- `ANALYZE TABLE events` runs after index creation for fresh optimizer stats.",
        "- Buffer pool is NOT flushed between runs; runs 2-3 reflect warm-cache behaviour.",
        "- Raw EXPLAIN ANALYZE outputs: `docs/benchmarks/raw/`.",
        "",
    ]
    return "\n".join(L)


def drop_index_if_exists(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.STATISTICS "
            "WHERE table_schema = DATABASE() "
            "  AND table_name = 'events' "
            "  AND index_name = 'idx_service_ts'"
        )
        exists = cur.fetchone()[0]
    if exists:
        print("  idx_service_ts exists - dropping for clean BEFORE state ...")
        with conn.cursor() as cur:
            cur.execute("ALTER TABLE events DROP INDEX idx_service_ts")
        print("  Dropped.")


def main() -> None:
    print("=" * 60)
    print("  LogPulse - Index Benchmark")
    print("=" * 60)
    env = load_env()
    conn = connect(env)
    row_count = confirm_row_count(conn)
    drop_index_if_exists(conn)
    results: dict = {}

    benchmark_phase(conn, "before", results)

    print(f"\n{'-'*60}")
    print("  Creating INDEX idx_service_ts ON events (service, ts) ...")
    t0 = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute("CREATE INDEX idx_service_ts ON events (service, ts)")
    print(f"  Index created in {time.perf_counter() - t0:.2f} s")
    print("  Running ANALYZE TABLE events ...")
    with conn.cursor() as cur:
        cur.execute("ANALYZE TABLE events")
        cur.fetchall()
    print("  ANALYZE done.")

    benchmark_phase(conn, "after", results)

    print(f"\n{'-'*60}")
    print("  Writing outputs ...")
    md = build_summary_markdown(row_count, results)
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_FILE.write_text(md, encoding="utf-8")
    print(f"  Summary  -> {SUMMARY_FILE.relative_to(REPO_ROOT)}")
    print(f"  Raw dir  -> {RAW_DIR.relative_to(REPO_ROOT)}/")
    print(f"\n{'='*60}")
    print("  Benchmark complete.")
    print(f"{'='*60}\n")
    conn.close()


if __name__ == "__main__":
    main()