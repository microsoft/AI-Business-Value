# ARCHIVED — Cost Consumption (M365 Admin Center) setup reference

> **ARCHIVED / reference only — these landing flows are not recommended for new deployments.**
> Historical instructions are retained below. The [core ingester](../../notebooks/Copilot_Cost_Consumption_Ingester.ipynb)
> and [base Fabric build](../../README.md) remain active, as does the
> [ProductFeedback flow](../../flows/Copilot_ProductFeedback_Email_to_OneLake.json).

**Who this is for:** anyone lighting up the **first Consumption page** on the dashboard — the one
that shows per-user **Cowork / WorkIQ / Other** credit split and monthly credit usage against the
per-user cap. **No coding required for the basic path.**

> **Is this step optional?** Yes. If you don't supply this export, the Consumption page just stays
> empty and everything else works. Only do this if you want the surface-split and per-user cap
> analytics.

> **Cost vs Credit — don't confuse the two.** *This* guide covers the **Microsoft 365 Admin Center →
> Copilot → Cost management → Consumption** export (per-user Cowork / WorkIQ / Other credits and
> monthly cap utilisation). A separate export — the **Power Platform Admin Center** MCS Messages
> reports (per-agent Copilot Studio *message* credits) — powers the *Credits Consumed* page and is
> documented in the [archived Copilot Studio credit guide](../extended/Fabric%20+%20Copilot%20Studio/CREDIT-CONSUMPTION-SETUP.md).
> Different portal, different grain — they answer different questions and are additive, not
> alternatives.

---

## What you're setting up

Microsoft's per-user cost management view — how many **Cowork / WorkIQ / Other** credits each
licensed Copilot user has consumed, and their utilisation against their **monthly credit cap** —
comes out of the **Microsoft 365 Admin Center** as one downloadable CSV. There is **no API** to pull
it automatically, so the flow is:

```
Microsoft 365 Admin Center           Fabric Lakehouse                    Power BI
  (download 1 CSV export)     →   Files/cost_consumption/    →   Consumption page
                                          │
                                   ingester notebook
                                    builds 1 table
```

You do this **once a month** (or whenever you want fresh numbers).

---

## Step 1 — Get the export from MAC

You need **Global Reader**, **Global Administrator**, or the **Copilot Administrator** role in the
tenant to see the Cost management view.

