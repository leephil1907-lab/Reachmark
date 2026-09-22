"""Reachmark brand brain — the second brain every crew agent shares.

One home for everything the business knows about itself:

* the **knowledge engine** (``load_knowledge`` / ``match_answer`` / ``detect_intent``)
  that answers visitor questions from ``knowledge/reachmark.md`` — verified facts only;
* the **structured brand facts** (tiers, timing, process, voice, ethics, sectors)
  that mirror that file, so agents and pages quote identical numbers;
* the **lifecycle** map that runs the business from discovery to delivery to review;
* a one-page **brief** each agent loads before it writes a single customer-facing word.

Drift rule: the structured facts mirror the knowledge file, and
``tests/test_brain.py`` fails if they ever disagree. Change a price once — in the
knowledge file — and the tests tell you the brain needs the same edit.
"""

import os
import re

BRAIN_VERSION = '1.0.0'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(ROOT, 'knowledge', 'reachmark.md')


STOPWORDS = {'the', 'a', 'an', 'is', 'are', 'do', 'does', 'you', 'your', 'we', 'i', 'to', 'of', 'for', 'and',
             'or', 'in', 'on', 'it', 'this', 'that', 'can', 'how', 'much', 'my', 'me', 'with', 'what', 'have',
             'be', 'will', 'would', 'about', 'need', 'want', 'please', 'hi', 'hello', 'hey', 'there',
    'please', 'thanks', 'thank', 'first', 'next', 'last', 'best', 'top', 'ever', 'just', 'still', 'really',
    'actually', 'today', 'tomorrow', 'again', 'maybe', 'also', 'hey'}
# A single overlapping keyword plus one tag hit is enough to quote a published answer;
# anything below that, or any question carrying vocabulary this knowledge base has never
# seen, is handed to the owner instead of guessed at.
MIN_SCORE = 1.8
# --------------------------------------------------------------------------- #
# Knowledge base
# --------------------------------------------------------------------------- #
def load_knowledge(path=None):
    """Parse the markdown knowledge file into topics with questions and answers."""
    path = path or KB_PATH
    topics = []
    try:
        with open(path, encoding='utf-8') as fh:
            text = fh.read()
    except OSError:
        return topics
    current = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith('## '):
            current = {'topic': line[3:].strip().lower(), 'tags': [], 'qa': [], 'facts': []}
            topics.append(current)
            continue
        if current is None:
            continue
        if line.lower().startswith('tags:'):
            current['tags'] = [t.strip().lower() for t in line[5:].split(',') if t.strip()]
            continue
        if line.startswith('Q:'):
            current['qa'].append({'q': line[2:].strip(), 'a': ''})
            continue
        if line.startswith('A:'):
            if current['qa']:
                current['qa'][-1]['a'] = line[2:].strip()
            else:
                current['qa'].append({'q': current['topic'], 'a': line[2:].strip()})
            continue
        if line.startswith('- ') and len(line) > 8:
            current['facts'].append(line[2:].strip())
    return [t for t in topics if t['qa'] or t['facts']]


def _stem(word):
    """Very light stemming so 'costs' matches 'cost' and 'days' matches 'day'.

    Deliberately conservative: this decides which published answer to quote, it never
    invents one. A wrong stem can only move a question between two verified topics.
    """
    if len(word) > 4 and word.endswith('ing'):
        return word[:-3]
    if len(word) > 4 and word.endswith('es'):
        return word[:-2]
    if len(word) > 3 and word.endswith('s') and not word.endswith('ss'):
        return word[:-1]
    return word


def _tokens(text):
    return [_stem(w) for w in re.findall(r"[a-z0-9']+", (text or '').lower()) if w not in STOPWORDS and len(w) > 1]


