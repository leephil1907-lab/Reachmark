"""Business-specific one-page website generation.

This is the module that turns a *saved business record* (plus any measured audit
and harvested brand) into a complete one-page website spec:

    theme      the visual system (trade palette, or the colours/logo/fonts actually
               observed on the business's own page)
    copy       business-specific headline, tagline, about and three offers
    brandmark  a generated SVG monogram when the business has no logo to harvest
    images     the business's own imagery first, craft photography behind it
    facts      the measured, saved fields the page is allowed to state
    hours      the listed opening hours, parsed into a readable weekly table
    map        a real, keyless map (OpenStreetMap when we have coordinates)
    reviews    the business's real Google rating, plus a "leave a review" link
    faq        honest, localized answers built only from saved fields
    jsonld     LocalBusiness structured data so the page is a real, indexable site

Design rules (the same ones the rest of the crew lives by):

* **Facts never come from a model.** Copy is generated from the business's own
  gathered fields. When a language-model provider is configured it only improves
  the *phrasing*; the deterministic engine is always the fallback and the model can
  never introduce a price, a review, an hour or a claim.
* **Nothing is invented.** Missing fields stay missing. The page says so rather
  than filling the gap.
* **The design matches the business.** The theme is the trade's own palette, or the
  business's observed brand when we could read it, never the studio's house style.
"""
import html
import json
import re
from urllib.parse import quote

from web.concept import detect_archetype, concept_copy, build_theme, ARCH_THEMES
from web.i18n import t as _t

# Words a model is never allowed to put in a business's mouth.
BANNED = ('award-winning', 'award winning', 'best in', 'number one', 'number 1',
          '#1', 'guaranteed', 'world-class', 'world class', 'leading', 'top-rated',
          'top rated', 'cheapest', 'unbeatable', 'the best', 'industry-leading')
# A digit in generated prose is a red flag: prices, hours, ratings and years are
# facts, and facts come only from saved fields.
DIGIT_RE = re.compile(r'\d')

# Opening-hours parsing (OpenStreetMap / schema.org style day codes).
_DAY_CODES = ('mo', 'tu', 'we', 'th', 'fr', 'sa', 'su')
_DAY_NAMES = {'mo': 'Monday', 'tu': 'Tuesday', 'we': 'Wednesday', 'th': 'Thursday',
              'fr': 'Friday', 'sa': 'Saturday', 'su': 'Sunday'}


def _clean(text, limit=600):
    text = re.sub(r'\s+', ' ', str(text or '')).strip()
    return text[:limit]


def business_profile(lead, audit=None):
    """Assemble everything gathered about one business into a single profile.

    Pure function over already-saved data. Every value is something the record or a
    measured observation actually contained; empty means "not gathered".
    """
    lead = lead or {}
    audit = audit or {}
    observations = audit.get('observations') or {}
    brand = observations.get('brand') or {}
    signals = observations.get('signals') or {}
    try:
        rating = float(lead.get('rating')) if lead.get('rating') not in (None, '') else None
    except (TypeError, ValueError):
        rating = None
    try:
        review_count = int(lead.get('review_count')) if lead.get('review_count') not in (None, '') else None
    except (TypeError, ValueError):
        review_count = None
    try:
        latitude = float(lead.get('latitude')) if lead.get('latitude') not in (None, '') else None
    except (TypeError, ValueError):
        latitude = None
    try:
        longitude = float(lead.get('longitude')) if lead.get('longitude') not in (None, '') else None
    except (TypeError, ValueError):
        longitude = None
    return {
        'name': _clean(lead.get('name'), 120),
        'category': _clean(lead.get('category'), 80),
        'city': _clean(lead.get('city'), 80),
        'address': _clean(lead.get('address'), 200),
        'phone': _clean(lead.get('phone'), 40),
        'email': _clean(lead.get('email'), 120),
        'hours': _clean(lead.get('opening_hours'), 200),
        'website': _clean(lead.get('website'), 300),
        'rating': rating,
        'review_count': review_count,
        'place_id': _clean(lead.get('place_id'), 120),
        'latitude': latitude,
        'longitude': longitude,
        'brand': brand,
        'signals': signals,
        'site_title': _clean(signals.get('title') or brand.get('title'), 160),
        'site_description': _clean(signals.get('meta_description') or brand.get('description'), 300),
        'audit_status': _clean(audit.get('status') or lead.get('audit_status'), 40),
    }


