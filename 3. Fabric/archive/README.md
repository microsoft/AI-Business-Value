# ARCHIVED — Fabric reference assets

Older versions and moved add-ons/flows are kept as **archived reference, not recommended active
deployment paths**. **You don't need anything in here for a new deployment** —
use the current files in [`../`](../). The [repository license](../../LICENSE.md) still applies.

| File | What it is | Why it's archived |
|---|---|---|
| `ValueLens - Fabric (Power Query, pre-2307).pbit` | The previous template. It did all the audit-log JSON parsing, list-explode and joins **inside Power Query**, on every refresh. | Replaced by the **2307 (Spark)** build. That heavy shaping now runs once in the `Copilot_Audit_Log_Processor` notebook, so the current `../ValueLens - Fabric.pbit` reads a ready-made table and refreshes in seconds instead of hours. See [`../README.md`](../README.md). |

The output columns, measures and report pages are identical between the two — only *where the
transformation runs* changed (Power Query → Spark).

## Moved reference content

| Folder | Archived contents |
|---|---|
| [`extended/`](extended/README.md) | Copilot Studio extension, credit-consumption landing flows, notebooks and samples. Historical setup only; not a recommended active add-on. |
| [`flows/`](flows/COST-CONSUMPTION.md) | Cost-consumption email and SharePoint landing flows, plus their [setup guide](flows/COST-CONSUMPTION-SETUP.md) and schema reference. Not recommended for new deployments. |

The [core notebooks](../notebooks/) and [ProductFeedback flow](../flows/Copilot_ProductFeedback_Email_to_OneLake.json)
remain active. The archived extension's `_shared/notebooks/` and `notebooks/_core/` mirrors remain
**synchronized, not frozen**: edit the canonical notebooks, then run
[`scripts/sync-shared.ps1`](../../scripts/sync-shared.ps1) from the repository root.
See the [mirror maintenance contract](extended/_shared/README.md).
