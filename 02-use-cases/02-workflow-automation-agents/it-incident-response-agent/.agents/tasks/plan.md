# Implementation Plan: Route the agent's Claude calls through Claude Platform on AWS

Project root (quote every path, it contains `&`):
`/Users/pathipat/Work/Learning/Yip-aws-strands&agentcore/agentcore-samples/02-use-cases/02-workflow-automation-agents/it-incident-response-agent`
Repo venv: `/Users/pathipat/Work/Learning/Yip-aws-strands&agentcore/agentcore-samples/.venv` (python3.14, has `uv`, strands-agents 1.50.2, boto3 1.43; **anthropic is NOT installed there yet**).
No worktree. Do not commit. Only the model-loading path changes.

## Findings (what was actually read / confirmed)

Read in this repo:
- `app/ITIncidentAgent/model/load.py`: `load_model(priority="MEDIUM") -> BedrockModel`; `LOW` uses `FAST_MODEL_ID`, otherwise `AGENT_MODEL_ID`; returns `BedrockModel(model_id=...)`.
- `app/ITIncidentAgent/config.py`: `REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION", "us-west-2")`; `AGENT_MODEL_ID` / `FAST_MODEL_ID` are the last two lines (Model section).
- `app/ITIncidentAgent/main.py`: only calls `load_model()` / `load_model(priority)` and passes the result to `strands.Agent(model=...)` (lines ~378, 398, 516, 534). It uses no BedrockModel-specific attributes. `_bedrock_runtime` there is only for `apply_guardrail`, so it stays untouched. **main.py needs no edits.**
- `app/ITIncidentAgent/pyproject.toml`: deps are `aws-opentelemetry-distro`, `bedrock-agentcore`, `botocore[crt]`, `mcp`, `strands-agents >= 1.13.0, < 2.0`. hatchling build.
- `app/ITIncidentAgent/uv.lock` exists; it currently pins `strands-agents 1.42.0`, and has no `anthropic` entry. Dockerfile runs `uv sync --frozen --no-dev` (twice), so the lock must be regenerated.
- `agentcore/agentcore.json`: `runtimes[0].envVars` ends with `AGENT_MODEL_ID` and `FAST_MODEL_ID` (lines 22-23).
- `.gitignore` already ignores `.env`, `.env.local`, `.env.*.local`, so both env files are gitignored. Templates: `.env.example` and `agentcore/.env.local.example`.

Read in installed strands (`.venv/lib/python3.14/site-packages/strands/models/anthropic.py`, strands 1.50.2):
- `AnthropicModel.__init__(self, *, client_args=None, **model_config)`: runs `validate_config_keys`, sets `self.config = AnthropicModel.AnthropicConfig(**model_config)`, then `self.client = anthropic.AsyncAnthropic(**client_args)`. No SigV4 support.
- **`max_tokens` is `Required[int]` and `model_id` is `Required[str]`** in `AnthropicConfig`. So `max_tokens` must always be passed. Use 4096.
- The module does `import anthropic` at top level, so the `anthropic` package must be installed. The strands extra `strands-agents[anthropic]` resolves to `anthropic<1.0.0,>=0.21.0` in the 1.50.2 metadata.
- Streaming and requests go through `self.client.messages.stream(...)` / `self.client.messages.create(...)` (async). Overwriting `self.client` after `super().__init__` is therefore sufficient.

