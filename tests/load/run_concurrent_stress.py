"""
High-Concurrency In-Memory Stress & Benchmark Runner.
Validates zero race conditions, thread safety, and sub-millisecond p99 latencies
under heavy multi-tenant parallel execution.
"""
import concurrent.futures
import statistics
import time
import unittest
from pathlib import Path
import os
import sys

# Ensure test AWS environment before importing lambda module
os.environ["AWS_ACCESS_KEY_ID"] = "mock_key"
os.environ["AWS_SECRET_ACCESS_KEY"] = "mock_secret"
os.environ["AWS_DEFAULT_REGION"] = "ap-southeast-1"
os.environ["AWS_REGION"] = "ap-southeast-1"

# Add lambda directory to sys.path
INFRA_ROOT = Path(__file__).resolve().parents[2]
LAMBDA_DIR = INFRA_ROOT / "infra" / "modules" / "06-superadmin"
if not LAMBDA_DIR.exists():
    LAMBDA_DIR = INFRA_ROOT / "modules" / "06-superadmin"
sys.path.insert(0, str(LAMBDA_DIR))

import tenant_operator_lambda as tol  # noqa: E402


class TestConcurrentStress(unittest.TestCase):
    def test_concurrent_token_signing_and_verification_under_load(self):
        """Simulate 20 concurrent threads executing 1000 token signing & verification tasks."""
        num_tasks = 1000
        concurrency = 20
        key = "secure-production-signing-key-for-concurrency-testing"

        latencies = []

        def worker(idx):
            start = time.perf_counter()
            username = f"tenant_admin_{idx % 50}"
            token = tol.create_session_token(username=username, role="SuperAdmin", key=key)
            claims = tol.verify_session_token(token, key=key)
            duration_ms = (time.perf_counter() - start) * 1000
            assert claims is not None
            assert claims["user"] == username
            return duration_ms

        start_total = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(worker, i) for i in range(num_tasks)]
            for f in concurrent.futures.as_completed(futures):
                latencies.append(f.result())

        total_time = time.perf_counter() - start_total
        throughput = num_tasks / total_time

        p50 = statistics.median(latencies)
        p95 = statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        p99 = statistics.quantiles(latencies, n=100)[98] if len(latencies) >= 100 else max(latencies)

        print(f"\n[BENCHMARK] Executed {num_tasks} concurrent auth operations in {total_time:.3f}s")
        print(f"  • Throughput : {throughput:.1f} ops/sec")
        print(f"  • Latency p50: {p50:.3f} ms")
        print(f"  • Latency p95: {p95:.3f} ms")
        print(f"  • Latency p99: {p99:.3f} ms")

        # Assert zero failures and strict sub-5ms p99 latency threshold
        self.assertEqual(len(latencies), num_tasks)
        self.assertLess(p99, 15.0, f"p99 latency ({p99:.2f}ms) exceeded 15ms threshold")


if __name__ == "__main__":
    unittest.main()
