# Reachmark Digital — AI Outbound Lead Generation & Booking Blueprint

**Status:** architecture proposal; not a claim that every provider is connected or production-tested.  
**Existing application:** Flask/Python, React/esbuild, SQLite on Railway `/data/reachmark.sqlite3`, single production replica, existing lead directory, website checks, outreach composer/outbox, campaign/provider abstraction, webhook handling, booking routes, and Paystack billing. Preserve these capabilities and extend them incrementally.

## 1. Product outcome

A customer submits their own website URL and a target-customer profile. Reachmark reads the submitted website, extracts the customer's offer and ideal customer profile (ICP), discovers relevant businesses and decision-makers, enriches and verifies records, prepares evidence-led personalized outreach, sends only through an explicitly connected and enabled provider, detects replies, and routes interested prospects to a booking page. Every stage is observable in the Reachmark CRM.

The user's website URL is the **client/business being marketed**, not automatically a prospect. Reachmark must distinguish:
- **Client profile:** the user/business whose services are being sold.
- **Prospect account:** a business that might buy those services.
- **Prospect contact:** a person at that account.
- **Opportunity:** a potential engagement and its stage.
- **Campaign:** a configured outreach plan with one delivery provider.

Do not infer guaranteed revenue, fabricate website defects, or send automatically just because a URL was submitted. Default to preview → user approval → controlled launch.

## 2. Recommended provider stack

| Concern | Preferred integration | Alternate / notes |
|---|---|---|
| Prospect discovery | Apollo API: company search and people search | Reachmark's existing Maps/Places discovery remains useful for local SMBs. Use explicit filters for country, industry, headcount, role and domain. |
| Enrichment and personalization | Clay tables, enrichment waterfalls, Claygent/AI columns, and supported Clay-to-CRM/API/webhook actions | Confirm the customer's Clay plan exposes the specific integration/API action required. Clay's UI/workflow capabilities and public API availability are not interchangeable; keep an adapter boundary and support CSV/manual import as fallback. |
| Email execution | Instantly API v2 | Smartlead API v1 as a selectable alternative. One Reachmark campaign must use exactly one execution provider. |
| Booking | Calendly API v2, embed, and webhooks | Chili Piper if the customer needs enterprise routing / qualification rules and its API access is available on their plan. Start with a per-workspace booking URL and Calendly event webhooks. |
| Workflow engine | Existing Flask services + durable database-backed jobs initially | Add Redis + RQ/Celery or a managed queue when volume requires retries/concurrency; do not add infrastructure before the current single-worker workflow is reliable. |
| AI generation | Existing AI adapter / configured model provider | Require structured JSON output and evidence references; redact unnecessary personal data. |
| Monitoring | Structured logs, Sentry, `/healthz`, deployment SHA, external uptime check | Alert on failed jobs, provider auth errors, rising bounces, webhook failures and backup failure. |

### API references and integration notes

- Apollo base: `https://api.apollo.io/api/v1`; API key in `x-api-key`. Use `POST /mixed_companies/search` for organizations and the current Apollo people-search endpoint documented for the account; use organization/person enrichment only where needed and budget credits. Respect pagination, rate limits and provider terms.
- Instantly API v2: base `https://api.instantly.ai/api/v2`; use a scoped API key with `Authorization: Bearer …`. Use provider API operations to validate accounts, create/manage campaigns, add leads, pause leads/campaigns, read analytics, manage blocklists and configure webhooks. Pin the API version and verify exact request schemas against the account's current API reference.
- Smartlead API v1: base `https://server.smartlead.ai/api/v1`; current documentation describes `api_key` query authentication. Keep the key server-side, redact it from URLs/logs, and never expose it to browser JavaScript. Use the documented campaigns, sequences, leads, email accounts, statistics, unsubscribe and webhook endpoints.
- Calendly API v2: use a personal access token for a single-user connection or OAuth for multi-user/customer connections. Create webhook subscriptions for invitee-created, invitee-canceled and routing-form-submission events. Validate webhook signatures and deduplicate by event ID.
- Clay: prefer its supported native integrations and configured table/workflow webhook actions. Before coding against a purported public Clay endpoint, verify it is the correct Clay sales-enrichment product, is available on the customer's plan, and is documented for table/row writes. Do not build against similarly named unrelated APIs.

All provider calls must go through server-side adapter modules. Keep secrets in Railway environment variables or a secrets manager; encrypt persisted OAuth refresh tokens/API credentials if they must be stored per workspace.

