# Ingestion: reviewed load strategy, scale & upgrades

Guidance for the current Fabric notebook set — especially the reviewed snapshot-safety
and merge-key changes.

This is the base **No-Studio** build: three core sources — **audit logs**, **licensed users**, and
**org data**. Optional add-ons (Cowork / Work IQ consumption, product feedback, Agents 365) follow the
same rules; Copilot Studio agent-transcript analytics and PPAC message-credit tables live in the
separate [Fabric + Copilot Studio](../extended/Fabric%20+%20Copilot%20Studio/) build.

---

## 1. Load strategy per source

The current core path is **not** "append everything forever". It now mixes
**overwrite snapshots** with **stable-key merge** where appropriate.

| Source / table | Recommended mode | Current reviewed behaviour |
|---|---|---|
| **Audit log** → `copilot_interactions_parsed` (`Copilot_Audit_Log_Direct_Ingester`) | **Backfill = overwrite**; **incremental = merge** | Incremental re-queries the trailing `LOOKBACK_DAYS = 7` and relies on stable row keys (`Id`, `Source_RecordKey`, `Source_MessageKey`, `Source_ResourceKey`). |
| **Licensed users** → `copilot_licensed_users` (`Copilot_Licensed_Users_Direct_Ingester`) | **overwrite** | Snapshot source. Rejects empty, malformed and conflicting duplicate rows before replacement. |
| **Org / people** → `copilot_org_data` (`Copilot_Org_Data_Direct_Ingester`) | **overwrite** | Snapshot source. Rejects malformed pages, conflicting duplicates and manager cycles before replacement. |
| **Agent 365 registry** → `agents_365` (`Copilot_Agent365_Registry_Ingester`) | **overwrite** | Snapshot source. Rejects rows with missing `Title ID` and conflicting duplicates. |
| **Agent 365 CSV lander** → `agents_365` (`Copilot_Agent365_Lander`) | **overwrite** | Snapshot fallback. Use only as an alternative source for the same table. |
| **Product feedback** → `user_feedback` (`Copilot_ProductFeedback_Ingester`) | **overwrite only** | `append` is explicitly rejected; missing exports preserve the existing snapshot unless you allow an empty first placeholder. |

### Parsed audit keys and deliberate upgrade path

Older parsed tables may be missing the reviewed stable key columns:

- `Id`
- `Source_RecordKey`
- `Source_MessageKey`
- `Source_ResourceKey`

If so, incremental runs fail clearly and require a **deliberate fresh backfill**.

Important implications:

1. **Validate in a separate output/staging target first** if you want to compare old vs new parsed output.
2. A backfill to the **same** parsed table **overwrites it in place**.
3. You cannot reconstruct perfect historical deduplication for legacy rows that never had the new identifiers.

### Backfilling history
For "all data since 1 Jan 2026", use `MODE='backfill'` in the **audit ingester**, not the dashboard.
The notebook already chunks each run into `CHUNK_HOURS` windows and retries transient 5xx/429 failures,
so a long backfill survives Purview throttling. Graph still caps each audit query to a rolling 7-day
window, so history is assembled as bounded windows rather than one giant pull.

After a parsed-table backfill, rerun **`Copilot_Audit_Log_Processor`** before refreshing Power BI.

---

## 2. Keep Power Query thin

The Fabric path is built so the PBIT reads **already-shaped Delta tables** and does only light typing
and measures — the heavy parsing (audit `AuditData` flatten, agent-identity resolution) happens in the
Spark notebooks. If a refresh is taking minutes:

1. **Prefer incremental refresh** over re-importing everything each run — see
   [`INCREMENTAL-REFRESH.md`](INCREMENTAL-REFRESH.md).
2. **No per-row M expansion.** Don't add record/JSON parsing in the PBIT on the Fabric path — that work
   belongs in the ingester notebook, so the table you connect to is already flat.

> If you see Power Query doing real transformation on a large feed, push it into the ingester notebook
> and have the PBIT read the resulting Delta table.

---

## 3. Resiliency (already in the build)

- **Audit ingester** uses a shared `requests.Session` with `urllib3` **Retry** (`429/500/502/503/504`,
  exponential backoff, honours `Retry-After`) plus an outer retry loop, so transient **504 Gateway
  Timeouts** during poll/fetch no longer abort the run. The requery / backfill window is split into
  `CHUNK_HOURS` slices with a configurable `MAX_WAIT_MIN_PER_QUERY`, and records stream to Lakehouse
  Files (bounded driver memory).
- **Consumption dates** parse US-format `Usage_Date` with explicit `"en-US"` culture, so they don't
  fail on non-US machine/region locales.
- **Product feedback** now treats the feed as a strict snapshot source: safe overwrite, no append.

## 4. Licensed-user classifier note

The reviewed licensed-user ingester recognizes the exact Microsoft 365 E7 tokens added in the local
notebook changes. Keep deliberate custom `COPILOT_SKU_PATTERNS` / `COPILOT_SKU_EXCLUDE` overrides
deliberate — defaults are not silently merged into an override, and broad "match anything containing
E7" rules are not recommended.

---

## 5. Production: stable build & upgrade path

**Pin a known-good commit.** Build your automation against a specific Git **tag / commit SHA** of this
repo rather than tracking `main`, so an upstream change can't break a running pipeline:

1. Validate a commit in a non-prod workspace (run the ingesters + refresh the PBIT).
2. Tag it (e.g. `v2026.07-fabric`) and point production at that tag.
3. To upgrade: diff the new tag's `3. Fabric/notebooks/`, test in non-prod, then move the tag.

**Compatibility tips:**
- Drive notebooks via the CONFIG cell (tagged as the pipeline `parameters` cell) — don't fork the
  notebook body, so upgrades are a definition swap.
- Keep secrets in **Key Vault** (`notebookutils.credentials.getSecret`), not in the CONFIG cell.
- Treat the Delta **table + column names** (`copilot_interactions_parsed`, `copilot_licensed_users`,
  `copilot_org_data`) as the integration contract; build dependencies on those, not on intermediate
  tables. Contract changes are called out so you can upgrade without surprises.
