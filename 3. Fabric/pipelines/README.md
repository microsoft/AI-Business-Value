# Fabric pipelines

Scheduled orchestration for the Direct Ingester notebooks and the downstream Audit Log Processor.

## Deployment

1. **Import the 4 notebooks** into your Fabric workspace first (one-time):
   - `3. Fabric/notebooks/Copilot_Audit_Log_Direct_Ingester.ipynb`
   - `3. Fabric/notebooks/Copilot_Licensed_Users_Direct_Ingester.ipynb`
   - `3. Fabric/notebooks/Copilot_Org_Data_Direct_Ingester.ipynb`
   - `3. Fabric/notebooks/Copilot_Audit_Log_Processor.ipynb`

2. **Find each notebook's ID** — open the notebook in Fabric, look at the URL:
   ```
   https://app.fabric.microsoft.com/groups/<WORKSPACE_ID>/synapsenotebooks/<NOTEBOOK_ID>?experience=...
                                          ^^^^^^^^^^^^^^                  ^^^^^^^^^^^^
   ```
   Both GUIDs are visible in the URL. Save them — you'll need 5 GUIDs total (1 workspace + 4 notebooks).

3. **Create a new pipeline** in Fabric:
   - Workspace → **+ New** → **Data pipeline** → name it `CopilotAdoptionPipeline`
   - Use the JSON view (toolbar → **View** → **JSON** or "Code") and paste the contents of [`CopilotAdoptionPipeline.DataPipeline/pipeline-content.json`](CopilotAdoptionPipeline.DataPipeline/pipeline-content.json)
   - Replace the placeholder values:
     - `REPLACE_WITH_AUDIT_LOG_NOTEBOOK_ID` → your audit-log notebook GUID
     - `REPLACE_WITH_AUDIT_LOG_PROCESSOR_NOTEBOOK_ID` → your audit-log processor notebook GUID
     - `REPLACE_WITH_LICENSED_USERS_NOTEBOOK_ID` → your users notebook GUID
     - `REPLACE_WITH_ORG_DATA_NOTEBOOK_ID` → your org-data notebook GUID
     - `REPLACE_WITH_WORKSPACE_ID` → your workspace GUID (used by every activity)
     - *(Only if you turn optional sources on)* the optional notebook GUIDs — see [Optional sources](#optional-sources-opt-in) below. Leave them as placeholders if unused; they never run while their toggle is `false`.
   - Save

4. **Run manually first** to validate: pipeline editor → **Run** at top. The 3 ingesters start in parallel (Org Data only when enabled). Audit log ingestion typically runs 5–15 min (Purview polling); users + org each <30 sec. The processor then runs after audit-log ingestion, licensed-users ingestion and the Agents 365 conditional branch succeed, writing `copilot_interactions_curated`. Processor runtime depends on data volume and Spark startup.

5. **Schedule it**: pipeline editor → **Schedule** at top → e.g. weekly Sunday 02:00. Activities run on the same cadence.

6. **Refresh the semantic model only after pipeline success.** This repository does **not** include a semantic-model refresh activity in the pipeline JSON. If you add one, make it wait for the processor and all other enabled model sources to succeed; a fixed-time refresh alone does not guarantee ingestion and processing have finished.

**Existing deployments:** import the processor notebook, add `Run_Audit_Log_Processor` from the updated JSON (including its `dependsOn` entries), and replace its notebook/workspace placeholders with your IDs. Preserve your existing activity IDs and parameter settings. Updating this repository does not automatically update a manually imported Fabric pipeline.

## Activity design notes

| Activity | Runtime | Dependencies and output |
|---|---|---|
| `Run_Audit_Log_Ingester` | 5–15 min (Purview-bound) | Reads Graph audit log API; writes to `dbo.copilot_interactions_parsed`. No dependency on other tables. |
| `Run_Licensed_Users_Ingester` | <30 sec | Reads Graph reports endpoint; writes to `dbo.copilot_licensed_users`. No dependency on audit log. |
| `Conditionally_Run_Org_Data` → `Run_Org_Data_Ingester` | <30 sec when enabled | Reads Graph users endpoint; writes to `dbo.copilot_org_data`. **Optional** — gated by the `EnableOrgDataPull` parameter. |
| `Run_Audit_Log_Processor` | Depends on data volume / Spark startup | Reads `copilot_interactions_parsed`, `copilot_licensed_users` and available `agents_365`; writes `copilot_interactions_curated`. Runs only after its three upstream dependencies succeed. |

The ingesters remain parallel. The processor is a downstream transform, not another ingester:

```text
Run_Audit_Log_Ingester -------+
Run_Licensed_Users_Ingester --+--> Run_Audit_Log_Processor --> curated table
Conditionally_Run_Agent365 --+
```

The processor depends on the **outer** `Conditionally_Run_Agent365` activity, not its nested notebook.
With `EnableAgent365 = false`, the empty false branch succeeds and processing can continue; with it
enabled, processing waits for the configured Agent 365 branch to succeed. In the **shipped pipeline
JSON**, that branch runs the **CSV lander** (`Copilot_Agent365_Lander.ipynb`), not the registry
ingester. If you prefer the app-only registry notebook, swap the referenced notebook ID and ensure
the Graph permissions are in place. The processor can use an existing `agents_365` table when the
pull is disabled, or handle its absence as documented in the notebook. Org Data and the other
optional sources are not processor inputs, so they have no dependency edge to it.
Total runtime now includes the downstream processing stage.

## Pipeline parameters

| Parameter | Type | Default | Purpose |
|---|---|---|---|
| `EnableOrgDataPull` | Boolean | `true` | When `false`, the Org Data Ingester is skipped. Use this for customers who upload Entra/HRIS data manually (e.g. from their internal HRIS system) instead of pulling from Microsoft Graph — common because Graph's `/users` data is often incomplete vs the customer's source-of-truth HRIS. |
| `EnableDataverse` | Boolean | `false` | When `true`, runs the Agent Transcript Parser (Copilot Studio transcripts from Dataverse). |
| `EnableConsumption` | Boolean | `false` | When `true`, runs the Credit Consumption Ingester. **Export-only** — the CSVs must already be in `Files/credit_consumption/`. |
| `EnableProductFeedback` | Boolean | `false` | When `true`, runs the Product Feedback Ingester. **Export-only** — the CSVs must already be in `Files/product_feedback/`. |
| `EnableAgent365` | Boolean | `false` | When `true`, runs the configured Agents 365 branch. In the shipped JSON this is the **CSV lander**. |

When you trigger the pipeline manually, Fabric prompts for parameter values. When you schedule it (via the Schedule button), the schedule definition stores fixed parameter values — so you can have, e.g., a weekly schedule with the core sources on and any optional sources you've wired up enabled.

## Optional sources (opt-in)

The pipeline includes the optional ingesters too, each gated by its own `Enable*` parameter and
**defaulted to `false`** — so out of the box the pipeline behaves exactly like the core-only version.
To switch one on: set its parameter to `true` **and** replace its notebook GUID placeholder.

| Toggle | Activity | Notebook | Notebook-ID placeholder | Notes |
|---|---|---|---|---|
| `EnableDataverse` | `Conditionally_Run_Dataverse_Transcripts` | `Copilot_Agent_Transcript_Parser.ipynb` | `REPLACE_WITH_TRANSCRIPT_PARSER_NOTEBOOK_ID` | Live Dataverse pull. Needs the app reg as a Dataverse **Application User** (see [`../docs/PERMISSIONS.md`](../docs/PERMISSIONS.md)). |
| `EnableConsumption` | `Conditionally_Run_Credit_Consumption` | `Copilot_Credit_Consumption_Ingester.ipynb` | `REPLACE_WITH_CREDIT_CONSUMPTION_NOTEBOOK_ID` | **PPAC credit build — now a [Fabric + Copilot Studio](../extended/Fabric%20+%20Copilot%20Studio/) add-on**, kept here transitionally. Land the 3 CSVs in `Files/credit_consumption/` first (see [`CREDIT-CONSUMPTION-SETUP.md`](../extended/Fabric%20+%20Copilot%20Studio/CREDIT-CONSUMPTION-SETUP.md)). |
| `EnableProductFeedback` | `Conditionally_Run_Product_Feedback` | `Copilot_ProductFeedback_Ingester.ipynb` | `REPLACE_WITH_PRODUCT_FEEDBACK_NOTEBOOK_ID` | **Export-only.** Land the CSV in `Files/product_feedback/` first (manually or via a [flow](../flows/)). |
| `EnableAgent365` | `Conditionally_Run_Agent365` | `Copilot_Agent365_Lander.ipynb` | `REPLACE_WITH_AGENT365_NOTEBOOK_ID` | Shipped default. Reads an exported agent registry CSV from `Files/agent365/agents.csv`. Swap to `Copilot_Agent365_Registry_Ingester.ipynb` only if you deliberately adopt the Graph app-only path. |

> **Export-only sources need their files landed before the pipeline runs.** Credit consumption and
> product feedback have no API, so schedule their [Power Automate landing flow](../flows/) to run
> *before* this pipeline (or land the files by hand), otherwise the ingester finds nothing and writes
> an empty table.

All optional ingestion branches start in parallel with the core ingesters. The processor waits
for the Agents 365 conditional branch only; the other optional branches remain independent.
The toggles follow the same `Enable*` naming as the PBIT's model toggles, so "on in the pipeline"
lines up with "on in the report".

## Failure handling

- Audit ingestion and processing each have `retry: 1`; users/org have `retry: 2`, all at 60s intervals. Ingestion retries handle transient Graph throttling; processor retries rerun the transform.
- If audit log fails after retry, users + org still complete (parallel branches don't block each other)
- If audit ingestion, licensed-users ingestion or the Agents 365 condition fails, the processor is skipped. Do not refresh the model against an old curated table after such a run.
- If the processor fails, ingestion outputs remain available but the pipeline has not produced a successful curated-data update. Resolve the failure before refreshing the model.
- If any single activity ultimately fails, the pipeline run is marked failed but partial Delta writes are preserved
- Use Fabric Monitor Hub → Pipeline runs → click into the failed activity → view notebook job log for diagnostics

## Schedule recommendation

Microsoft Graph's audit log API caps each query at 7 days back. Recommended schedule cadence:

| Cadence | When | Trade-off |
|---|---|---|
| **Weekly** (recommended) | Sundays 02:00 UTC | Matches Graph's 7-day window cleanly; no overlap, no gaps |
| Daily | 02:00 UTC | More frequent updates; needs careful date-window management to avoid duplicate rows (the audit log Message_Id dedup mostly handles this) |
| Monthly | Last day of month | Misses any 8th+ day of data — only use if you accept this |

Schedule the pipeline as one ingestion-and-processing unit, then refresh the semantic model after
successful completion. If you customize ingestion cadences, preserve the processor's dependencies
so it runs only after its required source tables are ready.
