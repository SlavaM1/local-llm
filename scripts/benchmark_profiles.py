#!/usr/bin/env python3
"""Run local Baseline/Optimized comparisons and save real Ollama metrics."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROMPTS = [
    "Объясни разницу между Docker image и container. Ответь максимум 5 пунктами.",
    (
        "Напиши на Java 21 метод, который принимает List<Integer>, удаляет дубликаты, "
        "сортирует по убыванию и возвращает первые 5 элементов. Используй Stream API."
    ),
    (
        "Spring Boot сервис получает HTTP 504 при обращении к downstream. connect timeout "
        "200 ms, socket timeout 1000 ms, overall timeout 1200 ms. Объясни, чем отличаются "
        "эти timeout и где искать проблему."
    ),
    "Сравни REST и Kafka для взаимодействия двух backend-сервисов. Дай критерии выбора, плюсы и минусы.",
    "Ответь строго тремя пунктами: зачем в RAG нужен reranker?",
]


def api_request(base_url: str, method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=270) as response:
            return json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}: {exc.reason}") from exc


def command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return result.stdout.strip() or None
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def resource_snapshot() -> dict[str, Any]:
    gpu = command_output(
        [
            "nvidia-smi",
            "--query-gpu=memory.used,memory.total,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    )
    container_id = command_output(["docker", "compose", "ps", "-q", "ollama"])
    container = None
    if container_id:
        raw = command_output(
            [
                "docker",
                "stats",
                "--no-stream",
                "--format",
                "{{json .}}",
                container_id,
            ]
        )
        if raw:
            try:
                container = json.loads(raw)
            except json.JSONDecodeError:
                container = {"raw": raw}
    snapshot: dict[str, Any] = {"captured_at": datetime.now(timezone.utc).isoformat()}
    if gpu:
        values = [part.strip() for part in gpu.splitlines()[0].split(",")]
        if len(values) == 3:
            snapshot["gpu"] = {
                "vram_used_mib": int(values[0]),
                "vram_total_mib": int(values[1]),
                "utilization_percent": int(values[2]),
            }
    if container:
        snapshot["ollama_container"] = {
            "cpu_percent": container.get("CPUPerc"),
            "memory_usage": container.get("MemUsage"),
            "memory_percent": container.get("MemPerc"),
        }
    return snapshot


def unload_models() -> bool:
    """Ask local Ollama to unload both aliases so the first run is genuinely cold."""
    results = [
        command_output(["docker", "exec", "ollama", "ollama", "stop", model])
        for model in ("qwen3:8b", "qwen3-dev:8b")
    ]
    # `ollama stop` is silent on success; verify that no model remains loaded.
    loaded = command_output(["docker", "exec", "ollama", "ollama", "ps"])
    return results == [None, None] and bool(loaded) and len(loaded.splitlines()) == 1


def compare_once(base_url: str, prompt: str, phase: str, run: int) -> list[dict[str, Any]]:
    chat = api_request(base_url, "POST", "/api/chats", {})
    before = resource_snapshot()
    exchange = api_request(
        base_url,
        "POST",
        f"/api/chats/{chat['id']}/compare",
        {"content": prompt},
    )
    after = resource_snapshot()
    records = []
    for key in ("baseline_message", "optimized_message"):
        message = exchange[key]
        metric = message.get("metrics") or {}
        record = {
            "phase": phase,
            "run": run,
            "prompt": prompt,
            "profile": metric.get("profile"),
            "answer": message["content"],
            "success": metric.get("success"),
            "latency_ms": metric.get("total_latency_ms"),
            "input_tokens": metric.get("input_tokens"),
            "output_tokens": metric.get("output_tokens"),
            "total_tokens": metric.get("total_tokens"),
            "generation_tokens_per_second": metric.get("generation_tokens_per_second"),
            "prompt_tokens_per_second": metric.get("prompt_tokens_per_second"),
            "ollama_total_duration_ms": metric.get("ollama_total_duration_ms"),
            "load_duration_ms": metric.get("load_duration_ms"),
            "context_window": metric.get("context_window"),
            "temperature": metric.get("temperature"),
            "max_tokens": metric.get("max_tokens"),
            "thinking": metric.get("thinking"),
            "resources_before": before,
            "resources_after": after,
        }
        records.append(record)
        print(f"\n[{phase} run {run}] {record['profile']}\n{'-' * 72}")
        print(record["answer"])
        print(
            "\nMetrics: latency={latency_ms:.1f} ms, tokens={input_tokens}->{output_tokens}, "
            "generation={generation_tokens_per_second:.1f} tok/s, load={load_duration_ms:.1f} ms".format(
                **{name: (value if value is not None else float("nan")) for name, value in record.items()}
            )
        )
    return records


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = []
    keys = sorted({(row["phase"], row["profile"]) for row in records})
    for phase, profile in keys:
        rows = [row for row in records if row["phase"] == phase and row["profile"] == profile]
        latencies = [row["latency_ms"] for row in rows if row["latency_ms"] is not None]
        speeds = [
            row["generation_tokens_per_second"]
            for row in rows
            if row["generation_tokens_per_second"] is not None
        ]
        summaries.append(
            {
                "phase": phase,
                "profile": profile,
                "runs": len(rows),
                "success_rate": sum(row["success"] is True for row in rows) / len(rows),
                "avg_latency_ms": statistics.fmean(latencies) if latencies else None,
                "min_latency_ms": min(latencies) if latencies else None,
                "max_latency_ms": max(latencies) if latencies else None,
                "avg_generation_tokens_per_second": statistics.fmean(speeds) if speeds else None,
            }
        )
    return summaries


def print_results_table(records: list[dict[str, Any]]) -> None:
    columns = (
        ("Phase", "phase", 7),
        ("Profile", "profile", 9),
        ("Latency", "latency_ms", 9),
        ("In", "input_tokens", 5),
        ("Out", "output_tokens", 5),
        ("Total", "total_tokens", 6),
        ("Gen/s", "generation_tokens_per_second", 7),
        ("Prompt/s", "prompt_tokens_per_second", 9),
        ("Ollama", "ollama_total_duration_ms", 9),
        ("Load", "load_duration_ms", 8),
        ("Ctx", "context_window", 5),
        ("Temp", "temperature", 5),
        ("Max", "max_tokens", 5),
        ("OK", "success", 3),
    )

    def display(value: Any) -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "yes" if value else "no"
        if isinstance(value, float):
            return f"{value:.1f}"
        return str(value)

    print("\nResults")
    print(" ".join(title.ljust(width) for title, _, width in columns))
    print(" ".join("-" * width for _, _, width in columns))
    for row in records:
        print(
            " ".join(
                display(row.get(key))[:width].ljust(width)
                for _, key, width in columns
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--prompt", action="append", help="Custom prompt; repeat for several prompts")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--warmup", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", default="benchmark_results.json")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be at least 1")

    prompts = args.prompt or PROMPTS
    records: list[dict[str, Any]] = []
    try:
        if args.warmup:
            is_cold = unload_models()
            phase = "cold" if is_cold else "initial"
            print(f"Running and recording the {phase}/warm-up comparison...")
            records.extend(compare_once(args.base_url, prompts[0], phase, 0))
        for prompt_index, prompt in enumerate(prompts, start=1):
            print(f"\n{'=' * 72}\nPrompt {prompt_index}: {prompt}")
            for run in range(1, args.runs + 1):
                phase = "warm" if args.warmup or run > 1 else "cold"
                records.extend(compare_once(args.base_url, prompt, phase, run))
    except RuntimeError as exc:
        print(f"Benchmark failed: {exc}", file=sys.stderr)
        return 1

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "summaries": summarize(records),
        "results": records,
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print_results_table(records)
    print("\nSummary")
    for row in report["summaries"]:
        print(
            f"{row['phase']:>4} {row['profile']:<9} runs={row['runs']} "
            f"success={row['success_rate']:.0%} avg={row['avg_latency_ms']:.1f} ms "
            f"min={row['min_latency_ms']:.1f} max={row['max_latency_ms']:.1f} "
            f"gen={row['avg_generation_tokens_per_second']:.1f} tok/s"
        )
    print(f"\nMachine-readable report: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
