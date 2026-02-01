# AI Content Factory – Project Plan & Operating Contract

## Project Goal & Strategic Intent

### What we are building

The AI Content Factory is a **general-purpose, spec-driven content generation system** designed to service **multiple clients**, across **multiple use cases**, using a **single, shared engine**.

It is not an affiliate engine, a blog generator, or an email writer.

It is a **content compiler**:

* Clients declare *what* they want (intent, form, persona, domain)
* The system deterministically produces content that satisfies those constraints
* Invalid or incoherent configurations fail fast

### Core objectives

1. **Serve multiple clients safely**

   * Each brand is isolated via configuration, not code
   * No client-specific forks
   * No leakage of tone, logic, or assumptions between brands

2. **Support multiple content use cases**

   * Product recommendations (affiliate and non-affiliate)
   * Thought leadership
   * Educational content
   * Digests and future formats

3. **Decouple content thinking from delivery**

   * Email, blog, LinkedIn, website, and future channels are delivery adapters
   * Delivery never changes the content’s meaning or reasoning

4. **Eliminate implicit decisions**

   * No agent infers intent, tone, persona, depth, or structure
   * All decisions are declared explicitly and validated

5. **Prioritise quality and trust over flexibility**

   * Hard fails only
   * No overrides
   * No “best effort” generation

### What success looks like

* A new client can be onboarded via YAML only
* The same engine can power:

  * an affiliate product site
  * an executive thought-leadership brand
  * a weekly email briefing
* The system scales by **adding configuration**, not code
* Content quality degrades *never silently*

---

This document is the **single source of truth** for how this project is executed by agents.
It defines **milestones, tasks, definitions of done, and operating rules**.

This file is intended to be handed directly to an agent.

---

## 0. Key Decisions (Locked)

These decisions are final unless this plan is explicitly revised.

* **Validation:** Unit tests only (v1)
* **Persistence:** BrandContextArtifact persisted as JSON on disk
* **Source fetching:** Live URL fetching is allowed (read-only)
* **HTTP User-Agent:** Deterministic and fixed to `AIContentFactoryFetcher-1.0`
* **Robots.txt compliance:** Evaluate robots for User-Agent `AIContentFactoryFetcher-1.0`; if disallowed, hard‑fail (no bypass)
* **Repo strategy:** Single repo, modularised (no fork yet)
* **Date validation:** Uses local system time (system clock); past dates hard‑fail
* **Topics:** Allowlist-only (auto-pick, if used, must choose from the allowlist)
* **Disclaimers:** Required disclaimers must be present; missing disclaimers hard‑fail
* **Products (v1):** Manual links only (no automatic product retrieval via affiliate APIs)
* **Products scope:** `products` is present only when the intent/form involves products; otherwise null/omitted
* **Thought leadership links:** Allowed; no special handling (treated as normal links/citations under the same fetch + robots rules)
* **ContentArtifact contract:** **Robust** (includes structured claims, sources, and compliance checklists)

Rationale:

* Unit tests are sufficient for a compiler-style system at this stage
* JSON artifacts provide determinism, debuggability, and cacheability
* Live fetching is required to avoid manual content drift
* Forking early adds coordination cost without upside

---

## 1. Agent Operating Rules (Non‑Negotiable)

These rules apply globally.

### 1.1 Milestone Execution

* The agent **must not start a new milestone without explicit user approval**
* At the end of each milestone, the agent must:

  * Mark all tasks as completed or not completed
  * Update this plan file to reflect completion (task checkboxes + “Next Action”)
  * Explicitly confirm the Definition of Done is met
  * List any discovered but unexecuted work

### 1.2 Git Discipline

* One milestone = one or more atomic commits
* The agent must:

  * Commit all work before requesting approval for the next milestone
  * Provide clear commit messages
  * Confirm a clean working tree
* **No work begins on the next milestone until commits are complete**

### 1.3 Scope Control

* No silent scope expansion
* If a task materially expands, the agent must:

  * Stop
  * Explain why
  * Ask for approval

### 1.4 Validation First

* Invalid config must fail **before** generation
* No inference, no auto-correction, no fallbacks

### 1.5 Progress Tracking

All tasks must be tracked using:

