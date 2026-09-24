"""Builder — turns a saved business record into a concept page and a review link.

The concept is composed from *that business's own saved fields* plus a
category-family template: never invented reviews, hours, prices, photos or
certifications. The page carries the concept and one question — do you want this
website built? — with three answers and an optional note.

A short CRO pass (from the vendored ``cro`` and ``copywriting`` playbooks) checks
the page it just built: one clear promise in the headline, one primary action,
short copy, an answer path a person can use on a phone in a few seconds.
"""
import json

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover
    class CrewError(Exception):
        pass

from crew.business import BRAIN_VERSION, ETHICS, STUDIO
from web.review_links import create_link, ensure_tables as ensure_link_tables
from crew.skills_loader import rules

# Category family → concept direction. `theme` matches a CSS palette in
# static/review.css; the words are placeholders the business replaces with facts.
FAMILIES = {
    'food': {'theme': 'ember', 'label': 'café & hospitality',
             'promise': 'Give people one clear place to see what you serve, when you are open, and how to find you.',
             'sections': [('Your menu, made findable', 'A clean, scannable menu section that works on a phone — with your prices, added only once you confirm them.'),
                          ('When you are open', 'Opening hours and location up front, plus one-tap directions, so nobody guesses.'),
                          ('A booking or enquiry path', 'Table requests or catering enquiries straight to your inbox, sized to how you actually run the day.')]},
    'wellness': {'theme': 'sage', 'label': 'wellness & beauty',
                 'promise': 'Let clients see your services, your availability and your real work before they book.',
                 'sections': [('Your treatments, described honestly', 'Each service with what it involves and how long it takes — no claims you cannot back up.'),
                              ('Your space and your people', 'Photographs you supply, and a short introduction to the practitioners.'),
                              ('A booking request that fits', 'A request form matched to the booking tool you already use.')]},
    'health': {'theme': 'clinic', 'label': 'clinics & health',
               'promise': 'Help patients understand your practice and reach you without friction.',
               'sections': [('Your services and approach', 'Plain-language explanations of what you treat and how you work.'),
                            ('Your practitioners', 'Real names, real roles, real credentials — nothing invented.'),
                            ('Appointments', 'An appointment enquiry built around your existing scheduling system.')]},
    'trades': {'theme': 'clay', 'label': 'trades & home services',
               'promise': 'Show the work you have done and make it obvious how to get a quote.',
               'sections': [('Proof of work', 'Photographs of completed jobs you supply, with the scope you are comfortable publishing.'),
                            ('What you cover', 'Service areas and the jobs you take — so the wrong calls stop coming.'),
                            ('Quote requests', 'A short quote form with photos so you can price without a site visit.')]},
    'professional': {'theme': 'navy', 'label': 'professional services',
                     'promise': 'Present your practice with authority and give clients a confidential way in.',
                     'sections': [('Your areas of work', 'Structured practice areas with clear scope and approach.'),
                                  ('Your team', 'Partners and staff with genuine credentials and experience.'),
                                  ('A confidential enquiry', 'A direct enquiry path scoped to how you take on clients.')]},
    'retail': {'theme': 'market', 'label': 'retail & boutique',
               'promise': 'Turn your catalogue and your story into something people can shop or ask about.',
               'sections': [('Your range', 'Products with accurate descriptions and prices you confirm.'),
                            ('Your story', 'Sourcing, values and the people behind the shop.'),
                            ('How to buy', 'A shopping or reservation enquiry matched to the system you use.')]},
    'fitness': {'theme': 'pulse', 'label': 'fitness & sport',
                'promise': 'Make classes, timetables and joining obvious at a glance.',
                'sections': [('Timetable and classes', 'A timetable that stays accurate, with levels explained.'),
                             ('Membership options', 'Straightforward pricing and what each plan includes.'),
                             ('Join or try', 'A trial or join request that lands with you, not in a void.')]},
    'auto': {'theme': 'steel', 'label': 'automotive',
             'promise': 'Show your services and let drivers book or ask with one tap.',
             'sections': [('Services and turnaround', 'What you fix, how long it usually takes, what to bring.'),
                          ('Location and hours', 'Directions, parking and opening hours up front.'),
                          ('Book or ask', 'A service request with vehicle details, so the first call is shorter.')]},
    'pets': {'theme': 'sage', 'label': 'pets & veterinary',
             'promise': 'Reassure owners with clear services, hours and an easy way to reach you.',
             'sections': [('Services for pets', 'Grooming, boarding or care explained without over-claiming.'),
                          ('Your team', 'The people who will actually handle the animals.'),
                          ('Book a visit', 'A booking request with the details you need to prepare.')]},
    'generic': {'theme': 'charcoal', 'label': 'local business',
                'promise': 'Give the business a clean place to explain what it does and start conversations.',
                'sections': [('What you do', 'A plain-language overview of the services or products on offer.'),
                             ('Why customers choose you', 'Real reasons, written with the owner — never invented.'),
                             ('How to reach you', 'Contact details and one simple next step, mobile-first.')]},
}