def match_answer(message, topics=None):
    """Return (topic, question, answer, score). Score 0 means 'no verified answer'."""
    topics = topics if topics is not None else load_knowledge()
    words = set(_tokens(message))
    low = (message or '').lower()
    best = (None, None, None, 0.0)
    for topic in topics:
        tag_hits = len(words & set(_tokens(' '.join(topic['tags']))))
        # A multi-word tag that appears verbatim ("how long", "review link") is strong evidence.
        phrase_hits = len([tag for tag in topic['tags'] if ' ' in tag and tag in low])
        for pair in topic['qa']:
            q_words = set(_tokens(pair['q']))
            overlap = len(words & q_words)
            phrase_bonus = 1.4 if pair['q'] and pair['q'] in (message or '').lower() else 0
            score = overlap * 1.0 + tag_hits * 0.8 + phrase_hits * 1.8 + phrase_bonus
            if score > best[3]:
                best = (topic['topic'], pair['q'], pair['a'], score)
        if not topic['qa'] and topic['facts'] and tag_hits:
            score = tag_hits * 0.8 + phrase_hits * 1.8
            if score > best[3]:
                best = (topic['topic'], topic['topic'], ' '.join(topic['facts'][:2]), score)
    if best[3] and best[3] < 3.0 and not _verified_vocabulary(words, topics):
        # The question turned on a word this knowledge base has never seen ("…unhappy with
        # the llama"). Weak evidence plus unknown vocabulary is not an answer, it is a
        # hand-off. The front desk would rather say nothing than quote the wrong fact.
        return (None, None, None, 0.0)
    return best


def _verified_vocabulary(words, topics):
    """True when every distinctive word in the question is recognisable to the knowledge base.

    Words are compared loosely (shared stems, one inside the other) so 'ecommerce' still
    counts as known when the base says 'e-commerce'. A genuinely foreign word — a name, an
    animal, another industry's jargon — marks the question as unverified until the score is
    strong enough to ignore it.
    """
    known = set()
    for topic in topics:
        known |= set(_tokens(' '.join(topic['tags'])))
        for pair in topic['qa']:
            known |= set(_tokens(pair['q']))
            known |= set(_tokens(pair['a']))
    for word in words:
        if len(word) < 5:
            continue
        if word in known:
            continue
        related = any(len(other) >= 5 and (word.startswith(other) or other.startswith(word) or other in word)
                      for other in known)
        if not related:
            return False
    return True


def detect_intent(message, topic=None, score=0):
    low = (message or '').lower()
    if re.search(r'\b(human|person|call me|speak to|talk to|owner|someone real|agent)\b', low):
        return 'human'
    if re.search(r'\b(price|pricing|cost|how much|budget|quote|fee|rate|\$)\b', low):
        return 'pricing'
    if re.search(r'\b(how long|timeline|when|delivery|deadline|days|start|how soon)\b', low):
        return 'timeline'
    if re.search(r'\b(sample|portfolio|example|showcase|design|figma|3d|preview)\b', low):
        return 'samples'
    if re.search(r'\b(website for my|build me|my business|my site|my website|need a website|needs a website|'
                 r'needs a site|want a website|want a site|looking for a website|looking for a site|redesign|'
                 r'rebuild my (site|website)|new (site|website))\b', low):
        return 'new_project'
    if re.search(r'\b(hi|hello|hey|good (morning|afternoon|evening))\b', low) and len(low.split()) <= 5:
        return 'greeting'
    if score >= MIN_SCORE and topic:
        return topic.replace(' ', '_')
    return 'unknown'




# --------------------------------------------------------------------------- #
# Structured brand facts — mirrors knowledge/reachmark.md (drift-tested)
# --------------------------------------------------------------------------- #
STUDIO = {
    'name': 'Reachmark',
    'tagline': 'Concept first, ask second.',
    'site_name': 'Reachmark — Find Potential. Make Your Mark.',
    'offer': 'clear, mobile-friendly websites that make it easier for customers to learn about services and get in touch',
}

