# Incremental refresh (Import mode)

The `ValueLens - Fabric.pbit` template ships with **incremental refresh already configured** on the
audit-interactions fact table, so you don't have to set it up. This note explains what it does, what it
needs, and how to change it.

Both core PBITs ship in **Import** mode, not Direct Lake. The policy below describes the Fabric
template; notebook ingestion and semantic-model refresh are separate operations.

## What's pre-configured

The fact table **`Chat + Agent Interactions (Audit Logs)`** (sourced from `copilot_interactions_curated`)
carries an Import-mode incremental-refresh policy:

| Setting | Value | Effect |
|---|---|---|
| Archive / rolling window | **12 months** | Only the last 12 months are kept; older rows drop off automatically. |
| Incremental window | **last ~7 days** | Only the most recent days are re-queried on each refresh. |
| Change detection | Rolling window (no polling) | Recent days are re-imported wholesale; older partitions are stored and never re-queried. |

Two auto-managed parameters, **`RangeStart`** and **`RangeEnd`** (DateTime), drive the partition filter
`CreationDate >= RangeStart and CreationDate < RangeEnd`. **Leave them alone** - Power BI sets them per
partition at refresh time. Don't delete, rename, or hard-code them.

## What to expect

- **The first refresh is a full load** of the whole 12-month window - expect it to take a while (tens of
  minutes on a large tenant). This is normal and happens once.
- **Every refresh after that re-imports the last ~7 days of the fact table**, so it's much faster and stays
  roughly constant no matter how much history has accumulated.
- The ~7-day incremental window overlaps your daily audit pull, so a missed or late run self-heals on the
  next refresh.

## Refresh orchestration

The shipped pipeline JSON has **no semantic-model refresh activity**. You can add a native Fabric
**Semantic model refresh** activity with **on-success** dependencies after
`Copilot_Audit_Log_Processor` **and all other enabled model-source branches**. Waiting for the
processor alone is insufficient if another enabled branch is still writing a table the model reads.

Alternatively, set a **later, separate Power BI Service refresh schedule**. This is
**not success-gated** on the pipeline: it can run even if ingestion failed or is still running.

## Requirements

- **Power BI Pro, Premium, Premium-Per-User (PPU), or Fabric capacity.** Import incremental refresh
  is supported on Pro; XMLA read-write partition bootstrapping needs a supported capacity / PPU
  workspace with XMLA read-write enabled.
- **Import storage mode** (the template's default). See *Import + incremental vs Direct Lake* below.
- Valid **data-source credentials** on the dataset (**Settings -> Data source credentials**). If they're
  missing you'll see *"Scheduled refresh is disabled because at least one data source does not have
  credentials"* - sign in to the SQL endpoint, then re-enable scheduled refresh.

## Changing the window

Do this in Power BI Desktop **before** you publish (or re-publish after changing):

1. In **Report** / **Model** view, right-click the **`Chat + Agent Interactions (Audit Logs)`** table ->
   **Incremental refresh**.
2. Adjust **"Archive data starting ... before refresh date"** (the rolling window - e.g. 6, 12, or 24
   months) and **"Incrementally refresh data starting ... before refresh date"** (the re-queried window -
   e.g. 3, 7, or 10 days).
3. **Apply**, then **Publish**. The next refresh in the Service re-partitions to match.

> A shorter rolling window (e.g. 6 months) = a smaller model and a faster first load. A longer incremental
> window = more self-healing overlap but slightly slower refreshes. **12 months / 7 days** is a sensible
> default for most tenants; 6-12 months of look-back covers the majority of adoption reporting.

## Import + incremental vs Direct Lake

Import is the shipped path; Direct Lake is an optional, separately built model:

| | Import + incremental refresh (default) | Direct Lake |
|---|---|---|
| Where it runs | Any SQL endpoint (Fabric, Databricks, Synapse, Azure SQL) | **Fabric only** - reads Delta straight from OneLake |
| Data movement | Imports recent partitions during model refresh | No import - reads Delta; refresh/reframing updates the model's view of the data |
| Best when | Non-Fabric backends, or you want a self-contained dataset | Model + Lakehouse are on the **same Fabric capacity** |
| Setup | Already configured here | Recreate the model as Direct Lake over the Lakehouse |

Keep the shipped **Import + incremental refresh** path unless you deliberately rebuild and validate
a Direct Lake model on supported Fabric capacity. Publishing a PBIT to Fabric does not convert it
to Direct Lake or remove its model-refresh requirement.

## Notes

- Incremental refresh applies to the **audit-interactions** fact table (the large, continuously growing
  feed). The current-state snapshot tables (org data, licensed users, credit, Agents 365) are small and
  refresh in full each run - they don't need a policy.
- This is the **Power BI dataset** incremental refresh. It's separate from the **notebook** high-water-mark
  ingest (`MODE=incremental` in the audit ingester), which controls how much data lands in the Lakehouse.
  The two complement each other: the notebook keeps the Lakehouse current, and incremental refresh keeps
  the dataset refresh cheap. See [`INGESTION-STRATEGY.md`](INGESTION-STRATEGY.md).
