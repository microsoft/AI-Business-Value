# ARCHIVED — extended Copilot Studio reference

> **ARCHIVED / reference only — not a recommended active add-on.**
> [`1. Local CSV`](../../../1.%20Local%20CSV/), [`2. SharePoint`](../../../2.%20SharePoint/) and
> [`3. Fabric`](../../) each run the **full core dashboard** on their own.
> The historical instructions below are retained for reference; use the active builds for new deployments.
> The [repository license](../../../LICENSE.md) still applies.

This formerly optional extension served tenants running **Copilot Studio agents** that wanted
deeper agent pages. It is a *superset* of the base Fabric build and historically required
[`3. Fabric`](../../) to be producing data first.

| Add-on | Status | Adds |
|---|---|---|
| **[Fabric + Copilot Studio](Fabric%20+%20Copilot%20Studio/)** | ARCHIVED / reference (formerly experimental) | Deeper **Copilot Studio agent** pages — transcript analysis (topics, resolution, containment), agent evaluation, and the Agent 365 registry detail. Includes the PPAC credit-consumption view. |

Each archived add-on includes local mirrors: the eight canonical notebooks from `3. Fabric/notebooks/` are mirrored into
the add-on's `notebooks/_core/` folder (kept byte-identical by
[`sync-shared.ps1`](../../../scripts/sync-shared.ps1), with CI enforcement).
The downstream [`Copilot_Audit_Log_Processor.ipynb`](../../notebooks/Copilot_Audit_Log_Processor.ipynb)
is not mirrored; it remains part of the base Fabric build.

> The historical add-on setup reuses the same Lakehouse parameters as the base
> [`3. Fabric`](../../) build.

## Maintaining the mirrored core notebooks

The `Fabric + Copilot Studio/notebooks/_core/` and `_shared/notebooks/` folders under
`3. Fabric/archive/extended/` remain **synchronized, not frozen**. They are **copies** of the eight
canonical notebooks (seven ingesters/landers plus `ValueLens_Data_Check.ipynb`) in
[`3. Fabric/notebooks/`](../../notebooks/). Do not edit them directly — edit the source,
then run [`sync-shared.ps1`](../../../scripts/sync-shared.ps1) from the repository root. See
[`_shared/README.md`](_shared/README.md) for the full rationale.