## 3. Target architecture

```text
Browser / PWA
  └─ Flask routes + session/CSRF/auth + plan/tenant guard
       ├─ Website intake + safe URL probe
       ├─ ICP/profile extractor ── AI adapter (structured JSON)
       ├─ Workflow/job coordinator ── durable job records + retry policy
       │    ├─ Discovery adapter ── Apollo / existing Maps-Places
       │    ├─ Enrichment adapter ── Clay / provider fallback / CSV
       │    ├─ Validation + dedupe + suppression gate
       │    ├─ Evidence-led personalization + human approval
       │    ├─ Campaign adapter ── Instantly v2 OR Smartlead v1
       │    └─ Booking adapter ── Calendly v2 OR Chili Piper
       ├─ Webhook receiver ── signature/shared-secret validation
       ├─ CRM timeline, pipeline, booking and campaign metrics
       └─ SQLite on /data (current); PostgreSQL + queue when scaling
```

Keep the existing app modular; do not split into microservices yet. The single-replica SQLite deployment is appropriate for a small pilot only if writes remain short, backups are verified, and job execution is coordinated. For multiple workers/replicas or high concurrent webhook traffic, migrate to PostgreSQL with transactions, unique constraints and a durable queue before scaling.

## 4. End-to-end workflow

### A. Website intake
1. User enters `website_url`, target geography, service/offer, industries, company size, buyer roles, language, monthly send budget, booking link, and preferred email provider.
2. Normalize the URL; allow only public HTTP/HTTPS. Block localhost, private/link-local IP ranges, cloud metadata addresses, non-HTTP schemes, and DNS rebinding/redirects to private IPs. Limit redirects, timeout, response size and content type. This is an SSRF boundary.
3. Run the existing website probe. Save timestamped observations (HTTP status, final URL, title, visible copy, service signals and evidence URLs). Treat a failed fetch as “not measured,” not as proof of a defect.
4. Generate a draft client profile and ICP in validated JSON. User edits and confirms before discovery.

### B. Prospect discovery
5. Convert ICP to explicit Apollo filters (industry, country/region, employee range, seniority/job title, technologies or keywords where supported). Search company records, then decision-makers; page with provider limits and store source/provider IDs.
6. Optionally run Reachmark's current Google Places/Maps and other supported local discovery for local businesses. Normalize domains and company names.
7. Dedupe by normalized email, domain + company, provider IDs, and fuzzy name/location match. Preserve provenance and `source_seen_at`, plus `last_enriched_at`; never silently overwrite a newer verified value with stale data.
8. Enforce per-workspace plan limits, provider credit budgets and per-job caps. Stop on rate-limit exhaustion and surface a clear partial-result state.

### C. Enrichment and scoring
9. Send selected records to Clay via a supported table/import/workflow integration. Enrich company size, industry, role, website signals and email verification only where needed. Use conditional enrichment to avoid spending credits on duplicates or low-fit records.
10. Normalize Clay results back into Reachmark using an idempotent import/webhook. Keep each field's source, timestamp and confidence; distinguish verified provider data from AI inference.
11. Score fit and evidence separately. Example explainable score: ICP fit 0–40, decision-maker relevance 0–25, evidence-backed opportunity 0–25, data completeness 0–10. Do not treat missing evidence as a positive signal. Save reasons, not just a total score.

### D. Draft, approve and launch
12. Generate an email using only sourced facts and a specific, relevant reason for contacting the prospect. Include a useful observation, offer, low-friction CTA, sender identity and required opt-out. Reject invented metrics, false familiarity, unsupported claims and generic fake personalization.
13. Display preview with evidence links, contact source, confidence, planned sequence, send window, mailbox identity, estimated volume and opt-out. Require user approval to launch; persist approver and timestamp.
14. Before adding a lead to any provider, run a final send gate: suppression list, opt-out history, bounced/invalid status, duplicate campaign membership, tenant ownership, jurisdiction policy, valid sender identity, approved copy, provider account health, daily caps and campaign state.
15. Push only approved leads to the selected provider with stable Reachmark IDs in custom fields. Store provider campaign/lead IDs. The provider controls delivery and schedules; Reachmark remains system of record for CRM stage and suppression.
16. Begin with a small, consented pilot and conservative sending caps. A “warmed” mailbox is not a bypass for mailbox-provider policies; monitor bounces, complaints and replies, and pause automatically when thresholds are exceeded.

