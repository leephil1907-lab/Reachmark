"""Measured, bounded observations about a public web page.

Every value this module returns is something a program actually read from a public
response — a status code, a byte count, a header, the presence of a `<meta
viewport>` tag. It deliberately produces **no quality score and no opinion**: the
Auditor agent turns these observations into a ranked list of gaps, and the console
always labels that ranking as "observed gaps", never as proof that a business needs
work. That distinction is the whole point of this project.

Network policy: public hosts only, standard ports only, HTTP(S) only, at most
``max_bytes`` read, honours robots.txt via ``agent_scout.robots_allowed``.
"""
import re, time
from datetime import datetime, timezone

import requests

UA = 'ReachmarkCrew/1.0 (+on-page observation for the studio owner; respects robots.txt)'
COPYRIGHT_RE = re.compile(r'(?:©|&copy;|copyright)[^0-9]{0,20}((?:19|20)\d{2})', re.I)
YEAR_RE = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)')


def observe(url, max_bytes=65536, timeout=12, respect_robots=True, verify_links=True):
    """Return a dict of measured observations for one public URL.

    {'ok': bool, 'reason': str|None, 'final_url': str, 'status': int|None,
     'https': bool, 'ms': int, 'bytes': int, 'headers': {...}, 'signals': {...},
     'robots': {...}, 'link_check': {...}, 'fetched_at': iso}
    """
    from agents.agent_scout import _public_host, robots_allowed
    result = {'ok': False, 'reason': None, 'final_url': url, 'status': None, 'https': bool((url or '').startswith('https://')),
              'ms': None, 'bytes': 0, 'headers': {}, 'signals': {}, 'robots': {}, 'fetched_at': datetime.now(timezone.utc).isoformat()}
    if not (url or '').strip():
        result['reason'] = 'No website URL recorded in the source — nothing to observe.'
        return result
    target = url if '://' in url else 'https://' + url
    allowed, why = _public_host(target)
    if not allowed:
        result['reason'] = f'Not observed: {why}.'
        return result
    if respect_robots:
        import urllib.parse
        parsed = urllib.parse.urlparse(target)
        ok, reason = robots_allowed(f'{parsed.scheme}://{parsed.netloc}', parsed.path or '/', timeout=6)
        result['robots'] = {'allowed': ok, 'reason': reason}
        if not ok:
            result['reason'] = f'Not observed: {reason}.'
            return result

    started = time.monotonic()
    try:
        response = requests.get(target, headers={'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml'},
                                timeout=timeout, allow_redirects=True, stream=True)
    except requests.RequestException as exc:
        result['ms'] = int((time.monotonic() - started) * 1000)
        result['reason'] = f'Connection failed at check time ({type(exc).__name__}). Not proof the site is dead.'
        return result
    try:
        result['ms'] = int((time.monotonic() - started) * 1000)
        result['status'] = response.status_code
        result['final_url'] = str(response.url)
        result['https'] = str(response.url).startswith('https://')
        result['headers'] = {k.lower(): v[:300] for k, v in response.headers.items()
                             if k.lower() in ('content-type', 'server', 'last-modified', 'cache-control', 'x-powered-by')}
        if response.status_code in (401, 403, 429):
            result['reason'] = f'HTTP {response.status_code}: access restricted or rate-limited. Inconclusive, not a fault.'
            return result
        if response.status_code >= 400:
            result['reason'] = f'HTTP {response.status_code}: the listed page did not respond successfully at this time.'
            return result
        content_type = response.headers.get('Content-Type', '')
        if 'html' not in content_type:
            result['reason'] = f'Response is {content_type.split(";")[0] or "not HTML"} — a page was served, but not a readable web page.'
            return result
        raw = response.raw.read(max_bytes, decode_content=True) or b''
        html = raw.decode(response.encoding or 'utf-8', 'replace')
    except requests.RequestException as exc:
        result['reason'] = f'Read failed mid-response ({type(exc).__name__}).'
        return result
    finally:
        response.close()

    result['bytes'] = len(raw)
    body = re.sub(r'(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>', ' ', html)
    text = re.sub(r'\s+', ' ', re.sub(r'(?s)<[^>]+>', ' ', body))
    title_match = re.search(r'(?is)<title[^>]*>(.*?)</title>', html)
    desc_match = re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']{0,300})', html)
    viewport = re.search(r'(?is)<meta[^>]+name=["\']viewport["\'][^>]*content=["\']([^"\']{0,120})', html)
    copyright_years = [int(y) for y in COPYRIGHT_RE.findall(text)][:3]
    if not copyright_years:
        copyright_years = [int(y) for y in YEAR_RE.findall(text)][:1]
    anchor_refs = re.findall(r'(?i)href=["\']#([^"\'\s>]+)', html)
    anchor_ids = set(re.findall(r'(?is)(?:id|name)=["\']([^"\'\s>]+)', html))
    broken_anchors = sorted({ref for ref in anchor_refs if ref not in anchor_ids})
    signals = {
        'title': (title_match.group(1).strip()[:200] if title_match else ''),
        'meta_description': (desc_match.group(1).strip()[:300] if desc_match else ''),
        'viewport': (viewport.group(1).strip() if viewport else ''),
        'lang': (re.search(r'(?is)<html[^>]+lang=["\']([a-zA-Z\-]{2,10})', html) or [None, ''])[1],
        'h1_count': len(re.findall(r'(?is)<h1[\s>]', html)),
        'h2_count': len(re.findall(r'(?is)<h2[\s>]', html)),
        'form_count': len(re.findall(r'(?is)<form[\s>]', html)),
        'img_count': len(re.findall(r'(?is)<img[\s>]', html)),
        'img_missing_alt': len(re.findall(r'(?is)<img(?![^>]*\balt=)[^>]*>', html)),
        'has_tel_link': bool(re.search(r'href=["\']tel:', html, re.I)),
        'has_mailto_link': bool(re.search(r'href=["\']mailto:', html, re.I)),
        'has_contact_link': bool(re.search(r'href=["\'][^"\']*(contact|kontakt|contacto)[^"\']*["\']', html, re.I)),
        'has_booking_link': bool(re.search(r'(?i)(book\s*(now|online|appointment)|calendly|booksy|simplybook|setmore|acuity)', html + text)),
        'has_map_embed': bool(re.search(r'(?i)(google\.com/maps|maps\.google|openstreetmap\.org/export|mapbox)', html)),
        'has_social_link': bool(re.search(r'(?i)(facebook\.com|instagram\.com|linkedin\.com|tiktok\.com)', html)),
        'has_analytics': bool(re.search(r'(?i)(googletagmanager|google-analytics|gtag\(|plausible\.io|matomo|fathom)', html)),
        'has_schema': bool(re.search(r'(?i)application/ld\+json', html)),
        'copyright_years': copyright_years,
        'visible_words': len(text.split()),
        'has_favicon': bool(re.search(r'(?is)<link[^>]+rel=["\'](?:shortcut )?icon["\']', html)),
        'http_resource_refs': len(re.findall(r'(?i)(?:src|href)=["\']http://', html)),
        'generator': ((re.search(r'(?is)<meta[^>]+name=["\']generator["\'][^>]*content=["\']([^"\']{0,80})', html)
                       or [None, ''])[1] or '').strip(),
        'server_header': '; '.join(value for key, value in result['headers'].items()
                                   if key in ('server', 'x-powered-by')),
        'anchor_refs': len(anchor_refs),
        'broken_anchors': broken_anchors[:5],
        'broken_anchor_count': len(broken_anchors),
    }
    result['signals'] = signals
    result['link_check'] = (check_links(html, result['final_url']) if verify_links
                            else {'checked': 0, 'broken': [], 'skipped': 0})
    result['ok'] = True
    return result


