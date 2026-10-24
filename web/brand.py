"""Brand harvesting: the visual identity actually observed on a public page.

Pure functions over already-fetched HTML — no network calls here. Everything
returned is something the markup literally contained: a theme-color meta tag,
an og:image URL, hex codes printed in style blocks, font names from stylesheet
links. Each asset keeps a short `source` label so the studio can see *where*
it was seen, and the concept page only ever claims "observed on your page".

When a business has no readable page (or no brand traces on it), the concept
builder falls back to the trade archetype palette — still specific to the
craft, never the studio's own colours.
"""
import re
from urllib.parse import urljoin, urlparse

HEX_RE = re.compile(r'#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b')
META_TAG_RE = re.compile(r'(?is)<meta\s+[^>]*>')
LINK_TAG_RE = re.compile(r'(?is)<link\s+[^>]*>')
IMG_TAG_RE = re.compile(r'(?is)<img\s+[^>]*>')
STYLE_BLOCK_RE = re.compile(r'(?is)<style[^>]*>(.*?)</style>')
STYLE_ATTR_RE = re.compile(r'(?is)\sstyle\s*=\s*"([^"]{0,2000})"')
ATTR_RE = re.compile(r'''(?i)([\w\-:]+)\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))''')
FONT_FAMILY_RE = re.compile(r'(?i)font-family\s*:\s*([^;}{]{1,160})')
TRACKING_HINTS = ('pixel', 'track', 'beacon', 'spacer', 'blank.gif', 'transparent')


def _attrs(tag):
    """Parse tag attributes into a lowercase-keyed dict (first win)."""
    out = {}
    for m in ATTR_RE.finditer(tag):
        key = m.group(1).lower()
        if key not in out:
            out[key] = (m.group(3) if m.group(3) is not None
                        else m.group(4) if m.group(4) is not None else m.group(5))
    return out


def _absolute(base_url, ref):
    ref = (ref or '').strip()
    if not ref or ref.lower().startswith(('data:', 'javascript:', 'mailto:', 'tel:')):
        return ''
    try:
        absolute = urljoin(base_url or '', ref)
    except Exception:
        return ''
    if urlparse(absolute).scheme not in ('http', 'https'):
        return ''
    return absolute[:500]


def _normalise_hex(code):
    code = code.strip().lower()
    if len(code) == 4:  # #abc -> #aabbcc
        code = '#' + ''.join(ch * 2 for ch in code[1:])
    return code


def _is_usable_colour(code):
    """Drop pure neutrals so the accent pick is a real brand colour."""
    try:
        r, g, b = int(code[1:3], 16), int(code[3:5], 16), int(code[5:7], 16)
    except ValueError:
        return False
    if max(r, g, b) - min(r, g, b) < 24:  # grey / black / white
        return False
    if min(r, g, b) > 205:  # near-white page background
        return False
    if max(r, g, b) < 25:  # near-black page background
        return False
    return True


def _font_names(css_text):
    names = []
    for m in FONT_FAMILY_RE.finditer(css_text or ''):
        first = m.group(1).split(',')[0].strip().strip('"\'')
        if first and first.lower() not in ('inherit', 'initial', 'unset', 'serif',
                                           'sans-serif', 'monospace', 'cursive',
                                           'fantasy', 'system-ui'):
            names.append(first[:60])
    return names


