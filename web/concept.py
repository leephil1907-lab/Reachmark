"""Concept-site copy engine: business category -> archetype -> localized one-pager copy.

Six craft archetypes keep every preview's write-up specific to the trade instead
of generic filler. Copy lives in the locale files (cc.<arch>_<field>) so all six
locales stay covered; offers are stored as "Title — description" and split here.
"""
import re

from .i18n import t as _t

ARCHETYPES = {
    'food': ('bakery', 'restaurant', 'caf', 'fast food', 'bar', 'food', 'pizza',
             'grill', 'kitchen', 'bistro', 'eat', 'diner', 'sushi'),
    'beauty': ('hair', 'beauty', 'tattoo', 'pet groom', 'barber', 'salon', 'spa',
               'nail', 'grooming'),
    'health': ('dentist', 'physio', 'pharmacy', 'clinic', 'veterinary', 'veterinarian',
               'vet', 'gym', 'fitness', 'doctor', 'dental', 'hospital', 'opt', 'wellness'),
    'home': ('plumb', 'electric', 'hvac', 'roof', 'carpent', 'painter', 'car wash',
             'laundry', 'auto repair', 'repair', 'clean', 'garden', 'locksmith',
             'mason', 'renovat'),
    'stay': ('hotel', 'guest house', 'florist', 'clothes', 'supermarket',
             'convenience', 'travel', 'tour', 'shop', 'store', 'market', 'boutique',
             'flor'),
}
FIELDS = ('tag', 'about', 'o1', 'o2', 'o3')


def detect_archetype(category):
    """Map a free-text business category to one of the six archetypes."""
    text = (category or '').strip().lower()
    for arch, keywords in ARCHETYPES.items():
        if any(k in text for k in keywords):
            return arch
    return 'pro'


def concept_copy(archetype, locale='en'):
    """Return {'tag', 'about', 'offers': [{'t','d'} x3]} for an archetype+locale."""
    if archetype not in ARCHETYPES and archetype != 'pro':
        archetype = 'pro'
    strings = {f: _t(f'cc.{archetype}_{f}', locale) for f in FIELDS}
    offers = []
    for f in ('o1', 'o2', 'o3'):
        bits = re.split(r'\s*—+\s*', strings[f], maxsplit=1)
        title, desc = (bits + [''])[:2]
        offers.append({'t': title.strip(), 'd': desc.strip()})
    return {'tag': strings['tag'], 'about': strings['about'], 'offers': offers,
            'archetype': archetype}


# Trade palettes: when the business has no readable page, the preview still
# dresses in the craft's own colours — never the studio's house style.
ARCH_THEMES = {
    'food': {'bg': '#faf4e9', 'surface': '#f2e8d3', 'card': '#fffdf6',
             'ink': '#2b1a10', 'muted': '#6f5b47', 'faint': '#a5906f',
             'accent': '#b3541e', 'soft': '#f3e4cd', 'vibe': 'serif',
             'tools': ['WhatsApp', 'Instagram', 'Google Maps']},
    'beauty': {'bg': '#1d1118', 'surface': '#291623', 'card': '#2e1a29',
               'ink': '#faeef4', 'muted': '#d3b3c4', 'faint': '#8f7386',
               'accent': '#f0a3c4', 'soft': 'rgba(0,0,0,.30)', 'vibe': 'serif',
               'tools': ['WhatsApp', 'Instagram', 'Calendly']},
    'health': {'bg': '#0a1a1c', 'surface': '#0f2427', 'card': '#122b2e',
               'ink': '#eaf7f5', 'muted': '#a9ccc8', 'faint': '#6d8f8c',
               'accent': '#63d6c3', 'soft': 'rgba(0,0,0,.30)', 'vibe': 'sans',
               'tools': ['WhatsApp', 'Google Calendar', 'Google Maps']},
    'home': {'bg': '#181310', 'surface': '#231b15', 'card': '#292017',
             'ink': '#f6efe3', 'muted': '#cbb894', 'faint': '#8a7a5c',
             'accent': '#e8b04b', 'soft': 'rgba(0,0,0,.30)', 'vibe': 'sans',
             'tools': ['WhatsApp', 'Google Maps', 'Stripe']},
    'stay': {'bg': '#140e20', 'surface': '#1d142e', 'card': '#241a36',
             'ink': '#f1eafb', 'muted': '#c2b1dd', 'faint': '#84779f',
             'accent': '#c6a1f2', 'soft': 'rgba(0,0,0,.30)', 'vibe': 'serif',
             'tools': ['WhatsApp', 'Google Maps', 'Instagram']},
    'pro': {'bg': '#0c1425', 'surface': '#111b31', 'card': '#152239',
            'ink': '#eaf1fb', 'muted': '#a9bcd4', 'faint': '#6e8199',
            'accent': '#82b4f7', 'soft': 'rgba(0,0,0,.30)', 'vibe': 'sans',
            'tools': ['WhatsApp', 'Calendly', 'Stripe']},
}
SHOWCASE = {
    'food': {'hero': '/static/concept/food/hero-oven.jpg',
             'offers': ['/static/concept/food/offer-sourdough.jpg',
                        '/static/concept/food/offer-croissant.jpg',
                        '/static/concept/food/offer-cakes.jpg'],
             'craft': '/static/concept/food/craft-baker.jpg',
             'strip': '/static/concept/food/case-pastries.jpg'},
    'beauty': {'hero': '/static/concept/beauty/hero.jpg',
               'offers': ['/static/concept/beauty/offer-1.jpg',
                          '/static/concept/beauty/offer-2.jpg',
                          '/static/concept/beauty/offer-3.jpg'],
               'craft': '/static/concept/beauty/craft.jpg',
               'strip': '/static/concept/beauty/strip.jpg'},
    'health': {'hero': '/static/concept/health/hero.jpg',
               'offers': ['/static/concept/health/offer-1.jpg',
                          '/static/concept/health/offer-2.jpg',
                          '/static/concept/health/offer-3.jpg'],
               'craft': '/static/concept/health/craft.jpg',
               'strip': '/static/concept/health/strip.jpg'},
    'home': {'hero': '/static/concept/home/hero.jpg',
             'offers': ['/static/concept/home/offer-1.jpg',
                        '/static/concept/home/offer-2.jpg',
                        '/static/concept/home/offer-3.jpg'],
             'craft': '/static/concept/home/craft.jpg',
             'strip': '/static/concept/home/strip.jpg'},
    # Stay teaser: hero + first offer. The template guards missing slots,
    # so partial showcases still render complete pages.
    'stay': {'hero': '/static/concept/stay/hero.jpg',
             'offers': ['/static/concept/stay/offer-1.jpg']},
}
SERIF_HINTS = ('serif', 'georgia', 'times', 'garamond', 'playfair', 'merriweather',
               'lora', 'cormorant', 'bodoni', 'didot', 'fraunces', 'dm serif')
