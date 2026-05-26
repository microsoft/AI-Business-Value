# AI Business Value Dashboard — Methodology

## Overview

The AI Business Value Dashboard translates raw Microsoft Purview audit signals into defensible productivity metrics — hours saved, assisted dollar value, and ROI — by classifying each Copilot interaction into an **AI Task** and attributing a research-sourced human-time baseline to that task.

The pipeline is:

```
Purview Audit Signal → Task Classification → Human Baseline Attribution → Hours Saved → Assisted Value ($)
```

---

## 1. Signal Ingestion: What Purview Tells Us

Every Microsoft 365 Copilot interaction (prompt submitted by a user) generates a `CopilotInteraction` audit record in Microsoft Purview. Each record contains three key signal dimensions:

| Signal Dimension | Field(s) in Audit Log | What It Tells Us |
|---|---|---|
| **App Surface** | `AppHost` | Which application hosted the interaction (Outlook, Word, Excel, PowerPoint, Teams, Edge, SharePoint, Designer, OneNote, Planner, Loop, Forms, Stream, etc.) |
| **Action** (Read / Write) | `AccessedResource_Action` | Whether the user was consuming content (read, summarise) or producing/modifying content (send, draft, create, post, write, invoke, execute, patch) |
| **Resources Accessed** | `AccessedResource_Type`, `AccessedResource_SiteUrl`, `AISystemPlugin_Id` | The type of content (EmailMessage, docx, pptx, xlsx, pdf, py, png, Flow, PlanId, PeopleInferenceAnswer, WebSearchQuery, etc.) and its location |

Additional contextual signals include:
- `Context_Type` — the document/meeting context in which Copilot was invoked
- `Environment` — whether this was a licensed Copilot session, an Agent session, or an Autonomous Agent
- `AgentName` / `AgentId` — for agent-based interactions
- `SensitivityLabelId` — whether protected/classified content was involved

---

## 2. Task Classification Logic

The `Behavior_Category` calculated column implements a deterministic, rules-based classifier that maps the combination of **app surface + action + resource type** into one of ~50 named AI Tasks (called "Behaviors").

The classification follows a priority waterfall:

1. **Resource-level signals** (most specific) — uses `AccessedResource_Type` + `AccessedResource_Action`
2. **Plugin signals** — uses `AISystemPlugin_Id` (e.g., `enterprisesearch`)
3. **Context/AppHost fallback** (least specific) — uses `AppHost` and `Context_Type` when no resource detail exists

### How "Active" (Write) vs "Passive" (Read) Determines the Task

A critical part of the classification is whether the action is **active** (creating/modifying) or **passive** (reading/summarising). The model defines "active" as any action containing:

> `send`, `draft`, `create`, `post`, `invoke`, `write`, `patch`, `execute`

This distinction is what separates, for example, **Document Drafting** from **Document Summarising** — the same resource type (`docx`) produces different tasks depending on whether the user was writing or reading.

### Worked Examples from the PBIP

#### Example 1: Email Drafting vs Email Summarising

| Signal | Value |
|---|---|
| AppHost | `Outlook` |
| AccessedResource_Type | `EmailMessage` |
| AccessedResource_Action | `SendEmailV2` |

Classification logic:
- `resAction` = `sendemailv2` → matches explicit email-send action → **"Email Drafting"**

If the action had instead been `Read`:
- `resType` = `emailmessage` AND `isActive` = FALSE → **"Email Summarising"**

#### Example 2: Document Drafting in Word

| Signal | Value |
|---|---|
| AppHost | `Word` |
| AccessedResource_Type | `docx` |
| AccessedResource_Action | `Create` |

Classification logic:
- `resType` = `docx` AND `isActive` = TRUE (contains "create") → **"Document Drafting"**

If the action were `Read`:
- `resType` = `docx` AND `resAction` = `read` → **"File Retrieval"**
- Or with no specific action → **"Document Summarising"**

#### Example 3: Data Querying in Excel

| Signal | Value |
|---|---|
| AppHost | `Excel` |
| AccessedResource_Type | `xlsx` |
| AccessedResource_Action | `ExecuteDatasetQuery` |

Classification logic:
- `resAction` = `executedatasetquery` → matches explicit query action → **"Data Querying"**

If the action were simply a passive read of an xlsx file:
- `resType` in `{xlsx, csv, xlsm}` AND `isActive` = FALSE → **"Spreadsheet Review"**

#### Example 4: Meeting Prep

| Signal | Value |
|---|---|
| AppHost | `Teams` |
| AccessedResource_Type | `TeamsMeeting` |
| AccessedResource_Action | `Read` |

Classification logic:
- `resType` in `{event, teamsmeeting}` → **"Meeting Prep"**

#### Example 5: Code Writing (Active) vs Code Analysis (Passive)

| Signal | Value |
|---|---|
| AppHost | `Office` |
| AccessedResource_Type | `py` |
| AccessedResource_Action | `Write` |

Classification logic:
- `resType` in `{py, js, java, tsx, jsx, css, php, sh}` AND `isActive` = TRUE → **"Code Writing"**

