# Project Plan — The Product Wheel (Astro site)

## Rules (how this plan is updated)

This file is the source of truth for project status.

Update rules (strict):
1) Use GitHub-style checkboxes for all actionable items: `- [ ]` / `- [x]`.
2) Never delete tasks. If something is no longer relevant, mark it `- [x]` and add a log entry noting "closed as obsolete" (with rationale).
3) Never rewrite history: tasks/milestones may be appended, but existing task text should not be edited except:
	- changing checkbox state,
	- adding a short "(superseded by M#-T#)" note at the end of the line.
4) Every time you mark anything done, append exactly one entry to the Activity Log with:
	- date (YYYY-MM-DD),
	- what changed (milestone/task IDs),
	- evidence (file paths and/or commands run).
5) A task may be checked off only if its Definition of Done is met and evidence is recorded.
6) New work is added by appending: new milestone at the end, or new tasks at the end of an existing milestone’s task list.
7) Keep milestones ordered oldest → newest. Keep the Activity Log append-only, oldest → newest.
8) Brand rule: always use “The Product Wheel” for visible name and meta `og:site_name`.

## Milestone Template

Use milestone IDs `M1`, `M2`, … and task IDs `M1-T1`, `M1-T2`, … so updates are unambiguous.

Template:

## Milestone M<N>: <short name>

**Goal:** <1–2 sentences>

**Definition of Done**
- [ ] DoD-1: <observable outcome>
- [ ] DoD-2: <observable outcome>
- [ ] DoD-3: <validation outcome>

**Tasks**
- [ ] M<N>-T1: <task> (owner: agent|human) (estimate: S|M|L)
- [ ] M<N>-T2: <task> (owner: agent|human) (estimate: S|M|L)

**Notes**
- Dependencies:
- Risks:

## Milestones

## Milestone M1: Brand Unification (The Product Wheel)

**Goal:** Ensure “The Product Wheel” is the only brand name visible across the site and metadata defaults.

**Definition of Done**
- [ ] DoD-1: No remaining old brand/domain strings in site UI (header/footer/nav) across home, /posts, a category page, and a post page.
- [ ] DoD-2: Default metadata uses “The Product Wheel” (at minimum page titles and `og:site_name` defaults).
- [ ] DoD-3: Site builds successfully.

**Tasks**
- [x] M1-T1: Create a single source of truth for brand name (e.g., a constant) and use it in layouts/components. (owner: agent) (estimate: S)
- [x] M1-T2: Replace/clean up any remaining old brand strings in the site. (owner: agent) (estimate: S)
- [x] M1-T3: Run `npm run build` (or equivalent) for the Astro site and fix any errors introduced. (owner: agent) (estimate: S)

**Notes**
- Dependencies:
- Risks: low; mostly string/constants changes.

## Milestone M2: Metadata Foundation (title/desc/canonical/OG/Twitter)

**Goal:** Provide consistent, correct SEO/social metadata for all pages (home, listings, categories, posts).

**Definition of Done**
- [ ] DoD-1: Every page has a correct `<title>` and meta description (with sane defaults and per-page overrides).
- [ ] DoD-2: Canonical URLs are present and consistent.
- [ ] DoD-3: OG + Twitter tags are present (including image where applicable).

**Tasks**
- [x] M2-T1: Add a reusable SEO/head helper (layout or component) with sane defaults. (owner: agent) (estimate: M)
- [x] M2-T2: Wire the helper into home, /posts, category pages, and Post layout. (owner: agent) (estimate: M)
- [x] M2-T3: Validate output HTML for at least one page of each type. (owner: agent) (estimate: S)

## Milestone M3: Structured Data (JSON-LD)

**Goal:** Add JSON-LD to improve search features and clarify site structure.

**Definition of Done**
- [ ] DoD-1: Post pages include Article + BreadcrumbList JSON-LD.
- [ ] DoD-2: /posts and category pages include CollectionPage + ItemList JSON-LD.
- [ ] DoD-3: JSON-LD validates (basic sanity: valid JSON, expected fields present).

**Tasks**
- [x] M3-T1: Implement JSON-LD generators for posts and listings. (owner: agent) (estimate: M)
- [x] M3-T2: Integrate into relevant layouts/pages. (owner: agent) (estimate: S)

## Milestone M4: Affiliate Trust + Conversion UX (no comparison table)