ROUND_HINTS = ('round', 'quicksand', 'nunito', 'comfortaa', 'baloo', 'fredoka',
               'poppins', 'dm sans', 'manrope')


def _luminance(hexcode):
    """Relative luminance 0..1 for a #rrggbb string (0 on garbage)."""
    try:
        rgb = [int(hexcode[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    except (ValueError, TypeError, IndexError):
        return 0
    conv = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * conv[0] + 0.7152 * conv[1] + 0.0722 * conv[2]


def build_theme(archetype, brand=None):
    """Compose the preview theme: observed brand first, trade palette behind.

    Returns {'colors': {...tokens incl. accent/accent_ink/line...},
    'logo', 'logo_source', 'images': [{'url','alt'}], 'fonts': [...],
    'has_brand': bool, 'archetype': str, 'widget_key': 'pc.w_<arch>_t'}.
    Only strict #rrggbb colours and http(s)/data URLs pass through.
    """
    from .brand import _is_usable_colour as _usable
    arch = archetype if archetype in ARCH_THEMES else 'pro'
    base = dict(ARCH_THEMES[arch])
    brand = brand or {}
    accent, accent_source = base['accent'], 'trade palette'
    candidates = []
    if brand.get('theme_color'):
        candidates.append(brand['theme_color'])
    candidates.extend(brand.get('colors') or [])
    for cand in candidates:
        code = (cand or '').strip().lower()
        if re.fullmatch(r'#[0-9a-f]{6}', code) and _usable(code):
            accent, accent_source = code, 'observed on page'
            break
    base['accent'] = accent
    base['accent_ink'] = '#201405' if _luminance(accent) > 0.45 else '#fff8ef'
    r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
    base['line'] = f'rgba({r},{g},{b},.22)'
    base['accent_source'] = accent_source
    fonts = [str(f)[:60] for f in (brand.get('fonts') or []) if str(f).strip()][:3]
    joined = ' '.join(fonts).lower()
    if any(h in joined for h in SERIF_HINTS):
        base['vibe'] = 'serif'
    elif any(h in joined for h in ROUND_HINTS):
        base['vibe'] = 'round'
    logo = str(brand.get('logo') or '')
    if not logo.lower().startswith(('https://', 'http://', 'data:image/')):
        logo = ''
    images = []
    for img in (brand.get('images') or [])[:6]:
        url = str((img or {}).get('url') or '')
        if url.lower().startswith(('https://', 'http://', 'data:image/')):
            images.append({'url': url[:800], 'alt': str(img.get('alt') or '')[:120]})
    return {'colors': base, 'showcase': dict(SHOWCASE.get(arch, {})),
            'logo': logo[:800],
            'logo_source': str(brand.get('logo_source') or '')[:60],
            'images': images, 'fonts': fonts,
            'has_brand': bool(logo or images or accent_source == 'observed on page'
                              or fonts),
            'archetype': arch, 'widget_key': f'pc.w_{arch}_t'}
