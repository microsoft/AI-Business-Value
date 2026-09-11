# ARCHIVED — Files-mode smoke test reference

> **ARCHIVED / reference only.** This sample belongs to the archived Copilot Studio extension,
> not a recommended active add-on. The historical smoke-test instructions and sample content
> are retained below; see the [archived extension README](../../README.md) for context.

A CI-friendly smoke test for the canonical transcript parser
(`../Copilot_Agent_Transcript_Parser.ipynb`). Runs the entire parse + build
chain in plain Python against the sample CSV in
`copilot_transcripts/conversationtranscripts.csv` — **no Fabric workspace,
no Dataverse tenant, no Spark required**.

## What it verifies

- Every code cell of the canonical notebook parses (AST-clean)
- Every build_* function runs against a realistic transcript shape
- All **7** output Delta tables produce non-zero row counts
- The 8 deep-dive enrichment columns populate against the real Copilot
  Studio transcript schema (`SessionInfo`, `IntentRecognition`,
  `VariableAssignment`, `GPTAnswer`, `ConnectedAgentInitializeTraceData`,
  `AuthenticationTraceData`, `ErrorTraceData`)
- `agent_variables` decomposes `VariableAssignment` activities

## Historical run command (reference only)

From the repository root, change to the archived sample folder:

```powershell
Set-Location -LiteralPath '.\3. Fabric\archive\extended\Fabric + Copilot Studio\notebooks\samples'
python smoketest_files_mode.py
```

Exit code 0 = pass, non-zero = fail.

## What's in the sample CSV

Eight synthetic transcripts (all UPNs anonymised to `user-NNN@example.local`),
each exercising a different combination of trace types:

| # | Shape | Tests |
|---|---|---|
| 1 | Resolved single-agent (`SessionInfo` + `IntentRecognition` + `VariableAssignment`) | Explicit outcome, topic, variables |
| 2 | Abandoned (user gave up) | `is_authenticated`, abandonment |
| 3 | `ErrorTraceData` present | `agent_errors`, `ErrorCategory` |
| 4 | `ConnectedAgentInitializeTraceData` | `agent_subagents`, `MultiAgentSession` |
| 5 | Multiple `VariableAssignment` | `agent_variables` decomposition |
| 6 | `GPTAnswer` + `PluginInvocationTraceData` | `GenerativeResponseCount`, `PluginCallCount` |
| 7 | Anonymous (no `aadObjectId`) | `is_authenticated = False` |
| 8 | Returning user (same `aadObjectId` as #1) | `is_returning_user = True` |

## Expected output

```
SMOKE TEST RESULT — row counts per table
  ✓ dbo.agent_sessions              rows:      8   cols: 29
  ✓ dbo.agent_turns                 rows:     16   cols: 20
  ✓ dbo.agent_errors                rows:      1   cols: 6
  ✓ dbo.agent_subagents             rows:      2   cols: 8
  ✓ dbo.agent_catalogue             rows:      2   cols: 3
  ✓ dbo.agent_performance           rows:      8   cols: 57
  ✓ dbo.agent_variables             rows:      5   cols: 3
SMOKE TEST: PASSED ✓
```
