# Zoho CRM integration for Reachmark

## Purpose

Use Zoho CRM as an optional customer-relationship system for teams that already work in Zoho. Reachmark remains responsible for public-site observations, opportunity reports, proposals, contracts, project execution and invoice state. Zoho can mirror qualified commercial relationships and follow-up tasks; it must not replace Reachmark's evidence or payment records.

## Recommended lifecycle

1. A prospect is discovered and deduplicated in Reachmark.
2. A user reviews the evidence and qualifies the prospect.
3. Only after qualification, Reachmark can create or update a Zoho Lead (or Contact + Account when a relationship is already established).
4. A proposal accepted by the user can be represented as a Zoho Deal with a mapped stage and explicit currency/amount.
5. Approved follow-up tasks can be synchronized to Zoho Tasks.
6. Reachmark remains the source of truth for the signed proposal/contract, delivery status and invoice/payment state unless a future, explicit two-way mapping is implemented.

## Field mapping

| Reachmark | Zoho CRM | Rule |
| --- | --- | --- |
| Lead name / business name | Lead Last Name / Company | Never create a record without Zoho's required fields |
| Public website | Website | Store only a validated public URL |
| Email / phone | Email / Phone | Leave blank if not observed; never fabricate |
| Category / location | Description or custom fields | Preserve source context and evidence link |
| Reachmark lead ID | Custom external ID field | Use for idempotency and duplicate prevention |
| Qualification status | Lead Status | Map only supported, configured values |
| Proposal amount + currency | Deal Amount + Currency | Never infer an amount; unset price stays unset |
| Next follow-up | Task due date / subject | Create only after a user-approved action |

Actual Zoho field API names and pipeline stages must be read from the connected Zoho account before writes are enabled. Do not assume custom fields exist.

## Connection and security

- Use Zoho OAuth with the minimum CRM scopes needed for leads, contacts, accounts, deals and tasks.
- Keep client secret, refresh token and access token server-side in deployment secrets; never commit credentials or send them to the browser.
- Prefer a dedicated integration module with bounded timeouts, retry/backoff for rate limits, structured redacted logs and a sync status per record.
- Store a stable Zoho record ID and a sync timestamp in Reachmark only after Zoho confirms the write.
- Make sync idempotent using the Reachmark external ID; repeated requests must update the mapped record instead of creating duplicates.
- Do not send outreach automatically. Creating a CRM record or task is not permission to send email, WhatsApp or SMS.
- Provide a preview, explicit connect/disconnect controls, and a user-triggered sync action before any write is enabled.

## Environment configuration

A future implementation should use deployment variables such as `ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, `ZOHO_ACCOUNTS_BASE_URL`, `ZOHO_API_BASE_URL`, and `ZOHO_CRM_ENABLED`. Keep the default disabled until OAuth credentials, data-center region, scopes, field mapping and test-account behavior are verified.

## Zoho Catalyst

Catalyst is an optional future fit for isolated serverless jobs, webhook receivers or integration processing if Reachmark outgrows its existing Flask/Railway backend. Do not move core functionality to Catalyst merely for branding: first prove a concrete operational need and define idempotency, auth, observability and failure recovery.

## Acceptance criteria before calling this integration live

- OAuth connection and token refresh verified against the correct Zoho data center.
- Read-only field/metadata discovery works before any write capability is enabled.
- Dry-run mapping shows exactly which fields will be created or updated.
- External-ID deduplication, retries, rate limits and disconnect behavior are tested.
- Writes require user initiation and are audited.
- No credential, contact detail or prospect record is exposed in logs or public pages.
- CI includes mock-based tests; live Zoho smoke tests run only in a dedicated test account.
