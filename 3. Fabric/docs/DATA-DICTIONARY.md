# Data Dictionary & Source Contract

This is the **single source of truth** for the tables the dashboard consumes. Both deployment
versions read the *same* logical tables with the *same* column names — only the **source layer**
differs:

| Version | Source layer | Each table loads via |
| --- | --- | --- |
| **Fabric** | OneLake Lakehouse (Delta) | `FabricTable("<delta_table>")` via either the SQL analytics endpoint or the OneLake Tables endpoint |
| **SharePoint** | CSV files in SharePoint/OneDrive | `SharePointCsv("<file>")` / `Web.Contents(...)` |

Because the schema is identical, the report, every measure, and all downstream M is shared. A
producer (notebook or script) is "compatible" **iff** the Delta table / CSV it writes exposes the
exact column names below (casing and spaces matter).

> **Base (No-Studio) build.** This build reads three **core** sources plus a few standard **optional**
> sources. Copilot Studio agent-transcript analytics (the `agent_*` Dataverse tables) and the PPAC
> per-agent / per-user message-credit tables are **not** part of this build — they live in the separate
> [Fabric + Copilot Studio](../extended/Fabric%20+%20Copilot%20Studio/) template.

---

## Tier model — core vs optional

Optional sources must **degrade to an empty table with the correct columns** when absent, so the
template never breaks. See `OPTIONAL-SOURCES.md` for the `EmptyTable` + `try…otherwise` +
`Enable_*` toggle pattern.

| # | Dashboard table | Lakehouse Delta name | Tier | Fabric producer | SharePoint producer |
| --- | --- | --- | --- | --- | --- |
| 1 | Chat + Agent Interactions (Audit Logs) | `copilot_interactions_curated` | **Core** | `Copilot_Audit_Log_Direct_Ingester` → `Copilot_Audit_Log_Processor` | `GetCopilotInteractions*` |
| 2 | Copilot Licensed | `copilot_licensed_users` | **Core** | `Copilot_Licensed_Users_Direct_Ingester` | `GetCopilotUsers*` |
| 3 | Chat + Agent Org Data | `copilot_org_data` | **Core** | `Copilot_Org_Data_Direct_Ingester` | `Get-EntraOrgData*` |
| 4 | Agents 365 | `agents_365` | *Optional* | `Copilot_Agent365_Registry_Ingester` *(default)* · `Copilot_Agent365_Lander` *(CSV fallback)* | `Get-Agents365Registry` |
| 5 | ProductFeedback | `user_feedback` | *Optional* | `Copilot_ProductFeedback_Ingester` | OCV feedback CSV |
| 6 | Copilot Cost Consumption | `copilot_cost_consumption` | *Optional* | `Copilot_Cost_Consumption_Ingester` | SharePoint CSV (`Cost Consumption File`) |

> **Delta table names are lower-case** throughout (`copilot_interactions_parsed`,
> `copilot_interactions_curated`, …). The dashboard table names in column 2 are the *model* names and
> may contain spaces.

> **Cost consumption (row 6)** is the **Microsoft 365 Admin Center → Copilot → Cost management** export
> (Cowork / Work IQ credits). It's standard across all templates. The **PPAC** message-credit tables
> (per-agent / per-user) are a Studio add-on — see the Extended build.

All other model tables (Calendar, legends, ranking/summary, glossary, value maps, etc.) are
**calculated/DAX or static** — they have no external source and are version-independent.

---

## Core tables

### 1. `copilot_interactions_parsed` — audit interactions (ingester output)
Producer flattens Purview/Graph `CopilotInteraction` audit JSON **upstream** (the report M is a thin
pass-through guarded by `Table.HasColumns`, so missing optional columns are tolerated).

