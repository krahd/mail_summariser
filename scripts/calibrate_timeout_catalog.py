"""Calibration tool to measure model latencies and generate timing hints.

This script measures round-trip times for `/api/generate` calls against a
local Ollama server and emits a simple JSON report with average latency and
latency-per-1k-tokens figures for each measured model.

Usage examples:
  python scripts/calibrate_timeout_catalog.py --models llama-2-13b,vicuna-13b

The output is written to stdout by default or to `--out` when provided.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List
from urllib.request import Request, urlopen

from modelito import tokenizer
from modelito import ollama_service


def _measure_single_prompt(endpoint: str, model: str, prompt_text: str, max_tokens: int, timeout: int):
    req = Request(
        endpoint,
        data=json.dumps({"model": model, "prompt": prompt_text,
                        "max_tokens": max_tokens}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    with urlopen(req, timeout=timeout) as resp:
        resp.read()
    end = time.monotonic()
    latency = end - start
    input_tokens = tokenizer.count_tokens(prompt_text)
    return latency, input_tokens


def _measure_prompt_runs(endpoint: str, model: str, prompt_text: str, iterations: int, max_tokens: int, timeout: int):
    samples: List[Dict[str, Any]] = []
    errors: List[str] = []
    for _ in range(iterations):
        try:
            latency, input_tokens = _measure_single_prompt(
                endpoint, model, prompt_text, max_tokens, timeout)
        except Exception as exc:
            errors.append(str(exc))
            continue
        samples.append({"prompt_len": len(prompt_text),
                       "input_tokens": input_tokens, "latency": latency})
    return samples, errors


def measure_model(url: str, port: int, model: str, prompts: List[str], iterations: int, max_tokens: int, timeout: int) -> Dict[str, Any]:
    samples: List[Dict[str, Any]] = []
    errors: List[str] = []

    for prompt in prompts:
        endpoint = ollama_service.endpoint_url(url, port, "/api/generate")
        s, e = _measure_prompt_runs(endpoint, model, prompt, iterations, max_tokens, timeout)
        samples.extend(s)
        errors.extend(e)

    results: Dict[str, Any] = {
        "model": model,
        "samples": samples,
        "runs": len(samples),
        "avg_latency_seconds": (sum(s["latency"] for s in samples) / len(samples)) if samples else 0.0,
        "avg_seconds_per_1000_input_tokens": (
            (sum(s["latency"] for s in samples) / sum(s["input_tokens"] for s in samples)) * 1000
        ) if any(s["input_tokens"] for s in samples) else ((sum(s["latency"] for s in samples) / len(samples)) if samples else 0.0),
    }
    if errors:
        results["errors"] = errors
    return results


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Calibrate timeout catalog using Ollama generate latencies")
    parser.add_argument("--url", default="http://localhost")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--models", default="llama-2-13b",
                        help="Comma-separated model names to test")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    # simple default prompts; replace {text} with short text for measurement
    default_prompts = [
        "Summarize the following text in one sentence: The quick brown fox jumps over the lazy dog.",
        "Write a short (2-line) summary for: Machine learning models can be fine-tuned for specific tasks.",
        "Extract action items: Please prepare the report and send to the team by Friday."
    ]

    if not ollama_service.server_is_up(args.url, args.port):
        print(f"Ollama server not available at {args.url}:{args.port}. Aborting.")
        return 2

    report: Dict[str, Any] = {"calibrated_at": time.strftime(
        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "models": []}
    for model in models:
        print(f"Measuring model {model}...")
        res = measure_model(args.url, args.port, model, default_prompts,
                            args.iterations, args.max_tokens, args.timeout)
        report["models"].append(res)

    out_text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out_text)
        print(f"Wrote calibration report to {args.out}")
    else:
        print(out_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