TIERS = {
    'starter': {
        'name': 'Starter', 'price': 650, 'unit': 'per launch',
        'pages': 'one striking page', 'revisions': 1,
        'includes': ['your content with a Figma template', 'mobile responsive', 'SEO basics',
                     'contact form', 'live 3D preview', '1 revision'],
        'blurb': 'Starter $650 per launch — one striking page with mobile, SEO basics, a contact form, a live 3D preview and 1 revision.',
    },
    'growth': {
        'name': 'Growth', 'price': 1250, 'unit': 'per launch',
        'pages': 'up to 5 pages plus blog', 'revisions': 3,
        'includes': ['CMS for your own updates', 'booking or e-commerce ready', 'SEO + analytics',
                     '3 revisions', 'priority support'],
        'blurb': 'Growth $1,250 — up to 5 pages plus blog, CMS for updates, booking or e-commerce ready, SEO + analytics, 3 revisions, priority support.',
    },
    'bespoke': {
        'name': 'Bespoke', 'price': None, 'unit': 'estimate',
        'pages': 'custom scope', 'revisions': 'founder-led',
        'includes': ['custom Figma from scratch', 'API, payment or map integrations',
                     'performance 95+ target', 'founder-led build'],
        'blurb': 'Bespoke is custom/estimate — custom Figma from scratch, API/payment/map integrations, performance 95+ target, founder-led build.',
    },
}

TIMING = {
    'preview': 'a live 3D preview in about 7 days from an agreed scope',
    'preview_days': 7,
    'support': '7-day support',
    'support_days': 7,
    'start': 'work starts once you approve the scope',
}

PROCESS = [
    'You send an enquiry (name, email, what you need — optional budget and timeline).',
    'The studio replies with a tailored estimate.',
    'You approve the scope.',
    'The concept preview and then the build happen.',
    'Revisions, then launch.',
]

CONTACT = {
    'enquiry_path': '/enquire',
    'receptionist_path': '/receptionist',
    'pricing_path': '/about#pricing',
    'showcase_path': '/showcase',
    'reviews_path': '/reviews',
}

VOICE = {
    'rules': [
        'Plain words, short sentences, one ask per message.',
        'Warm but never gushing; confident but never hyped.',
        'Name only facts that are saved or published — never a guess.',
        'When unsure, say so plainly and hand to the studio owner.',
        'No fake familiarity, no invented deadlines, no invented prices.',
    ],
    'greeting': 'Hello — this is the Reachmark front desk.',
    'signoff': 'Nothing is charged until you approve the scope.',
}

ETHICS = {
    # Exact approved lines — agents quote these, never paraphrase them.
    'opt_out_email': 'Reply “no thanks” or use the unsubscribe link to stop all contact.',
    'opt_out_sms': "Reply STOP and I'll stop.",
    'opt_out_share': '— You received this once, from a public business listing. Reply STOP or use the unsubscribe link and you will not be contacted again.',
    'opt_out_chat': 'reply STOP and I will not write again.',
    'opt_out_sms_note': 'Reply STOP to opt out.',
    'concept_intro': ' by {studio} as an independent concept — nothing here is published under your name until you say yes.',
    'concept_disclaimer': ('Independent concept prepared by the studio. Not the official website of '
                           '{name}. No reviews, prices, hours, certifications or photographs have been '
                           'invented; all content is confirmed with the business before a build.'),
    'chat_no_charge': 'No charge, nothing published under your name unless you say yes.',
    'no_charge_until_scope': 'nothing is charged until you approve scope',
    'contact_basis': ('public listing {source}, recorded {date} — the address was published by the business '
                      'itself and every message carries the opt-out line.'),
    'suppression': 'Every outreach message carries an unsubscribe link, blocked addresses are kept in a permanent suppression list, and no further mail is sent to them.',
    'one_per_day': 'One message per business per day.',
    'review_ask_honest': 'Only if you mean it — a few honest words help more than polished ones.',
}