**Goal:** Improve disclosure placement and make product CTAs clearer without changing content structure.

**Definition of Done**
- [ ] DoD-1: Affiliate disclosure is visible before the first outbound product CTA and remains accessible near CTAs.
- [ ] DoD-2: Outbound affiliate links use appropriate `rel` attributes (e.g., `sponsored nofollow`).
- [ ] DoD-3: “Jump to picks” affordance exists for long posts and is keyboard accessible.

**Tasks**
- [x] M4-T1: Adjust disclosure placement for Post layout (above picks/first CTA). (owner: agent) (estimate: S)
- [x] M4-T2: Normalize outbound link attributes for affiliate CTAs. (owner: agent) (estimate: S)
- [x] M4-T3: Add a “Jump to picks” CTA (sticky or prominent) with a target anchor. (owner: agent) (estimate: M)
- [x] M4-T4: Widen the inline affiliate disclosure callout on post pages. (owner: agent) (estimate: S)

## Milestone M5: Taxonomy + Discovery

**Goal:** Improve browsing and reduce dead ends (empty categories), plus add related content navigation.

**Definition of Done**
- [ ] DoD-1: Empty categories are hidden from nav/footers and category listings.
- [ ] DoD-2: Post pages include Related guides and Next/Previous navigation.
- [ ] DoD-3: /posts page supports quick filtering or search (minimum viable UX).

**Tasks**
- [x] M5-T1: Hide categories with zero posts in UI lists. (owner: agent) (estimate: S)
- [x] M5-T2: Implement Related guides (same category + recent). (owner: agent) (estimate: M)
- [x] M5-T3: Add Next/Previous navigation on posts. (owner: agent) (estimate: S)
- [x] M5-T4: Add basic filter/search on /posts (client-side OK). (owner: agent) (estimate: M)

## Milestone M6: Accessibility + Polish Pass

**Goal:** Ensure strong baseline accessibility and consistent UI polish.

**Definition of Done**
- [ ] DoD-1: Single H1 per page, sensible heading order, and working skip link.
- [ ] DoD-2: Visible focus states for interactive elements.
- [ ] DoD-3: Hero images have appropriate `alt` and sizing/lazy-loading where appropriate.

**Tasks**
- [x] M6-T1: Audit and fix heading hierarchy + skip-link behavior. (owner: agent) (estimate: S)
- [x] M6-T2: Improve focus states and link affordances. (owner: agent) (estimate: S)
- [x] M6-T3: Ensure images have width/height and reasonable loading strategy. (owner: agent) (estimate: S)

## Milestone M7: Post-launch Backlog (Growth + Quality)

**Goal:** Add the next wave of improvements that increase traffic, trust, and conversion without changing the core content model.

**Definition of Done**
- [ ] DoD-1: Priority “traffic foundations” items (robots/sitemap/canonicals) are verified on production.
- [ ] DoD-2: One measurable conversion/engagement improvement shipped (analytics event or CTA experiment).
- [ ] DoD-3: No regressions in build or accessibility baselines.

**Tasks**
- [ ] M7-T1: Set `SITE_URL` in Vercel env and verify canonical + JSON-LD URLs are production-correct. (owner: human) (estimate: S)
- [ ] M7-T2: Add `robots.txt` and `sitemap.xml` (or Astro integration) and verify in production. (owner: agent) (estimate: M)
- [ ] M7-T3: Add lightweight analytics (Plausible/Umami) + track key events (CTA clicks, Jump to picks). (owner: agent) (estimate: M) (superseded by M7-T9)
- [ ] M7-T4: Fix card/category label consistency (e.g., avoid duplicate/alias category pills across lists). (owner: agent) (estimate: M)
- [ ] M7-T5: Add “Last updated” on posts and include `dateModified` visible on page. (owner: agent) (estimate: S)
- [ ] M7-T6: Add RSS feed for guides. (owner: agent) (estimate: M)
- [ ] M7-T7: Add OpenGraph image strategy (default OG image + per-post OG where missing). (owner: agent) (estimate: M)
- [ ] M7-T8: Performance pass (Lighthouse: LCP/CLS) and fix top offenders. (owner: agent) (estimate: M)
- [x] M7-T9: Embed Google Analytics 4 (GA4) via `gtag.js` in the site layout (env-driven + prod-only). (owner: agent) (estimate: S)
- [ ] M7-T10: Verify GA4 receives page_view + track key engagement events (affiliate CTA click, “Jump to picks”). (owner: agent) (estimate: M)
- [x] M7-T11: Collapse bottom-of-post navigation to a single “More guides” section. (owner: agent) (estimate: S)
- [x] M7-T12: Tighten guide card spacing on /posts (reduced vertical gaps). (owner: agent) (estimate: S)
- [x] M7-T13: Improve post content heading styles (make “Intro” and other H2/H3 less muted). (owner: agent) (estimate: S)
- [x] M7-T14: Add a /cookies page with a “reset preferences” control. (owner: agent) (estimate: S)
- [x] M7-T15: Add cookie consent banner (bottom) that gates analytics loading. (owner: agent) (estimate: M)
- [x] M7-T16: Track all outbound link clicks (after consent) via a single delegated click handler. (owner: agent) (estimate: M)
- [x] M7-T17: Set `PUBLIC_GA_MEASUREMENT_ID` in Vercel (Production + Preview if desired). (owner: human) (estimate: S)
- [ ] M7-T18: Deploy latest site changes and verify `/cookies` resolves + cookie banner appears on production. (owner: human) (estimate: S)
- [ ] M7-T19: Fix prod GA env injection (ensure `const GA_ID = "G-..."` in page source) and redeploy. (owner: human) (estimate: S)