* `[ ]` Not started
* `[x] Completed
* `[!]` Blocked / needs decision

---

## 2. Project Milestones (Overview)

```
M1 ─ Canonical Schema & Models
M2 ─ Validation Engine
M3 ─ Brand Understanding & Source Ingestion
M4 ─ Pipeline Refactor (Spec‑Driven)
M5 ─ Delivery Adapters
M6 ─ Operational Tooling & Docs
```

Milestones are sequential and must not overlap.

---

## 3. Milestone Details

---

## 🧱 MILESTONE 1: Canonical Schema & Models

**Goal**
Define the complete, explicit mental model of the system.

### Tasks

* [x] Finalise global enums (`ai_content_factory_schema.yaml`)
* [x] Finalise illegal combinations matrix (`ai_content_factory_schema.yaml`)
* [x] Finalise Brand Profile YAML schema (`ai_content_factory_schema.yaml` + `content_factory/brands/` examples)
* [x] Finalise Content Request YAML schema (`ai_content_factory_schema.yaml` + `content_factory/requests/` examples)
* [x] Add `brand_sources` section with enums and requirements
* [x] **Define the Robust `ContentArtifact` contract (output schema)**

  * [x] Sections + blocks structure (no blob-only output)
  * [x] Products payload (conditional)
  * [x] Claims list with types + citation requirement flags
  * [x] Sources list (URL/file IDs + what they support)
  * [x] Constraints/compliance checklist (matrix + brand policy checks)
  * [x] Generation metadata (brand, intent, form, domain, persona/modifiers, depth, version, timestamps)
* [x] Add example brand configs (Alisa + Affiliate) (`content_factory/brands/`)
* [x] Add example run request (`content_factory/requests/`)
* [x] Add example ContentArtifact output JSON (`content_factory/examples/`)

### Robust ContentArtifact Contract (v1)

The ContentArtifact is the **canonical compiled output** of a run. Delivery adapters may **format** it for different channels/destinations, but must not change meaning, add claims, reorder reasoning, or invent content.

#### Top-level fields

* `artifact_version` (string): Contract version (e.g. `"1.0"`).
* `brand_id` (string)
* `run_id` (string): Unique run identifier.
* `generated_at` (ISO timestamp)

#### Spec metadata (echo of inputs)

* `intent` (enum)
* `form` (enum)
* `domain` (enum)
* `content_depth` (enum, fixed per brand)
* `audience`:

  * `primary_audience` (enum)
  * `audience_sophistication` (enum)
* `persona`:

  * `primary_persona` (enum)
  * `persona_modifiers` (list[enum])
  * `science_explicitness` (enum)
  * `personal_presence` (enum)
  * `narration_mode` (enum)

#### Structured content (required)

* `sections` (list[Section])

Section

* `id` (string): Stable identifiers such as `intro`, `how_chosen`, `picks`, `alternatives`, `closing`.
* `heading` (string | null)
* `blocks` (list[Block])

Block

* `type` (enum): `paragraph` | `bullets` | `numbered` | `callout` | `quote` | `divider`
* `text` (string | null): For paragraph/callout/quote.
* `items` (list[string] | null): For bullets/numbered.
* `meta` (dict | null): Optional formatting hints (never required for meaning).

#### Products (conditional)

* `products` (list[Product] | null): Present only when intent involves products.

In v1, product entries (including URLs) must be provided explicitly as manual inputs.

Product

* `pick_id` (string)

* `title` (string)

* `url` (string)

* `rating` (float | null)

* `reviews_count` (int | null)

* `provider` (string | null)

* `pick_copy` (dict[pick_id, list[Block]] | null): Copy blocks mapped to each pick.

#### Publishable rationale (required when applicable)

* `rationale`:

  * `how_chosen_blocks` (list[Block])
  * `selection_criteria` (list[string])

This is **not** chain-of-thought. It is publishable, reader-facing reasoning (e.g. “How this list was chosen”, “Skip it if…” criteria).

#### Claims (robust QA support)

* `claims` (list[Claim])

Claim

* `id` (string)
* `text` (string)
* `claim_type` (enum): `fact` | `inference` | `opinion` | `advice`
* `requires_citation` (bool)
* `supported_by_source_ids` (list[string])

#### Sources (for traceability)

* `sources` (list[Source])

Source

* `source_id` (string)
* `kind` (enum): `url` | `file`
* `ref` (string): URL or file path
* `purpose` (enum): aligns with `brand_sources.source_purpose`
* `notes` (string | null)

#### Compliance & validation checklist (hard-fail expectations)

* `checks`:

  * `matrix_validation_passed` (bool)
  * `brand_policy_checks_passed` (bool)
  * `required_sections_present` (bool)
  * `products_present_when_required` (bool)
  * `citations_present_when_required` (bool)
  * `topic_allowlist_passed` (bool)
  * `required_disclaimers_present` (bool)
  * `robots_policy_passed` (bool)
  * `disallowed_claims_found` (list[string])

Adapters must refuse to render if `checks.*_passed` is false.

### Definition of Done

* Brand and request files can be validated without running generation
* No implicit defaults exist
* All enums are documented
* Example configs are valid

---

## 🧪 MILESTONE 2: Validation Engine

**Goal**
Fail fast with precise, human‑readable errors.

### Tasks

* [x] Implement Pydantic models for all schemas (`content_factory/models.py`)
* [x] Enum enforcement everywhere
* [x] Illegal matrix validation (`content_factory/validation.py` + `ai_content_factory_schema.yaml`)
* [x] Brand source requirement validation (`content_factory/models.py`)
* [x] Domain → persona validation (`content_factory/validation.py`)
* [x] Unit tests for valid and invalid configs (`tests/test_content_factory_validation.py`)

### Definition of Done

* No invalid config reaches any agent
* Errors point to exact fields
* Matrix violations are explicit
* Date fields are validated against local system time
* Topic selection is validated as allowlist-only
* Unit tests cover all failure classes

---

## 🧠 MILESTONE 3: Brand Understanding & Source Ingestion

**Goal**
Convert raw brand sources into a deterministic BrandContextArtifact.

### Why live URL fetching is required

* Brand sites evolve
* Manual copy/paste drifts silently
* Authority content must reflect current positioning

### Tasks

* [x] Define `BrandContextArtifact` schema (`content_factory/brand_context.py`)
* [x] Implement source loader (public URLs + local files) (`content_factory/brand_context.py`)
* [x] Enforce `robots.txt` compliance per configured User-Agent (hard-fail on disallow)
* [ ] Extract:

  * key terminology
  * positioning statements
  * allowed / disallowed claims
  * voice signals
* [x] Extract:

  * key terminology
  * positioning statements
  * allowed / disallowed claims (v1: placeholder signals only)
  * voice signals (v1: lightweight HTML-derived signals)
* [x] Persist artifact as JSON per brand (`content_factory/brand_context.py`)
* [x] Manual refresh only (v1) (`scripts/build_brand_context.py`)

### Definition of Done

* Writing agents never read raw URLs
* Brand understanding is cached and repeatable
* Missing, unreachable, or robots.txt‑disallowed sources hard‑fail (evaluated for `AIContentFactoryFetcher-1.0`)

---

## 🔁 MILESTONE 4: Pipeline Refactor (Spec‑Driven)

**Goal**
Remove all implicit logic from the content pipeline.

### Tasks

* [ ] Refactor pipeline to accept Brand + Request only
* [ ] Deterministic intent → form → persona routing
* [ ] Inject BrandContextArtifact into agents
* [ ] Remove agent‑side guessing
* [ ] Update QA and repair agents to validate against specs

### Definition of Done

* Same inputs always produce same outputs
* Agents never choose tone, depth, or structure
* Pipeline is entirely declarative

---

## 📦 MILESTONE 5: Delivery Adapters

**Goal**
Decouple generation from formatting and destinations.

### Dependency

* Depends on Robust `ContentArtifact` contract defined in Milestone 1

### Tasks

* [ ] Define `ContentArtifact` output contract
* [ ] Blog adapter (Astro‑compatible markdown)
* [ ] Email adapter (plain + HTML‑ready)
* [ ] LinkedIn adapter (long‑form text)
* [ ] Enforce destination rules from matrix

### Definition of Done

* One ContentArtifact feeds all adapters
* Adapters never rewrite meaning or tone
* Destination constraints are enforced

---

## 🛠️ MILESTONE 6: Operational Tooling & Docs

**Goal**
Make the system usable and safe.

### Tasks

* [ ] CLI: validate brand files
* [ ] CLI: validate run requests
* [ ] CLI: execute a run
* [ ] Onboarding documentation
* [ ] Error reference guide
* [ ] Project README

### Definition of Done

* A new brand can be onboarded without code changes
* Invalid configs fail before runtime
* Docs reflect actual behaviour

---

## 🧾 MILESTONE 7: Affiliate API Product Automation (Backlog)

**Goal**
Enable optional automatic product retrieval/enrichment via affiliate APIs.

This milestone is explicitly **not required** for v1, which remains manual links only.

### Tasks

* [ ] Define a provider-agnostic affiliate API interface (search, lookup, pricing/availability metadata)
* [ ] Implement first provider adapter(s) behind that interface (auth, rate limits, retries, caching)
* [ ] Add “product enrichment” step to turn manual seeds into structured `Product` fields
* [ ] Add deterministic test fixtures + unit tests for API adapters (no live network in tests)
* [ ] Add config switches to keep v1 behavior defaulting to manual links only (API automation opt-in)

### Definition of Done

* Affiliate API automation can be enabled explicitly (opt-in)
* Manual-links-only remains the default behavior
* Unit tests cover adapter behavior without live network calls

---

## 4. Rules for Plan Evolution

* This plan is **living but controlled**
* If new tasks or milestones are discovered:

  * They must be added here
  * Marked as *added*
  * Approved before execution

---

## 5. Next Action

Await explicit approval to begin:

**→ Approve Milestone 4**

No work will start before approval.
