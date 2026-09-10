# Troubleshooting — template load errors

If the template fails to **Load** (the *"N queries are blocked by the following errors"* dialog),
work through this page. Almost every load failure is **config or parameter-side, not network** — if
the SQL endpoint connection itself had failed you'd see a *login/timeout* error, not a Power Query
"queries are blocked" dialog.

> **First rule of triage:** a "queries are blocked" dialog means the connection to the Fabric SQL
> endpoint **succeeded**. The template got far enough to run queries. So the problem is privacy
> levels, missing tables, or optional toggles — not port 1433, service tags, or SSL inspection.

---

## 1. "…references other queries or steps… please rebuild this data combination"

**Full message:**

> Query '…' (step '__out') references other queries or steps, so it may not directly access a data
> source. Please rebuild this data combination.

This is Power Query's **data-privacy Firewall** (a.k.a. `Formula.Firewall`) — an *internal* Power BI
Desktop mechanism, **nothing to do with your corporate firewall**. It fires because the template is
parameter-driven: the **SQL Endpoint** and **Lakehouse Name** parameters are folded into the
`Sql.Database()` call, and the privacy engine refuses to combine a parameter with a data source.

**Fix:** turn privacy levels off in Power BI Desktop:

1. **File → Options and settings → Options**
2. **Current File → Privacy → "Always ignore Privacy Level settings"**
3. Do the same under **Global → Privacy** (so it sticks for future refreshes).
4. **Close & Apply / Load** again.

This one change typically clears the bulk of the blocked queries.

---

## 2. "There weren't enough elements in the enumeration to complete the operation"

This means the table the query expected is **empty or doesn't exist** in the Lakehouse you pointed the
template at. Two usual causes:

### a) Wrong Lakehouse in the parameter
The **Lakehouse Name** parameter must point at the Lakehouse the **three core notebooks** wrote to.
Verify the core tables exist and have rows — in the Fabric portal, open the SQL endpoint and run:

```sql
SELECT COUNT(*) FROM dbo.copilot_interactions_parsed;
SELECT COUNT(*) FROM dbo.copilot_licensed_users;
SELECT COUNT(*) FROM dbo.copilot_org_data;
```

If any return 0 or error, the ingester notebook for that table either didn't run or wrote to a
**different** Lakehouse. Re-point the parameter, or re-run the notebook against the correct Lakehouse.

### b) An optional source is toggled on but its notebook hasn't run
If an `Enable_*` parameter is set to **Include** but the matching notebook/lander hasn't populated its
table, that table is absent → this error.

**Fix:** set **every** optional toggle to **Exclude**, Load, and confirm the core dashboard works.
Then enable one optional source at a time, only *after* its notebook has run. See
[`OPTIONAL-SOURCES.md`](OPTIONAL-SOURCES.md).

---

## 3. Start on the base template first

If you're deploying the **Fabric Extended (+ Studio Agent Deepdive)** build, get the base
**`ValueLens - Fabric`** template loading cleanly first. The Extended build adds Dataverse / Copilot
Studio dependencies that compound the errors above if core isn't working yet.

---

## Recommended load order

1. **Turn off Privacy Levels** (fixes error #1).
2. **Confirm the 3 core tables have rows** (fixes error #2a) — re-point **Lakehouse Name** if needed.
3. **Set all `Enable_*` toggles to Exclude** (fixes error #2b).
4. **Load.** Confirm the core pages render.
5. Enable optional sources **one at a time**, after each notebook has run.

---

## Is it *ever* the network?

Rarely, and it looks different. A genuine connectivity block shows up as a **login/connection
timeout** to `<yourendpoint>.datawarehouse.fabric.microsoft.com` on TDS port **1433** — *before* any
query runs, so you never reach the "queries are blocked" dialog. If you see that instead:

- Confirm outbound **TCP 1433** to `*.datawarehouse.fabric.microsoft.com` is allowed (Fabric SQL uses
  1433 only — there's no 11000–11999 redirect range like Azure SQL DB).
- Behind a corporate proxy/egress, allow-list by **FQDN** (`*.datawarehouse.fabric.microsoft.com`,
  `*.fabric.microsoft.com`, `login.microsoftonline.com`). Azure **service tags** (`PowerBI`,
  `AzureCloud`) only apply to Azure NSG/Firewall, not corporate proxies.
- SSL/TLS inspection must allow the Microsoft auth + Fabric endpoints end-to-end.

But the "queries are blocked" dialog is **not** this — see the first rule of triage above.

---

See [`README.md`](../README.md) for the full setup, [`PERMISSIONS.md`](PERMISSIONS.md) for grants,
[`OPTIONAL-SOURCES.md`](OPTIONAL-SOURCES.md) for how absent sources stay green, and the read-only
checker pack under [`checker/`](checker/).