Confirmed from the anthropic-sdk-python source on GitHub (`src/anthropic/lib/aws/_client.py`, `_credentials.py`) and the AWS Claude Platform docs ("Making requests"):
- Real classes: `anthropic.AnthropicAWS` (sync) and **`anthropic.AsyncAnthropicAWS`** (async), subclass of `AsyncAnthropic`.
- Real `AsyncAnthropicAWS.__init__` kwargs include: `api_key`, `aws_access_key`, `aws_secret_key`, **`aws_region`**, `aws_profile`, `aws_session_token`, **`workspace_id`**, `skip_auth`, `base_url`, `timeout`, `max_retries`, `default_headers`, `http_client`, ... The names `aws_region` and `workspace_id` are correct.
- Behaviour: SigV4 service name `aws-external-anthropic`; base URL `https://aws-external-anthropic.<region>.api.aws`; adds the `anthropic-workspace-id` header; region and workspace id are both required, otherwise `AnthropicError` at construction. Credentials come from the default AWS credential chain (botocore), which means container role in AgentCore and the local profile on a dev machine.
- **Gotcha:** auth mode is chosen in `resolve_auth_mode`. If the env var `ANTHROPIC_AWS_API_KEY` is set (and no explicit AWS key/profile args), the client silently switches to API-key mode. The loader must guard against this, since we promise SigV4 (see step 2).
- Extras on `anthropic`: `aws = ["boto3 >=1.28.57, <2", "botocore >=1.31.57, <2"]` (also `bedrock` with the same deps). So the extra name is `aws`.
- Version constraint risk: anthropic on PyPI is now 1.14.0 (needs `httpx2`), but the strands anthropic extra in the installed 1.50.2 requires `anthropic<1.0.0`. The newest 0.x release seen is 0.120.2, and 0.117.1 contains an `AnthropicAWS.copy()` fix. So pin `anthropic[aws] >= 0.117.1, < 1.0.0`.

**Not yet verified locally.** The sandbox shell hung while trying to create a probe venv, so the installed-package check (`dir(anthropic)` and `inspect.signature`) was not run. Step 3 below makes this check mandatory before any code is considered final. If `AsyncAnthropicAWS` is missing from the version uv resolves under `<1.0.0`, STOP and report instead of guessing.

## Design decisions

- Subclass `AnthropicModel` and replace `self.client` after `super().__init__()`. Rationale: strands hardcodes `AsyncAnthropic` and offers no injection point; this reuses all message formatting and streaming and is the smallest change.
- Keep `load_model(priority)` signature, so `main.py` is untouched.
- Express `strands-agents[anthropic]` plus an explicit `anthropic[aws]` pin. Rationale: the strands extra keeps strands' own compatibility bound visible to the resolver, and `anthropic[aws]` guarantees the AWS client and boto3/botocore.
- `max_tokens=4096` as a module constant in `load.py` (strands requires it).
- Only `sigv4` is supported. `CLAUDE_AWS_AUTH_MODE` other than `sigv4` raises `NotImplementedError`.
- Out of scope but must be flagged to the user (see "Known gap" at the end): the deployed runtime role needs `aws-external-anthropic:CallWithBearerToken`.

## Steps

- [ ] 1. Update `config.py` model section.
      In the Model section: change `AGENT_MODEL_ID` default to `"claude-sonnet-4-6"` and `FAST_MODEL_ID` default to `"claude-haiku-4-5"`. Add, with a short comment block naming Claude Platform on AWS (Anthropic-operated, SigV4):
      `ANTHROPIC_AWS_WORKSPACE_ID = os.getenv("ANTHROPIC_AWS_WORKSPACE_ID", "")` and `CLAUDE_AWS_AUTH_MODE = os.getenv("CLAUDE_AWS_AUTH_MODE", "sigv4")`.
      Leave `REGION` and every other variable exactly as-is.
      Files: `app/ITIncidentAgent/config.py`
      Verify: from `app/ITIncidentAgent`, run `"<repo>/.venv/bin/python" -c "import config; print(config.AGENT_MODEL_ID, config.FAST_MODEL_ID, repr(config.ANTHROPIC_AWS_WORKSPACE_ID), config.CLAUDE_AWS_AUTH_MODE, config.REGION)"` with the relevant env vars unset. Expect `claude-sonnet-4-6 claude-haiku-4-5 '' sigv4 us-west-2`. Then run it again with the four env vars set and confirm they are picked up.