def extract_brand(html, base_url, max_images=6):
    """Return the brand pack observed in `html` fetched from `base_url`.

    {'colors': [...up to 8 hex, most frequent first...], 'theme_color': str,
     'logo': str, 'logo_source': str, 'images': [{'url','alt'}],
     'fonts': [...up to 6...], 'site_name': str, 'title': str, 'description': str}
    Empty strings / lists mean "not observed" — never invented.
    """
    pack = {'colors': [], 'theme_color': '', 'background_color': '', 'text_color': '',
            'logo': '', 'logo_source': '', 'favicon': '', 'images': [], 'fonts': [],
            'site_name': '', 'title': '', 'description': '', 'navigation': [],
            'contact_details': [], 'social_links': [], 'service_description': '',
            'homepage_screenshot': '', 'mobile_screenshot': ''}
    html = html or ''
    if not html.strip():
        return pack

    metas = [_attrs(t) for t in META_TAG_RE.findall(html[:200000])]
    meta_content = {}
    for attrs in metas:
        key = (attrs.get('property') or attrs.get('name') or '').strip().lower()
        if key and 'content' in attrs and key not in meta_content:
            meta_content[key] = attrs['content'].strip()[:500]

    pack['site_name'] = meta_content.get('og:site_name', '')
    pack['description'] = meta_content.get('og:description', '') or meta_content.get('description', '')
    title_match = re.search(r'(?is)<title[^>]*>(.*?)</title>', html[:20000])
    pack['title'] = (re.sub(r'\s+', ' ', title_match.group(1)).strip()[:200]
                     if title_match else meta_content.get('og:title', ''))

    # --- colours: declared theme colour first, then most-printed hex codes.
    theme = (meta_content.get('theme-color')
             or meta_content.get('msapplication-tilecolor') or '').strip()
    if re.fullmatch(r'#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?', theme):
        pack['theme_color'] = _normalise_hex(theme)
    css_haystack = ' '.join(STYLE_BLOCK_RE.findall(html[:300000]))
    css_haystack += ' ' + ' '.join(STYLE_ATTR_RE.findall(html[:300000]))
    counts = {}
    for m in HEX_RE.finditer(css_haystack):
        code = _normalise_hex('#' + m.group(1))
        counts[code] = counts.get(code, 0) + 1
    ranked = sorted(counts, key=lambda c: -counts[c])
    pack['colors'] = [c for c in ranked if _is_usable_colour(c)][:8]

    # --- logo candidates, best source first.
    logo_url, logo_source = '', ''
    og_logo = _absolute(base_url, meta_content.get('og:logo', ''))
    if og_logo:
        logo_url, logo_source = og_logo, 'og:logo'
    imgs = []
    for tag in IMG_TAG_RE.findall(html[:300000]):
        attrs = _attrs(tag)
        src = _absolute(base_url, attrs.get('src', ''))
        if not src:
            continue
        lowered = (attrs.get('src', '') + ' ' + attrs.get('class', '') + ' '
                   + attrs.get('id', '')).lower()
        if any(hint in lowered for hint in TRACKING_HINTS):
            continue
        try:
            w = int((attrs.get('width') or '0').strip() or 0)
        except ValueError:
            w = 0
        imgs.append({'url': src, 'alt': (attrs.get('alt') or '').strip()[:120],
                     'logoish': 'logo' in ((attrs.get('alt') or '') + ' ' + lowered),
                     'width': w})
    if not logo_url:
        for img in imgs:
            if img['logoish']:
                logo_url, logo_source = img['url'], 'img alt/src contains "logo"'
                break
    links = [_attrs(t) for t in LINK_TAG_RE.findall(html[:100000])]
    if not logo_url:
        for attrs in links:
            rel = (attrs.get('rel') or '').lower()
            if 'apple-touch-icon' in rel:
                candidate = _absolute(base_url, attrs.get('href', ''))
                if candidate:
                    logo_url, logo_source = candidate, 'apple-touch-icon'
                    break
    if not logo_url:
        for attrs in links:
            rel = (attrs.get('rel') or '').lower()
            if rel in ('icon', 'shortcut icon'):
                candidate = _absolute(base_url, attrs.get('href', ''))
                if candidate:
                    logo_url, logo_source = candidate, 'favicon'
                    break
    pack['logo'], pack['logo_source'] = logo_url, logo_source

    # --- images: social cards first, then page imagery (logos excluded).
    seen, images = set(), []
    for key, source in (('og:image', 'og:image'), ('twitter:image', 'twitter:image')):
        url = _absolute(base_url, meta_content.get(key, ''))
        if url and url not in seen and url != logo_url:
            seen.add(url)
            images.append({'url': url, 'alt': '', 'source': source})
    for img in imgs:
        if len(images) >= max_images:
            break
        if img['url'] in seen or img['url'] == logo_url or img['logoish']:
            continue
        if img['width'] and img['width'] < 100:
            continue
        seen.add(img['url'])
        images.append({'url': img['url'], 'alt': img['alt'], 'source': 'page image'})
    pack['images'] = images

    # --- fonts: hosted font CSS first, then declared families.
    fonts = []
    for attrs in links:
        href = attrs.get('href', '')
        if 'fonts.googleapis.com/css' in href or 'fonts.gstatic.com' in href:
            for family in re.findall(r'family=([^&:;]+)', href):
                name = family.replace('+', ' ').strip()[:60]
                if name and name not in fonts:
                    fonts.append(name)
        if len(fonts) >= 6:
            break
    if len(fonts) < 6:
        for name in _font_names(css_haystack):
            if name not in fonts:
                fonts.append(name)
            if len(fonts) >= 6:
                break
    pack['fonts'] = fonts

    # Keep the favicon distinct from a full logo; it is the explicit fallback
    # when a larger logo asset is not available.
    for attrs in links:
        rel = (attrs.get('rel') or '').lower().split()
        if 'icon' in rel or ('shortcut' in rel and 'icon' in rel):
            candidate = _absolute(base_url, attrs.get('href', ''))
            if candidate:
                pack['favicon'] = candidate
                break
    if not pack['favicon']:
        pack['favicon'] = _absolute(base_url, '/favicon.ico')

    # Observe declared surface/text colors separately from accent colors.
    css_text = css_haystack + ' ' + ' '.join(
        (attrs.get('style') or '') for attrs in [_attrs(t) for t in IMG_TAG_RE.findall(html[:300000])]
    )
    for prop, key in (('background(?:-color)?', 'background_color'), ('color', 'text_color')):
        match = re.search(r'(?i)(?:^|[;{}])\s*' + prop + r'\s*:\s*(#[0-9a-f]{3}(?:[0-9a-f]{3})?)', css_text)
        if match:
            pack[key] = _normalise_hex(match.group(1))

    # Navigation is only claimed when an actual <nav> element is present.
    nav_blocks = re.findall(r'(?is)<nav\b[^>]*>(.*?)</nav\s*>', html[:300000])
    navigation = []
    for block in nav_blocks:
        for anchor in re.findall(r'(?is)<a\b[^>]*>.*?</a\s*>', block):
            tag_match = re.match(r'(?is)<a\b[^>]*>', anchor)
            attrs = _attrs(tag_match.group(0)) if tag_match else {}
            href = _absolute(base_url, attrs.get('href', ''))
            label = re.sub(r'(?is)<[^>]+>', ' ', anchor)
            label = re.sub(r'\s+', ' ', label).strip()[:80]
            if href and label and not any(item['url'] == href for item in navigation):
                navigation.append({'label': label, 'url': href})
            if len(navigation) >= 20:
                break
        if len(navigation) >= 20:
            break
    pack['navigation'] = navigation

    # Only include contact endpoints explicitly present in href attributes.
    contacts, socials = [], []
    for tag in re.findall(r'(?is)<a\b[^>]*>', html[:300000]):
        attrs = _attrs(tag)
        href = (attrs.get('href') or '').strip()
        low = href.lower()
        if low.startswith(('mailto:', 'tel:')):
            value = href[:200]
            if value not in contacts:
                contacts.append(value)
        absolute = _absolute(base_url, href)
        if absolute and any(domain in urlparse(absolute).netloc.lower() for domain in
                            ('facebook.com', 'instagram.com', 'linkedin.com', 'tiktok.com',
                             'youtube.com', 'x.com', 'twitter.com', 'threads.net')):
            if absolute not in socials:
                socials.append(absolute)
    pack['contact_details'] = contacts[:12]
    pack['social_links'] = socials[:12]
    pack['service_description'] = pack['description'] or pack['title']
    # Empty screenshot paths explicitly mean no screenshot was captured.
    pack['homepage_screenshot'] = ''
    pack['mobile_screenshot'] = ''
    return pack