def check_links(html, base_url, limit=6, timeout=5):
    """Follow up to `limit` same-host links from the fetched page. Bounded and honest.

    Returns {'checked': n, 'broken': [{'url', 'status', 'note'}], 'skipped': n}. A failed
    fetch is reported as failed-at-check-time, never as proof the destination is dead.
    """
    import urllib.parse
    from agents.agent_scout import _public_host
    empty = {'checked': 0, 'broken': [], 'skipped': 0}
    try:
        base_host = urllib.parse.urlparse(base_url or '').netloc.lower()
    except Exception:
        return empty
    if not base_host:
        return empty
    seen, targets, skipped = set(), [], 0
    for ref in re.findall(r'(?i)href=["\']([^"\'#>]+)', html or ''):
        if ref.lower().startswith(('javascript:', 'mailto:', 'tel:', 'data:')):
            skipped += 1
            continue
        absolute = urllib.parse.urljoin(base_url, ref.split('#')[0])
        if not absolute.lower().startswith(('http://', 'https://')):
            skipped += 1
            continue
        if urllib.parse.urlparse(absolute).netloc.lower() != base_host:
            skipped += 1
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        targets.append(absolute)
    checked, broken = 0, []
    for target in targets[:limit]:
        allowed, _why = _public_host(target)
        if not allowed:
            skipped += 1
            continue
        checked += 1
        try:
            response = requests.head(target, headers={'User-Agent': UA}, timeout=timeout,
                                     allow_redirects=True)
            if response.status_code in (405, 501):
                response = requests.get(target, headers={'User-Agent': UA}, timeout=timeout,
                                        allow_redirects=True, stream=True)
                response.close()
            if response.status_code >= 400:
                broken.append({'url': target[:300], 'status': response.status_code,
                               'note': f'HTTP {response.status_code} at check time.'})
        except requests.RequestException as exc:
            broken.append({'url': target[:300], 'status': None,
                           'note': f'{type(exc).__name__} at check time — may be temporary, '
                                   'not proof the page is gone.'})
    skipped += len(targets) - min(len(targets), limit)
    return {'checked': checked, 'broken': broken, 'skipped': skipped}


