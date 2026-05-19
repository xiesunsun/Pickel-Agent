# Runtime Provider Error Surfacing Design

## Goal

When a provider call hangs or raises, the CLI should stop appearing frozen and show the raw exception details so model behavior can be diagnosed immediately.

## Scope

- Add an outer runtime timeout around `provider.generate(...)` using the existing model `provider_options.timeout_seconds` value when present.
- Print the full Python traceback in the CLI when a turn fails.
- Keep provider implementations and the event model unchanged.

## Non-Goals

- No unified exception taxonomy.
- No new runtime failure event types.
- No debug mode or structured error formatting.

## Approach

`ReActStrategy` already owns the step loop and the direct await on `context.provider.generate(...)`. That is the narrowest place to enforce a per-step timeout without changing every provider implementation.

`ChatLoop.run()` already catches top-level turn failures. Replacing the current single-line `Request failed: ...` rendering with a raw traceback preserves the existing control flow while exposing the real stack and exception type.

## Files

- Modify `src/myopenclaw/runs/strategy/react.py` to wrap model generation in `asyncio.wait_for(...)` when a timeout is configured.
- Modify `src/myopenclaw/cli/chat.py` to render `traceback.format_exc()`.
- Add regression coverage in `tests/runs/test_runner.py` and `tests/cli/test_chat_loop.py`.