CATEGORY_HINTS = [
    (('café', 'cafe', 'restaurant', 'bakery', 'fast food', 'bar', 'food'), 'food'),
    (('hair', 'beauty', 'salon', 'spa', 'tattoo', 'wellness', 'massage'), 'wellness'),
    (('dentist', 'clinic', 'physio', 'pharmacy', 'doctor', 'medical', 'veterinar'), 'health'),
    (('plumber', 'electrician', 'hvac', 'roof', 'carpenter', 'painter', 'builder', 'landscap', 'clean'), 'trades'),
    (('lawyer', 'accountant', 'estate agent', 'consult', 'agency', 'office'), 'professional'),
    (('shop', 'store', 'boutique', 'market', 'florist', 'cloth', 'supermarket'), 'retail'),
    (('gym', 'fitness', 'yoga', 'pilates', 'sport'), 'fitness'),
    (('auto', 'car', 'garage', 'tyre', 'mechanic', 'wash'), 'auto'),
    (('pet', 'groom', 'kennel', 'vet'), 'pets'),
]


def family_for(category, name=''):
    haystack = f'{category or ""} {name or ""}'.lower()
    for keys, family in CATEGORY_HINTS:
        if any(key in haystack for key in keys):
            return family
    return 'generic'


def compose_concept(lead, settings, tone='Professional'):
    """Deterministic concept copy from the saved record. No invented specifics.

    When the lead's trade matches a stored Builder-memory brief, the brief's
    structure (promise + feature sections) directs the page while the
    business's own name, facts and brand stay untouched. Service blueprints
    and unmatched trades fall back to the family template.
    """
    family = family_for(lead.get('category'), lead.get('name'))
    template = FAMILIES[family]
    memory_meta = {'applied': False}
    try:
        from builder.memory import apply_prompt, match_prompt
        brief = match_prompt(lead.get('category'), lead.get('name'))
        if brief is not None and brief.get('kind') == 'website':
            directed = apply_prompt(brief, lead)
            theme_family = directed['theme_family']
            template = {'theme': FAMILIES[theme_family]['theme'],
                        'label': directed['label'],
                        'promise': directed['promise'],
                        'sections': [(s['title'], s['body']) for s in directed['sections']]}
            family = theme_family
            memory_meta = directed['memory']
    except Exception:
        template = FAMILIES[family]
        memory_meta = {'applied': False}
    studio = (settings.get('agency') or STUDIO['name']).strip()
    place = (lead.get('city') or '').strip()
    name = lead.get('name') or 'this business'
    headline = {
        'Professional': f'{name} — a clearer front door.',
        'Warm': f'{name}, easier to find and easier to choose.',
        'Concise': f'{name}: clearer, faster, found.',
    }.get((tone or 'Professional').title(), f'{name} — a clearer front door.')
    intro = (f'{template["promise"]} Prepared for {name}'
             + (f' in {place}' if place else '')
             + ETHICS['concept_intro'].format(studio=studio))
    contact = {
        'phone': (lead.get('phone') or '').strip(),
        'email': (lead.get('email') or '').strip(),
        'address': (lead.get('address') or '').strip(),
        'hours': (lead.get('opening_hours') or '').strip(),
        'website': (lead.get('website') or '').strip(),
    }
    facts = [line for line in [
        f'Listed category: {lead.get("category")}' if lead.get('category') else '',
        f'Area: {place}' if place else '',
        f'Phone on the listing: {contact["phone"]}' if contact['phone'] else '',
        f'E-mail published by the business: {contact["email"]}' if contact['email'] else '',
        f'Listed hours: {contact["hours"]}' if contact['hours'] else '',
    ] if line]
    return {
        'theme': template['theme'], 'family': family, 'family_label': template['label'],
        'memory': memory_meta,
        'headline': headline[:140], 'intro': intro[:600],
        'sections': [{'title': title, 'body': body} for title, body in template['sections']],
        'facts': facts,
        'contact': contact,
        'studio': studio,
        'disclaimer': ETHICS['concept_disclaimer'].format(name=name),
        'cro_rules_applied': rules('cro', 'value proposition', 3) + rules('copywriting', 'principle', 3),
    }


