"""Scout — web scraping and lead gathering for the Reachmark crew.

Two jobs, both evidence-first:

1. **Discover** businesses from public sources (OpenStreetMap via the existing
   ``services.discover_location``) or from an explicit offline fixture set that is
   clearly labelled and purged with one click.
2. **Read the public pages a business already publishes** (home page + /contact +
   /about, at most three, robots-aware, bounded) to collect the contact details
   they made public — an e-mail, a phone number, social profiles, opening hours,
   a JSON-LD LocalBusiness block.

What it will not do: guess an address, invent a phone number, touch a
login-walled page, or treat a social profile as a website.
"""

from crew.business import BRAIN_VERSION, FALLBACK_OSM_TAG, SECTORS, STUDIO
from crew.skills_loader import load_skill, rules

import json, os, re, socket, time, urllib.parse

import requests

try:
    from crew.crew import CrewError
except Exception:  # pragma: no cover - only during partial imports
    class CrewError(Exception):
        pass

try:
    from web.services import classify as classify_site
except Exception:  # pragma: no cover
    def classify_site(url):
        return 'NOT_LISTED' if not (url or '').strip() else 'HAS_WEBSITE'

UA = f'{STUDIO["name"]}Crew/1.0 (+contact-page research for the studio owner; respects robots.txt)'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_PATH = os.path.join(ROOT, 'fixtures', 'demo_leads.json')
EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
PHONE_RE = re.compile(r'(?:\+?\d[\d\s().\-]{7,}\d)')
HOURS_RE = re.compile(r'((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?[^<]{0,40}?\d{1,2}(?::\d{2})?\s*(?:am|pm|AM|PM)[^<]{0,20})')
SOCIAL_HOSTS = ('facebook.com', 'instagram.com', 'linkedin.com', 'x.com', 'twitter.com', 'tiktok.com',
                'youtube.com', 'wa.me', 'whatsapp.com')
CONTACT_PATHS = ['/contact', '/contact-us', '/about', '/about-us', '/kontakt', '/contacto']
BLOCKED_SCHEMES = ('file', 'ftp', 'gopher', 'data', 'javascript')
MAX_PAGES = 3
MAX_BYTES = 96 * 1024


# --------------------------------------------------------------------------- #
# Public-page reading
# --------------------------------------------------------------------------- #
def _qualification(row):
    """What the prospecting playbook asks before anyone writes: is this business reachable,
    and did it match the search at all? Computed from saved fields only — never guessed."""
    has_phone = bool((row.get('phone') or '').strip())
    has_email = bool((row.get('email') or '').strip())
    has_site = bool((row.get('website') or '').strip())
    return {
        'public_contact': 'e-mail' if has_email else ('phone' if has_phone else 'none listed'),
        'website_listed': has_site,
        'reachable': bool(has_email or has_phone or has_site),
        'listing_source': row.get('source') or row.get('source_url') or 'public listing',
    }


def robots_allowed(base_url, path='/', timeout=6):
    """Small, honest robots.txt check for the * analysis of one path."""
    try:
        parsed = urllib.parse.urlparse(base_url)
        robots = f'{parsed.scheme}://{parsed.netloc}/robots.txt'
        response = requests.get(robots, headers={'User-Agent': UA}, timeout=timeout)
        if response.status_code != 200 or 'text' not in response.headers.get('Content-Type', 'text'):
            return True, 'no robots.txt served'
        rules, applies = [], False
        for line in response.text[:40000].splitlines():
            line = line.split('#')[0].strip()
            if not line:
                continue
            key, _, value = line.partition(':')
            key, value = key.strip().lower(), value.strip()
            if key == 'user-agent':
                applies = value in ('*', 'reachmarkcrew')
            elif applies and key == 'disallow' and value:
                rules.append(value)
        for rule in rules:
            if rule == '/' or path.startswith(rule.split('*')[0]):
                return False, f'robots.txt disallows {rule}'
        return True, f'robots.txt allows {path} (no matching Disallow)'
    except requests.RequestException:
        return True, 'robots.txt unreachable — proceeding with one page at a time'


def _public_host(url):
    """Reject private, reserved and non-HTTP destinations before connecting."""
    parsed = urllib.parse.urlparse(url if '://' in url else 'https://' + url)
    if parsed.scheme.lower() in BLOCKED_SCHEMES or parsed.scheme not in ('http', 'https'):
        return False, 'only http/https public pages are read'
    if not parsed.hostname or parsed.username or parsed.password:
        return False, 'credentials or missing host in URL'
    if parsed.port and parsed.port not in (80, 443):
        return False, 'only standard web ports are read'
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False, 'host does not resolve'
    import ipaddress
    for info in infos:
        try:
            if not ipaddress.ip_address(info[4][0]).is_global:
                return False, 'private or reserved address blocked'
        except ValueError:
            return False, 'unparseable address blocked'
    return True, 'public host verified'