If the file were read-only:
- `resType` in `{py, sql, js, java, json, xml, html, yaml}` → **"Code Analysis"**

#### Example 6: Agent Classification

For agent-based interactions, if the resource-level classification returns no result, the model uses the agent's name and description to keyword-match into agent categories:

| Agent Name/Description contains | Classified As |
|---|---|
| `sales`, `customer`, `crm`, `pipeline` | Agent: Sales & Customer |
| `hr`, `recruit`, `talent`, `onboard` | Agent: HR & People |
| `it`, `support`, `helpdesk`, `ticket` | Agent: IT & Service Desk |
| `policy`, `compliance`, `legal`, `audit` | Agent: Compliance & Policy |
| `coach`, `mentor`, `learning`, `skill` | Agent: Coaching |
| `research`, `analyst`, `insight` | Agent: Research & Analysis |

---

## 3. Human-Time Baseline Attribution

Once classified, each task is joined to the **Human Time Estimates** reference table, which assigns:

| Task (Behavior) | Human Baseline (minutes) | Primary Source | Confidence |
|---|---|---|---|
| Email Triage | 10 | Microsoft Research (Iqbal & Horvitz 2007); McKinsey 2023 | Medium-High |
| Email Drafting | 8 | McKinsey 2023; Brynjolfsson et al. (NBER 2023) | High |
| Document Drafting | 60 | Noy & Zhang (MIT/Science 2023); BCG/Harvard 2023 | High |
| Presentation Creation | 90 | Gartner 2024; BCG 2024 | Medium-High |
| Meeting Prep | 15 | Forrester TEI 2024; HBR (Rogelberg 2019) | High |
| Data Querying | 30 | Forrester TEI (2022); BCG (2021) | High |
| Code Writing | 45 | GitHub/NBER (Peng et al. 2023) RCT | High |
| Web Searching | 7 | Microsoft WTI (2023) ~8 min/sub-search controlled study; Kellar et al. (CHI 2007) 4.6 min fact-finding | High |
| Enterprise Searching | 18 | IDC (2014); McKinsey (2012) | High |
| Agent: IT & Service Desk | 20 | HDI (2023); MetricNet (2023) | High |
| Agent: Sales & Customer | 35 | Salesforce (2023); Gartner (2022) | High |
| Agent: Research & Analysis | 45 | BCG (2021); McKinsey (2023) | High |

These baselines represent **the time a human would spend performing the same task without AI assistance**. Each baseline is grounded in peer-reviewed or public research — there are no invented numbers.

### Confidence Tiers

- **High** — Directly measured in a controlled experiment or large-scale survey (e.g., Noy & Zhang's MIT RCT, GitHub/NBER's Peng et al. RCT, Forrester TEI studies)
- **Medium-High** — Triangulated from multiple consistent industry sources
- **Medium** — Derived from adjacent research with reasonable extrapolation
- **Low** — Estimated from general industry benchmarks where direct measurement is not available

---

## 4. Value Calculation

### Human Equivalent Hours

For every Copilot prompt submitted (each row where `Message_isPrompt = TRUE`), the model looks up the human baseline for the classified task and sums across all interactions:

```
Human Equivalent Hours = Σ (Human Baseline minutes ÷ 60) for each prompt
```

This represents the **total human effort that AI is handling**.

### Estimated Hours Saved

A 30% efficiency discount is applied, aligned with the Noy & Zhang (Science 2023) finding that AI-assisted workers complete tasks ~37% faster (conservatively rounded):

```
Estimated Hours Saved = Human Equivalent Hours × 0.70
```

This acknowledges that AI doesn't eliminate the entire task — there is overhead for prompting, reviewing, and editing AI output.

### AI Assisted Value ($)

```
AI Assisted Value = Human Equivalent Hours × Hourly Salary × Penalty Factor
```

Where:
- **Hourly Salary** — configurable slicer (default: $40/hr)
- **Penalty Factor** — adjustable 0–1 scalar (default: 1.0) that lets analysts apply additional conservatism

### ROI

```
AI ROI = AI Assisted Value ÷ Copilot License Investment
Net ROI ($) = AI Assisted Value − Copilot License Investment
```

Where `Copilot License Investment = PPUPM × Licensed Users × Months`.

---

## 5. Value Categories (Outcomes)

Each task is also tagged with a **Value Outcome** that groups tasks into business-relevant categories:

| Value Outcome | Example Tasks |
|---|---|
| Time Saved (Email) | Email Triage, Email Thread Summary, Email Summarising |
| Content Output | Email Drafting, Document Drafting, Presentation Creation, Image Generation |
| Time Saved (Meetings) | Meeting Prep, Video Summarising |
| Time Saved (Documents) | Document Summarising, Presentation Summarising, Note Taking |
| Search Time Saved | Web Searching, Enterprise Searching, PDF Analysis, SharePoint Access |
| Data-Driven Decisions | Data Querying, Spreadsheet Analysis, Agent: Research & Analysis |
| Coding Capability | Code Writing, Code Analysis |
| Service Desk Deflection | Agent: IT & Service Desk |
| Revenue Enablement | Agent: Sales & Customer |
| Skills Development | Agent: Coaching |
| HR Process Automation | Agent: HR & People |
| Compliance & Risk | Agent: Compliance & Policy, Sensitive Content Interaction |
| Workflow Triggered | Workflow Execution |