### E. Replies, booking and CRM
17. Provider webhooks enter a single HTTPS receiver. Validate signature/shared secret where supported, validate schema, store the raw event safely, and deduplicate using provider event ID or a deterministic hash. Queue processing and return quickly.
18. Normalize events to `sent`, `bounced`, `reply_received`, `unsubscribe`, `interested`, `out_of_office`, `meeting_booked`, etc. Reply, unsubscribe, hard bounce and complaint events immediately pause or suppress the prospect across future campaigns. Auto-replies should not be classified as positive intent.
19. For a positive reply, create a CRM task and send the prospect to the workspace's approved Calendly/Chili Piper booking link. Do not claim a meeting exists until the booking provider confirms it.
20. Calendly webhooks update booking state on invitee-created/canceled; dedupe event IDs and handle reschedules as cancel + create or the provider's documented event type. Store event URI, start/end, timezone, status and associated Reachmark prospect/campaign.
21. Update pipeline and analytics: discovered → enriched → approved → queued → contacted → replied → qualified → booked → attended → won/lost. Track denominator definitions and attribution explicitly.

## 5. DNS and sender authentication

Use a dedicated, brand-consistent outbound subdomain (for example `mail.reachmarkdigital.xyz` or a separate customer-owned sending domain) rather than changing the website's DNS or mixing marketing with transactional mail. Choose the final domain only after sender/provider setup.

1. **SPF:** publish one SPF TXT record at the exact sending domain, including all legitimate sending services. Never publish multiple SPF records at the same hostname; merge provider includes according to each provider's current instructions. Keep within SPF DNS-lookup limits.
2. **DKIM:** enable signing in each sender/provider and publish every selector TXT/CNAME record it gives you. Use 2048-bit keys where supported. Verify messages are signed by the expected domain.
3. **DMARC:** start with a monitored policy such as `v=DMARC1; p=none; rua=mailto:dmarc-reports@YOUR-REPORTING-DOMAIN; adkim=s; aspf=s; pct=100` after creating a real monitored reporting mailbox. Tight alignment is optional; choose based on sender configuration. Review reports, fix all legitimate senders, then move gradually to `quarantine` and `reject` when safe. Do not copy the placeholder literally.
4. **Alignment:** ensure the visible From domain aligns with the SPF-authenticated envelope domain or DKIM signing domain. Provider defaults may use a different bounce domain; configure custom tracking/return-path domains where supported.
5. **MX and mailbox setup:** use provider-supplied MX records for actual inboxes, not the website host. Verify SPF/DKIM/DMARC with DNS and real-message headers before sending.
6. **TLS, unsubscribe and complaint handling:** use TLS, a working visible unsubscribe route and one-click unsubscribe headers where applicable. Propagate opt-outs to Reachmark's global suppression table and the sending provider's global blocklist. Keep complaint rates low; pause on abnormal bounces/complaints.
7. **Monitoring:** review Google Postmaster Tools where eligible, DMARC reports, provider account health, bounce/complaint trends and domain reputation. Do not promise inbox placement based on DNS records alone.

Google's published guidance requires SPF or DKIM for all senders to Gmail and SPF + DKIM + DMARC for bulk senders (5,000+ messages/day to personal Gmail accounts), with From-domain alignment and one-click unsubscribe for marketing/subscribed messages. Reachmark should implement the stronger SPF + DKIM + DMARC baseline for every outbound domain regardless of volume.

## 6. Suggested data model additions

Extend existing tables/migrations rather than creating a parallel CRM:

- `workspaces` / tenant ownership for all records (verify existing isolation before multi-tenant rollout).
- `integrations`: workspace, provider, status, encrypted credential reference, scopes, created/updated timestamps.
- `client_profiles`: website URL, offer, ICP JSON, confirmed-by, confirmed-at.
- `workflow_runs`: ID, workspace, idempotency key, stage, status, progress, retry count, error code, timestamps.
- `workflow_jobs`: run ID, job type, status, attempts, next-run time, lock/lease, safe error summary.
- `prospects`: account/contact normalized fields, stage, fit score, score reasons, source provenance, source timestamps, consent/lawful-basis notes where required.
- `enrichment_events`: provider, provider record ID, field payload, source, timestamp, confidence and cost/credit metadata.
- `campaigns`: provider enum, provider campaign ID, configuration, approved version, approval metadata, state and daily caps.
- `campaign_memberships`: Reachmark prospect ID, provider lead ID, sequence state, last event and timestamps; unique key on campaign + prospect.
- `provider_events`: provider, provider event ID/hash unique, received time, payload hash, processed state and retry metadata.
- `bookings`: provider, provider event URI, prospect/campaign foreign keys, start/end/timezone, state, dedupe key.
- `suppression_entries`: normalized email/domain, reason, source, scope (global/workspace), created timestamp; unique normalized key.
- `audit_log`: actor, workspace, action, object type/id, timestamp and redacted metadata.