---

## Activity Log (append-only)

- 2026-01-31 — agent — Initialized plan file — Evidence: PROJECT_PLAN.md
- 2026-01-31 — agent — Completed: M1-T1, M1-T2, M1-T3 — Evidence: site/src/content/site/taxonomy.json, site/src/layouts/SiteLayout.astro, site/package.json, site/scripts/validate_content.mjs, `npm run build`
- 2026-01-31 — agent — Completed: M2-T1, M2-T2, M2-T3 — Evidence: site/src/layouts/SiteLayout.astro, site/src/pages/index.astro, site/src/pages/posts/index.astro, site/src/pages/posts/[...slug].astro, site/astro.config.mjs, `npm run build`
- 2026-01-31 — agent — Completed: M3-T1, M3-T2 — Evidence: site/src/lib/structuredData.ts, site/src/pages/posts/[...slug].astro, site/src/pages/posts/index.astro, site/src/pages/posts/[group].astro, site/src/pages/category/[category].astro, `npm run build`
- 2026-01-31 — agent — Completed: M4-T1, M4-T2, M4-T3 — Evidence: site/src/pages/posts/[...slug].astro, site/src/layouts/PostLayout.astro, site/src/components/ProductTable.astro, site/src/components/ProductCard.astro, site/src/components/ProductListItem.astro, `npm run build`
- 2026-01-31 — agent — Completed: M5-T1, M5-T2, M5-T3, M5-T4 — Evidence: site/src/pages/index.astro, site/src/pages/posts/index.astro, site/src/pages/posts/[...slug].astro, site/src/components/TopTopicsNav.astro, `npm run build`
- 2026-01-31 — agent — Completed: M6-T1, M6-T2, M6-T3 — Evidence: site/src/pages/index.astro, site/src/styles/global.css, site/src/layouts/PostLayout.astro, `npm run build`
- 2026-01-31 — agent — Completed: M4-T4 — Evidence: site/src/layouts/PostLayout.astro, site/src/pages/posts/[...slug].astro, `npm run build`
- 2026-01-31 — agent — Completed: M7-T11, M7-T12, M7-T13 — Evidence: site/src/pages/posts/[...slug].astro, site/src/pages/posts/index.astro, site/src/layouts/PostLayout.astro, `npm run build`
- 2026-01-31 — agent — Completed: M7-T9, M7-T14, M7-T15, M7-T16 — Evidence: site/src/layouts/SiteLayout.astro, site/src/pages/cookies.astro, `npm run build`
- 2026-01-31 — agent — Completed: M7-T17 — Evidence: user confirmed Vercel env var `PUBLIC_GA_MEASUREMENT_ID` set
- 2026-01-31 — agent — Completed: M7-T18 — Evidence: `git push`, `Invoke-WebRequest https://theproductwheel.com/`, `Invoke-WebRequest https://theproductwheel.com/cookies`
- 2026-01-31 — agent — Correction: Re-opened M7-T18; added M7-T19 — Evidence: `Invoke-WebRequest https://theproductwheel.com/` shows `const GA_ID = ""` (banner stays hidden)