- [ ] 2. Rewrite `model/load.py` (depends on step 1 for the new config names).
      - Update the module docstring: model calls go through Claude Platform on AWS (Anthropic-operated, endpoint `https://aws-external-anthropic.<region>.api.aws`), SigV4 with the default AWS credential chain, no API key stored, bare model ids (`claude-sonnet-4-6`, `claude-haiku-4-5`), and the IAM requirement `aws-external-anthropic:CallWithBearerToken`. Keep the cost-routing explanation.
      - Replace imports: drop `strands.models.bedrock.BedrockModel`; import `anthropic` and `from strands.models.anthropic import AnthropicModel`; import `AGENT_MODEL_ID, FAST_MODEL_ID, REGION, ANTHROPIC_AWS_WORKSPACE_ID, CLAUDE_AWS_AUTH_MODE` from `config`.
      - Define `class ClaudePlatformAWSModel(AnthropicModel)` with `__init__(self, *, aws_region: str, workspace_id: str, **model_config)`: call `super().__init__(**model_config)` first (sets `self.config`), then `self.client = anthropic.AsyncAnthropicAWS(aws_region=aws_region, workspace_id=workspace_id)`. After construction, assert/raise a clear `RuntimeError` if `self.client._use_sigv4` is falsy (this is the `ANTHROPIC_AWS_API_KEY` gotcha); if that private attribute is missing in the resolved version, fall back to checking `os.environ.get("ANTHROPIC_AWS_API_KEY")` and raise if set. Add a short comment on why `client_args` is not used.
      - `load_model(priority: str = "MEDIUM") -> ClaudePlatformAWSModel`: validate `CLAUDE_AWS_AUTH_MODE.lower() == "sigv4"` else `NotImplementedError` naming the unsupported value; raise `ValueError` with clear text if `ANTHROPIC_AWS_WORKSPACE_ID` is empty or `REGION` is empty; keep LOW -> `FAST_MODEL_ID` else `AGENT_MODEL_ID`; return `ClaudePlatformAWSModel(aws_region=REGION, workspace_id=ANTHROPIC_AWS_WORKSPACE_ID, model_id=model_id, max_tokens=MAX_TOKENS)` with module constant `MAX_TOKENS = 4096`.
      Files: `app/ITIncidentAgent/model/load.py`
      Verify: do after step 3 (needs the dependency installed). Then, with `AWS_REGION=us-east-1 ANTHROPIC_AWS_WORKSPACE_ID=wrkspc_test` and any AWS creds present, `python -c "from model.load import load_model; m=load_model('LOW'); print(type(m).__name__, m.get_config()['model_id'], type(m.client).__name__, m.client.base_url)"` prints `ClaudePlatformAWSModel claude-haiku-4-5 AsyncAnthropicAWS https://aws-external-anthropic.us-east-1.api.aws/`. Also confirm `load_model()` -> `claude-sonnet-4-6`; empty workspace id -> `ValueError`; `CLAUDE_AWS_AUTH_MODE=apikey` -> `NotImplementedError`; `ANTHROPIC_AWS_API_KEY=x` -> the guard error.

- [ ] 3. Add dependencies and regenerate the lock (do this BEFORE running the step 2 verification).
      In `pyproject.toml` dependencies: change `"strands-agents >= 1.13.0, < 2.0"` to `"strands-agents[anthropic] >= 1.13.0, < 2.0"` and add `"anthropic[aws] >= 0.117.1, < 1.0.0"` (keep the list alphabetical-ish and the existing spacing style). Do not touch other deps. From `app/ITIncidentAgent` run `uv lock` (use `"/Users/pathipat/Work/Learning/Yip-aws-strands&agentcore/agentcore-samples/.venv/bin/uv"` or `uv` if on PATH). Prefer a minimal lock diff (no `--upgrade`). If resolution fails because of the `anthropic<1.0.0` bound in the strands extra, report the exact conflict and adjust only the anthropic pin; do not drop the AWS client.
      Then verify the real client against the resolved version using a throwaway env OUTSIDE the repo, e.g. `uv venv /tmp/itir-verify --python 3.12` then `uv sync --frozen --active`-style install, or `uv run --frozen --no-project`-style equivalent, with `UV_PROJECT_ENVIRONMENT=/tmp/itir-verify uv sync --frozen --no-dev` run in `app/ITIncidentAgent`. In that env run:
      `/tmp/itir-verify/bin/python -c "import anthropic, inspect; print(anthropic.__version__); print([n for n in dir(anthropic) if 'AWS' in n or 'Aws' in n]); print(inspect.signature(anthropic.AsyncAnthropicAWS.__init__))"`.
      Expect `AsyncAnthropicAWS` in the list and `aws_region` / `workspace_id` in the signature. **If not, STOP and report.**
      Files: `app/ITIncidentAgent/pyproject.toml`, `app/ITIncidentAgent/uv.lock`
      Verify: `uv sync --frozen --no-dev` succeeds in a throwaway env (exactly what the Dockerfile does), and `import strands.models.anthropic` works in that env. Use that same env for step 2 and step 6 checks (`PYTHONPATH=app/ITIncidentAgent`). Delete `/tmp/itir-verify` and any `.venv` created inside the project afterwards.