Every table query must enforce workspace ownership. Use parameterized SQL, short transactions, foreign keys, indexes for normalized email/domain and event IDs, and migration tests. Do not store unnecessary sensitive data or raw API secrets.

## 7. Suggested module and route layout

Fit into the existing Flask conventions; these are target module names, not a claim that they already exist:

```text
web/outbound/
  routes.py                 # authenticated intake, preview, approve, run status
  orchestrator.py           # state machine and job transitions
  schemas.py                # request/response validation
  policy.py                 # suppression, send gate, limits, jurisdiction rules
  scoring.py                # explainable fit/evidence scoring
  providers/
    apollo.py               # discovery + enrichment
    clay.py                 # supported Clay workflow/table adapter
    instantly.py             # Instantly API v2
    smartlead.py             # Smartlead API v1
    calendly.py              # Calendly API v2 + webhook verification
    chili_piper.py           # optional adapter after API access is confirmed
  webhooks.py                # provider-specific validation + event normalization
  jobs.py                    # retryable, idempotent job handlers
  repositories.py            # DB persistence and tenant-scoped queries
```

Target endpoints (adapt names to existing route contracts; do not duplicate routes already implemented):
- `POST /api/outbound/runs` — validate URL + ICP and create a draft run.
- `GET /api/outbound/runs/<run_id>` — stage/progress/errors.
- `POST /api/outbound/runs/<run_id>/discover` — start discovery.
- `POST /api/outbound/runs/<run_id>/approve` — approve selected records and copy version.
- `POST /api/outbound/campaigns` — create campaign configuration.
- `POST /api/outbound/campaigns/<id>/launch` and `/pause` — guarded provider actions.
- `POST /api/webhooks/instantly`, `/api/webhooks/smartlead`, `/api/webhooks/calendly` — validate, persist, deduplicate, enqueue.
- `POST /api/outbound/suppressions` — authorized global/workspace opt-out management.

Use CSRF protection for session-authenticated browser mutations; webhooks use provider-specific authentication and are not CSRF endpoints. Rate-limit intake and public probes separately. Return a run ID immediately and expose progress rather than holding a browser request open during provider calls.

### Example orchestration pseudocode

```python
def start_outbound_run(user, payload):
    require_authenticated_workspace(user)
    url = validate_public_http_url(payload["website_url"])  # SSRF-safe
    run = create_run(
        workspace_id=user.workspace_id,
        idempotency_key=payload["idempotency_key"],
        stage="website_analysis",
        status="queued",
    )
    enqueue("analyze_client_site", run.id, url, payload["icp"])
    return {"run_id": run.id, "status": "queued"}, 202

def process_discovery(run_id):
    run = load_run(run_id)
    profile = require_confirmed_client_profile(run.workspace_id)
    companies = apollo.search_companies(profile.icp_filters)
    contacts = apollo.search_contacts(companies, profile.icp_filters)
    candidates = dedupe_and_record_provenance(contacts)
    enriched = clay.enrich_if_supported(candidates)
    eligible = [p for p in enriched if policy.pre_send_eligible(p, run.workspace_id)]
    drafts = personalization.draft_with_evidence(profile, eligible)
    save_preview(run_id, drafts)
    set_run_state(run_id, "awaiting_approval")

def launch_campaign(campaign_id, actor):
    campaign = load_campaign_for_workspace(campaign_id, actor.workspace_id)
    require_approved_copy_and_contacts(campaign)
    require_sender_health_and_authentication(campaign)
    require_suppression_check(campaign)
    result = provider_for(campaign.provider).launch(campaign)
    save_provider_acceptance(campaign, result)  # only then mark active
```

## 8. Reliability and security requirements

