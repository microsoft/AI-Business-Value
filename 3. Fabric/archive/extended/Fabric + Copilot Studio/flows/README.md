# ARCHIVED — Copilot Credit Consumption landing flows (Studio build)

> **ARCHIVED / reference only — not recommended for new deployments.** Historical configuration
> instructions are retained below. The active [`3. Fabric`](../../../../README.md) build and
> [ProductFeedback flow](../../../../flows/Copilot_ProductFeedback_Email_to_OneLake.json) remain active.

> **Part of the *Fabric + Copilot Studio* build.** These flows land the **Power Platform Admin
> Center (PPAC)** message-consumption export that feeds the Studio-exclusive **Credits Consumed**
> page. The leaner *No Studio* template ([`3. Fabric/`](../../../../README.md)) does **not**
> use them. For the setup walkthrough see [`../CREDIT-CONSUMPTION-SETUP.md`](../CREDIT-CONSUMPTION-SETUP.md).

These two Power Automate flows remove the **manual export → save** step for the Power Platform
message-consumption reports (`EntitlementConsumption*_MCSMessages_*.csv`). They drop the CSVs
straight into the Fabric Lakehouse at **`Files/credit_consumption/`**, where
[`../notebooks/Copilot_Credit_Consumption_Ingester.ipynb`](../notebooks/Copilot_Credit_Consumption_Ingester.ipynb)
picks them up on its next run.

```
                       ┌─ Email arrives with CSV ─┐
Power Platform export ─┤                          ├─▶ OneLake  Files/credit_consumption/*.csv ─▶ Ingester notebook ─▶ Delta
                       └─ Dropped to SharePoint ──┘
```

| File | When to use |
| --- | --- |
| `Copilot_Consumption_Email_to_OneLake.json` | The reports arrive by **email** (e.g. the customer mails the export, or a scheduled PPAC export is mailed). |
| `Copilot_Consumption_SharePoint_to_OneLake.json` | The customer prefers a **governed SharePoint document library** drop folder. |

Both write to OneLake with the **DFS (ADLS Gen2) three-step pattern**: `PUT ?resource=file` →
`PATCH ?action=append` → `PATCH ?action=flush`.

> **PPAC vs MAC — don't confuse the two credit exports.** This is the **per-agent Copilot Studio
> *message* credit** export from the **Power Platform Admin Center** (`credit_consumption_*` tables →
> `Enable_Consumption`). The **per-user Cowork / Work IQ *surface* credit** export from the **M365
> Admin Center** is a *different* source whose core ingester remains active; its landing flows
> and guides are now archived —
> see [`3. Fabric/archive/flows/COST-CONSUMPTION.md`](../../../flows/COST-CONSUMPTION.md)
> (`copilot_cost_consumption` → `Enable_CostConsumption`).

## Import & configure

1. **Power Automate** → *My flows* → *Import* → *Import Package (Legacy)* or paste the definition into a new flow.
2. Re-create the connection the trigger needs:
   - Email flow → **Office 365 Outlook** connection.
   - SharePoint flow → **SharePoint** connection.
3. Set the flow **parameters**:
   - `OneLakeWorkspace` — Fabric workspace name or GUID (e.g. `<your-workspace>`).
   - `OneLakeLakehouse` — lakehouse name **without** the `.Lakehouse` suffix (e.g. `<your-lakehouse>`).
   - `TargetFolder` — keep `Files/credit_consumption` (must match `SOURCE_DIR` in the ingester notebook).
   - `TenantId`, `ClientId`, `ClientSecret` — identity used for the OneLake calls (see below).
   - Email flow only: `SubjectFilter` (default `Copilot Usage Dashboard`).
   - SharePoint flow only: `SharePointSite`, `SharePointLibrary`, `SharePointFolder`.

## OneLake write permission (the one real prerequisite)

The HTTP actions authenticate with **Azure AD OAuth, audience `https://storage.azure.com/`**.
The identity in `ClientId` must be able to **write** to the workspace's OneLake:

- Add the **app registration** (or a **workspace identity** / service principal) as a
  **Member or Contributor** on the **Fabric workspace** that holds the lakehouse.
- Put the secret in **Azure Key Vault** and reference it — don't ship a literal `ClientSecret`.
- Tenant setting **“Service principals can use Fabric APIs”** must be enabled for the SP route.

> Prefer not to use an app secret? Swap the three `Http` actions for the **OneLake / Azure Blob
> connector** actions and authenticate the connection interactively — the create/append/flush
> URIs stay identical.

## Idempotency / re-runs

Microsoft's export filenames already carry the day-window + a `(1)` suffix on re-download, so
re-landing is safe: the ingester runs with `WRITE_MODE='overwrite'` (full snapshot) by default and
`unionByName`s every file in the folder. If you switch the notebook to `'append'`, prune the folder
(or dedupe on `SourceFile`) between loads.

## Not all customers will send consumption data

That's expected. If `Files/credit_consumption/` is empty, the ingester writes **empty, correctly-named**
tables and the PBIP's **`Enable_Consumption = "Exclude"`** toggle keeps the billing visuals dormant —
the transcript-native `Total Cost Units` (displayedCost) view keeps working regardless.

> The optional-source toggles are **list parameters** with the values `"Include"` / `"Exclude"`
> (not `true`/`false`). Set `Enable_Consumption` to `"Include"` once the data is landing.

## Reusing this pattern

The same `PUT → append → flush` landing mechanism works for **any** export-only Microsoft report —
only the **trigger filter** and **target folder** change. The *No Studio* template documents the
generalised pattern (and the product-feedback example that ships in every build) in
[`3. Fabric/flows/README.md`](../../../../flows/README.md#generalising-to-other-export-only-sources).
