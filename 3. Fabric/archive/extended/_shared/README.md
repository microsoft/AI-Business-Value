# ARCHIVED — _shared core Fabric notebook mirrors

> **ARCHIVED / reference only — not a recommended active add-on.** The core notebooks
> remain active in [`3. Fabric/notebooks/`](../../../notebooks/); these mirrors are **not frozen**.

These are **byte-identical copies** of the eight canonical notebooks (seven ingesters/landers
plus `ValueLens_Data_Check.ipynb`) shipped under
[`3. Fabric/notebooks/`](../../../notebooks/). The historical mirror layout under
`3. Fabric/archive/extended/` keeps core notebook copies alongside the archived add-on.

## Files

| Notebook | Purpose |
|---|---|
| `Copilot_Audit_Log_Direct_Ingester.ipynb` | Purview-style Copilot chat + agent interaction audit logs → `dbo.audit_logs` |
| `Copilot_Licensed_Users_Direct_Ingester.ipynb` | Microsoft 365 Copilot licence assignments → `dbo.licensed_users` |
| `Copilot_Org_Data_Direct_Ingester.ipynb` | Entra user + manager hierarchy → `dbo.org_data` |
| `Copilot_ProductFeedback_Ingester.ipynb` | OCV product feedback exports → `dbo.product_feedback` |
| `Copilot_Cost_Consumption_Ingester.ipynb` | Monthly Copilot cost/consumption → `dbo.cost_consumption` |
| `Copilot_Agent365_Registry_Ingester.ipynb` | Agent 365 registry via Graph (app-only, GA) → `dbo.agents_365` |
| `Copilot_Agent365_Lander.ipynb` | Optional Agent 365 CSV lander → `dbo.agents_365` |
| `ValueLens_Data_Check.ipynb` | Data validation checks for the Fabric Lakehouse |

## Do not edit here

The **source of truth is `3. Fabric/notebooks/`**. Edit there, then run:

```powershell
.\scripts\sync-shared.ps1
```

from the repo root. [`scripts/sync-shared.ps1`](../../../../scripts/sync-shared.ps1)
continues to synchronize all eight notebooks into both
`3. Fabric/archive/extended/_shared/notebooks/` and
`3. Fabric/archive/extended/Fabric + Copilot Studio/notebooks/_core/`.
CI runs the same script in check mode on every push and fails the build if drift is detected.
The downstream [`Copilot_Audit_Log_Processor.ipynb`](../../../notebooks/Copilot_Audit_Log_Processor.ipynb)
is deliberately not mirrored; it remains in the active base Fabric build.