SECTORS = ['café', 'wellness studio', 'renovation and trades', 'clinic', 'law firm', 'retail',
           'finance dashboard', 'invoice SaaS']

PROMISES = [
    'A live 3D preview in about 7 days from an agreed scope.',
    'Revisions follow the tier: 1 for Starter, 3 for Growth, founder-led for Bespoke.',
    'Every plan includes domain and hosting guidance plus 7-day support.',
    'The concept preview is prepared before any commitment.',
    'Nothing is charged until you approve the scope.',
]

NON_PROMISES = [
    'No rankings, traffic or revenue outcome is promised anywhere.',
    'No guarantees are published, and none should be assumed.',
    'Public map coverage is uneven; website checks are observations at a point in time.',
]

TAGLINE = 'Concept first, ask second.'
FALLBACK_OSM_TAG = ('shop', 'hairdresser')

# What each crew member carries from the brain into its run.
FOCUS = {
    'scout': ['Evidence first: save only what public sources publish.',
              'A missing website link is not proof a business needs work.',
              'Sectors the studio serves: ' + ', '.join(SECTORS) + '.'],
    'auditor': ['Observe and date; never score what was not measured.',
                'Inconclusive stays inconclusive — BLOCKED is not failure.'],
    'builder': ['Concepts carry saved facts only — no invented specifics.',
                'Every concept states it is independent and unpublished.'],
    'scribe': ['Short, specific, one ask — in the owner’s voice.',
               'Every message carries the opt-out line, word for word.'],
    'closer': ['Nothing outbound without a separate human approval.',
               'Opt-outs are checked on every dispatch and kept forever.'],
    'receptionist': ['Answer only from verified facts; hand over when unsure.',
                      'An email address becomes a captured enquiry, never a dead end.'],
    'brag': ['Celebrate only measured facts stored in this workspace.',
             'Never claim a video exists until one does.'],
    'video': ['Record the real page — no frames faked, no facts invented.',
              'The script quotes saved facts and measured observations only.'],
}


# --------------------------------------------------------------------------- #
# Accessors
# --------------------------------------------------------------------------- #
def tier(name):
    """One tier by id ('starter' | 'growth' | 'bespoke'). {} when unknown."""
    return dict(TIERS.get((name or '').lower(), {}))


def tier_line(name):
    """Short shelf label: 'Starter · $650' or 'Bespoke · estimate'."""
    row = TIERS.get((name or '').lower())
    if not row:
        return ''
    if row['price'] is None:
        return f"{row['name']} · estimate"
    return f"{row['name']} · ${row['price']:,}"


def price_mention():
    """The only price shorthand any agent may use unprompted."""
    return f"Sites from ${TIERS['starter']['price']} {TIERS['starter']['unit']}"


def opt_out(channel='email'):
    """The exact approved opt-out line for a channel."""
    return ETHICS.get(f'opt_out_{channel}', ETHICS['opt_out_email'])


def facts_for(topic):
    """The knowledge file's questions and answers for one topic (or [] unknown)."""
    want = (topic or '').lower()
    for entry in load_knowledge():
        if entry['topic'] == want or want in entry['topic']:
            return list(entry['qa'])
    return []


def brand_for(agent_id):
    """What one crew member carries: its focus lines plus the shared voice."""
    return {'agent': agent_id or '', 'brain': BRAIN_VERSION,
            'focus': list(FOCUS.get(agent_id or '', FOCUS['receptionist'])),
            'voice': list(VOICE['rules']), 'tagline': TAGLINE}


