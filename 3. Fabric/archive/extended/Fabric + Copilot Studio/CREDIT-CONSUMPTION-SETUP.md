# ARCHIVED — Credit Consumption (billing) setup reference

> **ARCHIVED / reference only — not a recommended active add-on.** The historical instructions
> below apply to the archived Copilot Studio build. For new deployments, start with
> the active [`3. Fabric`](../../../README.md) build.

**Who this is for:** anyone setting up the **optional** "Copilot Studio credit consumption"
billing pages on the Fabric version of the dashboard. **No coding required for the basic path.**

> **Is this step optional?** Yes. If you don't supply consumption data, the billing pages just
> stay empty and everything else works. Only do this if you want the **Credits Consumed**,
> **Agent Evaluation** billing cards, etc.

> **Credit vs Cost — don't confuse the two.** *This* guide covers **Copilot Studio credit
> consumption** — the Power Platform Admin Center `MCSMessages` exports (per-agent / per-user /
> per-environment **message** credits). A separate, newer source — the **Microsoft 365 Admin Center →
> Copilot → Cost management → Consumption** export — breaks credits down by **Cowork / WorkIQ / Other**
> surface and is documented in the [archived cost-consumption reference](../../flows/COST-CONSUMPTION.md).
> Different portals, different grain.

---

## What you're setting up

Microsoft's **per‑message credit consumption** numbers (how many Copilot Studio message credits
each environment, agent, and user used) come out of the **Power Platform Admin Center** as three
downloadable CSV files. There is **no API** to pull them automatically, so the flow is:

```
Power Platform Admin Center        Fabric Lakehouse                 Power BI
  (download 3 CSV exports)   →   Files/credit_consumption/   →   Credits Consumed pages
                                         │
                                  ingester notebook
                                  builds 3 tables
```

You do this **once a month** (or whenever you want fresh numbers).

---

## Step 1 — Get the three exports

In the **Power Platform Admin Center** → **Billing** → **Licensing / Copilot Studio messages**
(your portal wording may vary), download these three reports. The files are named like this:

| File name starts with… | What it contains |
|---|---|
| `EntitlementConsumptionTenantDetailsReport_MCSMessages…` | Credits per **environment**, per day |
| `EntitlementConsumptionTenantPerAgentDetailsReport_MCSMessages…` | Credits per **agent** |
| `EntitlementConsumptionTenantPerUserDetailsReport_MCSMessages…` | Credits per **user** |

Save all three somewhere you can find them (e.g. your Downloads folder).

---

## Step 2 — Put the files in the Lakehouse

Pick **one** of the two options below.

### Option A — Manual upload (simplest, recommended to start) ⭐

1. Open your Fabric workspace → open the **`<your-lakehouse>`** lakehouse.
2. In the **Files** area, create a folder called **`credit_consumption`** (lower‑case, exactly that).
   - *Already there from a previous run?* Just open it.
3. **Drag and drop** the three CSV files into that folder.

That's it — no code. The folder should now contain the three `EntitlementConsumption…` files.

### Option B — Automate it with a Power Automate flow (hands‑off)

If you'd rather not upload by hand each month, import one of the ready‑made flows in
[`flows/`](flows/) so the files land automatically:

- **`Copilot_Consumption_Email_to_OneLake.json`** — watches an inbox; when an email with the
  consumption CSVs arrives, it drops them into `Files/credit_consumption/` for you.
- **`Copilot_Consumption_SharePoint_to_OneLake.json`** — same idea, but watches a SharePoint
  document library instead of email.

Setup steps and the one permission you need are in [`flows/README.md`](flows/README.md).
(You only need this if you want it automated — Option A works fine on its own.)

---

## Step 3 — Run the ingester notebook (once)

This turns the three CSVs into three tidy tables the dashboard can read.

1. In your Fabric workspace, import **`notebooks/Copilot_Credit_Consumption_Ingester.ipynb`**
   (**+ New → Import notebook**) — *or* open it if it's already there.
2. Attach it to the **`<your-lakehouse>`** lakehouse and **pin it as default** (📌).
3. Click **Run all**. It finishes in well under a minute.

When it's done you'll have three new tables in the lakehouse:
`credit_consumption_tenant`, `credit_consumption_agent`, `credit_consumption_user`.

> You can re‑run this any time you drop in fresh CSVs — it replaces the old numbers each time.

---

## Step 4 — Switch the billing pages on in Power BI

1. Open the archived dashboard, [`ValueLens - Fabric (+ Studio Agent Deepdive).pbit`](ValueLens%20-%20Fabric%20%28+%20Studio%20Agent%20Deepdive%29.pbit), in **Power BI Desktop**.
2. **Home → Transform data → Edit parameters** and set **`Enable_Consumption`** to **`Include`**.
3. Make sure the **Fabric SQL Endpoint** and **Lakehouse** parameters point at your
   `<your-lakehouse>` lakehouse.
4. **Home → Refresh.**

The **Credits Consumed** page should now populate — total credits, billed vs non‑billed, a
"Credit consumption by agent" treemap, and a **Billing Period** label showing the date range your
export covers (read straight from the data).

---

## A few things worth knowing

- **It can take a minute or two to show up.** After the notebook runs, Fabric's SQL endpoint needs
  a short moment to "see" the new tables. If a refresh comes back empty straight after running the
  notebook, **wait a minute and refresh again**.
- **There is no date *slicer* on the billing page — that's deliberate.** The per‑agent and per‑user
  exports are 30‑day totals with **no daily breakdown**, so they can't be filtered by date. Instead
  the page shows a **Billing Period** label (e.g. "14 Apr – 11 May 2026") inferred from the data so
  you always know the window the numbers cover.
- **Two views of "cost".** These billing pages show what Microsoft actually *charges* (prepaid +
  pay‑as‑you‑go credits). That's different from the transcript‑native `displayedCost` you see on the
  Agent Sessions page, which only covers generative steps. Expect the billing total to be higher.

---

## If something looks wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Billing pages are empty after refresh | `Enable_Consumption` still `Exclude`, or files not in the folder | Set it to `Include`; confirm the 3 CSVs are in `Files/credit_consumption/` and the notebook has run |
| Empty *immediately* after running the notebook | SQL endpoint hasn't synced yet | Wait ~1 minute, refresh again |
| Refresh error: *"The column '…' of the table wasn't found"* | The CSVs were ingested by a different/older script with different column names | Re‑run **this** repo's `Copilot_Credit_Consumption_Ingester.ipynb` — it produces the exact column names the model expects (`Agent_Name`, `Billed_credit`, `Usage_Date`, etc.) |
| Numbers look like only billed credits | Treemap/cards using the wrong measure | The treemap should use **Total Consumed Credits** (billed + non‑billed) from the Agent table |

---

*Related: [`flows/README.md`](flows/README.md) (automated landing) ·
[`OPTIONAL-SOURCES.md`](../../../docs/OPTIONAL-SOURCES.md) (how optional sources stay
"green" when absent) · [`DATA-DICTIONARY.md`](../../../docs/DATA-DICTIONARY.md)
(column reference).*