```
CreationDate, AgentId, AgentName,
AppIdentity_AppId, AppIdentity_DisplayName, AppIdentity_PublisherId,
ApplicationName, ClientRegion,
Audit_UserId, Audit_UserId_Normalized, Workload,
AppHost, ThreadId, SensitivityLabelId, Context_Type,
AISystemPlugin_Id, AISystemPlugin_Name, ModelTransparencyDetails_ModelName,
AccessedResource_Type, AccessedResource_Action, AccessedResource_SiteUrl, AccessedResource_SensitivityLabelId,
Message_Id, Message_isPrompt, Resource_Count,
InteractionDate, WeekStart, MonthStart,
Agent_TitleID, Agent_EntraId
```

> **Agent identifiers (two keys, used together).** `Agent_TitleID` is parsed from the legacy
> `CopilotStudio.Declarative.{title}` / `T_`/`P_` forms. `Agent_EntraId` captures the **Microsoft
> Entra Agent ID** GUID that **Agent 365** now stamps into the audit `AgentId` instead of the
> declarative string. When agents are registered/recreated under Entra Agent ID, `Agent_TitleID`
> would otherwise land NULL and drop out of the Agents join — `Agent_EntraId` keeps them resolvable
> via the registry crosswalk. The two are populated mutually exclusively per row (legacy → TitleID,
> Entra → EntraId), so old and new agents both join cleanly during a mixed migration.

### 1b. `copilot_interactions_curated` — the table the Fabric model actually reads
`Copilot_Audit_Log_Processor` reads `copilot_interactions_parsed` (joining `copilot_licensed_users`
and `agents_365`) and writes **`copilot_interactions_curated`**. This — not the `_parsed` table — is
what the Fabric template's `Chat + Agent Interactions (Audit Logs)` partition binds to. It is the
same shape the template's Power Query used to produce, but computed once in Spark and V-Ordered on
disk so the shipped Import templates can read a flat fact table quickly.

**Schema = every column of `copilot_interactions_parsed`, plus these 26 enrichment columns:**

```
Environment, License Status, Is_Sensitive, AI_Model,
Behavior_Category, Behavior_Enriched, Behavior_Enriched_Full, Behavior_Source,
Value_Outcome, Usage_Mode, Expertise_Role, Efficiency_Breakdown,
Web_Grounded_Signal, Behavior_Plausible, Workflow_Action,
Is_Agent_Activity, Agent Filter, Grounding Source, Agent_Surface, Execution_Trigger,
UserMonthKey, Delegation_Event_Key, ActivityDate, Agent Last Used Date,
User_Stage_Maturity, User_Stage
```

> **`Behavior_Category` is the join key for the value model.** It relates to the static
> `Human Time Estimates` table inside the `.pbit`, which holds the per-behaviour
> `Human Baseline (min)` figures. `Estimated Hours Saved` resolves those at query time via
> `RELATED` — the baselines are **not** materialised into this Delta table.
>
> Use `WRITE_MODE = "overwrite"` for the first backfill, then `"merge"` for daily runs. The notebook
> asserts all 26 columns are present before writing, so a partial enrichment fails loudly rather than
> silently shipping an incomplete fact table.

### 2. `copilot_licensed_users` — licensed user list
The producer sanitizes spaces→underscores, writing `User_Principal_Name` and `Has_license`; the
model's variant lists accept both those and the spaced/camel forms (see finding **B** below — resolved).
Key columns:

```
User_Principal_Name  (canonical join key; also accepts: User Principal Name / userPrincipalName / UserPrincipalName)
Has_license          (Yes/No flag; also accepts: Has license / HasLicense / HasCopilot / …)
UPN_Normalized       (lower(trim(UPN)) — dedupe + join key)
… plus all Office365ActiveUserDetail columns (sanitized)
```

### 3. `copilot_org_data` — Entra org / people data
Dashboard normalizes dynamically (UPN/PersonId variants, `Department`→`Organization`) and adds
`PersonId_Normalized` + `TotalEmployees` if missing.

```
id, PersonId, displayName, Organization, JobTitle, companyName,
officeLocation, city, country, accountEnabled, managerUPN
```

**Join key:** `PersonId` = **userPrincipalName (UPN)** — used by the **Audit Logs** path
(`Audit_UserId → PersonId`). `id` (AAD object id) is also emitted for downstream joins.

