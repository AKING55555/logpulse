#!/usr/bin/env python3
"""
LogPulse Synthetic Data Generator
Generates and loads 1,000,000+ realistic distributed log events into MySQL 8.
Uses reproducible random seeding and batched multi-row INSERTs (5,000 rows per transaction).
"""

import argparse
import datetime
import math
import os
import random
import sys
import time
import uuid
from typing import List, Tuple

import pymysql

# Fixed seed for reproducibility
RANDOM_SEED = 42

SERVICES = [
    "auth-service",
    "payment-service",
    "order-service",
    "inventory-service",
    "notification-service",
]

HOSTS = [f"host-{i:02d}.ec2.internal" for i in range(1, 11)]

ENDPOINTS = {
    "auth-service": [
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/refresh",
        "/api/v1/auth/verify",
    ],
    "payment-service": [
        "/api/v1/payments/charge",
        "/api/v1/payments/refund",
        "/api/v1/payments/methods",
        "/api/v1/payments/webhook",
    ],
    "order-service": [
        "/api/v1/orders/create",
        "/api/v1/orders/status",
        "/api/v1/orders/cancel",
        "/api/v1/orders/list",
    ],
    "inventory-service": [
        "/api/v1/inventory/check",
        "/api/v1/inventory/reserve",
        "/api/v1/inventory/restock",
        "/api/v1/inventory/sku",
    ],
    "notification-service": [
        "/api/v1/notifications/email",
        "/api/v1/notifications/sms",
        "/api/v1/notifications/push",
        "/api/v1/notifications/webhook",
    ],
}

ERROR_MESSAGES = [
    "Connection timeout to upstream service",
    "Database deadlock detected during transaction commit",
    "HTTP 502 Bad Gateway from downstream provider",
    "Token validation failed: signature expired",
    "Payment gateway rejected authorization: InsufficientFunds",
    "Out of memory error in worker pool",
]

WARN_MESSAGES = [
    "Slow database query execution > 500ms",
    "Rate limit threshold reached 85%",
    "Retry attempt 2/3 for RPC call",
    "Cache miss for key prefix session:*",
    "High memory watermark warning: heap utilization 78%",
]

INFO_MESSAGES = [
    "Processed request successfully in 24ms",
    "User authentication succeeded",
    "Order status updated to SHIPPED",
    "Dispatched push notification batch",
    "Inventory reservation released for expired cart",
]

DEBUG_MESSAGES = [
    "Resolved DNS for internal service cluster",
    "Connection pool active=12 idle=8 max=50",
    "Parsed request payload headers and schema",
    "Evaluating feature flag checkout_v2=TRUE",
]


def load_env_defaults():
    """Loads configuration from environment variables or .env file."""
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    env = {}
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


def generate_batch(batch_size: int, start_time: datetime.datetime, total_seconds: float) -> List[Tuple]:
    """Generates a batch of synthetic log tuples."""
    batch = []
    for _ in range(batch_size):
        # 1. Unique trace ID
        trace_id = str(uuid.uuid4())

        # 2. Service & Host
        service = random.choice(SERVICES)
        host = random.choice(HOSTS)

        # 3. Log Level: ~5% ERROR, ~15% WARN, ~60% INFO, ~20% DEBUG
        r_level = random.random()
        if r_level < 0.05:
            level = "ERROR"
            message = random.choice(ERROR_MESSAGES)
        elif r_level < 0.20:
            level = "WARN"
            message = random.choice(WARN_MESSAGES)
        elif r_level < 0.80:
            level = "INFO"
            message = random.choice(INFO_MESSAGES)
        else:
            level = "DEBUG"
            message = random.choice(DEBUG_MESSAGES)

        # 4. Timestamp spread evenly across last 7 days with millisecond resolution
        offset_seconds = random.uniform(0, total_seconds)
        ts = start_time + datetime.timedelta(seconds=offset_seconds)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        # 5. Endpoint
        endpoint = random.choice(ENDPOINTS[service])

        # 6. Latency: lognormal distribution (long-tailed)
        # LogNormal(mean=3.6, sigma=0.9) produces median ~36ms, mean ~60ms, with occasional long tail up to 3000ms+
        latency_ms = int(math.exp(random.gauss(3.6, 0.9)))
        if level == "ERROR":
            # Errors often correlate with timeouts
            latency_ms += random.choice([0, 500, 1500, 5000])

        batch.append((trace_id, service, host, level, ts_str, message, latency_ms, endpoint))
    return batch