def _rgb(hex_colour):
    value = _normalise_hex(hex_colour or '')
    if not re.fullmatch(r'#[0-9a-f]{6}', value):
        return None
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def _luminance(rgb):
    def channel(v):
        v = v / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a, b):
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(hex_colour, target, amount):
    rgb = _rgb(hex_colour)
    if not rgb:
        return '#202820'
    other = _rgb(target) or (16, 21, 16)
    vals = [round(v * (1 - amount) + w * amount) for v, w in zip(rgb, other)]
    return '#' + ''.join(f'{v:02x}' for v in vals)


def report_theme(brand):
    """Build a readable report palette from observed brand data; never invent identity."""
    brand = brand if isinstance(brand, dict) else {}
    candidates = [brand.get('theme_color')] + list(brand.get('colors') or [])
    primary = next((c.lower() for c in candidates if _rgb(c)), '')
    if not primary:
        primary = '#d6f269'
    rgb = _rgb(primary)
    white, charcoal = (255, 255, 255), (16, 21, 16)
    # A very light brand colour remains an accent; use a darkened variant for headings.
    if _contrast(rgb, white) < 4.5:
        strong = _mix(primary, '#101510', 0.48)
    else:
        strong = primary
    strong_rgb = _rgb(strong) or charcoal
    on_strong = '#ffffff' if _contrast(strong_rgb, white) >= _contrast(strong_rgb, charcoal) else '#101510'
    secondary = next((c.lower() for c in (brand.get('colors') or [])
                      if _rgb(c) and c.lower() != primary), '')
    return {
        'primary': primary,
        'strong': strong,
        'on_primary': on_strong,
        'secondary': secondary,
        'logo': (brand.get('logo') or '').strip(),
        'logo_source': (brand.get('logo_source') or '').strip(),
        'favicon': (brand.get('favicon') or '').strip(),
        'background_color': (brand.get('background_color') or '').strip(),
        'text_color': (brand.get('text_color') or '').strip(),
        'navigation': (brand.get('navigation') or [])[:20],
        'contact_details': (brand.get('contact_details') or [])[:12],
        'social_links': (brand.get('social_links') or [])[:12],
        'service_description': (brand.get('service_description') or '').strip(),
        'homepage_screenshot': (brand.get('homepage_screenshot') or '').strip(),
        'mobile_screenshot': (brand.get('mobile_screenshot') or '').strip(),
        'site_name': (brand.get('site_name') or '').strip(),
        'title': (brand.get('title') or '').strip(),
        'description': (brand.get('description') or '').strip(),
        'fonts': (brand.get('fonts') or [])[:3],
        'detected': bool(brand.get('logo') or brand.get('colors') or brand.get('theme_color')
                         or brand.get('site_name') or brand.get('title')),
        'background': '#f5f6f0',
        'text': '#202820',
        'muted': '#687064',
        'reachmark': '#d6f269',
        'severity_critical': '#b42318',
        'severity_warning': '#b54708',
        'severity_success': '#247044',
    }