---

## Optional tables

### 4. `agents_365`
Landed into the Lakehouse by **`Copilot_Agent365_Registry_Ingester`** (the default — Graph app-only,
runs unattended) or by `Copilot_Agent365_Lander` (CSV fallback → `dbo.agents_365`; Delta
column-mapping preserves spaced header names like `Agent name`). **Pick one, never run both** — they
write the same table. Read via `FabricTable("agents_365")`, wrapped with `Enable_Agent365`. The Fabric
model is now **100% Lakehouse-sourced**. Columns from the Agents MAC export.

#### ⚠️ Two different Agent 365 exports — registry vs observability

Microsoft exposes Agent 365 data as **two separate exports**, and they do **not** carry the same
columns. Which one you land decides how much of the **🛡 Agent Health** page populates:

| Export | Source | Carries |
|---|---|---|
| **Registry / catalogue** | Graph `/beta/copilot/admin/catalog/packages` — used by `Copilot_Agent365_Registry_Ingester` and by PAX `-IncludeAgent365Info` | A **28-column inventory**: agent name, Title ID, publisher/developer, version, availability, sensitivity, capability and permission flags, created/last-updated metadata |
| **Observability** | Microsoft Admin Center → **Agents** export ([agent map docs](https://learn.microsoft.com/en-us/microsoft-365/admin/manage/agent-map)) | Usage telemetry: `Users shared`, `Active Users`, `Total sessions`, `Exception rate`, `Last Activity Date` |

The **registry export does not emit the observability columns.** If you land only the registry /
PAX output — the documented default — those five fields are unavailable.

**The model tolerates this.** The Agents 365 query ends with a *stable superset guard* that adds any
model-declared column the chosen source did not supply as a **typed null**, so:

- the table always returns the same column set regardless of which export you land,
- refresh never fails with a missing-column error, and
- visuals bound to an unavailable field render **blank** rather than breaking the page.

To populate the observability visuals, land the **Admin Center Agents export** instead of (or merged
with) the registry export. `Agent Activity Status` falls back to audit-log-derived activity when
`Last Activity Date` is absent, so agent recency still works on the registry-only path.

> Adding a column to the Agents 365 model? Add it to the guard's `__expected` list in the query too,
> or it will be unstable on any source that doesn't emit it.

#### Agent identity resolution (3-key bridge: Entra → Title ID → Name)

The interactions fact joins the Agents dimension through a **resolved key** (`Agent_LinkID`) rather
than the raw `Agent_TitleID`. This is necessary because the **audit log and the MAC Agents export use
different identifier namespaces** — the audit `AgentId` is an `SPO_…` blob, a built-in name
(`WordDraftingAgent`), or an **Entra Agent ID GUID** (Agent 365), while the export keys on `T_…`
Title IDs. On real tenant data the raw `Agent_TitleID → Title ID` join matches **0%**; resolving the
shared **display name** lifts that to ~**84% of distinct agents** (the unmatched remainder are mostly
Microsoft first-party agents that legitimately have no registry row).

Resolution is done in Power Query (no DAX circular-dependency risk; mirrors the existing license merge),
as a **priority chain** that always lands on a real registry `Title ID` or null:

1. **Entra Agent ID** — `Agent_EntraId → agents_365[Entra Agent ID]` (future Agent 365 agents).
2. **Direct Title ID** — `Agent_TitleID` only when it already *is* a registry Title ID.
3. **Normalised name** — `lower(trim(AgentName)) → agents_365[Agent name]` (the high-yield fallback).

`Agent_LinkID = COALESCE(EntraTitle, DirectTitle, NameTitle)`. All three lookup maps are deduped and
null-guarded, so the 1.2M-row fact never fans out. The relationship is
**`Chat + Agent Interactions[Agent_LinkID] → agents_365[Title ID]`** (replaces the old `Agent_TitleID`
relationship; cross-filter direction unchanged).

**Zero-touch identity detection.** `agents_365` is given an add-if-missing **`Entra Agent ID`** column
that **auto-detects** the GUID from whatever the export provides — it picks the first present of
`Entra Agent ID → EntraAgentId → Agent ID → Bot Id` (and common variants). The customer never has to
create or populate a column by hand; a non-matching GUID simply does not join (no false links). Until
an export carries Entra GUIDs, custom agents still resolve by name.

### 5. `user_feedback` — Product Feedback (OCV export)
An OCV/Viva feedback **CSV** dropped at `Files/product_feedback/`, parsed by
`Copilot_ProductFeedback_Ingester.ipynb`. The dashboard's `ProductFeedback` table renames the OCV
space-named columns. The empty placeholder emits the **full superset** so a missing/partial export
cannot break refresh, and the notebook now rejects `WRITE_MODE='append'` for this snapshot source:

```
Feedback Id, Comment, Translated Comment, Comment Language,
Date Submitted UTC, Feedback Type, Microsoft Response Status,
App, App Language, Platform, Source Type, Logs, Attachments,
User Id, User Email, Browser, Browser Version,
AI Context Prompt, AI Context Response Message,
Survey Question, Survey Response Option, Additional Metadata,
Date Submitted Date, Sentiment
```
*(The model should also keep `MissingField.Ignore` on `Table.RenameColumns` so partial OCV exports remain tolerant.)*

### 6. `copilot_cost_consumption` — Copilot credit usage (MAC Cost management export)
Produced by `Copilot_Cost_Consumption_Ingester` from the **Microsoft 365 Admin Center → Copilot →
Cost management** per-user CSV export (export-only; no API). **Auto-detects two export shapes** and maps
both to one unified contract: the **surface split** (`Cowork`/`WorkIQ`/`Other` credits) and the
**per-user usage** export (monthly limit / used / % used / sessions). This is the **only**
customer-pullable place Cowork/WorkIQ credits appear. Gated by `Enable_CostConsumption`; both Fabric and
SharePoint paths produce the identical contract. Header matching is **case-insensitive**.

```
User_Principal_Name   (text; join key → org PersonId_Normalized / UPN)
Display_Name          (text; usage export)
Cowork_Credits        (double; surface export; blank for usage)
WorkIQ_Credits        (double; surface export; blank for usage)
Other_Credits         (double; surface export; blank for usage)
Total_Credits         (double; = Cowork+WorkIQ+Other, or Monthly credits used)
Monthly_Credit_Limit  (double; usage export — per-user budget)
Pct_Used              (double 0–1 fraction; usage export)
Session_Count         (int64; usage export)
M365_Copilot_Licensed (text; usage export)
Last_Activity_Date    (date; parses ISO timestamp + en-US M/d/yyyy)
SourceFile, LoadDate  (lineage)
```
Columns absent from a given export load as null. Grain is a **per-user snapshot**. UPN match isn't 100% —
unmatched users surface under an **"(Unattributed)"** organization bucket. See
`../flows/COST-CONSUMPTION.md`.

---

## Known compatibility findings (historical — all resolved)

Kept for traceability. None of these are open; if you hit one of these symptoms, you are on an old
template or an old notebook.

| ID | Table | Finding | Fix |
| --- | --- | --- | --- |
| A | `user_feedback` | Empty placeholder had 6 cols; `Table.RenameColumns` expects 17 → refresh broke when no feedback.csv | **Fixed** in notebook (full superset). Also add `MissingField.Ignore` in model. |
| B | `copilot_licensed_users` | Producer writes underscore names; model variant lists only have spaced/camel forms → UPN + licence load null | **Fixed** — underscore variants added to model |
| C | `agents_365` | Fabric model read a SharePoint URL | **Fixed** — `Copilot_Agent365_Lander` lands `dbo.agents_365`; table now `FabricTable` + `Enable_Agent365` |
| D | Audit/Licensed/Org core M | Staged from an older snapshot assuming RAW audit JSON (unconditional adds + `Json.Document`) → "field already exists" on pre-flattened producer output | **Fixed** — re-based on the fixed versions (17 `HasColumns` guards, conditional parse) |