def main():
    parser = argparse.ArgumentParser(description="Generate and load synthetic LogPulse events into MySQL.")
    parser.add_argument("--rows", type=int, default=1_000_000, help="Number of rows to generate (default: 1,000,000)")
    parser.add_argument("--batch-size", type=int, default=5000, help="Batch size per INSERT statement (default: 5,000)")
    parser.add_argument("--host", type=str, default=None, help="MySQL host (default: from .env or 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="MySQL port (default: from .env or 3307)")
    parser.add_argument("--user", type=str, default=None, help="MySQL user (default: from .env or logpulse_user)")
    parser.add_argument("--password", type=str, default=None, help="MySQL password")
    parser.add_argument("--database", type=str, default=None, help="MySQL database (default: logpulse)")
    args = parser.parse_args()

    env = load_env_defaults()
    host = args.host or env.get("DB_HOST", "127.0.0.1")
    port = args.port or int(env.get("DB_PORT", 3307))
    user = args.user or env.get("DB_USER", "logpulse_user")
    password = args.password or env.get("DB_PASSWORD", "logpulse_password")
    db_name = args.database or env.get("DB_NAME", "logpulse")

    # Safety Guard: Ensure loader only runs against local container
    if host not in ("127.0.0.1", "localhost") or port != 3307:
        print(f"Safety Error: Loader is restricted to local container (host=127.0.0.1/localhost, port=3307). Received host={host}, port={port}", file=sys.stderr)
        sys.exit(1)

    print("==================================================")
    print("LogPulse Synthetic Data Generator")
    print(f"Target: {user}@{host}:{port}/{db_name}")
    print(f"Rows to generate : {args.rows:,}")
    print(f"Batch size       : {args.batch_size:,} rows per transaction")
    print(f"Random seed      : {RANDOM_SEED}")
    print("==================================================")

    random.seed(RANDOM_SEED)

    # 7-day span ending at 2026-10-03 00:00:00 UTC
    end_time = datetime.datetime(2026, 10, 3, 0, 0, 0)
    start_time = end_time - datetime.timedelta(days=7)
    total_seconds = (end_time - start_time).total_seconds()

    print(f"Data timeframe   : {start_time} to {end_time} (7 days)")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        charset="utf8mb4",
        autocommit=False,
    )

    insert_sql = (
        "INSERT INTO events (trace_id, service, host, level, ts, message, latency_ms, endpoint) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
    )

    rows_loaded = 0
    start_wall_time = time.time()

    try:
        with conn.cursor() as cursor:
            # Temporarily optimize for bulk load
            cursor.execute("SET foreign_key_checks = 0;")
            cursor.execute("SET unique_checks = 0;")

            total_batches = (args.rows + args.batch_size - 1) // args.batch_size
            for batch_idx in range(1, total_batches + 1):
                cur_batch_size = min(args.batch_size, args.rows - rows_loaded)
                batch_data = generate_batch(cur_batch_size, start_time, total_seconds)

                cursor.executemany(insert_sql, batch_data)
                conn.commit()
                rows_loaded += cur_batch_size

                if batch_idx % 10 == 0 or rows_loaded == args.rows:
                    elapsed = time.time() - start_wall_time
                    rate = rows_loaded / elapsed if elapsed > 0 else 0
                    percent = (rows_loaded / args.rows) * 100.0
                    print(f"Progress: {rows_loaded:,}/{args.rows:,} rows ({percent:5.1f}%) | "
                          f"Elapsed: {elapsed:6.2f}s | Speed: {rate:8.0f} rows/s")

            # Restore settings
            cursor.execute("SET foreign_key_checks = 1;")
            cursor.execute("SET unique_checks = 1;")
            conn.commit()

        total_elapsed = time.time() - start_wall_time
        overall_rate = rows_loaded / total_elapsed if total_elapsed > 0 else 0

        print("==================================================")
        print("Data Generation & Load Complete!")
        print(f"Total Rows Loaded : {rows_loaded:,}")
        print(f"Total Elapsed Time: {total_elapsed:.2f} seconds")
        print(f"Average Throughput: {overall_rate:.0f} rows/second")
        print("==================================================")

    except Exception as e:
        conn.rollback()
        print(f"Error during bulk loading: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
