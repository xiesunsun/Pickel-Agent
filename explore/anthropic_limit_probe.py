from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass
from typing import Any, Awaitable, TypeVar

from anthropic import (
    APIStatusError,
    APITimeoutError,
    AsyncAnthropic,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    UnprocessableEntityError,
)

_FILLER_LINE = (
    "filler-{index:06d}: alpha beta gamma delta epsilon zeta eta theta iota "
    "kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega"
)
_T = TypeVar("_T")


@dataclass
class ProbeConfig:
    model: str
    api_base: str
    api_key: str | None
    timeout_seconds: float
    max_retries: int
    thinking: str | None
    temperature: float | None = None


@dataclass
class ProbeError:
    kind: str
    message: str


@dataclass
class ContextAttempt:
    filler_units: int
    input_tokens: int | None
    success: bool
    latency_seconds: float
    stop_reason: str | None = None
    error: ProbeError | None = None


@dataclass
class OutputAttempt:
    requested_max_tokens: int
    input_tokens: int | None
    success: bool
    latency_seconds: float
    stop_reason: str | None = None
    output_tokens: int | None = None
    visible_chars: int = 0
    visible_lines: int = 0
    error: ProbeError | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe native Anthropic API context and output limits."
    )
    parser.add_argument(
        "--model",
        default="claude-jupiter-v1-p",
        help="Model name or alias sent directly to the Anthropic API",
    )
    parser.add_argument(
        "--api-base",
        default="https://api.anthropic.com",
        help="Anthropic API base URL",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Per-request timeout in seconds",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="SDK retry count",
    )
    parser.add_argument(
        "--thinking",
        default="xhigh",
        help="Anthropic thinking effort; use 'off' to disable",
    )
    parser.add_argument(
        "--probe",
        choices=("context", "output", "both"),
        default="both",
        help="Which probe(s) to run",
    )
    parser.add_argument(
        "--context-max-units",
        type=int,
        default=65536,
        help="Upper bound for context filler units during binary search",
    )
    parser.add_argument(
        "--context-start-units",
        type=int,
        default=256,
        help="Initial filler_units for context probing; useful when resuming from a known lower bound",
    )
    parser.add_argument(
        "--context-probe-max-tokens",
        type=int,
        default=64,
        help="max_tokens used for context-window validation requests",
    )
    parser.add_argument(
        "--output-start",
        type=int,
        default=4096,
        help="Initial requested max_tokens for output probing",
    )
    parser.add_argument(
        "--output-max",
        type=int,
        default=131072,
        help="Largest requested max_tokens to try for output probing",
    )
    parser.add_argument(
        "--output-prompt-style",
        choices=("capacity", "legacy"),
        default="capacity",
        help="Prompt shape used for output probing",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=5.0,
        help="How often to print 'still waiting' progress messages",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=2.0,
        help="Sleep between large probe attempts to reduce burst pressure",
    )
    parser.add_argument(
        "--preflight-count-tokens",
        action="store_true",
        help="Call count_tokens before each attempt; slower but useful for diagnostics",
    )
    return parser.parse_args()


def build_probe_config(args: argparse.Namespace) -> ProbeConfig:
    thinking = None if args.thinking.lower() in {"off", "none", "false", "disable"} else args.thinking
    return ProbeConfig(
        model=args.model,
        api_base=args.api_base,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
        timeout_seconds=args.timeout,
        max_retries=args.max_retries,
        thinking=thinking,
    )


def build_client(config: ProbeConfig) -> AsyncAnthropic:
    kwargs: dict[str, Any] = {
        "base_url": config.api_base,
        "timeout": config.timeout_seconds,
        "max_retries": config.max_retries,
    }
    if config.api_key is not None:
        kwargs["api_key"] = config.api_key
    return AsyncAnthropic(**kwargs)


def build_common_request_params(config: ProbeConfig, prompt: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": config.model,
        "messages": [{"role": "user", "content": prompt}],
    }
    thinking, output_config = build_thinking_config(config)
    if thinking is not None:
        params["thinking"] = thinking
    if output_config is not None:
        params["output_config"] = output_config
    if config.temperature is not None:
        params["temperature"] = config.temperature
    return params


