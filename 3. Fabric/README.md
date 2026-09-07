# Fabric / Lakehouse deployment (recommended)

Notebooks pull your Copilot data from Microsoft Graph and write Delta tables
straight into a Lakehouse. 

![Fabric architecture](ValueLens_Fabric_Architecture.png)

> **Not only Fabric.** The same notebooks and template also run on **Azure Databricks**, **Synapse
> Spark**, **Azure SQL**, or a **Fabric Warehouse** with no real changes. See
> [Works beyond Fabric](#works-beyond-fabric).

## What's here

| Item | Purpose |
|---|---|
| `ValueLens - Fabric.pbit` | Import-mode Power BI template using the Lakehouse SQL analytics endpoint (TDS/TCP 1433). |
| `ValueLens - Fabric OneLake.pbit` | The same core report, importing Delta tables through OneLake over HTTPS/443. An alternative when the SQL endpoint's TCP connection is blocked. This is **not Direct Lake** mode. |
| `notebooks/` | The base (*No Studio*) ingester notebooks — audit logs, licensed users, org data — **plus `Copilot_Audit_Log_Processor`**, which does the heavy audit-log shaping once in Spark. Optional: feedback, Agents 365, Cowork / Work IQ. See [`notebooks/README.md`](notebooks/README.md). |
| `pipelines/`, `flows/`, `docs/` | Optional: a Fabric pipeline to run the core notebooks on a schedule, Power Automate flows for export-only sources, and reference docs. |
| `archive/` | The previous (pre-2307) Power-Query template, kept for reference only. Not needed for a new deployment. |

> Copilot Studio agent-transcript analytics is a **separate optional add-on** — see
> [Optional sources](#optional-sources). Everything in this Quick start is the core, Studio-free path.

## 📚 Dashboard pages

<details>
<summary>13 core report pages — activation, adoption, value, governance, feedback &amp; appendices</summary>

| Page | Purpose |
|---|---|
| **◆ Activation** | Activation across teams — licensed vs unlicensed, active vs inactive |
| **🎯 Readiness** | Ranks unlicensed / low-adoption users by upgrade‑priority score |
| **📡 Adoption** | User counts, coverage %, licensed vs unlicensed reach |
| **🔮 Activity** | Copilot and agent usage, tasks and behaviour mix |
| **🚀 Value** | Hours saved, dollar‑equivalent assisted value, and the business case |
| **🌱 Power Users** | Usage patterns, user progression and organisation comparisons |
| **🛡 Agent Health** | Agent inventory, usage and governance; unavailable source telemetry remains blank |
| **💬 Feedback** | Thumbs up/down sentiment and verbatim feedback themes |
| **📈 Heatmap** | Activity heatmap across the reporting period |
| **🏅 Leaderboard** | Top users, agents, and functions |
| **📘 Appendix: Key Concepts** | Methodology and key‑concept explainers |
| **🧬 Appendix: Signal - Impact Table** | Trace raw signals through to value (audit trail) |
| **📘 Appendix: Glossary** | Metric definitions and research sources |

</details>

### Report filters and views

The core reports use a right-hand filter column. Slicer headings use a consistent
8 pt size, matching **Agent Name**. Each applicable page has one **Cowork vs Agent**
dropdown; switching view bookmarks preserves its current selection. The dropdown
uses the existing `Agent Filter` data: it does not invent Cowork activity when none
is present in the source.

Existing Licensed/Unlicensed bookmarks remain in place without a duplicate licence
slicer on those pages. On the Value page, **Value Table** hides the work-type
controls; **Time Saved** shows them again.

## Quick start

The notebooks land the Delta tables; the template is a thin client over them. At a glance:

1. **Create a Lakehouse** and note its SQL endpoint.
2. **Register an Entra app** with three Graph permissions.
3. **Run the core ingester notebooks** (audit logs, licensed users, org data).
4. **Run the curate notebook** — shapes the audit-log fact table once in Spark.
5. **Connect the template** — choose SQL or OneLake, enter connection and date parameters, then **Load**.
6. **Schedule the refresh** to match your notebook cadence.

<details>
<summary><b>1. Create a Lakehouse</b></summary>

In a Fabric workspace on a capacity (F2+ or trial): **+ New -> Lakehouse**, name it (e.g.
`<your-lakehouse>`). Note its **SQL endpoint** from Lakehouse settings -
`<workspace-guid>.datawarehouse.fabric.microsoft.com`.
</details>

<details>
<summary><b>2. Register an Entra app</b></summary>

Create an app registration with these **Microsoft Graph application** permissions (admin consent
required), then note the **Tenant ID**, **Client ID**, and a **Client secret value**:

| Permission | Used by |
|---|---|
| `AuditLogsQuery.Read.All` | Audit log notebook |
| `Reports.Read.All` | Licensed users notebook |
| `User.Read.All` | Org data notebook |
| `CopilotPackages.Read.All`, `Application.Read.All` | *Optional* — Agent 365 catalog notebook (app-registration path, see [Optional sources](#optional-sources)) |
</details>

<details>
<summary><b>3. Run the core ingester notebooks</b></summary>

For each core notebook (audit logs, licensed users, org data): **+ New -> Import notebook**, attach it
to your Lakehouse and pin it as default, then paste your three values into the `# === CONFIG ===`
cell and run.

| Notebook | Cadence | Output table |
|---|---|---|
| `Copilot_Audit_Log_Direct_Ingester.ipynb` | Daily (Graph caps audit queries to a 7-day window) | `dbo.copilot_interactions_parsed` |
| `Copilot_Licensed_Users_Direct_Ingester.ipynb` | Weekly / monthly | `dbo.copilot_licensed_users` |
| `Copilot_Org_Data_Direct_Ingester.ipynb` | Weekly | `dbo.copilot_org_data` |

Use each notebook's **Schedule** button, or wire all three into a single Fabric pipeline (see
`pipelines/`).

> For production, read the secret from Key Vault instead of a literal - each CONFIG cell has a
> commented `notebookutils.credentials.getSecret(...)` example.
</details>

<details>
<summary><b>4. Run the curate notebook</b> (shapes the audit-log fact table)</summary>

One extra notebook does the heavy audit-log shaping **once in Spark**, so Power BI never has to.
Import `notebooks/Copilot_Audit_Log_Processor.ipynb`, attach it to the same Lakehouse, and run it
**after** the audit-log ingester (and after the licensed-users / Agents 365 producers, which it joins).

| Notebook | Reads | Writes |
|---|---|---|
| `Copilot_Audit_Log_Processor.ipynb` | `copilot_interactions_parsed` (+ `copilot_licensed_users`, `agents_365`) | `dbo.copilot_interactions_curated` |

It parses the `AccessedResources` / `AISystemPlugin` JSON, explodes accessed resources, derives the
date columns, normalises the UPN, joins the licence flag and resolves the agent map — the **same
output** the template's Power Query used to produce, but computed once and V-Ordered on disk. The
template then reads this one table with **no transformation**, which is what makes refreshes fast and
Direct Lake possible.

> **It does not ingest, and does not replace the ingester.** Order per run:
> audit-log ingester → **this curate notebook** → semantic-model refresh. Drop it into the same
> pipeline immediately before the refresh. Use `WRITE_MODE = "overwrite"` for the first backfill,
> then `"merge"` for daily runs.
</details>

<details>
<summary><b>5. Connect the template</b></summary>

Choose one core template in Power BI Desktop. Both read the same processed
Lakehouse tables, including `copilot_interactions_curated`, `copilot_licensed_users`
and `copilot_org_data`. Complete notebook ingestion and processing before refreshing
the report.

For `ValueLens - Fabric.pbit`:

| Parameter | Required? | Value |
|---|---|---|
| **Fabric SQL Endpoint** | Yes | `<workspace-guid>.datawarehouse.fabric.microsoft.com` |
| **Lakehouse Name** | Yes | Your Lakehouse name (e.g. `<your-lakehouse>`) |

For `ValueLens - Fabric OneLake.pbit`:

| Parameter | Required? | Value |
|---|---|---|
| **Fabric Workspace ID** | Yes | The workspace GUID, not its display name |
| **Lakehouse ID** | Yes | The Lakehouse item GUID, not its name or SQL endpoint ID |

Both templates also require a date window:

| Parameter | Required? | Value |
|---|---|---|
| **RangeStart** | Yes | Start timestamp, inclusive, covering the history to import |
| **RangeEnd** | Yes | End timestamp, exclusive; use 1 September at midnight to include all of 31 August |
| `Enable_ProductFeedback` | Optional | `Include` to load `user_feedback`, else `Exclude` |
| `Enable_Agent365` | Optional | `Include` to load `agents_365`, else `Exclude` |

The release files have no prefilled tenant or test-Lakehouse identifiers. For OneLake,
copy the two GUIDs from the Lakehouse's Fabric URL. Names containing spaces are not
valid substitutes for these parameters. Sign in with an organisational account that
can read the selected source, then click **Load**. A connection dialog can remain
behind the main Desktop window; bring it forward if the report appears to be waiting.

Both templates use **Import** mode. Confirm refresh and report filters before
publishing, then configure the matching SQL or OneLake credentials in the service.
The OneLake connection still requires network access to OneLake and appropriate
permissions; HTTPS alone does not bypass tenant, proxy or data-access policy.
</details>

<details>
<summary><b>6. Schedule the refresh</b></summary>

In the Service: semantic model **Settings -> Data source credentials** -> sign in to the selected SQL or OneLake source, then
enable **Scheduled refresh** on a cadence that matches your notebook schedule.

> **Incremental refresh is pre-configured.** The template ships with an Import-mode incremental-refresh
> policy on the `Chat + Agent Interactions (Audit Logs)` fact table (rolling 12-month window, last
> ~7 days re-queried each run), so the first refresh loads history once and every scheduled refresh
> after that refreshes the recent partitions. It needs a **Premium / PPU / Fabric** capacity. To change the
> window - or to use **Direct Lake** instead - see [`docs/INCREMENTAL-REFRESH.md`](docs/INCREMENTAL-REFRESH.md).

The OneLake variant retains the policy but reads Delta through Power Query rather
than folding a T-SQL filter to the SQL endpoint. Do not assume equivalent refresh
performance on large datasets; validate service refresh duration and capacity use
for the intended history window.
</details>

## Optional sources

Leave every `Enable_*` toggle on `Exclude` and the core dashboard still works - optional tables simply
load empty. To switch one on, set its toggle to `Include` and run the matching notebook:

| Source | Toggle | Notebook |
|---|---|---|
| Cowork / Work IQ consumption (MAC) | `Enable_CostConsumption` | `notebooks/Copilot_Cost_Consumption_Ingester.ipynb` ([setup guide](flows/COST-CONSUMPTION-SETUP.md)) |
| Product feedback | `Enable_ProductFeedback` | `notebooks/Copilot_ProductFeedback_Ingester.ipynb` |
| Agents 365 | `Enable_Agent365` | **`notebooks/Copilot_Agent365_Registry_Ingester.ipynb`** *(default — Graph API app-only, scheduled/unattended)* **·** `notebooks/Copilot_Agent365_Lander.ipynb` *(CSV-export fallback — use only when the Ingester's app-reg permissions aren't available)* |

Cowork / Work IQ consumption and product feedback are **export-only** in Microsoft's portals (no API) -
the `flows/` folder has Power Automate flows that auto-land those exports for you. Full detail in
[`docs/OPTIONAL-SOURCES.md`](docs/OPTIONAL-SOURCES.md). The **Power Platform (PPAC) per-agent credit**
export is a Studio-build source — see the
[Fabric + Copilot Studio](extended/Fabric%20+%20Copilot%20Studio/README.md) build.

<details>
<summary><b>Copilot Studio agent deep-dive</b> — separate add-on template (click to expand)</summary>

Agent-transcript analytics and the Agents 365 registry preview are **not** part of the base *No Studio*
build — they ship as the **[Fabric + Copilot Studio](extended/Fabric%20+%20Copilot%20Studio/README.md)**
template and notebooks. To enable them:

1. Use the **Fabric + Copilot Studio** `.pbit` instead of the base template.
2. Set `Enable_Dataverse` = `Include`.
3. Run `3. Fabric/extended/Fabric + Copilot Studio/notebooks/Copilot_Agent_Transcript_Parser.ipynb`.

Full setup lives in the [Fabric + Copilot Studio README](extended/Fabric%20+%20Copilot%20Studio/README.md).
</details>

<details>
<summary><b>Manual export instructions</b> — for first-time setups or sources without an API (click to expand)</summary>

The notebooks above are the recommended path. If you'd rather export the underlying data by hand first
(common for a one-off pilot, or for sources that have no API), use the steps below. Each export
produces a CSV you can drop into the Lakehouse `Files/` area and ingest with the matching notebook.

### Audit logs — Microsoft Purview
- **Portal:** [security.microsoft.com](https://security.microsoft.com) → **Audit**
- **Role:** Audit Reader or Compliance Administrator
- **Activities:** `Copilot Activities – Interacted with Copilot` (required); optionally `Interacted with a Connected AI App` and `Interacted with an AI App` for third-party agent coverage
- **Output:** Set a date range, run the search, **Export → Download all results** (CSV, ~50 columns, one row per interaction)

### Licensed users — Microsoft 365 Admin Center
- **Portal:** [admin.microsoft.com](https://admin.microsoft.com) → **Reports → Usage → Microsoft 365 Copilot → Readiness**
- **Role:** Global Administrator or Reports Reader
- **Pre-step:** turn off "Display concealed user/group/site names" under **Settings → Org Settings → Reports** so user names aren't masked
- **Output:** Scroll to **Copilot Readiness Details**, click `...` → **Export** (CSV with `UserPrincipalName`, `Department`, `Has Copilot license assigned`, `LastActivityDate`)

### Org data — Microsoft Entra
- **Portal:** [entra.microsoft.com](https://entra.microsoft.com) → **Identity → Users → All users**
- **Role:** User Administrator or Global Reader
- **Required columns:** `UserPrincipalName`, `Department`. Recommended: `JobTitle`, `Office`, `City`, `Country`, `Manager`
- **Output:** **Download users** (CSV)
- **Bring your own org data (instead of Entra)?** Set the pipeline parameter `EnableOrgDataPull=false`
  and upload your own users CSV (same columns as above — the shape a **Viva Insights** org-data file
  uses). See [`pipelines/README.md`](pipelines/README.md).

### Agent 365 — Microsoft Admin Center
- **Default path:** **`notebooks/Copilot_Agent365_Registry_Ingester.ipynb`** pulls the catalog directly through the Microsoft Graph app registration (app-only — `CopilotPackages.Read.All` + `Application.Read.All`, admin-consented), so no manual export is needed and it can run scheduled/unattended.
- **Fallback:** `notebooks/Copilot_Agent365_Lander.ipynb` reads the manual admin-center CSV export from `Files/agent365/agents.csv`. Use this only when your tenant can't grant the Ingester's app-reg permissions, or for one-off / evaluation runs. The two notebooks target the same `dbo.agents_365` table — pick one, don't run both.
- **Portal:** [admin.microsoft.com](https://admin.microsoft.com) → **Agents**
- **Role:** Global Administrator or Reports Reader (with AI Admin in a Frontier-enrolled tenant)
- **Output:** **Export** from the Agents Overview (CSV: agent name, ID, availability status, last activity, template, assigned users)

### Cowork / Work IQ consumption — Microsoft 365 Admin Center
The Cowork / Work IQ per-user credit export is **export-only**. Land it in the Lakehouse
`Files/cost_consumption/` folder and ingest it with `notebooks/Copilot_Cost_Consumption_Ingester.ipynb`
— full portal steps are in [`flows/COST-CONSUMPTION-SETUP.md`](flows/COST-CONSUMPTION-SETUP.md);
schema and model wiring in [`flows/COST-CONSUMPTION.md`](flows/COST-CONSUMPTION.md).

### Credit consumption — Power Platform Admin Center *(Studio build)*
The **per-agent Copilot Studio message credit** export now ships with the **[Fabric + Copilot Studio](extended/Fabric%20+%20Copilot%20Studio/README.md)**
build — its notebook, flows and step-by-step guide live in `3. Fabric/extended/Fabric + Copilot Studio/`
([setup guide](extended/Fabric%20+%20Copilot%20Studio/CREDIT-CONSUMPTION-SETUP.md)).

### Product feedback — Microsoft Admin Center (Health)
- **Portal:** [admin.microsoft.com](https://admin.microsoft.com) → **Health → Product feedback**
- **Role:** Global Administrator or Reports Reader
- **Filters:** Product = **Microsoft 365 Copilot** (and optionally Copilot Studio); date range matching your audit export
- **Privacy:** to see user-level data, ensure "Display concealed user names in all reports" is disabled
- **Output:** **Export data** (CSV: date, UPN, product, feedback type, rating, verbatim comment)

### Copilot Studio agent transcripts — Power Apps / Power Automate
- **Portal:** [make.powerapps.com](https://make.powerapps.com) (one-off) or [make.powerautomate.com](https://make.powerautomate.com) (recurring)
- **Role:** System Administrator, System Customizer, or Environment Maker (Dataverse read on `ConversationTranscript`)
- **One-off:** open the **ConversationTranscript** table → **Data → Export data to Excel**, save as CSV
- **Recurring:** scheduled flow → **Dataverse → List rows** (table `ConversationTranscripts`, filter `createdOn ge [yesterday]`) → **Create file** in OneDrive/SharePoint or send via email; the AIBV email-landing flow in [`flows/`](flows/) can pick it up automatically

### Loading the exports
Drop each CSV into the matching folder under your Lakehouse `Files/` area (e.g. `Files/audit/`,
`Files/cost_consumption/`, `Files/feedback/`). Then run the matching notebook from the table above —
each notebook tolerates missing inputs, so partial coverage is fine for a first pass.

</details>

## Works beyond Fabric

<details>
<summary>Portable to Databricks, Synapse, Azure SQL, or a Fabric Warehouse (click to expand)</summary>

The two core artifacts are deliberately portable:

- **The notebooks** are plain Python + PySpark - they call Graph with `requests` and write Delta with
  `df.write.saveAsTable(...)`. They run unchanged on any Spark engine (Fabric, Databricks, Synapse).
- **The template** uses the `Sql.Database()` connector, which works against any SQL endpoint exposing
  those tables - Fabric Lakehouse or Warehouse, Databricks SQL Warehouse, Synapse SQL pool, Azure SQL.

To retarget, change just two things: point the notebooks' `OUTPUT_TABLE` at your database, and set the
template's two parameters (**Fabric SQL Endpoint** = your host, **Lakehouse Name** = your database).
The template only needs the three tables - `copilot_interactions_parsed`, `copilot_licensed_users`,
`copilot_org_data` - to exist in that one database with their expected schema. Already producing parsed
CSVs upstream? The [`../1. Local CSV/`](../1.%20Local%20CSV/) and [`../2. SharePoint/`](../2.%20SharePoint/)
paths consume them with no Spark step.
</details>

## Troubleshooting

<details>
<summary>Common symptoms and fixes (click to expand)</summary>

| Symptom | Fix |
|---|---|
| `401`/`403` from Graph | Confirm the three **application** permissions are admin-consented; regenerate the client secret if expired. The audit notebook needs `AuditLogsQuery.Read.All` specifically (it calls `/security/auditLog/queries`). |
| Audit query never finishes | Purview processes it asynchronously; the notebook polls with backoff. If it times out, narrow `LOOKBACK_DAYS` in the CONFIG cell. |
| `Login failed` / `cannot open database` (Power BI) | The SQL endpoint host or database name is wrong - recheck the Lakehouse settings page. |
| `the key didn't match any rows` | A notebook ran against the wrong Lakehouse - pin your Lakehouse as default and re-run. |
| All users show "Unlicensed" | The licensed-users notebook hasn't run yet, or its report period is too narrow (`REPORT_PERIOD = 'D30'`). |
| Agent Health visuals blank (`Users shared`, `Active Users`, `Total sessions`, `Exception rate`, `Last Activity Date`) | Expected when you land the **registry / catalogue** export (`Copilot_Agent365_Registry_Ingester`, Graph `/catalog/packages`, or PAX `-IncludeAgent365Info`). That is a 28-column inventory and carries no usage telemetry — those five fields come from the Admin Center → **Agents** observability export. The query adds them as typed nulls so refresh still succeeds. See [`docs/DATA-DICTIONARY.md`](docs/DATA-DICTIONARY.md#4-agents_365). |
| Refresh slow (minutes to hours) | Almost always the audit-log transforms running inside Power Query. Make sure you've run **`Copilot_Audit_Log_Processor`** and that the fact table points at `copilot_interactions_curated` (the shaping is meant to happen upstream in Spark, not on refresh). The template also ships with **incremental refresh** pre-configured (first load is full, then only recent days) — needs a Premium/PPU/Fabric capacity; see [`docs/INCREMENTAL-REFRESH.md`](docs/INCREMENTAL-REFRESH.md). Fastest option on Fabric: convert to **Direct Lake**. |

</details>

## Reference

- **Roles & permissions (all sources):** [`docs/PERMISSIONS.md`](docs/PERMISSIONS.md)
- **Table schemas:** [`docs/DATA-DICTIONARY.md`](docs/DATA-DICTIONARY.md)
- **Incremental refresh (Import mode):** [`docs/INCREMENTAL-REFRESH.md`](docs/INCREMENTAL-REFRESH.md)
- **Optional sources in depth:** [`docs/OPTIONAL-SOURCES.md`](docs/OPTIONAL-SOURCES.md)
- **Cowork / Work IQ consumption, step by step:** [`flows/COST-CONSUMPTION-SETUP.md`](flows/COST-CONSUMPTION-SETUP.md) (start here) · [`flows/COST-CONSUMPTION.md`](flows/COST-CONSUMPTION.md) (schema + model wiring)
- **PPAC credit consumption (Studio build):** [`Fabric + Copilot Studio/CREDIT-CONSUMPTION-SETUP.md`](extended/Fabric%20+%20Copilot%20Studio/CREDIT-CONSUMPTION-SETUP.md)
- **Audit-log JSON schema:** [Microsoft Learn - CopilotInteraction](https://learn.microsoft.com/en-us/office/office-365-management-api/copilot-schema)
