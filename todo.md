# Main Website Audit + "Fix all" — Reachmark

## Audit (complete)
- [x] Enumerate all public routes + templates
- [x] Verify all internal links resolve to routes
- [x] Verify all referenced static assets exist
- [x] Check sample-count consistency (10 samples; some copy said 8)
- [x] Check for placeholder IDs / TODO / lorem
- [x] Check legal page dates + copyright years
- [x] Check for fabricated social proof (Trustpilot / testimonials)

## Fix 1 — objective inconsistencies (8 → 10 samples)
- [x] app.py home SEO description → 10
- [x] app.py about SEO description → 10
- [x] app.py sitemap comment → 10
- [x] about.html "Browse 8 Templates" → 10
- [x] about.html "Browse eight premium..." → ten
- [x] about.html "See the 8 live templates" → 10

## Fix 2 — remove fabricated proof (Trustpilot rating + invented testimonials)
- [x] about.html: banner line, Trustpilot strip, Trustpilot section, review-head badge,
      fake Alex R. card, footer badge → honest "live review wall" framing
- [x] showcase.html: strip, section, footer badge → honest framing + tp.badge/empty keys
- [x] enquire.html: star strip + footer badge → honest framing
- [x] signup.html + login.html: 5-star trust rows → single honest star
- [x] carousel.js: "alongside Trustpilot" toast + comment → honest
- [x] premium.css: Trustpilot comment + Trustpilot-green (#00b67a) → brand green (#5b7d2a)
- [x] locales (en/es/fr/de/pt/zh): replace au.l_trust, au.s_tr, au.s_tr_s, enq.tp,
      enq.tp_note, tp.*, show.js_thanks; add tp.badge, tp.empty, tp.empty_s
- [x] Verified: no "4.8/5", "127 reviews", "Trustpilot", "Sarah M./David K./Alex R."
      remain in templates or locales

## Fix 3 — wire /enquire?plan= prefill
- [x] web/enquiries.py: read + validate ?plan=starter|growth|bespoke, pass plan metadata
- [x] enquiry-form.html: pre-fill budget + message, show plan chip, hidden plan field
- [x] Smoke-tested: starter/growth/bespoke prefill; bogus/empty ignored

## Verify
- [x] Run full test suite (464 tests pass)
- [x] Smoke-test /enquire?plan= routes
- [x] Clean up temp scripts
- [ ] Commit + push to feature/branded-email-clean-site-google-places (PR #2)
- [ ] Report to user