def build_review_link(ctx, lead, concept):
    """Create (or refresh) the review link for this lead and return it."""
    ensure_link_tables(ctx.db)
    studio = (ctx.settings().get('agency') or STUDIO['name']).strip()
    base = (ctx.settings().get('public_base_url') or '').rstrip('/')
    token_preview = '/r/<token>'
    share = compose_share_message(lead, concept, studio, base, token_preview)
    chat_preview = compose_chat_message(lead, studio, token_preview, concept.get('family_label', ''))
    link = create_link(ctx.db, ctx.now, lead, concept, share, run_id=ctx.run['id'], chat_message=chat_preview)
    share = compose_share_message(lead, concept, studio, base, f'{base}/r/{link["token"]}' if base else f'/r/{link["token"]}')
    with ctx.db() as c:
        chat = compose_chat_message(lead, studio, f'{base}/r/{link["token"]}' if base else f'/r/{link["token"]}',
                                    concept.get('family_label', ''))
        c.execute('UPDATE review_links SET share_message=?,chat_message=?,updated=? WHERE id=?',
                  (share, chat, ctx.now(), link['id']))
    link['share_message'] = share
    link['chat_message'] = chat
    link['share_url'] = f'{base}/r/{link["token"]}' if base else f'/r/{link["token"]}'
    return link


def compose_share_message(lead, concept, studio, base, link_url):
    """The forward-to-the-business message that carries the review link."""
    name = lead.get('name') or 'there'
    place = f" in {lead['city']}" if lead.get('city') else ''
    return (
        f"Hello {name},\n\n"
        f"I'm {studio}. I noticed a couple of small things about how customers find you{place}"
        f"{' — ' + concept['family_label'] + ' is a competitive space' if concept.get('family') else ''}, "
        f"so I sketched an independent website concept using only the details already listed publicly.\n\n"
        f"You can look at it here (about 60 seconds, nothing to install): {link_url}\n\n"
        f"At the end of the page there are three buttons — if a website like this would help, tap "
        f"“Yes — build my website” and I'll come back with scope and a fixed price. If not, tap "
        f"“Not right now” or “I already have a website” and I won't follow up again.\n\n"
        f"Either way, thank you for the minute.\n\n{studio}\n" + ETHICS['opt_out_share']
    )[:2000]


def compose_chat_message(lead, studio, link_url, family_label=''):
    """The same invitation sized for WhatsApp or SMS — plain text, link early, one ask.

    Kept under 480 characters on purpose: a first message to a business should be readable
    without scrolling, and every copy must carry the opt-out line.
    """
    name = (lead.get('name') or 'there').strip()
    kind = f"{family_label} " if family_label else ''
    text = (
        f"Hi {name} — {studio} here.\n\n"
        f"I built a 60-second {kind}concept page for you using only the details already public "
        f"about your business: {link_url}\n\n"
        f"{ETHICS['chat_no_charge']} If it is not useful, "
        f"{ETHICS['opt_out_chat']}"
    )
    return text[:480]


def cro_checks(concept):
    """Small, honest pass over the page the Builder just made."""
    sections = concept.get('sections', [])
    words = len(' '.join([concept.get('headline', ''), concept.get('intro', '')] +
                         [s['body'] for s in sections]).split())
    checks = [
        {'name': 'One clear promise above the fold', 'ok': bool(concept.get('headline')) and len(concept['headline']) <= 90,
         'detail': f'Headline is {len(concept.get("headline", ""))} characters.'},
        {'name': 'One primary action on the page', 'ok': True, 'detail': 'The only action is the three-answer review question.'},
        {'name': 'Readable on a 360 px screen', 'ok': True, 'detail': 'Single-column layout, 16 px minimum body text, no fixed widths.'},
        {'name': 'Copy an owner can read in under a minute', 'ok': words <= 320, 'detail': f'{words} words of concept copy.'},
        {'name': 'No invented specifics', 'ok': not any(ch.isdigit() for ch in concept.get('intro', '')),
         'detail': 'Prices, reviews, certifications and hours come only from saved fields.'},
        {'name': 'Contact details present or explicitly absent', 'ok': True,
         'detail': 'Shows only what the listing already publishes; missing fields stay missing.'},
    ]
    return checks, words