def build_thinking_config(
    config: ProbeConfig,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    effort = config.thinking
    if not isinstance(effort, str):
        return None, None
    return (
        {"type": "adaptive", "display": "summarized"},
        {"effort": effort},
    )


def build_context_prompt(filler_units: int) -> str:
    lines = [
        "Context window probe.",
        "Read the payload below and reply with exactly ACK.",
        "",
    ]
    lines.extend(_FILLER_LINE.format(index=index) for index in range(filler_units))
    return "\n".join(lines)


def build_output_prompt(style: str) -> str:
    if style == "legacy":
        return "\n".join(
            [
                "Output token ceiling probe.",
                "Produce a numbered plain-text list and do not stop voluntarily.",
                "Each line must use this template with the next number:",
                "[n] alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega",
                "Continue until the API stops you.",
                "Do not add an introduction, summary, or explanation.",
                "Start immediately at line 1.",
            ]
        )

    return "\n".join(
        [
            "This is an output-capacity stress test.",
            "Produce a continuous plain-text stream of fixed-format records.",
            "The stream has no final record and no semantic conclusion.",
            "Output exactly one record per line using this format:",
            "R000001|ALPHA|BETA|GAMMA|DELTA|EPSILON|ZETA|ETA|THETA|IOTA|KAPPA|LAMBDA|MU|NU|XI|OMICRON|PI|RHO|SIGMA|TAU|UPSILON|PHI|CHI|PSI|OMEGA",
            "Rules:",
            "1. Increment the six-digit record number by one on each new line.",
            "2. Keep every field after the record number exactly unchanged.",
            "3. Do not add headings, explanations, summaries, conclusions, blank lines, or markdown.",
            "4. Do not stop because the task seems complete. The stream is intentionally endless.",
            "5. If you would normally conclude, instead emit the next record.",
            "6. Start immediately with record R000001.",
        ]
    )


def log(message: str) -> None:
    print(message, flush=True)


async def with_heartbeat(
    awaitable: Awaitable[_T],
    *,
    label: str,
    heartbeat_seconds: float,
) -> _T:
    task = asyncio.create_task(awaitable)
    started = time.perf_counter()
    while True:
        done, _ = await asyncio.wait({task}, timeout=heartbeat_seconds)
        if task in done:
            return await task
        elapsed = time.perf_counter() - started
        log(f"{label} still waiting... elapsed={elapsed:.1f}s")


async def count_input_tokens(
    *,
    client: AsyncAnthropic,
    config: ProbeConfig,
    prompt: str,
    heartbeat_seconds: float,
    label: str,
) -> int | None:
    params = build_common_request_params(config, prompt)
    log(f"{label} count_tokens start")
    response = await with_heartbeat(
        client.messages.count_tokens(**params),
        label=f"{label} count_tokens",
        heartbeat_seconds=heartbeat_seconds,
    )
    input_tokens = getattr(response, "input_tokens", None)
    parsed = int(input_tokens) if input_tokens is not None else None
    log(f"{label} count_tokens done input_tokens={parsed}")
    return parsed


def extract_input_tokens_from_usage(message: Any) -> int | None:
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    return int(input_tokens) if input_tokens is not None else None


def classify_error(exc: Exception) -> ProbeError:
    if isinstance(exc, AuthenticationError):
        return ProbeError("auth", str(exc))
    if isinstance(exc, APITimeoutError):
        return ProbeError("timeout", str(exc))
    if isinstance(exc, RateLimitError):
        return ProbeError("rate_limit", str(exc))
    if isinstance(exc, BadRequestError):
        return ProbeError("bad_request", render_api_error(exc))
    if isinstance(exc, UnprocessableEntityError):
        return ProbeError("unprocessable_entity", render_api_error(exc))
    if isinstance(exc, APIStatusError):
        return ProbeError(f"http_{exc.status_code}", render_api_error(exc))
    return ProbeError(type(exc).__name__, str(exc))


def render_api_error(exc: APIStatusError) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
    return str(exc)


def is_validation_limit_error(error: ProbeError) -> bool:
    if error.kind not in {"bad_request", "unprocessable_entity"}:
        return False
    lowered = error.message.lower()
    markers = ("max_tokens", "context window", "prompt is too long", "too many tokens")
    return any(marker in lowered for marker in markers)


def is_infrastructure_error(error: ProbeError) -> bool:
    if error.kind in {"timeout", "rate_limit", "http_529", "http_500", "http_502", "http_503", "http_504"}:
        return True
    lowered = error.message.lower()
    markers = ("overloaded", "rate limit", "timeout", "connection")
    return any(marker in lowered for marker in markers)


async def run_context_attempt(
    *,
    client: AsyncAnthropic,
    config: ProbeConfig,
    filler_units: int,
    probe_max_tokens: int,
    heartbeat_seconds: float,
    preflight_count_tokens: bool,
) -> ContextAttempt:
    label = f"[context units={filler_units}]"
    prompt = build_context_prompt(filler_units)
    input_tokens = None
    if preflight_count_tokens:
        input_tokens = await count_input_tokens(
            client=client,
            config=config,
            prompt=prompt,
            heartbeat_seconds=heartbeat_seconds,
            label=label,
        )
    params = build_common_request_params(config, prompt)
    params["max_tokens"] = probe_max_tokens

    started = time.perf_counter()
    log(f"{label} stream start max_tokens={probe_max_tokens}")
    try:
        async with client.messages.stream(**params) as stream:
            response = await with_heartbeat(
                stream.get_final_message(),
                label=f"{label} stream",
                heartbeat_seconds=heartbeat_seconds,
            )
    except Exception as exc:
        error = classify_error(exc)
        latency = time.perf_counter() - started
        log(f"{label} stream failed after {latency:.2f}s error={error.kind}: {error.message}")
        return ContextAttempt(
            filler_units=filler_units,
            input_tokens=input_tokens,
            success=False,
            latency_seconds=latency,
            error=error,
        )

    latency = time.perf_counter() - started
    stop_reason = getattr(response, "stop_reason", None)
    input_tokens = input_tokens if input_tokens is not None else extract_input_tokens_from_usage(response)
    log(f"{label} stream success after {latency:.2f}s stop_reason={stop_reason}")
    return ContextAttempt(
        filler_units=filler_units,
        input_tokens=input_tokens,
        success=True,
        latency_seconds=latency,
        stop_reason=stop_reason,
    )


async def probe_context_limit(
    *,
    client: AsyncAnthropic,
    config: ProbeConfig,
    start_units: int,
    max_units: int,
    probe_max_tokens: int,
    heartbeat_seconds: float,
    pause_seconds: float,
    preflight_count_tokens: bool,
) -> list[ContextAttempt]:
    attempts: list[ContextAttempt] = []
    low = 0
    high = max(1, start_units)
    while high <= max_units:
        attempt = await run_context_attempt(
            client=client,
            config=config,
            filler_units=high,
            probe_max_tokens=probe_max_tokens,
            heartbeat_seconds=heartbeat_seconds,
            preflight_count_tokens=preflight_count_tokens,
        )
        attempts.append(attempt)
        if attempt.error is not None and is_infrastructure_error(attempt.error):
            log(
                "[context] stopping probe due to infrastructure error: "
                f"{attempt.error.kind}: {attempt.error.message}"
            )
            break
        if attempt.success:
            low = high
            high *= 2
            if high <= max_units and pause_seconds > 0:
                log(f"[context] pausing {pause_seconds:.1f}s before next attempt")
                await asyncio.sleep(pause_seconds)
            continue
        if attempt.error is not None and is_validation_limit_error(attempt.error):
            break
        log(
            "[context] stopping probe due to non-validation failure: "
            f"{attempt.error.kind if attempt.error is not None else 'unknown'}: "
            f"{attempt.error.message if attempt.error is not None else 'unknown'}"
        )
        break

    if not attempts:
        return attempts

    last = attempts[-1]
    if last.success:
        return attempts

    if last.error is None or not is_validation_limit_error(last.error):
        return attempts

    left = (low + 1) if low > 0 else max(1, high // 2)
    right = min(high - 1, max_units)
    while left <= right:
        middle = (left + right) // 2
        attempt = await run_context_attempt(
            client=client,
            config=config,
            filler_units=middle,
            probe_max_tokens=probe_max_tokens,
            heartbeat_seconds=heartbeat_seconds,
            preflight_count_tokens=preflight_count_tokens,
        )
        attempts.append(attempt)
        if attempt.error is not None and is_infrastructure_error(attempt.error):
            log(
                "[context] stopping binary search due to infrastructure error: "
                f"{attempt.error.kind}: {attempt.error.message}"
            )
            break
        if attempt.success:
            low = middle
            left = middle + 1
            if left <= right and pause_seconds > 0:
                log(f"[context] pausing {pause_seconds:.1f}s before next attempt")
                await asyncio.sleep(pause_seconds)
            continue
        if attempt.error is None:
            log("[context] stopping binary search due to unknown failure without error details")
            break
        if not is_validation_limit_error(attempt.error):
            log(
                "[context] stopping binary search due to non-validation failure: "
                f"{attempt.error.kind}: {attempt.error.message}"
            )
            break
        right = middle - 1
    return attempts


def extract_text_from_message(message: Any) -> str:
    chunks: list[str] = []
    for block in getattr(message, "content", []):
        block_type = getattr(block, "type", None)
        if block_type != "text":
            continue
        text = getattr(block, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks)


async def run_output_attempt(
    *,
    client: AsyncAnthropic,
    config: ProbeConfig,
    requested_max_tokens: int,
    heartbeat_seconds: float,
    preflight_count_tokens: bool,
    output_prompt_style: str,
) -> OutputAttempt:
    label = f"[output max_tokens={requested_max_tokens}]"
    prompt = build_output_prompt(output_prompt_style)
    input_tokens = None
    if preflight_count_tokens:
        input_tokens = await count_input_tokens(
            client=client,
            config=config,
            prompt=prompt,
            heartbeat_seconds=heartbeat_seconds,
            label=label,
        )
    params = build_common_request_params(config, prompt)
    params["max_tokens"] = requested_max_tokens

    started = time.perf_counter()
    log(f"{label} stream start")
    try:
        async with client.messages.stream(**params) as stream:
            message = await with_heartbeat(
                stream.get_final_message(),
                label=f"{label} stream",
                heartbeat_seconds=heartbeat_seconds,
            )
    except Exception as exc:
        error = classify_error(exc)
        latency = time.perf_counter() - started
        log(f"{label} stream failed after {latency:.2f}s error={error.kind}: {error.message}")
        return OutputAttempt(
            requested_max_tokens=requested_max_tokens,
            input_tokens=input_tokens,
            success=False,
            latency_seconds=latency,
            error=error,
        )

    latency = time.perf_counter() - started
    usage = getattr(message, "usage", None)
    output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
    text = extract_text_from_message(message)
    stop_reason = getattr(message, "stop_reason", None)
    input_tokens = input_tokens if input_tokens is not None else extract_input_tokens_from_usage(message)
    log(
        f"{label} stream success after {latency:.2f}s"
        f" stop_reason={stop_reason} output_tokens={output_tokens}"
    )
    return OutputAttempt(
        requested_max_tokens=requested_max_tokens,
        input_tokens=input_tokens,
        success=True,
        latency_seconds=latency,
        stop_reason=stop_reason,
        output_tokens=int(output_tokens) if output_tokens is not None else None,
        visible_chars=len(text),
        visible_lines=text.count("\n") + (1 if text else 0),
    )


async def probe_output_limit(
    *,
    client: AsyncAnthropic,
    config: ProbeConfig,
    output_start: int,
    output_max: int,
    heartbeat_seconds: float,
    pause_seconds: float,
    preflight_count_tokens: bool,
    output_prompt_style: str,
) -> list[OutputAttempt]:
    attempts: list[OutputAttempt] = []
    requested = output_start
    last_success: int | None = None
    first_failure: int | None = None

    while requested <= output_max:
        attempt = await run_output_attempt(
            client=client,
            config=config,
            requested_max_tokens=requested,
            heartbeat_seconds=heartbeat_seconds,
            preflight_count_tokens=preflight_count_tokens,
            output_prompt_style=output_prompt_style,
        )
        attempts.append(attempt)
        if attempt.error is not None and is_infrastructure_error(attempt.error):
            log(
                "[output] stopping probe due to infrastructure error: "
                f"{attempt.error.kind}: {attempt.error.message}"
            )
            break
        if attempt.success:
            last_success = requested
            requested *= 2
            if requested <= output_max and pause_seconds > 0:
                log(f"[output] pausing {pause_seconds:.1f}s before next attempt")
                await asyncio.sleep(pause_seconds)
            continue
        first_failure = requested
        break

    if last_success is None or first_failure is None:
        return attempts

    if attempts[-1].error is None or not is_validation_limit_error(attempts[-1].error):
        return attempts

    left = last_success + 1
    right = first_failure - 1
    while left <= right:
        middle = (left + right) // 2
        attempt = await run_output_attempt(
            client=client,
            config=config,
            requested_max_tokens=middle,
            heartbeat_seconds=heartbeat_seconds,
            preflight_count_tokens=preflight_count_tokens,
            output_prompt_style=output_prompt_style,
        )
        attempts.append(attempt)
        if attempt.error is not None and is_infrastructure_error(attempt.error):
            log(
                "[output] stopping binary search due to infrastructure error: "
                f"{attempt.error.kind}: {attempt.error.message}"
            )
            break
        if attempt.success:
            last_success = middle
            left = middle + 1
            if left <= right and pause_seconds > 0:
                log(f"[output] pausing {pause_seconds:.1f}s before next attempt")
                await asyncio.sleep(pause_seconds)
            continue
        if attempt.error is not None and is_validation_limit_error(attempt.error):
            right = middle - 1
            continue
        break
    return attempts


def print_model_header(
    config: ProbeConfig,
    *,
    preflight_count_tokens: bool,
    output_prompt_style: str,
) -> None:
    log("Model probe configuration")
    log(f"  model: {config.model}")
    log(f"  api_base: {config.api_base}")
    log(f"  timeout_seconds: {config.timeout_seconds}")
    log(f"  max_retries: {config.max_retries}")
    log(f"  thinking: {config.thinking or 'off'}")
    log(f"  api_key: {'set' if config.api_key else 'missing'}")
    log(f"  output_prompt_style: {output_prompt_style}")
    log(
        "  token_count_mode: preflight"
        if preflight_count_tokens
        else "  token_count_mode: response_usage"
    )
    log("")


def print_context_summary(
    attempts: list[ContextAttempt],
    *,
    probe_max_tokens: int,
    max_units: int,
) -> None:
    log("Context probe")
    if not attempts:
        log("  No attempts were run.")
        log("")
        return

    headers = ("units", "input_tokens", "ok", "stop", "latency_s", "error")
    rows = [
        (
            str(item.filler_units),
            str(item.input_tokens) if item.input_tokens is not None else "-",
            "yes" if item.success else "no",
            item.stop_reason or "-",
            f"{item.latency_seconds:.2f}",
            item.error.message if item.error is not None else "-",
        )
        for item in attempts
    ]
    log(render_table(headers, rows))

    successes = [item for item in attempts if item.success]
    failures = [item for item in attempts if not item.success]
    validation_failures = [
        item
        for item in failures
        if item.error is not None and is_validation_limit_error(item.error)
    ]
    infrastructure_failures = [
        item
        for item in failures
        if item.error is not None and is_infrastructure_error(item.error)
    ]
    if successes:
        best = max(
            successes,
            key=lambda item: (-1 if item.input_tokens is None else item.input_tokens),
        )
        log(
            "  Stable lower bound:"
            f" input_tokens={best.input_tokens},"
            f" requested_max_tokens={probe_max_tokens},"
            f" inferred_combined_floor={((best.input_tokens or 0) + probe_max_tokens)}"
        )
    if validation_failures:
        first_validation = min(validation_failures, key=lambda item: item.filler_units)
        log(
            "  First validation boundary:"
            f" units={first_validation.filler_units},"
            f" input_tokens={first_validation.input_tokens},"
            f" error={first_validation.error.message if first_validation.error is not None else 'unknown'}"
        )
    elif infrastructure_failures:
        first_infra = infrastructure_failures[0]
        log(
            "  First infrastructure failure:"
            f" units={first_infra.filler_units},"
            f" input_tokens={first_infra.input_tokens},"
            f" error={first_infra.error.message if first_infra.error is not None else 'unknown'}"
        )
        log(
            "  Hard boundary not reached."
            " Treat the result as inconclusive above the stable lower bound."
        )
    elif failures:
        first_other = failures[0]
        error_text = first_other.error.message if first_other.error is not None else "unknown"
        log(
            "  First non-validation failure:"
            f" units={first_other.filler_units},"
            f" input_tokens={first_other.input_tokens},"
            f" error={error_text}"
        )
        if first_other.error is not None and is_infrastructure_error(first_other.error):
            log(
                "  This failure looks like infrastructure pressure, not a hard model ceiling."
                " Treat the current result as inconclusive above the last successful point."
            )
        else:
            log(
                "  Hard boundary not reached."
                " Treat the result as inconclusive above the stable lower bound."
            )
    else:
        log("  Hard boundary not reached within the tested range.")
    if attempts[-1].success and attempts[-1].filler_units >= max_units:
        log(
            "  Search hit --context-max-units before it found a failure."
            " Raise that cap if you want a tighter ceiling."
        )
    log("")


def print_output_summary(
    attempts: list[OutputAttempt],
    *,
    output_max: int,
) -> None:
    log("Output probe")
    if not attempts:
        log("  No attempts were run.")
        log("")
        return

    headers = (
        "requested",
        "input_tokens",
        "ok",
        "stop",
        "output_tokens",
        "visible_lines",
        "latency_s",
        "error",
    )
    rows = [
        (
            str(item.requested_max_tokens),
            str(item.input_tokens) if item.input_tokens is not None else "-",
            "yes" if item.success else "no",
            item.stop_reason or "-",
            str(item.output_tokens) if item.output_tokens is not None else "-",
            str(item.visible_lines),
            f"{item.latency_seconds:.2f}",
            item.error.message if item.error is not None else "-",
        )
        for item in attempts
    ]
    log(render_table(headers, rows))

    successes = [item for item in attempts if item.success]
    failures = [item for item in attempts if not item.success]
    capped = [item for item in successes if item.stop_reason == "max_tokens"]
    if capped:
        best = max(capped, key=lambda item: item.requested_max_tokens)
        log(
            "  Largest successful request that actually hit max_tokens:"
            f" requested={best.requested_max_tokens},"
            f" output_tokens={best.output_tokens},"
            f" visible_lines={best.visible_lines}"
        )
    elif successes:
        best = max(successes, key=lambda item: item.requested_max_tokens)
        log(
            "  Largest successful request did not stop on max_tokens:"
            f" requested={best.requested_max_tokens},"
            f" stop_reason={best.stop_reason},"
            f" output_tokens={best.output_tokens}"
        )
    if failures:
        first = failures[0]
        error_text = first.error.message if first.error is not None else "unknown"
        log(
            "  First failure:"
            f" requested={first.requested_max_tokens},"
            f" error={error_text}"
        )
        if first.error is not None and first.error.kind == "timeout":
            log(
                "  The first failure was a timeout under the configured timeout_seconds."
                " That is not proof of the model's hard max_tokens ceiling."
            )
        if first.error is not None and is_infrastructure_error(first.error):
            log(
                "  This failure looks like infrastructure pressure, not a hard model ceiling."
                " Treat the current result as inconclusive above the last successful point."
            )
    if attempts[-1].success and attempts[-1].requested_max_tokens >= output_max:
        log(
            "  Search hit --output-max before it found a validation failure."
            " Raise that cap if you want to keep pushing."
        )
    log("")


def render_table(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(shorten(cell)))

    def render_row(values: tuple[str, ...]) -> str:
        padded = [
            shorten(value).ljust(widths[index])
            for index, value in enumerate(values)
        ]
        return "  " + " | ".join(padded)

    divider = "  " + "-+-".join("-" * width for width in widths)
    return "\n".join(
        [
            render_row(headers),
            divider,
            *(render_row(row) for row in rows),
        ]
    )


def shorten(value: str, limit: int = 80) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."


async def async_main(args: argparse.Namespace) -> int:
    config = build_probe_config(args)
    client = build_client(config)
    print_model_header(
        config,
        preflight_count_tokens=args.preflight_count_tokens,
        output_prompt_style=args.output_prompt_style,
    )

    if config.api_key is None:
        log("ANTHROPIC_API_KEY is not set. Requests will fail with authentication_error.")
        log("")

    try:
        if args.probe in {"context", "both"}:
            context_attempts = await probe_context_limit(
                client=client,
                config=config,
                start_units=args.context_start_units,
                max_units=args.context_max_units,
                probe_max_tokens=args.context_probe_max_tokens,
                heartbeat_seconds=args.heartbeat_seconds,
                pause_seconds=args.pause_seconds,
                preflight_count_tokens=args.preflight_count_tokens,
            )
            print_context_summary(
                context_attempts,
                probe_max_tokens=args.context_probe_max_tokens,
                max_units=args.context_max_units,
            )

        if args.probe in {"output", "both"}:
            output_attempts = await probe_output_limit(
                client=client,
                config=config,
                output_start=args.output_start,
                output_max=args.output_max,
                heartbeat_seconds=args.heartbeat_seconds,
                pause_seconds=args.pause_seconds,
                preflight_count_tokens=args.preflight_count_tokens,
                output_prompt_style=args.output_prompt_style,
            )
            print_output_summary(output_attempts, output_max=args.output_max)
    except AuthenticationError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        return 2

    return 0


def main() -> int:
    args = parse_args()
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