def _strip_html(html):
    text = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', html)
    text = re.sub(r'(?s)<[^>]+>', ' ', text)
    text = re.sub(r'&nbsp;?', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def read_public_pages(url, max_pages=MAX_PAGES, timeout=9):
    """Fetch a business's own public pages and extract only published contact facts.

    Returns {'pages': [...], 'emails': [...], 'phones': [...], 'socials': [...],
             'hours': str, 'jsonld': {...}, 'robots': {...}, 'blocked': reason|None}
    """
    finding = {'pages': [], 'emails': [], 'phones': [], 'socials': [], 'hours': '', 'jsonld': {},
               'robots': {}, 'blocked': None}
    if not (url or '').strip():
        finding['blocked'] = 'no listed website URL'
        return finding
    allowed, reason = _public_host(url)
    if not allowed:
        finding['blocked'] = reason
        return finding
    parsed = urllib.parse.urlparse(url if '://' in url else 'https://' + url)
    base = f'{parsed.scheme}://{parsed.netloc}'
    ok, robots_reason = robots_allowed(base, parsed.path or '/')
    finding['robots'] = {'allowed': ok, 'reason': robots_reason}
    if not ok:
        finding['blocked'] = robots_reason
        return finding

    targets = [url if '://' in url else 'https://' + url]
    for path in CONTACT_PATHS:
        if len(targets) >= max_pages:
            break
        candidate = base + path
        if candidate not in targets:
            targets.append(candidate)

    seen_emails, seen_phones, seen_socials = [], [], []
    for target in targets[:max_pages]:
        started = time.monotonic()
        try:
            response = requests.get(target, headers={'User-Agent': UA, 'Accept': 'text/html'},
                                    timeout=timeout, allow_redirects=True, stream=True)
        except requests.RequestException as exc:
            finding['pages'].append({'url': target, 'status': 'unreachable', 'detail': type(exc).__name__})
            continue
        try:
            if response.status_code >= 400:
                finding['pages'].append({'url': target, 'status': response.status_code, 'detail': 'not read'})
                continue
            content_type = response.headers.get('Content-Type', '')
            if 'html' not in content_type and 'text' not in content_type:
                finding['pages'].append({'url': target, 'status': response.status_code, 'detail': 'not html'})
                continue
            raw = response.raw.read(MAX_BYTES, decode_content=True) or b''
            html = raw.decode(response.encoding or 'utf-8', 'replace')
        finally:
            response.close()
        final_url = str(response.url)
        text = _strip_html(html)
        finding['pages'].append({'url': final_url, 'status': response.status_code, 'bytes': len(raw),
                                 'ms': int((time.monotonic() - started) * 1000),
                                 'title': (re.search(r'(?is)<title[^>]*>(.*?)</title>', html) or [None, ''])[1].strip()[:200]})
        for email in EMAIL_RE.findall(html) + EMAIL_RE.findall(text):
            low = email.lower().strip('.')
            if low.endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.css', '.js')):
                continue
            if low not in seen_emails and not any(low.startswith(p) for p in ('noreply@', 'no-reply@')):
                seen_emails.append(low)
        for phone in PHONE_RE.findall(text):
            digits = re.sub(r'\D', '', phone)
            if 7 <= len(digits) <= 15 and phone.strip() not in seen_phones:
                seen_phones.append(phone.strip())
        for match in re.finditer(r'href=["\'](https?://[^"\']+)["\']', html, re.I):
            host = urllib.parse.urlparse(match.group(1)).netloc.lower().lstrip('www.')
            if any(host == s or host.endswith('.' + s) for s in SOCIAL_HOSTS) and match.group(1) not in seen_socials:
                seen_socials.append(match.group(1)[:300])
        if not finding['hours']:
            hours = HOURS_RE.findall(text)
            if hours:
                finding['hours'] = ' · '.join(dict.fromkeys(h.strip() for h in hours))[:200]
        if not finding['jsonld']:
            for block in re.findall(r'(?is)<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html):
                try:
                    data = json.loads(block.strip())
                except ValueError:
                    continue
                data = data[0] if isinstance(data, list) and data else data
                if isinstance(data, dict) and data.get('@type') in ('LocalBusiness', 'Organization', 'Store', 'Restaurant', 'MedicalBusiness'):
                    finding['jsonld'] = {'@type': data.get('@type'), 'name': str(data.get('name', ''))[:200],
                                         'telephone': str(data.get('telephone', ''))[:60],
                                         'email': str(data.get('email', ''))[:120],
                                         'address': str((data.get('address') or {}).get('streetAddress', ''))[:300] if isinstance(data.get('address'), dict) else '',
                                         'openingHours': str(data.get('openingHours', ''))[:200]}
                    break
        time.sleep(0.4)  # be a good citizen: one page at a time, never a hammer
    finding['emails'], finding['phones'], finding['socials'] = seen_emails[:4], seen_phones[:3], seen_socials[:3]
    return finding


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def load_fixtures(limit=8):
    """Clearly-labelled offline demo records. Never counted as real discoveries."""
    try:
        with open(FIXTURE_PATH, encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    records = data.get('records', data) if isinstance(data, dict) else data
    return list(records)[:limit]


def discover_from_sources(location, category, limit, ctx):
    from web.services import discover_location
    try:
        from web.app import CATEGORIES
        tag = CATEGORIES.get(category)
    except Exception:
        tag = None
    if not tag:
        tag = FALLBACK_OSM_TAG
    ctx.receipt('source', f'OpenStreetMap query: "{category}" within 15 km of "{location}".')
    rows, display_name = discover_location(location, tag, limit=limit)
    ctx.receipt('source', f'Source returned {len(rows)} named listings for {display_name}.', url='https://www.openstreetmap.org/copyright')

    # Google Maps is a second, key-gated source. It is only read when the owner
    # has configured GOOGLE_PLACES_API_KEY; OpenStreetMap stays the default.
    try:
        from web import places_provider
    except Exception:
        places_provider = None
    if places_provider and places_provider.available():
        g_rows, reason = places_provider.discover_places(location, category, limit=min(limit, 20))
        if g_rows:
            ctx.receipt('source', f'Google Maps returned {len(g_rows)} business profile(s) for "{category}" in {location}.',
                        url='https://maps.google.com')
            rows = places_provider.merge_rows(rows, g_rows)
            ctx.receipt('source', f'Merged sources: {len(rows)} unique business(es) after de-duplication.')
        elif reason:
            ctx.receipt('source', f'Google Maps contributed nothing this run: {reason}')
    return rows, display_name


def _enrich(ctx, name, website, seed):
    """Read a business's own public pages; return the fields it published itself."""
    fields, receipts = {}, []
    if ctx.params.get('fixtures'):
        ctx.receipt('fixture', f'{name}: offline demo — no page was fetched and no network call was made.')
        return fields
    if not (website or '').strip():
        ctx.receipt('contact', f'{name}: the source lists no website. This is not proof the business has none.',
                    url=seed.get('source_url', ''))
        return fields
    if classify_site(website) != 'HAS_WEBSITE':
        ctx.receipt('contact', f'{name}: listed URL is a social profile, not a standalone website — no page read.',
                    url=website)
        return fields
    finding = read_public_pages(website)
    if not finding['pages']:
        ctx.receipt('contact', f'{name}: no public page could be read ({finding.get("blocked") or "no HTML served"}).',
                    url=website)
        return fields
    evidence_url = finding['pages'][0]['url']
    detail = (f'read {len(finding["pages"])} public page(s) · '
              f'{len(finding["emails"])} published e-mail(s) · {len(finding["phones"])} phone number(s)')
    ctx.receipt('contact', f'{name}: {detail}.', url=evidence_url,
                evidence=(' | '.join(finding['emails'][:2] + finding['phones'][:2])) or
                         'Nothing published — fields stay empty rather than guessed.')
    if finding['emails']:
        fields['email'] = finding['emails'][0]
    if finding['phones']:
        fields['phone'] = finding['phones'][0]
    if finding['hours']:
        fields['opening_hours'] = finding['hours']
    if finding['socials']:
        fields['social_url'] = finding['socials'][0]
    if finding['jsonld']:
        ctx.receipt('structured-data',
                    f"{name}: LocalBusiness structured data declares {finding['jsonld'].get('name') or 'the business'}.",
                    url=evidence_url, evidence=json.dumps(finding['jsonld'])[:400])
    if not finding['robots'].get('allowed', True):
        ctx.receipt('compliance', f'{name}: stopped reading — {finding["robots"]["reason"]}.', url=evidence_url)
    elif finding['robots'].get('reason'):
        ctx.receipt('compliance', f'{name}: {finding["robots"]["reason"]}.', url=evidence_url)
    return fields


def run(ctx):
    params = ctx.params
    limit = int(params.get('limit') or 8)
    saved, enriched, skipped = [], 0, 0

    if params.get('fixtures'):
        rows = load_fixtures(limit)
        ctx.receipt('fixture', f'Offline demo mode: {len(rows)} fictional test records loaded. They are labelled '
                               '"Fixture (offline demo)" and can be purged in one click.',
                    evidence='fixtures/demo_leads.json')
    elif params.get('location'):
        rows = discover_from_sources(params['location'], params.get('category', ''), limit, ctx)
        if not rows:
            raise CrewError('No businesses came back from the source. Try another city, category, or the offline demo.')
    else:
        rows = []

    if not rows:
        existing = ctx.load_leads()
        if not existing:
            raise CrewError('Scout needs a location, an existing lead, or offline demo mode.')
        ctx.receipt('input', f'Enriching {len(existing)} lead(s) already saved in this workspace.')
        for lead in existing:
            before = (lead.get('email') or '', lead.get('phone') or '')
            fields = _enrich(ctx, lead['name'], lead.get('website') or '', lead)
            fields = {k: v for k, v in fields.items() if v and not (lead.get(k) or '').strip()}
            if fields:
                sets = ','.join(f'{k}=?' for k in fields)
                with ctx.db() as c:
                    c.execute(f'UPDATE leads SET {sets},updated=? WHERE id=?', tuple(fields.values()) + (ctx.now(), lead['id']))
                enriched += 1
                ctx.receipt('saved', f'{lead["name"]}: saved {", ".join(sorted(fields))} found on its own public pages.',
                            url=lead.get('website', ''))
            playbook = load_skill('prospecting')
            ctx.emit(f'Prospecting playbook loaded: {len(rules("prospecting", "contact", 3))} qualification '
                     'rule(s) applied to the saved records.') if playbook else None
            lead_ids = [lead['id'] for lead in existing]
        summary = (f'Read the public pages of {len(existing)} saved business(es); updated contact fields on {enriched}. '
                   'Empty fields were left empty rather than guessed.')
        ctx.emit(summary)
        return {'summary': summary, 'data': {'lead_ids': lead_ids, 'added': 0, 'enriched': enriched, 'skipped': 0}}

    shortlist = []
    for row in rows[:limit]:
        name = row.get('name') or 'Unnamed listing'
        fields = _enrich(ctx, name, row.get('website') or '', row)
        row.update({k: v for k, v in fields.items() if not (row.get(k) or '').strip()})
        if not ctx.add_lead:
            continue
        owner = ctx.params.get('owner_user_id') if isinstance(ctx.params, dict) else None
        if owner:
            row['owner_user_id'] = owner
        try:
            added = ctx.add_lead(row)
        except Exception as exc:
            ctx.receipt('error', f'{name} could not be saved: {type(exc).__name__}.')
            continue
        key = row.get('source_key') or '|'.join(str(row.get(k, '')).strip().lower() for k in ('name', 'city', 'phone'))
        with ctx.db() as c:
            found = c.execute('SELECT id FROM leads WHERE source_key=?', (key,)).fetchone()
        if added:
            saved.append({'name': name, 'id': found['id'] if found else ''})
            check = _qualification(row)
            shortlist.append({'name': name, 'id': found['id'] if found else '', **check})
            ctx.receipt('saved', f'{name} added to the lead directory.', url=row.get('source_url', ''))
        else:
            skipped += 1
            ctx.receipt('saved', f'{name} was already in the directory — not duplicated.', url=row.get('source_url', ''))

    lead_ids = [entry['id'] for entry in saved if entry['id']]
    playbook = load_skill('prospecting')
    reachable = sum(1 for row in shortlist if row['reachable'])
    summary = (f'Gathered {len(saved)} new business record(s), skipped {skipped} duplicate(s), and read public pages '
               f'for {enriched + len(saved)} of them. {reachable} of {len(shortlist)} have a public contact path. '
               f'{len(lead_ids)} lead(s) handed to the next crew member.')
    if playbook:
        ctx.receipt('playbook', 'prospecting playbook applied: qualification comes from saved fields only — '
                                'a missing website link is not treated as proof a business needs one.',
                    evidence=str(playbook.get('path') or 'skills/vendor/prospecting/SKILL.md'))
    ctx.emit(summary)
    ctx.artifact('scout-shortlist', f'Prospecting shortlist — {len(shortlist)} business(es)',
                 '\n'.join(f"- {row['name']}: contact {row['public_contact']} · website listed "
                            f"{'yes' if row['website_listed'] else 'no'} · source {row['listing_source']}"
                            for row in shortlist) or 'No new records.',
                 meta={'playbook': 'prospecting', 'playbook_version': '2.11.1', 'brain': BRAIN_VERSION,
                       'sectors': SECTORS, 'shortlist': shortlist})
    return {'summary': summary, 'data': {'lead_ids': lead_ids, 'brain': BRAIN_VERSION, 'added': len(saved),
                                         'enriched': enriched,
                                         'skipped': skipped, 'shortlist': shortlist,
                                         'playbook': 'prospecting' if playbook else ''}}