- [ ] 4. Update `agentcore/agentcore.json` runtime env vars (independent of steps 1-3).
      In `runtimes[0].envVars`: set `AGENT_MODEL_ID` to `claude-sonnet-4-6`, `FAST_MODEL_ID` to `claude-haiku-4-5`; append `{ "name": "ANTHROPIC_AWS_WORKSPACE_ID", "value": "wrkspc_01MWdcjKZoBBh9UmXyJAVS4W" }`, `{ "name": "CLAUDE_AWS_AUTH_MODE", "value": "sigv4" }`, `{ "name": "AWS_REGION", "value": "us-east-1" }` using the existing one-object-per-line style. Leave memories, gateways, policyEngines, onlineEvalConfigs, OTEL and X-Ray vars untouched.
      Files: `agentcore/agentcore.json`
      Verify: `python3 -c "import json; d=json.load(open('agentcore/agentcore.json')); print({e['name']:e['value'] for e in d['runtimes'][0]['envVars'] if e['name'] in ('AGENT_MODEL_ID','FAST_MODEL_ID','ANTHROPIC_AWS_WORKSPACE_ID','CLAUDE_AWS_AUTH_MODE','AWS_REGION')})"` parses and shows the five expected values; `git diff --stat` shows only these lines changed in this file.

- [ ] 5. Create the two gitignored env files (independent).
      Project-root `.env` and `agentcore/.env.local`, each containing exactly the user's block:
      ```
      # Region must match the Claude Platform on AWS workspace.
      AWS_REGION=us-east-1
      ANTHROPIC_AWS_WORKSPACE_ID=wrkspc_01MWdcjKZoBBh9UmXyJAVS4W
      CLAUDE_AWS_AUTH_MODE=sigv4
      CLAUDE_MODEL_ID=claude-sonnet-4-6
      ```
      Assumption: also append `CDK_DEFAULT_ACCOUNT=402020382644` to the root `.env` only (the deploy-time `.env.example` requires it and the user gave this account; `agentcore/.env.local` is the container runtime file and does not need it). `CLAUDE_MODEL_ID` is kept because the user asked for it, but the code reads `AGENT_MODEL_ID`, so it has no effect; mention that in the final report. Do NOT put credentials in these files; the local AWS credential chain is used.
      Files: `.env`, `agentcore/.env.local`
      Verify: `git check-ignore -v .env agentcore/.env.local` lists both as ignored, and `git status --short` does not list them.

- [ ] 6. End-to-end check (after steps 1-5).
      a) Offline: run the step 2 checks in the verify env.
      b) Syntax: `python -m compileall app/ITIncidentAgent -q` (use the verify env or repo venv).
      c) Optional live smoke test, only if local AWS credentials resolve (`aws sts get-caller-identity` shows account 402020382644) and the principal holds `aws-external-anthropic:CallWithBearerToken`: with the `.env` values exported, run a one-shot `asyncio` stream through `load_model("LOW")` (for example via `strands.Agent(model=load_model("LOW"))("Say hi")`). If it returns 403/signature or permission errors, record the exact message and report it instead of changing code.
      d) `git status --short` and `git diff --stat` show changes only in `config.py`, `model/load.py`, `pyproject.toml`, `uv.lock`, `agentcore/agentcore.json` (plus the ignored env files and `.agents/`). Confirm `main.py`, memory, mcp_client, lambdas, and CDK are unchanged. Do not commit. Remove temp envs under `/tmp`.

## Order / dependencies
1 -> 2 (config names); 3 must be applied before 2 can be verified; 4 and 5 are independent; 6 last.

## Known gap to report (not changed here, per "leave AWS paths untouched")
`agentcore/cdk/lib/cdk-stack.ts` (Step 5b, `RuntimeAdditionalPolicy` statements list, around lines 295-345) grants the runtime role `bedrock:InvokeModel` only through the L3 default. A deployed runtime will get access-denied from Claude Platform on AWS until a statement allowing `aws-external-anthropic:CallWithBearerToken` (resource scoped to the workspace, or `*` as a first pass) is added. Local `agentcore dev` with the user's own credentials is unaffected. Also note `.env.example` and `agentcore/.env.local.example` still show Bedrock-style model ids; optional follow-up to update their Model sections.