def brief():
    """The whole brand on one page — prepended to any model phrasing prompt."""
    lines = [f"{STUDIO['name']} — {STUDIO['tagline']}", '',
               'Tiers (published, fixed wording):']
    for key in ('starter', 'growth', 'bespoke'):
        row = TIERS[key]
        lines.append(f"- {row['blurb']}")
    lines += ['', f"Timing: {TIMING['preview']}; {TIMING['support']}.",
              'Process: ' + ' '.join(f'{i + 1}) {step}' for i, step in enumerate(PROCESS)),
              '', 'Voice:'] + [f'- {rule}' for rule in VOICE['rules']]
    lines += ['', 'Ethics (quote exactly):',
              f"- Email opt-out: {ETHICS['opt_out_email']}",
              f"- SMS opt-out: {ETHICS['opt_out_sms']}",
              f'- Charging: {VOICE["signoff"]}',
              f"- Suppression: {ETHICS['suppression']}",
              '', 'Never promise:'] + [f'- {line}' for line in NON_PROMISES]
    return '\n'.join(lines)


def public():
    """Template-safe brand facts for public pages — no secrets, no internals."""
    return {
        'studio': STUDIO['name'], 'tagline': TAGLINE, 'brain': BRAIN_VERSION,
        'tiers': [{'id': key, 'name': row['name'],
                   'price_label': (f"${row['price']:,}" if row['price'] is not None else 'estimate'),
                   'unit': row['unit'], 'pages': row['pages'], 'revisions': row.get('revisions'),
                   'line': tier_line(key), 'blurb': row['blurb']} for key, row in TIERS.items()],
        'timing': dict(TIMING), 'process': list(PROCESS),
        'contact': dict(CONTACT), 'sectors': list(SECTORS),
    }


def lifecycle():
    """The business run start → delivery → review: stage, owner, route, evidence."""
    return [
        {'stage': 'discover', 'label': 'Find businesses', 'owner': 'scout',
         'via': 'crew pipeline: campaign / research', 'evidence': 'leads + source receipts'},
        {'stage': 'verify', 'label': 'Check the listing', 'owner': 'auditor',
         'via': 'crew pipeline: campaign / research', 'evidence': 'site_audits + ranked gaps'},
        {'stage': 'concept', 'label': 'Build the concept', 'owner': 'builder',
         'via': 'crew pipeline: campaign / prepare + review link /r/<token>',
         'evidence': 'review_links + views + answers'},
        {'stage': 'outreach', 'label': 'First message', 'owner': 'scribe',
         'via': 'crew pipeline: campaign + owner approval queue', 'evidence': 'draft artifacts + approvals'},
        {'stage': 'dispatch', 'label': 'Send or queue', 'owner': 'closer',
         'via': 'owner approval → SMTP or outbox', 'evidence': 'crew_dispatch + sends'},
        {'stage': 'capture', 'label': 'Answer & capture', 'owner': 'receptionist',
         'via': 'front desk on every page + /enquire', 'evidence': 'enquiries + receptionist_threads'},
        {'stage': 'deliver', 'label': 'Build & launch', 'owner': 'studio',
         'via': '/workspace projects + client portal', 'evidence': 'projects + invoices'},
        {'stage': 'review', 'label': 'Launch kit & review', 'owner': 'brag',
         'via': 'crew pipeline: launch + /reviews', 'evidence': 'launch artifacts + client_reviews'},
    ]


def review_ask(lead_name='', project='', studio=''):
    """A draft review request for won work — honest, no incentive, no fake link."""
    studio = (studio or STUDIO['name']).strip()
    about = project or (f'your website with {lead_name}' if lead_name else 'your website')
    subject = f'How did {about} turn out?'
    body = (f"Hi{( ' ' + lead_name) if lead_name else ''},\n\n"
            f"Now that {about} is live: would you leave a few words about working with {studio}? "
            f"{ETHICS['review_ask_honest']}\n\n"
            'Just reply to this message — a sentence or two and, if you like, a 1–5 rating. '
            'With your permission the studio quotes it word for word, or not at all.\n\n'
            f'Thank you either way.\n\n{studio}')
    return {'subject': subject[:200], 'body': body[:1500]}
