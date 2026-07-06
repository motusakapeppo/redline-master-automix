"""latency_test.py — Measures round-trip latency from simulated DSP trigger
to evaluate_js call through the async queue system in api.py.

Simulates the full path: DSP event → _emit() → queue → worker → evaluate_js.
Target: under 30ms average (60fps = 16.7ms frame budget)."""

import queue
import threading
import time
import statistics


# Simulated JS eval target (replaces pywebview's evaluate_js)
_JS_CALLS: list[float] = []
_JS_LOCK = threading.Lock()


def _fake_evaluate_js(js: str) -> None:
    """Stand-in for window.evaluate_js — records the timestamp."""
    with _JS_LOCK:
        _JS_CALLS.append(time.perf_counter())


# Replica of the Api._start_js_worker logic (same throttle, same drain)
_JS_THROTTLE_S = 1.0 / 60.0


def _worker(js_queue: queue.Queue, stop_event: threading.Event) -> None:
    last_js_time = 0.0
    while not stop_event.is_set():
        try:
            js = js_queue.get(timeout=0.1)
        except queue.Empty:
            continue
        if js is None:
            break
        # Drain stale entries
        while not js_queue.empty():
            try:
                next_js = js_queue.get_nowait()
                if next_js is None:
                    return
                js = next_js
            except queue.Empty:
                break
        # 60fps throttle
        now = time.perf_counter()
        if now - last_js_time < _JS_THROTTLE_S:
            continue
        last_js_time = now
        _fake_evaluate_js(js)


def run_latency_test(n_iterations: int = 100) -> dict:
    js_queue: queue.Queue[str | None] = queue.Queue()
    stop_event = threading.Event()
    worker = threading.Thread(target=_worker, args=(js_queue, stop_event), daemon=True)
    worker.start()

    latencies: list[float] = []

    for i in range(n_iterations):
        # Simulate DSP trigger
        trigger_time = time.perf_counter()

        # Push a JS eval (simulates _emit or _narrate)
        js_queue.put(f"onStep({i!r})")

        # Give the worker a chance to process
        time.sleep(0.002)  # 2ms

        # Check if the call was processed
        with _JS_LOCK:
            if _JS_CALLS:
                call_time = _JS_CALLS.pop(0)
                latency = (call_time - trigger_time) * 1000  # ms
                latencies.append(latency)

    # Stop the worker
    stop_event.set()
    worker.join(timeout=1.0)

    if not latencies:
        return {"error": "No JS calls were processed", "count": 0}

    latencies.sort()
    p95_idx = int(len(latencies) * 0.95)
    return {
        "count": len(latencies),
        "min_ms": round(min(latencies), 3),
        "max_ms": round(max(latencies), 3),
        "avg_ms": round(statistics.mean(latencies), 3),
        "median_ms": round(statistics.median(latencies), 3),
        "p95_ms": round(latencies[p95_idx], 3),
        "target_ms": 30.0,
        "target_met": statistics.mean(latencies) < 30.0,
    }


def main():
    print("=" * 60)
    print("  Neural Monitor - Latency Test")
    print("  Measures DSP trigger -> UI bridge round-trip time")
    print("=" * 60)

    # Warmup
    print("\nWarming up (10 iterations)...")
    run_latency_test(10)

    # Actual test
    print("Running 100 iterations...")
    result = run_latency_test(100)

    print(f"\n  Iterations : {result['count']}")
    print(f"  Min latency: {result['min_ms']:.3f} ms")
    print(f"  Max latency: {result['max_ms']:.3f} ms")
    print(f"  Avg latency: {result['avg_ms']:.3f} ms")
    print(f"  Median     : {result['median_ms']:.3f} ms")
    print(f"  P95        : {result['p95_ms']:.3f} ms")
    print(f"  Target     : < {result['target_ms']} ms")
    print(f"  Result     : {'PASS' if result['target_met'] else 'FAIL'} (avg {result['avg_ms']:.1f}ms {'<' if result['target_met'] else '>'} {result['target_ms']}ms)")
    print("=" * 60)

    return 0 if result['target_met'] else 1


if __name__ == "__main__":
    exit(main())
