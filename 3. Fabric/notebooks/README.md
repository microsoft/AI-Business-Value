# Fabric Notebooks - template

Each notebook writes one Delta table the semantic model reads via the `FabricTable(...)`
helper. They sit **flat** in this folder — import the ones for the sources you have.
The model gates every partition behind an `Enable_*` parameter, so the template opens
cleanly even before you've run the optional ingesters.

Tiers below match what the base (*No Studio*) dashboard actually needs:

- **Required** — the dashboard's backbone. Run the three ingesters, then the audit-log processor.
- **Recommended** — Agent 365 governance. Run the registry ingester if you can.
- **Optional** — product feedback, and Cowork / Work IQ credit consumption (Admin Center exports).

## Required — run these

**Step 1 — ingesters.** Each pulls from Graph and writes one Delta table:

| Notebook | Output table | Feeds |
|---|---|---|
| `Copilot_Audit_Log_Direct_Ingester` | `copilot_interactions_parsed` | Chat + Agent interactions (Purview usage backbone) |
| `Copilot_Licensed_Users_Direct_Ingester` | `copilot_licensed_users` | Licence readiness |
| `Copilot_Org_Data_Direct_Ingester` | `copilot_org_data` | Org / department dimension |

**Step 2 — process the audit-log fact table.** Run **`Copilot_Audit_Log_Processor`** **after** the Step 1 ingesters, immediately before the model refresh:

| Notebook | Reads | Output table |
|---|---|---|
| `Copilot_Audit_Log_Processor` | `copilot_interactions_parsed` (+ `copilot_licensed_users`, `agents_365`) | `copilot_interactions_curated` |

> **This is a transform, not an ingester** — it doesn't call Graph and doesn't replace the audit-log
> ingester. It does the JSON parse / explode / date / licence / agent-map work that the Power BI
> template used to do in Power Query on every refresh, and writes a flat, V-Ordered
> `copilot_interactions_curated` table that the model reads with no transformation. Use
> `WRITE_MODE = "overwrite"` for the first backfill, then `"merge"` for daily runs.

### E7 licensing update

`Copilot_Licensed_Users_Direct_Ingester` recognizes the verified Microsoft 365 E7
product name and identifiers as exact tokens, alongside existing Copilot aliases.
See [E7 mappings, override migration, evidence and limitations](../README.md#microsoft-365-e7-licence-classification).
After updating, run the licensed-user ingester, then the audit-log processor,
then refresh Power BI (including affected historical partitions if incremental).
`ValueLens_Data_Check` shows stored flags alongside assigned-product combinations;
it does not independently classify E7 or verify enabled service plans.

The canonical notebooks here are synchronized to `extended/_shared/notebooks`
and `extended/Fabric + Copilot Studio/notebooks/_core` using
`scripts/sync-shared.ps1`. The processor is inherited, not mirrored.

## Recommended — Agent 365 governance

Both notebooks feed the **Agents 365** page and write the **same** `dbo.agents_365` table, so
**pick exactly ONE — never run both.** Decision rule:

- **`Copilot_Agent365_Registry_Ingester` — the default.** Use it whenever the tenant has an
  **Agent 365 licence** and you can grant the app-only Graph permissions. It pulls the registry live
  and runs unattended on a schedule — no upload step.
- **`Copilot_Agent365_Lander` — manual fallback only.** Use it *only* when you can't grant those
  permissions (or for a one-off / evaluation), by hand-dropping the admin-center CSV export at
  `Files/agent365/agents.csv`. **The Ingester replaces this Lander** the moment the API / licence
  becomes available on the tenant.

| Notebook | Output table | When to use |
|---|---|---|
| `Copilot_Agent365_Registry_Ingester` | `agents_365` | **Default.** GA, **app-only** ingester (`CopilotPackages.Read.All` + `Application.Read.All`). Runs headless on a schedule and writes the full capability / permission detail. Gated by `Enable_Agent365`. |
| `Copilot_Agent365_Lander` | `agents_365` | **Fallback.** CSV lander — use only when the Ingester's app-reg permissions aren't available in the tenant, or for one-off / evaluation runs. The two write to the **same** `dbo.agents_365` table, so pick one — don't run both. |

## Optional — product feedback &amp; Cowork / Work IQ credit consumption

| Notebook | Output table | Feeds | Gated by |
|---|---|---|---|
| `Copilot_ProductFeedback_Ingester` | `user_feedback` | 💬 **Feedback** page | `Enable_ProductFeedback` |
| `Copilot_Cost_Consumption_Ingester` | `copilot_cost_consumption` | 🪙 **Credit Meter** page | `Enable_CostConsumption` |

**Product feedback** reads the Microsoft Admin Center → Health → Product feedback (OCV) export.
**Cowork / Work IQ** lands the **Microsoft Admin Center → Cowork / Work IQ** credit-consumption export
into `Files/cost_consumption/` — the **standard** consumption view across every template. See
[`../flows/COST-CONSUMPTION.md`](../flows/COST-CONSUMPTION.md) for the automated landing flow.

---

## Not in this folder

- **Power Platform Admin Center (PPAC) credit consumption** and the **Copilot Studio**
  transcript / registry notebooks now live with the fuller template in
  [`../../3. Fabric/extended/Fabric + Copilot Studio/`](../extended/Fabric%20+%20Copilot%20Studio/README.md).
  Add them only if you deploy that *Fabric + Copilot Studio* build.

---

**Note:** all model partitions are gated by an `Enable_*` parameter and fall back to
an empty table when their source isn't present, so the template opens cleanly even if
you haven't run its optional notebooks yet.