- **Idempotency:** client request idempotency key, unique campaign membership, provider event unique key, and idempotent booking writes.
- **Retries:** exponential backoff with jitter for transient network/429/5xx errors; respect `Retry-After`; dead-letter persistent failures and show operator action.
- **No false state:** only mark sent/active/booked when provider events or successful API responses confirm it.
- **Secrets:** environment/secret manager only; redact keys, email bodies and personal data from logs. Rotate credentials and scope API keys to minimum access.
- **Tenant isolation:** enforce workspace ownership in every route, job and webhook association. Never trust a workspace ID supplied by the browser without deriving/validating access.
- **Webhook defense:** HTTPS, body size limits, signature/shared-secret validation, timestamp/replay checks where supported, event dedupe, schema validation, fast 2xx after durable persistence.
- **SSRF defense:** public IP allowlist checks after every DNS resolution/redirect; block private/reserved IPs and metadata endpoints; strict response/time limits.
- **Email safety:** global suppression before every provider add/send, opt-out propagation, sender/recipient jurisdiction rules, accurate identity and address, no deceptive subject/headers, clear unsubscribe. Warm-up must not be used to evade provider limits.
- **Privacy:** data minimization, documented retention/deletion/export, audit trail, data processing terms and regional legal review for prospecting markets. Email discovery/enrichment is not itself permission to contact.
- **Backups:** automate SQLite backup + integrity check + offsite copy and restore drills now; migrate to PostgreSQL before multiple app replicas/worker processes.
- **Observability:** `run_id`, workspace ID, provider request ID, event ID and release SHA in structured logs; do not log tokens or full email bodies by default.

## 9. Acceptance tests and rollout gates

1. Unit tests: URL normalization/SSRF cases, schema validation, scoring explanations, dedupe, suppression, tenant boundaries, opt-out precedence and idempotency.
2. Provider contract tests with mocked responses: pagination, credits/rate limits, invalid credentials, timeouts, 429/5xx, provider schema changes, campaign launch/pause and partial failures.
3. Webhook tests: bad secret/signature, duplicate/out-of-order events, retries, hard bounce, unsubscribe, reply, auto-reply, meeting booked/canceled and malformed payloads.
4. Browser E2E: URL → profile confirmation → discovery → evidence report → approve → draft preview → campaign launch → simulated reply → booking confirmation → CRM timeline.
5. Live sandbox test per provider using internal/test addresses and low volume; verify real email headers, unsubscribe, webhook delivery, Calendly booking/cancel and suppression propagation.
6. Production gate: all tests green, clean deployment SHA, verified `/healthz`, successful backup/restore drill, configured sender authentication, credentials rotated, monitor alerts working and explicit owner approval to enable sending.
7. Roll out in phases: (a) read-only discovery + report; (b) Clay enrichment and draft generation; (c) approval + provider sync with campaign paused; (d) small controlled live pilot; (e) gradual volume increase after deliverability review.

## 10. Current implementation gap summary

The repository already contains a provider-neutral outreach architecture and documented Instantly/Smartlead campaign flow, lead suppression and webhook normalization. It also has lead management, website analysis, booking-related routes and a database-backed app. The blueprint above is therefore an extension, not a greenfield rebuild.

Before calling this production-ready, verify in code and on the live deployment:
- Apollo and Clay adapters, credentials, credit controls and real end-to-end discovery/enrichment.
- Exact current route contracts; do not duplicate existing `/api/booking`, `/api/bookings` or provider webhook endpoints.
- Calendly/Chili Piper adapter, authenticated webhook validation, reschedule/cancel handling and booking-to-prospect matching.
- Durable jobs/retries and single-worker safety; current Railway configuration explicitly uses one replica and SQLite.
- Global suppression consistency across UI, jobs and both outbound providers.
- Domain SPF/DKIM/DMARC alignment and real message-header verification for each sending domain.
- Tenant isolation, migrations, backup/restore, release SHA, monitoring and production E2E.
- Current API plan access, provider rate limits, retention terms and legal requirements for each target market.

## References

- Apollo docs: https://docs.apollo.io/ (organization search: https://docs.apollo.io/reference/organization-search)
- Instantly developer starter kit / API conventions: https://github.com/Instantly-ai/instantly-starter-kit
- Smartlead API guide: https://helpcenter.smartlead.ai/en/articles/125-full-api-documentation
- Clay enrichment overview: https://university.clay.com/docs/clay-enrichments-integration-overview
- Calendly API v2: https://developer.calendly.com/api-docs/overview/api/reference
- Calendly webhooks: https://calendly.com/help/webhooks-overview
- Gmail sender requirements: https://support.google.com/mail/answer/81126
