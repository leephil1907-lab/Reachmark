# Reachmark Digital — Outreach Architecture

Reachmark is the orchestration layer. Providers execute email delivery; Reachmark
owns CRM identity, campaign state, suppression, workflow decisions and normalized
events.

## Email providers

- Instantly — API v2, configured with INSTANTLY_API_KEY.
- Smartlead — API v1, configured with SMARTLEAD_API_KEY.
- A Reachmark campaign is created once and selects exactly one email execution
  provider.
- Provider campaign IDs are mapped to the Reachmark campaign.

## Current vertical slice

1. Create a campaign from the Reachmark workspace.
2. Select Instantly or Smartlead.
3. Add existing Reachmark leads with email addresses.
4. Start or pause the campaign from Reachmark.
5. Receive provider events through the Reachmark webhook endpoints.
6. Normalize reply and unsubscribe events into the CRM.
7. Move replied leads to the Replied stage and add unsubscribed emails to the
   global suppression table.

## Security

- Provider API keys are server-side only.
- Production webhook endpoints require a configured shared secret.
- Webhook events are idempotent by provider event ID.
- Provider failures are surfaced; Reachmark never marks a campaign active until
  the provider accepts the start request.

## Next slices

- Visual multi-step campaign builder.
- Provider mailbox/workspace selection.
- Unified inbox and normalized message records.
- WhatsApp, SMS, LinkedIn task and call adapters.
- Google Business locations, reviews, posts and performance.
- Agency/client workspace isolation, billing and reporting.
