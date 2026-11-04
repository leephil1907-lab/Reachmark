# Reachmark evaluation: reusable agent-skill library

**Evaluation date:** 2026-11-04  
**Repository baseline:** `main` at `802bde2290907f1af724f1a3728f479f559d18fd`  
**Scope:** Evaluate the six skills against the existing Reachmark codebase without changing production UI, application code, dependencies, or deployment configuration.

## Executive result

The library is useful, but it should be treated as a **selective toolkit**, not installed wholesale as a second agent framework.

Reachmark already has a runtime playbook system at `skills/vendor/`, loaded by `crew/skills_loader.py`. Its current catalogue includes cold-email, copywriting, CRO, prospecting, AI SEO, SEO audit, Brag, and Chief. The new library's strongest incremental value is frontend/design critique and disciplined minimal-diff engineering. Several of its skills overlap with existing checks or are only useful for narrow deliverables.

**No production files were changed during this evaluation.** This report is the only proposed repository change.

## Baseline evidence

- The project is a Flask + React + SQLite application. The public site is assembled from Jinja templates and a substantial set of dedicated CSS files.
- The homepage uses the existing Reachmark design stack: `fonts.css`, `header.css`, `motion.css`, `xdesign.css`, and `home-product.css`.
- The codebase has no root `DESIGN.md`, `design.md`, `PRODUCT.md`, or `AGENTS.md` in the inspected tree. The existing implementation and brand assets therefore remain the practical source of visual truth.
- The project already tests design behavior: reduced-motion support, component hooks, responsive header behavior, public-page navigation, pricing parity, no dead hash links, and public-claim integrity.
- The CI workflow includes frontend build, pytest, mobile/PWA audit, JavaScript syntax checks, Playwright browser flows, crew smoke tests, Lighthouse mobile/desktop audits, release gates, and Docker build.
- GitHub Actions on the inspected baseline reported **Test and build: success** and **Reachmark Release Gate: success**. The production deploy workflow was skipped for that commit; this evaluation does not claim a new deployment or a live-site browser test.
- Existing vendored playbooks are documented as unmodified MIT copies (with provenance in `skills/vendor/VENDOR.json`) and are read as prompt context, not executed as code.

## Six-skill assessment

| Skill | Reachmark fit | Result | Recommended use |
|---|---|---|---|
| Ponytail | High | Adopt as the default engineering review discipline | Before code changes: inspect callers, tests and fixtures; prefer the smallest complete diff; add focused tests for non-trivial logic. This reinforces Reachmark's existing test-first/release-gate approach. |
| Impeccable | High, with constraints | Use for UI critique and targeted refinement | Use its Operate mode for dashboard/admin screens and Persuade mode for public conversion pages. Preserve the existing Reachmark identity and behavior. Read its craft-floor guidance before any UI edit. |
| Taste Skill | Medium-high | Useful second opinion, not a replacement design system | Use for structured visual review at mobile/tablet/desktop widths and screenshot-based critique. Do not blindly run its direction generator or replace current tokens, typography, or page composition. |
| Hallmark | Conditional / low for this task | Do not activate on existing pages by default | Its own instructions say not to run on an existing design unless Hallmark is explicitly named. It is suitable for a separately authorized redesign, not routine Reachmark maintenance. |
| Answer Me With HTML | Low for this repository task | Not needed | Useful when a user explicitly needs a standalone visual explainer. Its bundled CLI is not part of Reachmark's app architecture and should not be added as a runtime dependency. |
| Anatomy | Low / specialist | Not needed for the current product review | Reserve for a specifically requested technical isometric illustration. It would add complexity without improving the current audit, SEO, billing, or lead workflow. |

## Practical test: what these skills change in Reachmark work

### 1. Engineering changes

Ponytail provides a strong check against unnecessary refactors. For Reachmark, that means:
- reuse the current Flask route/service and frontend patterns;
- avoid introducing another UI framework, CSS system, or skill loader;
- inspect all callers and relevant tests before touching shared functions;
- do not weaken auth, CSRF, payment verification, approval gates, rate limits, or data isolation in the name of simplifying code;
- keep any non-trivial logic change paired with a focused test.

**Value:** high. It directly supports the project's preference for small, safe changes.

### 2. Public website and workspace design

Impeccable and Taste Skill both offer useful critique methods, but they must be constrained by Reachmark's incumbent design:
- preserve the charcoal/lime palette, logo, typography, navigation, copy, and working interactions unless the task explicitly authorizes a change;
- review the actual rendered page rather than redesigning from source inspection alone;
- check the public conversion path (homepage → live audit → report/signup/pricing) and workspace task completion separately;
- verify mobile and desktop behavior, keyboard focus, reduced motion, contrast, and real content density;
- do not invent testimonials, performance figures, customer counts, or case studies.

**Value:** high for a deliberate review pass; low if used to generate an unsolicited redesign.

### 3. SEO and growth

The six-skill bundle is not a replacement for Reachmark's existing SEO playbooks. The repository already contains `ai-seo` and `seo-audit` under `skills/vendor/`, and the crew loader assigns them to the relevant agents. Keep those as the canonical runtime playbooks unless a deliberate migration is approved.

The external bundle can still help critique public-page structure and content clarity, but it should not create duplicate SEO instructions or add unverified AI-search claims.

**Value:** incremental, not foundational.

## Recommended operating policy

1. **Use Ponytail by default for code work.**
2. **Use Impeccable for requested UI reviews/refinements**, with an explicit preserve-existing-design constraint.
3. **Use Taste Skill selectively** when a visual critique needs a second structured rubric or multi-width screenshot review.
4. **Do not invoke Hallmark** for ordinary edits to existing Reachmark pages.
5. **Do not install Answer Me With HTML or Anatomy into the production application.** Keep them as optional authoring tools.
6. **Do not replace `skills/vendor/` or `crew/skills_loader.py`.** The current runtime playbook system already has clear provenance and domain-specific agent assignments.
7. Before any actual UI modification, capture the current state, identify the exact scope, and run the existing CI/release checks. Do not merge a visual change solely because a skill recommends it.

## What was not tested

- The skills' local scripts were not executed in a checked-out runtime, so no claim is made that Hallmark's sloplint, Taste Skill's browser inspector, Impeccable's CLI, or Anatomy audits passed.
- The production website was not verified in a real browser during this evaluation.
- No Paystack transaction, outbound email, live lead discovery, or production database mutation was attempted.
- The reported GitHub Actions results are for the existing baseline commit, not a newly run pipeline for this report branch.

## Final verdict

**Keep the library. Use it selectively.** Ponytail + Impeccable are the most valuable additions for Reachmark; Taste Skill is a useful optional visual-review companion. The remaining three are specialist tools, not everyday dependencies.

The biggest benefit is better decision discipline and review quality—not adding more code, more dependencies, or a new runtime skill system.
