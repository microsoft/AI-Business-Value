# ARCHIVED — Copilot Cost Consumption reference

> **ARCHIVED / reference only — these landing flows are not recommended for new deployments.**
> Historical Cowork / WorkIQ / Other credit instructions and model wiring are retained below.
> The [core Cost Consumption ingester](../../notebooks/Copilot_Cost_Consumption_Ingester.ipynb),
> [ProductFeedback flow](../../flows/Copilot_ProductFeedback_Email_to_OneLake.json), and
> [base Fabric build](../../README.md) remain active. The [repository license](../../../LICENSE.md) applies.

> **New to this source?** Start with the **[setup guide](COST-CONSUMPTION-SETUP.md)** — it walks
> through getting the CSV out of the Microsoft 365 Admin Center, dropping it in the Lakehouse, and
> running the ingester. This file is the **schema + model-wiring reference**; use it after you have
> the export landing.

This source brings in the **per-user Cowork / WorkIQ / Other credit split** that the Power Platform
message-consumption exports (`credit_consumption_*`) do **not** contain. It is **additive** to those
billing tables — the two answer different questions (per-agent Copilot Studio *message* credits vs
per-user *surface* credits).

```
                       ┌─ Email arrives with CSV ─┐
M365 Admin Center ─────┤                          ├─▶ OneLake  Files/cost_consumption/*.csv ─▶ Cost Consumption Ingester ─▶ Delta
 (Cost management)     └─ Dropped to SharePoint ──┘
```

## Where to get the export

**Microsoft 365 Admin Center → Copilot → Cost management.** It is **export-only — there is no API**.
The ingester **auto-detects two export shapes** (case-insensitive headers) and maps both to one contract:

- **Surface split** — `User Principal Name`, `Cowork Credits`, `WorkIQ Credits`, `Other Credits`,
  `Last Activity Date` (the Cowork/WorkIQ/Other view).
- **Per-user usage** — `Display Name`, `User Principal Name`, `Monthly credit limit`,
  `Monthly credits used`, `% Used`, `Session Count`, `Microsoft 365 Copilot license`,
  `Last activity date` (budget / utilization view).

## The two landing flows

| File | When to use |
| --- | --- |
| `Copilot_CostConsumption_Email_to_OneLake.json` | The export arrives by **email** (mailed, or a scheduled export is mailed). Subject filter default `Copilot Cost Management`. |
| `Copilot_CostConsumption_SharePoint_to_OneLake.json` | The customer prefers a **governed SharePoint document library** drop folder. |

Both write to OneLake with the **DFS (ADLS Gen2) three-step pattern** (`PUT ?resource=file` →
`PATCH ?action=append` → `PATCH ?action=flush`), audience `https://storage.azure.com/`, landing in
**`Files/cost_consumption/`** (must match `SOURCE_DIR` in `../../notebooks/Copilot_Cost_Consumption_Ingester.ipynb`).
The MAC export filename is not fixed, so the `FileNamePrefix` guard defaults to empty (accept any
`.csv`); set it once you know the real prefix to be stricter. Import & OneLake-permission steps are
identical to the credit-consumption flows — see the
[archived credit-consumption flow README](../extended/Fabric%20+%20Copilot%20Studio/flows/README.md).

## Unified column contract (both shapes → one table)

Source header → canonical name (case-insensitive match):

| Canonical name | Type | From surface export | From usage export |
|---|---|---|---|
| `User_Principal_Name` | text | `User Principal Name` | `User Principal Name` (**join key**) |
| `Display_Name` | text | — | `Display Name` |
| `Cowork_Credits` | double | `Cowork Credits` | — |
| `WorkIQ_Credits` | double | `WorkIQ Credits` | — |
| `Other_Credits` | double | `Other Credits` | — |
| `Total_Credits` | double | sum of the three | `Monthly credits used` |
| `Monthly_Credit_Limit` | double | — | `Monthly credit limit` |
| `Pct_Used` | double (0–1) | — | `% Used` (÷100) |
| `Session_Count` | int | — | `Session Count` |
| `M365_Copilot_Licensed` | text | — | `Microsoft 365 Copilot license` |
| `Last_Activity_Date` | date | `Last Activity Date` | `Last activity date` |

Columns absent from a given export load as **null** (so every measure stays valid). `SourceFile` and
`LoadDate` lineage are added. The model binds **by name** — these names must match exactly.

## Model wiring

- **Toggle:** `Enable_CostConsumption` (list parameter `"Include"` / `"Exclude"`, default `"Include"`).
- **Table:** `copilot_cost_consumption`, wrapped in the standard `EmptyTable` + `try…otherwise` pattern
  (Fabric reads the Delta table via `FabricTable`; SharePoint reads the `Cost Consumption File` CSV and
  does the light typing + `Total_Credits` in M).
- **Relationships:** `User_Principal_Name` → `Chat + Agent Org Data[PersonId]` (department / chargeback
  attribution for free); `Last_Activity_Date` → `Calendar[Date]`.
- **Grain:** per-user **snapshot** — `Last_Activity_Date` is "last activity", not a daily credit series.
  Treat like the existing credit tables (snapshot cards + billing-period label), not a daily trend.

## Not all customers will send this

That's expected. If `Files/cost_consumption/` is empty (or the toggle is `"Exclude"`), the ingester
writes an **empty, correctly-named** table and the Cost Consumption visuals stay dormant — the rest of
the dashboard is unaffected.

> The optional-source toggles are **list parameters** with the values `"Include"` / `"Exclude"`
> (not `true`/`false`). Set `Enable_CostConsumption` to `"Include"` once the data is landing.

## UPN attribution caveat

The UPN match against org data isn't guaranteed 100%. Users in the cost export with no matching org
row won't attribute to a department — surface them under an **"(Unattributed)"** bucket and show the
match rate, so a gap is visible rather than silently dropped.
