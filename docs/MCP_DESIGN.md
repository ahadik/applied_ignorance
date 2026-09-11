# Cloud MCP interface

Status: accepted design requirement, not implemented or deployed.

## Purpose

Let the user ask ChatGPT about their team and request cloud computations from a phone without depending on their Mac. MCP means Model Context Protocol. The backend performs calculations.  ChatGPT interprets the results and develops strategy. Keep tonight's local draft work independent of cloud deployment.

## Architecture

ChatGPT client → authenticated HTTPS MCP adapter at /mcp → application services → stored snapshots, analytical models, and job worker.

The CLI, future dashboard, and MCP adapter must share the same computation services. The adapter validates inputs and returns structured results. It must not duplicate scoring or optimization logic. Scheduled collection runs independently of chat sessions. Use Streamable HTTP with a maintained MCP SDK when implementing, rather than inventing a protocol implementation.

## Proposed tool contracts

All IDs are strings. Optional snapshot_id defaults to the latest suitable snapshot and is always resolved explicitly in the response. Season is mandatory for analyses. Week is mandatory for weekly analyses. Only expose implemented tools with validated input/output JSON schemas.

| Tool | Inputs | Output / semantics |
| --- | --- | --- |
| get_team_status | league_id, optional snapshot_id | Authorized user's roster, league rules, deadlines, feed freshness, outstanding work |
| get_draft_state | league_id, optional snapshot_id | Draft settings, observed picks, available player IDs when player data exists. Assigned versus unassigned slot |
| get_analysis | analysis_id | Saved calculations, assumptions, source versions, and results. Never invent a missing analysis |
| start_analysis | league_id, season, optional week, kind, snapshot_id, typed parameters, idempotency_key | Durable job_id. Kinds initially draft comparison, later lineup/waiver/trade. Validate kind-specific parameters |
| get_job | job_id | queued/running/succeeded/failed/cancelled, progress, analysis_id when successful, structured error when failed |

Start with get_team_status as the end-to-end integration probe. Expand analysis kinds only when their numerical engines and data are available. Player comparisons reference Sleeper IDs, not ambiguous names. Hypothetical overrides must be explicitly labeled and stored separately from observed facts. Limits on candidate counts, simulation sizes, runtime, and spend are enforced on the server.

## Result contract

Each result includes schema_version, request_id, generated_at (UTC), data_as_of, snapshot_id where applicable, source provenance and freshness, warnings, and structured data. Analyses additionally include analysis_id, model/code version, input hash, objective, assumptions, recorded simulation seed if used, and uncertainty or a statement that it is not estimated.

Never label a cached result live. Preserve provider publication time separately from retrieval time. Missing inputs produce an explicit missing_data result, not zero-valued substitutes. Job failures distinguish retryable transport failures from invalid inputs. Tool failures use the MCP error/result conventions and concise readable explanations alongside structured content.

## Authentication and boundaries

Use OAuth following current ChatGPT/MCP authorization requirements, including discovery and PKCE. Validate token issuer, audience, expiry, and scopes. Map identity to allowed leagues server-side. Supplied league_id and job_id are not authorization. Initial scopes: fantasy:read and fantasy:analyze. Keep vendor credentials in server-side secret storage and out of model context and logs.

Reading tools have read-only annotations. start_analysis creates a job and may incur bounded compute costs, so describe and annotate that side effect accurately. It is not a read-only operation. Deduplicate retries by authenticated identity plus idempotency key and payload hash, rejecting reuse with a different payload. Reads and bounded analyses need no extra application approval step beyond granted access and user instructions.

No arbitrary shell, SQL, URL-fetch, infrastructure-administration, or Sleeper account-write tools. Future action tools require a separately supported execution route and server-side permission checks. Approving a plan is distinct from submitting it to Sleeper. Treat retrieved news and external text as data, never executable instructions.

## Reliability and phone use

Long computations return job IDs promptly and survive phone disconnects. Results live in the backend, not chat memory. Notifications are a separate capability, not an assumed feature of MCP. A mobile dashboard can use the same application services if the native ChatGPT client cannot use this private connector.

Native mobile support is unverified. Before making it a production dependency, test this exact private connector with the user's account in the native ChatGPT app. A desktop Remote session that depends on an awake Mac does not satisfy the cloud-only requirement.

## Acceptance checks before release

1. Connect and authenticate in ChatGPT. Discover and call get_team_status.
2. Repeat from the user's phone with the Mac off, verifying fresh backend request logs and matching snapshot IDs.
3. Verify expired/revoked tokens and unauthorized league/job IDs are rejected.
4. Verify stale or absent projection feeds are labeled and cannot silently generate current recommendations.
5. Run a bounded analysis. Close the client. Reconnect and retrieve the same durable result.
6. Retry start_analysis and prove one job is created. Reject mismatched payload reuse.
7. Confirm CLI and MCP calculations match for identical inputs and recorded seeds.
8. Confirm no roster-change capability is advertised or accidentally invoked.

## Official references checked September 8, 2026

- [Connect and test](https://developers.openai.com/plugins/deploy/connect-chatgpt): HTTPS endpoint, tool discovery, and client testing.
- [Authentication](https://developers.openai.com/plugins/build/auth): OAuth discovery and authorization requirements.
- [MCP server guide](https://developers.openai.com/plugins/build/mcp-server): server implementation guidance.

Recheck client availability and protocol requirements at implementation time.
