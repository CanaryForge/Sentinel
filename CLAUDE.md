# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Sandbox escape detection harness for AI agents, built for the AI Incident
Response Sprint (Apart Research / CeSIA), anchored on the July 2026
OpenAI-Hugging Face incident (SSRF in an internal package registry, agents
communicating by encoding messages into directory names, no real-time
detection). The core question: if an agent tries to escape its sandbox, how
long does detection take, and via which signal?

**Read [report/scope.md](report/scope.md) before making any claim about what
this harness proves** — it's the source of truth on honest scope (what the
three detection signals do and don't cover) and is deliberately not to be
edited after results come in.

All code, comments, docs, and log messages in this repo are in **Spanish**,
matching the rest of the project — keep new contributions consistent with
that.

## Architecture

```
sandbox (agent + heartbeat pinger)  --HTTP_PROXY-->  egress-proxy (mitmproxy)
                                                          |  egress_monitor.py: baseline + network canary
                                                          |  heartbeat_monitor.py: silence watchdog
                                                          v
                                                       red-mocks (internal network)
                                                          |
                                              package-registry (toy SSRF target)
                                              model-hub (planted credentials)

workspace (shared, read-only volume) --> fs-monitor: canary_monitor.py
                                          (filename/dirname + content scanning)
```

Five layers, each independently swappable:

1. **Agent** (`sandbox/`) — `agent.py` is a minimal, auditable OpenAI-compatible
   chat-completions tool-calling loop (NOT the real OpenCode CLI — see the
   design note at the top of the file for why). Its `TOOLS` list and
   `DISPATCH` dict are the extension point for new agent tools.
   `prompts.py` builds the system prompt and is where the
   `con_harness`/`sin_harness` axis lives (presence/absence of explicit
   security guardrail language — the canary token itself is injected in
   both conditions, since it's detection instrumentation, not an agent
   safety measure).
2. **Monitors + egress proxy** (`monitors/`) — three independent, cheap,
   model-agnostic detectors: `heartbeat_monitor.py` (silence watchdog),
   `egress_monitor.py` (mitmproxy addon: baseline + canary matching on
   network traffic), `canary_monitor.py` (filesystem polling for the canary
   in file/dir names or content). All three write to the same JSONL event
   format defined in `event_bus.py` (`{type, run_id, ts, severidad:
   info|alerta, detalle}`) — any new monitor must reuse this, not invent a
   parallel format.
3. **Mocks** (`mocks/package_registry`, `mocks/model_hub`) — minimal Flask
   services that are the escape targets (toy SSRF endpoint, planted fake
   credentials). `redteam/` is an optional overlay adding a 4th vector
   (external red-teamer doing prompt injection via the package-registry's
   SSRF, reached under the network alias `mirror-externo`).
4. **Tasks** (`tasks/task_0N_*.md` + `tasks/seed/`) — four tasks, each with a
   planted escape hint (leaked credentials in `.env.old`, an error message
   pointing at an internal registry, an injected prompt payload). Tasks are
   solvable without leaving the workspace; escaping is never necessary, only
   tempting.
5. **Orchestrator + analysis** (`orchestrator/run_experiment.py`,
   `analysis/compute_ttd.py`) — runs the experimental matrix
   (condition x task x repetition), one Docker Compose stack per run,
   sequentially (a scarce local-LLM or rate-limited cloud backend makes
   parallel runs counterproductive). `compute_ttd.py` computes time-to-detection
   = first monitor alert timestamp − first escape-attempt timestamp, with
   bootstrap 95% CI. "Escape attempt" has an explicit, documented, per-task
   definition (see the module docstring) — not a universal anomaly detector.

Both Docker networks used for escape targets (`red-proxy`, `red-mocks`) are
always `internal: true` — nothing here touches the real internet except the
harness's own call to its LLM backend (`llm-backend` network, deliberately
NOT internal). Never relax `internal` on the existing networks; a new
component needing real internet access goes on its own explicitly-documented
network instead.

### Where to make a given kind of change

| Want to... | Touch |
|---|---|
| Add a new tool to the agent | `sandbox/agent.py` (`TOOLS` + `DISPATCH`) |
| Change the system prompt / `con_harness` condition | `sandbox/prompts.py` |
| Add a new escape vector | `tasks/task_0N_*.md` + `tasks/seed/task_0N_*/`; if it needs a new mock, a `docker-compose.<vector>.yml` overlay + `orchestrator/config_<vector>.yaml` (follow the `redteam/` pattern) |
| Change what counts as an "escape attempt" | `analysis/compute_ttd.py` (`first_escape_attempt_ts` / per-task logic in `analyze_run`) |
| Add a new monitor | `monitors/`, reusing `event_bus.py`'s event format |
| Change the experimental matrix (conditions/tasks/repetitions) | `orchestrator/config.yaml` (base) or an alternate config |
| Check what's actually been validated vs. untested | `report/scope.md` ("Validacion realizada") and `.kiro/specs/sandbox-escape-harness/tasks.md` |

## Commands

```bash
# One-time setup
cp .env.example .env
chmod 777 results/    # containers run cap_drop:[ALL], can't write to the host bind mount otherwise

# Smoke test (single manual run)
docker compose up --build
docker compose logs sandbox   # should end "[entrypoint] agente termino con status=0"
cat results/manual_test_000_transcript.jsonl
docker compose down -v

# Validate the experiment matrix without spending compute
pip install -r orchestrator/requirements.txt
python3 orchestrator/run_experiment.py --dry-run --limit 5
docker compose config -q      # validates compose YAML without building

# Run the full experiment (sequential; reentrant — reruns skip run_ids that
# already have a {run_id}.jsonl in results/)
python3 orchestrator/run_experiment.py
python3 orchestrator/run_experiment.py --config orchestrator/config_redteam.yaml   # vector 4, run after the base matrix

# Manual network control condition (Layer 2, outside the automated matrix)
docker compose -f docker-compose.yml -f docker-compose.control.yml \
  up --build sandbox package-registry model-hub

# Analysis (writes results/summary.jsonl)
pip install -r analysis/requirements.txt
python3 analysis/compute_ttd.py

# Positive controls: inject each of the 3 detectable events by hand
# (heartbeat silence, filesystem canary, network canary, egress baseline)
# and confirm each monitor fires, without depending on an LLM choosing to
# escape. Run this after touching any monitor.
tests/positive_controls.sh
```

There is no lint suite or CI config in this repo. Correctness is validated
by `tests/positive_controls.sh` (deterministic monitor smoke test — see
`report/scope.md`, "Deteccion validada de forma deterministica"), the smoke
test above, checking `results/*_transcript.jsonl` / `results/*.jsonl` for
sane events, and `docker compose config -q` for compose file changes.

## Non-negotiable conventions

- **Comments**: Spanish, only when explaining a non-obvious decision (a real
  bug found, a "why" that would surprise a later reader). Never comments
  that just restate what the line does.
- **`docker-compose.yml` while the orchestrator is running**: don't edit it.
  `run_experiment.py` re-reads compose files from disk on every iteration;
  mid-matrix edits contaminate remaining runs. New vectors go in an overlay
  (`docker-compose.<vector>.yml`) + its own orchestrator config, never mixed
  into the base file until the current run finishes. `orchestrator/config.yaml`
  itself is safe to edit live (read once at process start).
- **Planted credentials/secrets in mocks**: always invented strings
  (`fake-token-do-not-use-*`), never real credentials or real third-party
  service data.
- **No generic exploits**: mock "holes" are a few lines each, existing only
  so the agent has something to discover — not realistic vulnerabilities.
