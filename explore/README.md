# Exploration Scripts

This folder contains small, non-production scripts for inspecting provider behavior and integrations.

## Shared environment

The Anthropic probe uses the same credentials as the main app:

- `ANTHROPIC_API_KEY`
- or `api_key` on the selected `anthropic` model entry in `config.yaml`

The probe reads only the selected provider/model subtree from `config.yaml`, so unrelated env vars in other sections do not have to be set.

## Anthropic model limit probe

This script calls the native Anthropic API directly. It does not read `config.yaml`.

Default target:

- model: `claude-jupiter-v1-p`
- api base: `https://api.anthropic.com`
- timeout: `120`
- retries: `2`
- thinking: `xhigh`
- context validation `max_tokens`: `64`
- output prompt style: `capacity`
- token counting mode: use response `usage` by default, not a separate preflight request

Run both context-window and output-limit probes:

```bash
uv run python explore/anthropic_limit_probe.py --probe both
```

Run only the output probe:

```bash
uv run python explore/anthropic_limit_probe.py --probe output
```

Useful overrides:

```bash
uv run python explore/anthropic_limit_probe.py \
  --probe both \
  --model claude-jupiter-v1-p \
  --api-base https://api.anthropic.com \
  --timeout 120 \
  --max-retries 0 \
  --thinking xhigh \
  --output-prompt-style capacity \
  --output-start 4096 \
  --output-max 131072 \
  --context-probe-max-tokens 64 \
  --context-max-units 65536 \
  --pause-seconds 2 \
  --heartbeat-seconds 5
```

What the script reports:

- context probe: the last successful `input_tokens` count before a validation failure
- output probe: requested `max_tokens`, actual `usage.output_tokens`, `stop_reason`, visible line count, and the first failure mode
- live progress: every `count_tokens`, `create`, and `stream` call prints start, heartbeat, and completion lines so the script no longer appears stuck
- lower request pressure: by default the script avoids separate `count_tokens` calls and pauses briefly between large attempts
- output prompt styles:
  - `capacity`: fixed-format endless record stream for hard output ceiling probing
  - `legacy`: the older numbered-list prompt for comparison only

Implementation notes:

- output probe uses the streaming Messages API
- context probe also uses the streaming Messages API now, which is more robust for very large requests under `thinking=xhigh`

If you want the old diagnostic behavior and are willing to pay for more requests:

```bash
uv run python explore/anthropic_limit_probe.py --probe both --preflight-count-tokens
```

Note: with `thinking: xhigh`, hidden thinking tokens count against the output budget for the current turn. So a successful request with `stop_reason=max_tokens` may still produce less visible text than the reported `output_tokens`.

## OpenViking long-term memory exploration

This script inspects how myopenclaw can read OpenViking long-term memory.

Required environment variables:

- `OPENVIKING_BASE_URL`
- `OPENVIKING_USER_KEY`
- `OPENVIKING_ACCOUNT_ID`
- `OPENVIKING_USER_ID`
- `OPENVIKING_AGENT_ID`

Run:

```bash
uv run python explore/openviking_long_term_memory.py
```

Optional:

```bash
uv run python explore/openviking_long_term_memory.py --query "User's coding preferences" --limit 5
```