def gaps_from(observations, lead):
    """Ranked, sourced gap list. Weight table is fixed in code — nothing invented."""
    weights = [
        ('no_website_listed', 3, 'The source lists no website at all (not proof there is none).'),
        ('social_only', 3, 'The only listed URL is a social profile.'),
        ('dns_unresolved', 3, 'The listed domain did not resolve at check time.'),
        ('parked_suspected', 3, 'Domain-parking or domain-sale wording appeared on the page.'),
        ('http_error', 2, 'The listed page returned a client or server error.'),
        ('unreachable', 1, 'The listed page did not connect at check time (may be local network or temporary).'),
        ('no_https', 2, 'The page was served over plain HTTP, without TLS.'),
        ('no_viewport', 2, 'No viewport meta tag — the page does not declare mobile scaling.'),
        ('slow_first_byte', 1, 'First byte took over 2.5 seconds on this check.'),
        ('thin_page', 1, 'Fewer than 120 words of visible text on the page read.'),
        ('no_contact_path', 1, 'No contact link, tel: or mailto: link found on the page read.'),
        ('no_form_or_booking', 1, 'No form, booking link or enquiry path found on the page read.'),
        ('stale_copyright', 1, 'The newest year printed on the page is two or more years old.'),
        ('no_description', 1, 'No meta description — search snippets will be written by the search engine.'),
        ('no_images', 1, 'No images found on the page read.'),
        ('images_missing_alt', 1, 'Images without alt text were found on the page read.'),
        ('missing_title', 1, 'No page title — browser tabs and search results show the bare URL.'),
        ('missing_lang', 1, 'No page language declared — screen readers guess the pronunciation.'),
        ('no_h1', 1, 'No H1 heading — the page never states its topic.'),
        ('many_h1', 1, 'More than one H1 heading — the page has competing top headings.'),
        ('broken_anchors', 2, 'In-page links point at sections that do not exist.'),
        ('mixed_content', 2, 'A secure page loads resources over plain HTTP.'),
        ('no_favicon', 1, 'No favicon — browser tabs show a blank page icon.'),
        ('server_disclosure', 1, 'The server advertises its software in response headers.'),
        ('no_analytics_seen', 1, 'No common analytics snippet found on the page read — visits may go unmeasured.'),
        ('broken_links', 2, 'Sampled on-site links failed at check time.'),
    ]
    found, sources, reasons, evidence = [], {}, {}, {}
    status = (lead.get('audit_status') or '').upper()
    if not (lead.get('website') or '').strip():
        found.append('no_website_listed')
    elif status == 'SOCIAL_ONLY' or lead.get('status') == 'SOCIAL_ONLY':
        found.append('social_only')
    if status == 'DNS_UNRESOLVED':
        found.append('dns_unresolved')
    if status == 'PARKED_SUSPECTED':
        found.append('parked_suspected')
    if status == 'HTTP_ERROR':
        found.append('http_error')
    if status == 'UNREACHABLE':
        found.append('unreachable')
    signals = (observations or {}).get('signals', {})
    if observations and observations.get('ok'):
        if not observations.get('https'):
            found.append('no_https')
        if not signals.get('viewport'):
            found.append('no_viewport')
        if (observations.get('ms') or 0) > 2500:
            found.append('slow_first_byte')
        if (signals.get('visible_words') or 0) < 120:
            found.append('thin_page')
        if not (signals.get('has_contact_link') or signals.get('has_tel_link') or signals.get('has_mailto_link')):
            found.append('no_contact_path')
        if not (signals.get('form_count') or signals.get('has_booking_link')):
            found.append('no_form_or_booking')
        years = [y for y in (signals.get('copyright_years') or []) if isinstance(y, int)]
        if years and max(years) <= datetime.now(timezone.utc).year - 2:
            found.append('stale_copyright')
        if not signals.get('meta_description'):
            found.append('no_description')
        if not signals.get('img_count'):
            found.append('no_images')
        if signals.get('img_missing_alt'):
            found.append('images_missing_alt')
            reasons['images_missing_alt'] = (
                f"{signals['img_missing_alt']} of {signals.get('img_count') or '?'} images have no alt text — "
                'screen readers and image search skip them.')
        if not (signals.get('title') or '').strip():
            found.append('missing_title')
        if not (signals.get('lang') or '').strip():
            found.append('missing_lang')
        h1s = signals.get('h1_count') or 0
        if h1s == 0:
            found.append('no_h1')
        elif h1s > 1:
            found.append('many_h1')
            reasons['many_h1'] = (f'{h1s} H1 headings on one page — more than one top heading '
                                   'confuses the structure.')
        if signals.get('broken_anchor_count'):
            found.append('broken_anchors')
            first = (signals.get('broken_anchors') or ['?'])[0]
            reasons['broken_anchors'] = (
                f"{signals['broken_anchor_count']} in-page link(s) point at sections that do not exist "
                f'(e.g. #{first}) — visitors tap and nothing happens.')
        if observations.get('https') and (signals.get('http_resource_refs') or 0):
            found.append('mixed_content')
            reasons['mixed_content'] = (
                f"{signals['http_resource_refs']} resource(s) load over plain HTTP on a secure page — "
                'browsers may block them.')
        if 'has_favicon' in signals and not signals.get('has_favicon'):
            found.append('no_favicon')
        if (signals.get('server_header') or '').strip():
            found.append('server_disclosure')
        if 'has_analytics' in signals and not signals.get('has_analytics'):
            found.append('no_analytics_seen')
        check = observations.get('link_check') or {}
        if check.get('broken'):
            found.append('broken_links')
            reasons['broken_links'] = (
                f"{len(check['broken'])} of {check.get('checked', '?')} sampled on-site link(s) failed "
                f"at check time (e.g. {check['broken'][0]['url']}) — visitors hit dead ends.")
            evidence['broken_links'] = [item['url'] for item in check['broken'][:3]]
    table = {key: (weight, why) for key, weight, why in weights}
    ranked, total = [], 0
    for key in dict.fromkeys(found):
        weight, why = table[key]
        why = reasons.get(key, why)
        total += weight
        ranked.append({'key': key, 'weight': weight, 'reason': why, 'evidence': evidence.get(key, ''),
                       'source': 'Listing' if key in ('no_website_listed', 'social_only', 'dns_unresolved',
                                                      'parked_suspected', 'http_error', 'unreachable') else 'Measured on page'})
    ranked.sort(key=lambda item: -item['weight'])
    tier = 'hot' if total >= 6 else 'warm' if total >= 3 else 'watch' if total >= 1 else 'no_clear_gap'
    return {'gaps': ranked, 'score': total, 'tier': tier,
            'disclaimer': 'A ranked list of observed gaps at this point in time — not a claim that the business '
                          'wants or needs a new website. Confirm with the business.'}
