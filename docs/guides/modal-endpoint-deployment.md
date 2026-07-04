---
title: "Modal Endpoint Deployment and Smoke Test"
schema_type: common
status: published
owner: core-maintainer
purpose: "Operator runbook for deploying a Modal Auto Endpoint and running one live smoke-test generation for the experimental generation_provider=modal leg (ADR-010 item 2)."
tags:
  - guide
  - generation
  - modal
---

This is an operator-run procedure. Each numbered step spends real Modal credits or
provisions real infrastructure; do not automate it into a script that runs unattended.

## 1. Authenticate

    modal token new

Opens a browser OAuth flow. Confirms with `modal profile list` and `modal token current`.

## 2. Deploy the standard-tier endpoint

    modal endpoint create --name cyo-standard --model <HF id>

The exact Hugging Face model identifier for Gemma 26B-A4B, and whether Modal's curated
catalog covers it directly or needs a `--custom-hf-repo` flag, is **not confirmed** as of
this writing. Check Modal's current supported-model list (`modal endpoint create --help`
or the Modal dashboard) immediately before running this command.

## 3. Capture the endpoint URL

    modal endpoint list

Copy the live URL into your (gitignored) `.env`:

    MODAL_BASE_URL=<url from modal endpoint list>
    MODAL_MODEL=<the HF id used in step 2>

## 4. Run the live smoke test

Using the existing yield harness (now Modal-aware per this plan's Task 8), against a real
8-11-band brief:

    PYTHONPATH=. .venv/bin/python scripts/yield_harness.py \
        --briefs <path-to-an-8-11-band-briefs.json> \
        --provider modal --no-fallback --limit 1 \
        --out docs/planning/yield-results/modal-standard-smoke-test.json

`--no-fallback` and `--limit 1` keep this to exactly one measured story so the credit spend
is bounded and known before running a larger sample.

## 5. Record the result

Whatever `docs/planning/yield-results/modal-standard-smoke-test.json` shows (pass/fail,
cost, latency) is one data point toward the ADR-010 promotion gate, not the gate itself. Add
a short note to ADR-010's Validation section referencing this file.
