# Route IT incident agent LLM calls through Claude Platform on AWS (SigV4)

The agent's model loader now builds a strands `AnthropicModel` subclass whose client is replaced with `anthropic.AsyncAnthropicAWS`. Requests go to the Anthropic-operated Claude Platform on AWS endpoint, signed with SigV4 from the default AWS credential chain, instead of Amazon Bedrock. Config, dependencies, the AgentCore runtime env vars and two local env files were updated to match. `load_model(priority)` is unchanged, so `main.py` needs no edits. The class name and kwargs (`aws_region`, `workspace_id`) were verified by the coder against the installed `anthropic 0.125.0` and recorded in the plan's verification note.

Watch for: the deployed runtime role has no `aws-external-anthropic:CallWithBearerToken` permission yet, so a deployed runtime will be denied until `cdk-stack.ts` is updated (confirmed gap, out of scope per spec, flagged by the coder). The `_use_sigv4` guard reads a private SDK attribute (possible). `.env.example` files still show Bedrock-style ids (confirmed, minor).

**Verdict**: APPROVED

## High-level view

The loader replaces strands' hardcoded `AsyncAnthropic` client after the parent constructor has populated `self.config`. This reuses strands' message formatting and streaming with a minimal change. Only `sigv4` is accepted. A missing workspace id or region fails fast with a clear error, and the SDK's silent fallback to API-key auth (when `ANTHROPIC_AWS_API_KEY` is set) is turned into a `RuntimeError`.

Dependencies add `anthropic[aws] >= 0.117.1, < 1.0.0` and the `strands-agents[anthropic]` extra. The lock diff is additive (anthropic, distro, jiter, sniffio, plus the strands-agents dependency edges), with no unrelated version bumps. `agentcore.json` changes five env var lines in the existing one-object-per-line style, and everything else in the file is untouched. Config adds the two new variables, switches the model defaults to bare ids and leaves region resolution as it was.

The diff touches only `config.py`, `model/load.py`, `pyproject.toml`, `uv.lock` and `agentcore.json`. MCP, memory, DynamoDB, guardrail and EventBridge code is untouched, and nothing is committed (HEAD is still the merge commit; the only untracked path is `.agents/`).

<details>
<summary>Issues (3)</summary>

1. **Runtime IAM gap** (confirmed, non-blocking) — add an `aws-external-anthropic:CallWithBearerToken` statement to the runtime role in `agentcore/cdk/lib/cdk-stack.ts` before deploying. Local `agentcore dev` is unaffected.
2. **Private attribute in SigV4 guard** (possible, non-blocking) — `getattr(self.client, "_use_sigv4", ...)` depends on an SDK-internal name. The env-var fallback covers the case where the name disappears, but a future SDK change could make the guard silently less precise. Optionally add a small test or comment pinning the expected behavior.
3. **Stale Bedrock-style ids in templates** (confirmed, non-blocking) — `.env.example` and `agentcore/.env.local.example` still show Bedrock model ids. Update their Model sections as a follow-up.

</details>

<details>
<summary>Details</summary>

### SigV4 guard on the replaced client

`ClaudePlatformAWSModel.__init__` constructs `AsyncAnthropicAWS(aws_region=..., workspace_id=...)` and then checks `_use_sigv4`. The check exists because the SDK picks API-key mode whenever `ANTHROPIC_AWS_API_KEY` is set, which would contradict the documented "no stored key" posture. Failing loudly is the right failure mode (fail-closed). The weakness is the private attribute: the fallback default `not os.environ.get("ANTHROPIC_AWS_API_KEY")` only approximates what the SDK does, so the guard is best-effort rather than authoritative (possible). The change adds no tests for the guard, the `NotImplementedError` path or the empty-workspace path. The coder ran these as ad-hoc scripts and recorded the results, but they are not in the repo.

### Deployed-runtime permissions

The new `agentcore.json` env vars point the runtime at us-east-1 and the user's workspace, and the module docstring states the IAM requirement. The runtime role in `cdk-stack.ts` still only gets Bedrock access through the L3 default. The first deployed invocation will therefore fail with an access-denied error even though local runs work with the developer's credentials (confirmed by reading the plan's known-gap note; the CDK file was not modified). This is correctly out of scope for this diff but must be done before the deploy the user intends.

### Env files

`.env` and `agentcore/.env.local` both exist, are gitignored (`git status` does not list them) and contain the user's block verbatim, including the comment line and `CLAUDE_MODEL_ID`. They also carry additional keys (`AGENT_MODEL_ID`, `FAST_MODEL_ID`, `GATEWAY_AUTH_MODE`, and in `.env` the CDK account and placeholders). The coder's iteration-2 note records these as intentional and listed in the task spec. They are not tracked, so they are harmless to the diff. `CLAUDE_MODEL_ID` has no effect because the code reads `AGENT_MODEL_ID`. No credentials are written to either file.

### Verification evidence

The plan records the installed-package check (`AsyncAnthropicAWS` present, `aws_region`/`workspace_id` in the signature), loader construction for MEDIUM and LOW, the three error paths, `py_compile`, `uv lock --check` and the `agentcore.json` parse. Pylint, the Docker build and a live model call were not run. The live call and the Docker build remain unverified, so the real endpoint, the workspace permissions and the `uv sync --frozen` path in the image are untested (not blocking per the review scope). No re-run was done in this review; the spec evidence was read only.

</details>

<details>
<summary>File map</summary>

- `app/ITIncidentAgent/config.py`: bare model id defaults, plus `ANTHROPIC_AWS_WORKSPACE_ID` and `CLAUDE_AWS_AUTH_MODE`.
- `app/ITIncidentAgent/model/load.py`: `ClaudePlatformAWSModel` subclass and validated `load_model`.
- `app/ITIncidentAgent/pyproject.toml`: `anthropic[aws]` and the `strands-agents[anthropic]` extra.
- `app/ITIncidentAgent/uv.lock`: additive lock regeneration.
- `agentcore/agentcore.json`: runtime envVars (two changed, three added).

Full diff: `git diff -- 02-use-cases/02-workflow-automation-agents/it-incident-response-agent`

</details>