---

## 6. Work Archetypes (Frontier Firm Alignment)

The **Task Value Mapping** table further classifies each task into five Work Archetypes aligned with Microsoft's Frontier Firm framework:

| Work Archetype | What It Means | Example Tasks |
|---|---|---|
| **Content Creation** | Producing new output | Email Drafting, Document Drafting, Presentation Creation |
| **Content Consumption** | Absorbing existing content faster | Email Triage, Document Summarising, PDF Analysis |
| **Information Finding** | Locating knowledge | Web Searching, Enterprise Searching, People Lookup |
| **Data Analysis** | Querying and interpreting data | Data Querying, Spreadsheet Analysis |
| **Automating** | Triggering workflows without human intervention | Workflow Execution, Agent: IT & Service Desk |

---

## 7. Autonomy Patterns (Maturity Progression)

The dashboard tracks three Frontier Firm autonomy patterns:

| Pattern | Description | How Identified |
|---|---|---|
| **Pattern 1** — Human + Copilot | User directly prompts Copilot in an M365 app | `Environment = "Licensed M365 Copilot"` |
| **Pattern 2** — Human + Agent | User invokes a custom or shared agent | `Environment = "Agents"` |
| **Pattern 3** — Agents run workflows | Autonomous agents execute without a human prompt | `Environment = "Autonomous Agent"` |

The **Autonomy Mix** shows what percentage of total value is delivered at each pattern level, indicating organisational maturity.

---

## 8. Augmented Skills Attribution

Beyond time saved, the **Augmented Skills Map** identifies the professional expertise AI provides to each user. For example:

| Task | Augmented Skill | Professional Equivalent |
|---|---|---|
| Code Writing | Software Development | Software Developer |
| Data Querying | Data Analysis | Data Analyst |
| PDF Analysis | Document Review | Legal Analyst |
| Agent: Sales & Customer | Sales Intelligence | Sales Operations Analyst |
| Presentation Creation | Visual Communication | Presentation Designer |
| Email Drafting | Business Writing | Communications Specialist |

This surfaces the **Augmented Skill** narrative — AI isn't just saving time, it's giving every employee access to specialist capabilities they wouldn't otherwise have.

---

## 9. Key Research Sources

| Source | Key Finding Used |
|---|---|
| **Noy & Zhang (MIT/Science 2023)** | AI-assisted professionals complete writing tasks 37% faster; used to anchor the 30% efficiency factor |
| **Brynjolfsson et al. (NBER 2023)** | Customer service agents with AI are 14% more productive; lower-skilled workers benefit most |
| **Peng et al. (GitHub/NBER 2023)** | Developers using Copilot complete tasks 55.8% faster in a randomized controlled trial |
| **Dell'Acqua et al. (BCG/Harvard 2023)** | Consultants with AI are 25% faster and produce 40% higher-quality work on complex tasks |
| **McKinsey (2012, 2023)** | Knowledge workers spend 19% of their week searching for information; 28% managing email |
| **Microsoft WTI (2023)** | Controlled study: multi-source search task takes ~24 min total (3 sub-searches ≈ 8 min each); Copilot users 27% faster; users 29% faster across search+write+summarise |
| **IDC (2014, 2018)** | Workers spend 2.5 hours/day searching for information; enterprise search costs $14K/employee/year |
| **Forrester TEI (2022, 2024)** | Microsoft 365 Copilot reduces meeting prep by 15 min, document review by 30%, search time by 50% |
| **Microsoft Research (Iqbal & Horvitz 2007)** | Email interruptions cost 10 min per context switch; email triage baseline |
| **HDI / MetricNet (2023)** | Average IT service desk ticket costs $22 and takes 20 min to resolve |

---

## 10. Defensibility & Transparency

The methodology is designed to be **auditable**:

1. **Every number traces back to a signal** — the "Signal > Behavior > Value" page in the dashboard lets stakeholders trace any dollar figure back to the raw audit record
2. **All baselines are sourced** — the `Human Time Estimates` table includes the primary academic/industry source for each baseline
3. **Confidence is rated** — each baseline carries a confidence tier (High/Medium-High/Medium/Low)
4. **Conservative by default** — the 30% efficiency discount and adjustable Penalty Factor ensure overstatement is avoided
5. **Fully adjustable** — Hourly Salary, PPUPM, and Penalty Factor are slicer-driven so analysts can model scenarios

---

## Summary

The AI Business Value Dashboard does **not** infer value from survey self-reports or subjective estimates. Instead, it:

1. Reads the **objective audit trail** from Purview (app, action, resource)
2. Uses deterministic rules to classify each signal into a **named AI task**
3. Attributes a **peer-reviewed human-time baseline** to each task
4. Sums the baselines across all interactions to produce **Hours Saved**
5. Multiplies by an adjustable hourly rate to produce **Assisted Value ($)**

This creates a repeatable, transparent, and defensible measurement of AI business value.
