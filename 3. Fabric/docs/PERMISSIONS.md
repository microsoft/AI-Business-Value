# Roles & permissions — one-page reference

Everything you need to grant to stand up the Fabric dashboard, least-privilege.
Three kinds of permission are involved:

- **App permission / role** — what an automated (unattended) pull needs.
- **Export role** — the admin-portal role a person needs to download the data by hand.
- **Fabric workspace role** — needed to run the notebooks/pipeline and write to the Lakehouse.

> Optional sources are opt-in. Skip any you don't use — the dashboard still works (those pages load empty).

---

## Core sources (required)

Pulled automatically by the 3 core notebooks via one **Entra app registration** with these
**Microsoft Graph application** permissions (admin consent required):

| Source | Graph application permission | Manual-export role (if pulling by hand) |
|---|---|---|
| Audit logs (`copilot_interactions_parsed`) | `AuditLogsQuery.Read.All` | Audit Reader or Compliance Administrator |
| Licensed users (`copilot_licensed_users`) | `Reports.Read.All` | Global Reader or Reports Reader |
| Org data (`copilot_org_data`) | `User.Read.All` | Global Reader or User Administrator |

One app registration covers all three. Put the client secret in **Azure Key Vault**, not in a notebook.

---

## Optional sources (opt-in)

| Source | API? | Automated-pull permission | Manual-export role |
|---|---|---|---|
| **Cost consumption** (M365 Admin Center → Copilot → Cost management) | ❌ export-only | None — there is no API. Export and land the per-user CSV manually or via your own automation, then the active core ingester notebook reads it. | Global Administrator or Billing Administrator |
| **Product feedback** (OCV / M365 Health) | ❌ export-only | None — there is no API. Landed by the Power Automate flow, then ingested. | Global Administrator or Reports Reader |
| **Agents 365** | export/lander | Lander notebook reads an exported registry CSV. | Global Administrator or Reports Reader (with **AI Admin** in a Frontier-enrolled tenant) |

For the two **export-only** sources, the only "permission" to automate landing is the automation's **OneLake write**
right (next section) — the data itself must be exported by an admin (or a scheduled portal export) first.

The four `COST-CONSUMPTION` guides and cost flow JSON in [archive/flows](../archive/flows/) are
**archived reference**, not recommended active deployment instructions. The core cost ingester
and model support remain **active**.

> **Studio add-ons.** Copilot Studio agent-transcript (Dataverse) analytics and PPAC per-agent /
> per-user message-credit consumption need extra grants (a Dataverse **Application User** with read on
> the **Conversation Transcript** table; Power Platform admin export). Those are covered in the archived
> [Fabric + Copilot Studio](../archive/extended/Fabric%20+%20Copilot%20Studio/) build,
> kept as reference rather than a recommended active deployment.

---

## Fabric workspace & capacity (to run anything)

| What | Role / requirement |
|---|---|
| Run the notebooks / pipeline, write Delta to the Lakehouse | **Contributor** or **Member** on the Fabric workspace |
| Land export-only files via the Power Automate flows | The flow's identity (app reg or workspace identity) as **Member/Contributor** on the workspace; tenant setting **“Service principals can use Fabric APIs”** enabled |
| Capacity | Workspace on a Fabric capacity (**F2+** or trial) |
| Connect the Power BI template | Read on the Lakehouse **SQL endpoint** (the template signs in to it once) |

---

## Quick "who do I ask?" summary

- **Just the core dashboard:** one Entra app reg (3 Graph perms, admin-consented) + Contributor on the workspace.
- **+ Cost / Feedback:** an admin exports the CSVs (or schedules a portal export); land cost CSVs manually or via your own automation, and feedback via its flow — no extra API permission.
- **+ Agents 365:** an admin with Reports Reader (+ AI Admin) exports the registry.

See [`README.md`](../README.md) for the step-by-step, and [`OPTIONAL-SOURCES.md`](OPTIONAL-SOURCES.md)
for how absent sources stay green.