## Verification note (implementation iteration 1)

All installs and checks used the repo-root venv (`<repo>/.venv`, python3.14). No probe venvs remain.
- `uv lock` in `app/ITIncidentAgent` resolved `anthropic 0.125.0`; `uv lock --check` passes (128 packages). Dependencies are now `anthropic[aws] >= 0.117.1, < 1.0.0` and `strands-agents[anthropic] >= 1.13.0, < 2.0`.
- `uv pip install --python <repo>/.venv/bin/python "anthropic[aws]==0.125.0"` succeeded (exit 0).
- In that venv: `anthropic.__version__` = 0.125.0; `[n for n in dir(anthropic) if 'AWS' in n or 'Aws' in n]` = `['AnthropicAWS', 'AsyncAnthropicAWS']`; `AsyncAnthropicAWS.__init__` takes `aws_region` and `workspace_id` (plus api_key, aws_access_key, aws_secret_key, aws_profile, aws_session_token, ...); the client sets `_use_sigv4`.
- Loader checks, cwd = `app/ITIncidentAgent`, `PYTHONPATH=.`, env `AWS_REGION=us-east-1 ANTHROPIC_AWS_WORKSPACE_ID=wrkspc_test CLAUDE_AWS_AUTH_MODE=sigv4`, no network call:
  - `load_model('MEDIUM')` -> `ClaudePlatformAWSModel`, model_id `claude-sonnet-4-6`, max_tokens 4096, client `AsyncAnthropicAWS`, base_url `https://aws-external-anthropic.us-east-1.api.aws`.
  - `load_model('LOW')` -> model_id `claude-haiku-4-5`.
  - `ANTHROPIC_AWS_API_KEY=x` -> `RuntimeError` (SigV4 guard); empty workspace id -> `ValueError`; `CLAUDE_AWS_AUTH_MODE=apikey` -> `NotImplementedError`.
- `python -m py_compile config.py model/load.py main.py` -> OK.
- `agentcore.json` runtime envVars parse and show the five expected values.
- `git check-ignore -v` lists `.env` and `agentcore/.env.local` as ignored.
- `git status`: modified `agentcore.json`, `config.py`, `model/load.py`, `pyproject.toml`, `uv.lock` only (plus ignored env files and `.agents/`). `main.py` unchanged. Nothing committed.
- Not run: pylint (optional), Docker build (docker not installed), live model call (no network call requested).
- Note: `CLAUDE_MODEL_ID` from the user's original snippet is not written to the env files (spec lists `AGENT_MODEL_ID` instead); code reads `AGENT_MODEL_ID`.

## Verification note (iteration 2, review fixes)
- agentcore/agentcore.json restored from HEAD and re-edited with a byte-exact script (the editor tool re-serialized JSON on write). `git diff --stat` now shows 5 insertions / 2 deletions: two changed and three added env var lines, original one-object-per-line style intact.
- .env and agentcore/.env.local now include the user comment line and CLAUDE_MODEL_ID=claude-sonnet-4-6 from the original request, plus the keys the task spec lists (AGENT_MODEL_ID, FAST_MODEL_ID, GATEWAY_AUTH_MODE, and in .env the KB/guardrail/Jira placeholders and CDK_DEFAULT_ACCOUNT=402020382644). These extras are intentional. `git check-ignore -v` lists both as ignored.
- Re-ran with AWS_REGION=us-east-1 ANTHROPIC_AWS_WORKSPACE_ID=wrkspc_test CLAUDE_AWS_AUTH_MODE=sigv4, cwd app/ITIncidentAgent, repo venv: load_model(MEDIUM) -> ClaudePlatformAWSModel claude-sonnet-4-6 max_tokens 4096 AsyncAnthropicAWS https://aws-external-anthropic.us-east-1.api.aws; load_model(LOW) -> claude-haiku-4-5. No network call.
- py_compile config.py model/load.py main.py: OK. `uv lock --check`: Resolved 128 packages OK.
- Known gap: deployed runtime role needs aws-external-anthropic:CallWithBearerToken in cdk-stack.ts (not changed, out of scope).
- Not run: pylint, Docker build (docker not installed), live model call.