1. Sign in to **[`admin.microsoft.com`](https://admin.microsoft.com)**.
2. Left nav → **Copilot** → **Cost management** → **Consumption**.
   - *If you don't see Copilot in the left nav:* click **Show all**, then look under **Reports** or
     **Settings** depending on your tenant's MAC layout. The route is stable but the grouping shifts.
3. Choose the reporting period at the top of the page (usually **This month** or **Last month**).
4. Click **Export** (top-right) → **Export to CSV**.
5. Save the file somewhere you can find it (e.g. your Downloads folder). Filename varies by tenant —
   the ingester matches on column headers, not filename, so any `.csv` is fine.

**Two export shapes are supported** (the ingester auto-detects which one you have — case-insensitive
header matching):

- **Surface split** — headers include `User Principal Name`, `Cowork Credits`, `WorkIQ Credits`,
  `Other Credits`, `Last Activity Date`. Best for "where are credits being spent?" analysis.
- **Per-user usage** — headers include `Display Name`, `User Principal Name`, `Monthly credit limit`,
  `Monthly credits used`, `% Used`, `Session Count`, `Microsoft 365 Copilot license`,
  `Last activity date`. Best for "who's near their cap?" analysis.

You can drop either into the same folder; the ingester unifies them into one contract. Drop **both**
across successive months and you get both signals.

---

## Step 2 — Put the file in the Lakehouse

Pick **one** of the two options below.

### Option A — Manual upload (simplest, recommended to start) ⭐

1. Open your Fabric workspace → open the **`<your-lakehouse>`** lakehouse.
2. In the **Files** area, create a folder called **`cost_consumption`** (lower-case, exactly that).
   - *Already there from a previous run?* Just open it.
3. **Drag and drop** the CSV into that folder.

That's it — no code. The folder should now contain your MAC export.

### Option B — Automate it with a Power Automate flow (hands-off)

If you'd rather not upload by hand each month, import one of the ready-made flows in
[`3. Fabric/archive/flows/`](./) so the file lands automatically:

- **`Copilot_CostConsumption_Email_to_OneLake.json`** — watches an inbox; when an email with the
  consumption CSV arrives (e.g. a scheduled MAC export or a colleague forwarding the download), it
  drops the attachment into `Files/cost_consumption/` for you. Default subject filter:
  `Copilot Cost Management`.
- **`Copilot_CostConsumption_SharePoint_to_OneLake.json`** — same idea, but watches a governed
  SharePoint document library instead of email.

Both flows use the standard OneLake DFS three-step upload pattern and share the same setup +
permissions as the credit-consumption flows — see the
[archived credit-consumption flow README](../extended/Fabric%20+%20Copilot%20Studio/flows/README.md).

---

## Step 3 — Run the ingester notebook (once)

This turns the CSV into one tidy table the dashboard can read.

1. In your Fabric workspace, import **`../../notebooks/Copilot_Cost_Consumption_Ingester.ipynb`**
   (**+ New → Import notebook**) — *or* open it if it's already there.
2. Attach it to the **`<your-lakehouse>`** lakehouse and **pin it as default** (📌).
3. Click **Run all**. It finishes in well under a minute.

When it's done you'll have one new table in the lakehouse: **`copilot_cost_consumption`**.

> You can re-run this any time you drop in a fresh CSV — it replaces the old numbers each time.

---

## Step 4 — Switch the Consumption page on in Power BI

1. Open the dashboard ([`../../ValueLens - Fabric.pbit`](../../ValueLens%20-%20Fabric.pbit) or your live `.pbip`) in **Power BI Desktop**.
2. **Home → Transform data → Edit parameters** and set **`Enable_CostConsumption`** to **`Include`**.
3. Make sure the **Fabric SQL Endpoint** and **Lakehouse** parameters point at your
   `<your-lakehouse>` lakehouse.
4. **Home → Refresh.**

The **Consumption** page should now populate — total credits split by Cowork / WorkIQ / Other, users
near their monthly cap, session counts, and a **Reporting Period** label showing the date window
your export covers (read straight from the data).

---

## A few things worth knowing

- **It can take a minute or two to show up.** After the notebook runs, Fabric's SQL endpoint needs a
  short moment to "see" the new table. If a refresh comes back empty straight after running the
  notebook, **wait a minute and refresh again**.
- **Snapshot, not daily series.** `Last Activity Date` is *the user's last activity date*, not a
  daily credit trend. Treat this page like a monthly scorecard — the visuals are card + treemap +
  ranking, not a time series.
- **UPN attribution isn't guaranteed 100%.** Users in the cost export with no matching row in
  Chat + Agent Org Data won't get a Division/Manager attribution. The visuals surface these under
  an **(Unattributed)** bucket and show the match rate — a gap is visible rather than silently
  dropped.
- **Two views of "cost" in this dashboard.** *This* Consumption page shows what MAC reports as
  **credits used** against **monthly credit limits** (Cowork / WorkIQ / Other split). The
  ***Credits Consumed*** page (Studio Extended) shows the PPAC per-agent *message* credits — the
  actual billing meter for Copilot Studio agents. Different portals, different grain. Both are
  useful; neither replaces the other.

---

## If something looks wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Consumption page is empty after refresh | `Enable_CostConsumption` still `Exclude`, or file not in the folder | Set it to `Include`; confirm the CSV is in `Files/cost_consumption/` and the notebook has run |
| Empty *immediately* after running the notebook | SQL endpoint hasn't synced yet | Wait ~1 minute, refresh again |
| Refresh error: *"The column '…' of the table wasn't found"* | Ingested with a different/older script | Re-run **this** repo's `Copilot_Cost_Consumption_Ingester.ipynb` — it maps both MAC export shapes to the exact column names the model expects (`User_Principal_Name`, `Cowork_Credits`, `Total_Credits`, `Monthly_Credit_Limit`, `Pct_Used`, etc.) |
| Cowork/WorkIQ/Other visuals are blank but Total Credits works | You imported the *usage* shape (which has no surface split) rather than the *surface split* shape | Export the surface split view from MAC as well and drop it in the same folder — the ingester merges both |
| High share of **(Unattributed)** users | Org Data ingester hasn't run recently, or UPNs in the export don't match the directory | Re-run `Copilot_Org_Data_Direct_Ingester.ipynb`; investigate any UPN mismatches (guest accounts, `#EXT#` suffixes, admin UPN aliases) |

---

## Where to check MAC when Microsoft changes the UI

Microsoft has moved Copilot admin surfaces around several times since public preview. If the
Cost management view isn't where step 1 says it is, try these fallback paths in order:

1. `admin.microsoft.com` → **Show all** → **Reports** → **Usage** → filter for **Copilot**.
2. `admin.microsoft.com` → **Copilot** landing page → tile labelled **Cost**, **Consumption**, or
   **Utilization**.
3. Microsoft's current help page: search
   [Microsoft Learn](https://learn.microsoft.com/) for **"Microsoft 365 Copilot cost management"** —
   the doc always tracks the current UI location.

The ingester and column contract are stable regardless of where MAC hides the export button.

---

*Related: [archived credit-consumption flow README](../extended/Fabric%20+%20Copilot%20Studio/flows/README.md) (shared landing setup) ·
[`COST-CONSUMPTION.md`](COST-CONSUMPTION.md) (column contract + model wiring) ·
[`3. Fabric/docs/OPTIONAL-SOURCES.md`](../../docs/OPTIONAL-SOURCES.md) (how optional sources stay "green"
when absent) · [`3. Fabric/docs/DATA-DICTIONARY.md`](../../docs/DATA-DICTIONARY.md) (column reference) ·
[archived Copilot Studio credit guide](../extended/Fabric%20+%20Copilot%20Studio/CREDIT-CONSUMPTION-SETUP.md) (the different, PPAC-side credit guide).*
