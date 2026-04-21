# Runtime Provider Error Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface raw model-call exceptions in the CLI and convert configured provider timeouts into visible failures instead of silent hangs.

**Architecture:** Keep the change at the runtime boundary. `ReActStrategy` applies an outer timeout to `provider.generate(...)`, and `ChatLoop` renders the resulting traceback verbatim. This avoids a new exception layer while making failures debuggable.

**Tech Stack:** Python, asyncio, Rich, unittest

---

### Task 1: Add runtime timeout around provider.generate

**Files:**
- Modify: `src/myopenclaw/runs/strategy/react.py`
- Test: `tests/runs/test_runner.py`

- [ ] **Step 1: Write the failing timeout test**

Create a provider double that sleeps longer than the configured timeout and assert that `coordinator.run_turn(...)` raises `TimeoutError`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/runs/test_runner.py -k timeout -v`

- [ ] **Step 3: Write minimal implementation**

Read `context.agent.model_config.provider_options["timeout_seconds"]` when present and wrap `context.provider.generate(...)` with `asyncio.wait_for(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/runs/test_runner.py -k timeout -v`

- [ ] **Step 5: Keep implementation local**

Do not change provider classes or the runtime event model.

### Task 2: Render raw traceback in CLI

**Files:**
- Modify: `src/myopenclaw/cli/chat.py`
- Test: `tests/cli/test_chat_loop.py`

- [ ] **Step 1: Write the failing CLI test**

Use a coordinator that raises `ValueError("boom")` during `run_turn(...)` and assert the rendered output contains `Traceback` and `ValueError: boom`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cli/test_chat_loop.py -k traceback -v`

- [ ] **Step 3: Write minimal implementation**

Replace the single-line exception rendering with `traceback.format_exc()` in `ChatLoop.run()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/cli/test_chat_loop.py -k traceback -v`

- [ ] **Step 5: Verify no duplicate assistant render**

Keep the existing control flow for successful turns untouched.

### Task 3: Run focused regression suite

**Files:**
- Test: `tests/runs/test_runner.py`
- Test: `tests/cli/test_chat_loop.py`

- [ ] **Step 1: Run focused tests**

Run: `uv run pytest tests/runs/test_runner.py tests/cli/test_chat_loop.py -v`

- [ ] **Step 2: Review output**

Confirm timeout failure is raised, traceback is printed, and existing chat loop tests still pass.