def _initials(name):
    """Up to two initials from a business name, for the generated brandmark."""
    words = [w for w in re.split(r'[^\w&]+', name or '') if w]
    if not words:
        return '\u00b7'
    if len(words) == 1:
        return words[0][:2].upper()
    return (words[0][0] + words[1][0]).upper()


def brandmark_svg(name, accent, ink='#fff8ef'):
    """A clean monogram logo for a business that has no logo to harvest.

    Deterministic and self-contained: a rounded tile in the business's accent colour
    carrying its initials. Never claims to be the business's real logo.
    """
    initials = html.escape(_initials(name))
    label = html.escape((name or 'Business') + ' monogram')
    accent = accent if re.fullmatch(r'#[0-9a-fA-F]{6}', accent or '') else '#20251F'
    ink = ink if re.fullmatch(r'#[0-9a-fA-F]{6}', ink or '') else '#fff8ef'
    return (
        '<svg viewBox="0 0 64 64" role="img" aria-label="' + label + '" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<rect width="64" height="64" rx="16" fill="' + accent + '"/>'
        '<text x="32" y="42" text-anchor="middle" '
        'font-family="Manrope,Arial,sans-serif" font-size="26" font-weight="800" '
        'fill="' + ink + '">' + initials + '</text></svg>'
    )


def _expand_days(token):
    """'mo-fr' -> ['Monday'..'Friday']; 'sa' -> ['Saturday']; junk -> []."""
    token = (token or '').strip().lower()
    if not token:
        return []
    if '-' in token:
        a, b = (p.strip()[:2] for p in token.split('-', 1))
        if a in _DAY_CODES and b in _DAY_CODES:
            i, j = _DAY_CODES.index(a), _DAY_CODES.index(b)
            span = _DAY_CODES[i:j + 1] if i <= j else _DAY_CODES[i:] + _DAY_CODES[:j + 1]
            return [_DAY_NAMES[d] for d in span]
    if token[:2] in _DAY_CODES:
        return [_DAY_NAMES[token[:2]]]
    return []


def _day_label(days):
    """Collapse a day list into a readable label ('Monday – Friday', 'Every day')."""
    if len(days) >= 7:
        return 'Every day'
    idx = sorted(_DAY_CODES.index(d[:2].lower()) for d in days if d[:2].lower() in _DAY_CODES)
    if len(idx) >= 2 and idx == list(range(idx[0], idx[-1] + 1)):
        return f'{_DAY_NAMES[_DAY_CODES[idx[0]]]} \u2013 {_DAY_NAMES[_DAY_CODES[idx[-1]]]}'
    return ', '.join(days)


def parse_hours(raw):
    """Turn a listing's opening hours into a readable weekly table.

    Handles the common OpenStreetMap forms: 'Mo-Fr 07:00-15:00', 'Mo-Su 00:00-24:00',
    'Mo,Tu,We 09:00-17:00; Sa 10:00-14:00' and '24/7'. Returns [] when nothing parses.
    """
    raw = _clean(raw, 200)
    if not raw:
        return []
    if raw.strip().lower() in ('24/7', '24/7 open', 'open 24/7'):
        return [{'day': 'Every day', 'time': 'Open 24 hours'}]
    rows = []
    for part in re.split(r'[;|]', raw):
        part = part.strip()
        if not part:
            continue
        match = re.match(r'^([A-Za-z,\-\s]+?)\s+([0-9].*)$', part)
        if not match:
            continue
        days = []
        for token in re.split(r'[,\s]+', match.group(1)):
            days.extend(_expand_days(token))
        if not days:
            continue
        times = re.sub(r'\s*-\s*', ' \u2013 ', match.group(2).strip())
        rows.append({'day': _day_label(days), 'time': times})
    return rows[:7]


def _map(profile):
    """A real, keyless map: OpenStreetMap when we have coordinates, else a search embed."""
    lat, lon = profile.get('latitude'), profile.get('longitude')
    query = profile.get('address') or profile.get('city')
    if lat is not None and lon is not None:
        d = 0.008
        bbox = f'{lon - d},{lat - d},{lon + d},{lat + d}'
        return {
            'embed': f'https://www.openstreetmap.org/export/embed.html?bbox={bbox}&layer=mapnik&marker={lat},{lon}',
            'link': f'https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}',
            'label': profile.get('address') or profile.get('city') or '',
            'source': 'OpenStreetMap',
        }
    if query:
        return {
            'embed': f'https://maps.google.com/maps?q={quote(query)}&z=15&output=embed',
            'link': f'https://www.google.com/maps/search/?api=1&query={quote(query)}',
            'label': query,
            'source': 'Google Maps',
        }
    return None


