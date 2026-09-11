# Optional sources — the "load-or-empty" pattern

The template is designed so that **core** sources are required, but **optional** sources can be
present or absent without ever breaking a refresh. This is achieved with three pieces.

## 1. `EmptyTable` helper (Fabric model)

A shared expression that returns an empty table with a given set of columns:

```m
EmptyTable = (columns as list) as table => #table(columns, {})
```

When an optional source is missing or switched off, the table resolves to an **empty table with the
correct column names**, so every downstream step (type casts, renames, derived columns) still works
and the measures simply return `0`/blank.

## 2. `Enable_*` toggle parameters

| Parameter | Default | Controls |
| --- | --- | --- |
| `Enable_ProductFeedback` | `"Include"` | `user_feedback` (ProductFeedback — OCV export) |
| `Enable_Agent365` | `"Include"` | `agents_365` (Agents 365 registry) |
| `Enable_CostConsumption` | `"Include"` | `copilot_cost_consumption` (Cowork / Work IQ / Other credits — MAC Cost management export) |

Set a toggle to `"Exclude"` to skip that source entirely (no fetch attempt) — useful when a customer
hasn't licensed/exported it, or to speed up refresh.

> These are **list parameters** offering `"Include"` / `"Exclude"` (they render as a dropdown in
> *Edit Parameters*), not boolean `true`/`false`.

> **Studio add-ons.** Copilot Studio agent-transcript tables (`Enable_Dataverse`) and PPAC per-agent /
> per-user message-credit tables (`Enable_Consumption`) belong to the archived
> [Fabric + Copilot Studio](../archive/extended/Fabric%20+%20Copilot%20Studio/) build, not this one.
> It is reference material, not a recommended active deployment.

> **Cost consumption remains active.** `Enable_CostConsumption` and the core
> `Copilot_Cost_Consumption_Ingester` are unchanged. Only the four `COST-CONSUMPTION` guides and
> cost flow JSON moved to [archived flow references](../archive/flows/); they are not recommended
> active deployment instructions.

## 3. The per-table wrapper

Each optional table's M entry point is wrapped like this (Product Feedback shown):

```m
Promoted =
    if Enable_ProductFeedback = "Include"
    then (try FabricTable("user_feedback") otherwise EmptyTable({ ...contract columns... }))
    else EmptyTable({ ...contract columns... }),
```

- **Toggle off** → empty table (no source call).
- **Toggle on, table present** → real data.
- **Toggle on, table missing** → `try…otherwise` catches the error → empty table.

In every case the table has the contract columns from `DATA-DICTIONARY.md`, so the refresh succeeds.

### ProductFeedback extra hardening
`ProductFeedback` additionally uses `Table.RenameColumns(..., MissingField.Ignore)` so a **partial**
OCV export (missing some optional columns like `Survey Question`) is tolerated, not just a fully
absent one. The producing notebook's empty placeholder emits the full 23-column superset to match.

## SharePoint version

The SharePoint model uses the identical pattern, swapping the source call:

```m
Promoted =
    if Enable_ProductFeedback = "Include"
    then (try SharePointCsv(#"Product Feedback File") otherwise EmptyTable({ ... }))
    else EmptyTable({ ... }),
```

## Validation matrix

Before release, confirm a green refresh for each combination (at minimum):

| Product Feedback | Agent 365 | Cost Consumption | Expected |
| --- | --- | --- | --- |
| on (data) | on (data) | on (data) | full dashboard |
| off | off | off | core-only, no errors |
| on (missing) | on (missing) | on (missing) | empty optional tables, no errors |
| on (data) | on (data) | off | cost page blank, rest populated |

> ⚠️ These M changes must be opened & refreshed once in **Power BI Desktop** to validate (the edits
> were made directly in TMDL). Desktop will also assign proper lineage on first save.