def attach_site_faults(concept, audit):
    """Copy the latest measured faults onto the concept so the proposal quotes them."""
    gaps = ((audit or {}).get('gaps') or {}).get('gaps') or []
    concept['site_faults'] = [{'reason': gap.get('reason', ''), 'source': gap.get('source', ''),
                               'weight': gap.get('weight', 1)} for gap in gaps[:6]]
    if (audit or {}).get('created'):
        concept['faults_checked_at'] = (audit['created'] or '')[:10]
    return concept


def run(ctx):
    leads = ctx.load_leads()
    if not leads:
        raise CrewError('Builder has no leads. Run Scout and Auditor first, or pick a saved business.')
    if not ctx.params.get('include_review_link', True):
        ctx.emit('Review links are switched off for this run; concepts were built but no link was issued.')
    built = []
    for lead in leads[:ctx.params.get('limit') or 10]:
        if ctx.expired():
            ctx.emit('Builder stopped at the step time budget; remaining leads are untouched.')
            break
        concept = compose_concept(lead, ctx.settings(), ctx.params.get('tone', 'Professional'))
        try:
            from agents.agent_auditor import latest_audit
            attach_site_faults(concept, latest_audit(ctx.db, lead['id']))
        except Exception:
            concept.setdefault('site_faults', [])
        checks, words = cro_checks(concept)
        mem = concept.get('memory') or {}
        mem_note = (f" Builder memory {mem['prompt_id']} (v{mem['memory_version']}) applied;"
                    f" placeholders swapped for the business's own name."
                    if mem.get('applied') else '')
        ctx.receipt('concept', f"{lead['name']}: concept composed from {len(concept['facts'])} saved field(s) "
                               f"({concept['family_label']} direction, {words} words).{mem_note}",
                    url=lead.get('source_url', ''))
        for check in checks:
            if not check['ok']:
                ctx.receipt('cro', f"{lead['name']}: CRO check needs attention — {check['name']} ({check['detail']})")
        if not ctx.params.get('include_review_link', True):
            ctx.artifact('concept', f"Concept copy — {lead['name']}", json.dumps(concept, indent=2),
                         meta={'lead_id': lead['id'], 'checks': checks})
            continue
        link = build_review_link(ctx, lead, concept)
        with ctx.db() as c:
            c.execute("UPDATE leads SET stage=CASE WHEN stage='New' THEN 'Drafted' ELSE stage END,updated=? WHERE id=?",
                      (ctx.now(), lead['id']))
        built.append({'lead_id': lead['id'], 'name': lead['name'], 'link_id': link['id'], 'token': link['token'],
                      'share_url': link['share_url'], 'share_message': link['share_message']})
        ctx.receipt('review-link', f"{lead['name']}: review link issued (/r/{link['token'][:6]}…) with the three-answer "
                                   "question and view tracking.", url=link['share_url'])
        ctx.artifact('review-link', f"Review link — {lead['name']}",
                     f"Link: {link['share_url']}\n\nShare message:\n{link['share_message']}",
                     meta={'lead_id': lead['id'], 'brain': BRAIN_VERSION, 'token': link['token'],
                           'share_url': link['share_url']})
        if ctx.params.get('sms_note'):
            sms = (f"Hi {lead['name']}, {concept['studio']} here — I sketched a website idea for you "
                   f"using your public listing. 60-second look: {link['share_url']} {ETHICS['opt_out_sms_note']}")
            ctx.artifact('sms', f"SMS / WhatsApp note — {lead['name']}", sms[:320], meta={'lead_id': lead['id']})

    summary = (f'Built {len(built)} review link(s) ready to send. Each page carries only saved facts and asks '
               f'the three-answer question. Nothing has been sent to any business.')
    ctx.emit(summary)
    if built:
        ctx.artifact('share-copy', f'Share copy for {len(built)} review link(s)',
                     '\n\n---\n\n'.join(item['share_message'] for item in built), meta={'links': built})
    return {'summary': summary, 'data': {'leads': built, 'count': len(built),
                                         'lead_ids': [item['lead_id'] for item in built],
                                         'share_messages': len(built)}}
