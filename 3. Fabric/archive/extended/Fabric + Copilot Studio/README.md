# ARCHIVED — Fabric + Copilot Studio

> **ARCHIVED / reference only — not a recommended active add-on.** Historical setup instructions
> are retained below. Start new deployments with the active [`3. Fabric`](../../../README.md) build.

*(Formerly "Studio Agent Deepdive".)* A **formerly optional extension** of the standard Fabric dashboard for
tenants running **Copilot Studio agents**. The base
[`3. Fabric/ValueLens - Fabric.pbit`](../../../ValueLens%20-%20Fabric.pbit)
is the recommended starting point; this archived layer provided a deeper view of
**agent transcripts** and the **Agent 365 registry**.

**This folder includes local core notebook mirrors.** The downstream
[`Copilot_Audit_Log_Processor.ipynb`](../../../notebooks/Copilot_Audit_Log_Processor.ipynb) is not
mirrored and remains a dependency from the active base Fabric build.

## What's here

```
Fabric + Copilot Studio/
├── ValueLens - Fabric (+ Studio Agent Deepdive).pbit   ← the report
├── notebooks/
│   ├── _core/                                          ← core ingesters (mirrored from 3. Fabric — do not edit here)
│   │   ├── Copilot_Audit_Log_Direct_Ingester.ipynb
│   │   ├── Copilot_Licensed_Users_Direct_Ingester.ipynb
│   │   ├── Copilot_Org_Data_Direct_Ingester.ipynb
│   │   ├── Copilot_ProductFeedback_Ingester.ipynb
│   │   ├── Copilot_Cost_Consumption_Ingester.ipynb
│   │   ├── Copilot_Agent365_Registry_Ingester.ipynb
│   │   ├── Copilot_Agent365_Lander.ipynb
│   │   └── ValueLens_Data_Check.ipynb
│   ├── Copilot_Agent_Transcript_Parser.ipynb           ← Copilot Studio-specific
│   └── Copilot_Credit_Consumption_Ingester.ipynb       ← Copilot Studio-specific (PPAC billing)
├── flows/                                              ← Power Automate flows for PPAC credit landing
└── CREDIT-CONSUMPTION-SETUP.md
```

| Notebook | Purpose |
|---|---|
| **`_core/*`** | Eight canonical notebooks: seven M365 Copilot ingesters/landers plus `ValueLens_Data_Check.ipynb`. Byte-identical to those in `3. Fabric/notebooks/` (kept in sync by [`scripts/sync-shared.ps1`](../../../../scripts/sync-shared.ps1), not frozen). |
| `Copilot_Agent_Transcript_Parser.ipynb` | Parses **Copilot Studio agent transcripts** (Dataverse `ConversationTranscript`) into a Lakehouse Delta table for the agent pages. |
| `Copilot_Credit_Consumption_Ingester.ipynb` | Ingests the **Power Platform Admin Center (PPAC) per-agent Copilot Studio message credit** export into the `credit_consumption_*` Lakehouse tables (gated by `Enable_Consumption`). |
| `flows/` | Power Automate flows that auto-land the PPAC credit export into OneLake (email or SharePoint trigger). See [`flows/README.md`](flows/README.md). |
| `CREDIT-CONSUMPTION-SETUP.md` | Step-by-step guide for the PPAC credit export, the landing flows and the ingester. |

## Historical use case

Use the **base** template if you only need Microsoft 365 Copilot value (audit logs, licensing, org
data, feedback, Agent 365 export). This deepdive was intended for tenants also running **Copilot Studio
agents** that wanted:

- agent-level transcript analysis (topics, resolution, containment),
- the richer Agent 365 capability/permission detail, and
- per-agent **Copilot Studio message credit** consumption (PPAC billing).

## Historical setup (reference only)

1. Provision your **Fabric Lakehouse** and Entra app registration — see
   [`3. Fabric/README.md`](../../../README.md) for the parameters, RBAC roles, and Graph
   permissions the core ingesters need. (You only need to *read* that guide; you'll run the notebooks
   from this folder.)
2. Run the notebooks in **`notebooks/_core/`** in order — audit logs → licensed users → org data →
   product feedback → cost consumption → **Agent 365 registry**. For Agent 365 use
   **`Copilot_Agent365_Registry_Ingester.ipynb`** by default (Graph API app-only). Fall back to
   `Copilot_Agent365_Lander.ipynb` (CSV drop) only if you can't grant the Ingester's app-reg
   permissions. Both target the same `dbo.agents_365` table — pick one, don't run both.
3. Run **`notebooks/Copilot_Agent_Transcript_Parser.ipynb`** to land the Copilot Studio transcript
   tables. Needs Dataverse read on `ConversationTranscript`.
4. *(Optional)* Light up **agent credit consumption** — follow
   [`CREDIT-CONSUMPTION-SETUP.md`](CREDIT-CONSUMPTION-SETUP.md) to land the PPAC export (via the
   [`flows/`](flows/README.md) or manually) and run **`notebooks/Copilot_Credit_Consumption_Ingester.ipynb`**.
5. Open **`ValueLens - Fabric (+ Studio Agent Deepdive).pbit`** in Power BI Desktop, supply the same
   Lakehouse parameters as the base template, and set `Enable_Dataverse = Include` to light up the
   agent pages. Set `Enable_Consumption = Include` if you ran step 4.

## Editing the core notebooks

The `_core/` copies are **mirrors** — do not edit them directly. Edit the source in
[`3. Fabric/notebooks/`](../../../notebooks/), then run:

```powershell
.\scripts\sync-shared.ps1
```

from the repo root. All eight canonical notebooks continue to sync into
`3. Fabric/archive/extended/_shared/notebooks/` and
`3. Fabric/archive/extended/Fabric + Copilot Studio/notebooks/_core/` — archiving does **not**
freeze these mirrors. CI enforces zero drift on every push.

> This add-on is a superset of the base template — it reads the same core tables plus the agent
> tables, so it works only once the core ingesters are producing data.