def _reviews(profile):
    """The business's real Google rating (when we read it) plus a leave-a-review link.

    Nothing is invented: the rating is only ever the number the listing carried, and
    the review link points at the business's own Google listing.
    """
    name = profile.get('name')
    place_id = profile.get('place_id')
    city = profile.get('city') or ''
    if place_id:
        review_url = f'https://search.google.com/local/writereview?placeid={quote(place_id)}'
    elif name:
        review_url = f'https://www.google.com/maps/search/?api=1&query={quote((name + " " + city).strip())}'
    else:
        review_url = ''
    rating = profile.get('rating')
    count = profile.get('review_count')
    if not rating and not review_url:
        return None
    stars = int(round(rating)) if rating else 0
    return {'rating': rating, 'count': count, 'review_url': review_url,
            'stars': max(0, min(5, stars))}


def _faq(profile, locale='en'):
    """Honest, localized answers built only from saved fields.

    Each entry is included only when the page can answer it truthfully: the contact
    answer is always safe, the location answer needs an address or city, and the
    hours answer needs listed hours.
    """
    items = [{'q': _t('pc.faq1_q', locale), 'a': _t('pc.faq1_a', locale)}]
    if profile.get('address') or profile.get('city'):
        items.append({'q': _t('pc.faq2_q', locale), 'a': _t('pc.faq2_a', locale)})
    if profile.get('hours'):
        items.append({'q': _t('pc.faq3_q', locale), 'a': _t('pc.faq3_a', locale)})
    items.append({'q': _t('pc.faq4_q', locale), 'a': _t('pc.faq4_a', locale)})
    return items


def _jsonld(profile, site):
    """LocalBusiness structured data so the page is a real, indexable website."""
    data = {'@context': 'https://schema.org', '@type': 'LocalBusiness'}
    if profile.get('name'):
        data['name'] = profile['name']
    if profile.get('category'):
        data['description'] = f"{profile['category']}" + (f" in {profile['city']}" if profile.get('city') else '')
    if profile.get('address') or profile.get('city'):
        addr = {'@type': 'PostalAddress'}
        if profile.get('address'):
            addr['streetAddress'] = profile['address']
        if profile.get('city'):
            addr['addressLocality'] = profile['city']
        data['address'] = addr
    if profile.get('phone'):
        data['telephone'] = profile['phone']
    if profile.get('email'):
        data['email'] = profile['email']
    if profile.get('website'):
        data['url'] = profile['website']
    if profile.get('latitude') is not None and profile.get('longitude') is not None:
        data['geo'] = {'@type': 'GeoCoordinates', 'latitude': profile['latitude'],
                       'longitude': profile['longitude']}
    if profile.get('hours'):
        data['openingHours'] = profile['hours']
    if profile.get('rating') and profile.get('review_count'):
        data['aggregateRating'] = {'@type': 'AggregateRating',
                                   'ratingValue': profile['rating'],
                                   'reviewCount': profile['review_count']}
    return data


def _deterministic_copy(profile, archetype, locale='en'):
    """Craft-specific copy that names the real business, category and city.

    Built on the localized archetype strings so all six locales stay covered, then
    personalised with the business's own saved fields.
    """
    base = concept_copy(archetype, locale)
    name = profile['name'] or _t('pc.cat', locale)
    category = profile['category'] or base['tag']
    city = profile['city']
    where = _t('pc.hero_in', locale).format(c=city) if city else ''
    about = _t('pc.intro_a', locale).format(c=category.lower()) + where + '. ' + base['about']
    # If the business's own page described itself, quote it as their words.
    if profile['site_description'] and profile['site_description'].lower() not in about.lower():
        about = about + ' ' + profile['site_description']
    offers = [{'t': o['t'], 'd': o['d']} for o in base['offers']]
    return {'tag': base['tag'], 'about': _clean(about, 700), 'offers': offers,
            'headline': name, 'cta': _t('pc.cta', locale), 'archetype': archetype,
            'generated': False}


def _llm_copy(profile, archetype, locale='en'):
    """Ask the configured provider for better phrasing. Returns None on any problem.

    The model receives only the saved profile and is told, in the system prompt, that
    it may not invent anything. Its answer is validated before it is trusted.
    """
    try:
        from web.ai_provider import safe_complete
    except Exception:
        return None
    base = concept_copy(archetype, locale)
    system = (
        'You write short, honest website copy for a small local business. '
        'Use ONLY the facts in the JSON you are given. Never invent prices, reviews, '
        'opening hours, certifications, awards, years or claims. Never use words like '
        '"award-winning", "best", "guaranteed" or "number one". Do not use digits. '
        'Write in the same language as the locale code. '
        'Return strict JSON: {"tag": "...", "about": "...", '
        '"offers": [{"t": "...", "d": "..."}, {"t": "...", "d": "..."}, {"t": "...", "d": "..."}]}. '
        'tag is one short line (max 60 chars). about is 2-3 sentences (max 320 chars). '
        'Each offer title is 2-4 words and each offer description is one sentence.'
    )
    user = json.dumps({
        'locale': locale,
        'business': {k: profile[k] for k in ('name', 'category', 'city', 'address', 'hours')},
        'their_own_words': profile['site_description'],
        'craft_direction': {'tag': base['tag'], 'about': base['about'],
                            'offers': [o['t'] for o in base['offers']]},
    }, ensure_ascii=False)
    text, meta = safe_complete(system, user, max_tokens=600, temperature=0.5)
    if not text:
        return None
    return _validate_copy(text, profile, archetype, locale)


def _validate_copy(text, profile, archetype, locale):
    """Accept a model answer only if it is well-formed and invents nothing."""
    match = re.search(r'\{.*\}', text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return None
    tag = _clean(data.get('tag'), 80)
    about = _clean(data.get('about'), 400)
    offers = data.get('offers')
    if not tag or not about or not isinstance(offers, list) or len(offers) < 3:
        return None
    cleaned = []
    for offer in offers[:3]:
        if not isinstance(offer, dict):
            return None
        title = _clean(offer.get('t'), 60)
        desc = _clean(offer.get('d'), 200)
        if not title or not desc:
            return None
        cleaned.append({'t': title, 'd': desc})
    blob = ' '.join([tag, about] + [o['t'] + ' ' + o['d'] for o in cleaned]).lower()
    if any(word in blob for word in BANNED) or DIGIT_RE.search(blob):
        return None
    return {'tag': tag, 'about': about, 'offers': cleaned, 'headline': profile['name'],
            'cta': _t('pc.cta', locale), 'archetype': archetype, 'generated': True}


def generate_copy(profile, archetype, locale='en', use_llm=True):
    """Business-specific copy: model phrasing when available, deterministic always."""
    if use_llm:
        improved = _llm_copy(profile, archetype, locale)
        if improved:
            return improved
    return _deterministic_copy(profile, archetype, locale)


def _facts(profile):
    """The measured, saved fields the page is allowed to state."""
    facts = []
    if profile['category']:
        facts.append(f"Listed category: {profile['category']}")
    if profile['city']:
        facts.append(f"Area: {profile['city']}")
    if profile['phone']:
        facts.append(f"Phone on the listing: {profile['phone']}")
    if profile['email']:
        facts.append(f"E-mail published by the business: {profile['email']}")
    if profile['hours']:
        facts.append(f"Listed hours: {profile['hours']}")
    if profile['website']:
        facts.append(f"Website on the listing: {profile['website']}")
    return facts


def build_site(lead, audit=None, locale='en', use_llm=True):
    """Return the complete one-page website spec for one business.

    {'archetype', 'theme', 'copy', 'brandmark', 'brandmark_generated', 'images',
     'facts', 'profile', 'generated', 'hours', 'map', 'reviews', 'faq', 'jsonld'}
    """
    profile = business_profile(lead, audit)
    archetype = detect_archetype(profile['category'] or profile['name'])
    theme = build_theme(archetype, profile['brand'])
    copy = generate_copy(profile, archetype, locale, use_llm=use_llm)
    brandmark = ''
    brandmark_generated = False
    if not theme.get('logo'):
        brandmark = brandmark_svg(profile['name'], theme['colors']['accent'],
                                  theme['colors']['accent_ink'])
        brandmark_generated = True
    return {
        'archetype': archetype,
        'theme': theme,
        'copy': copy,
        'brandmark': brandmark,
        'brandmark_generated': brandmark_generated,
        'images': theme.get('images') or [],
        'facts': _facts(profile),
        'profile': profile,
        'generated': bool(copy.get('generated')),
        'hours': parse_hours(profile['hours']),
        'map': _map(profile),
        'reviews': _reviews(profile),
        'faq': _faq(profile, locale),
        'jsonld': _jsonld(profile, None),
    }
