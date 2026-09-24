"""Builder memory: match a gathered lead to its trade brief, then compose the
concept from the brief's *structure* with the business's *own facts*.

Contract (agreed with the owner):
- Business name, contact facts and observed brand are untouchable — every
  placeholder name from the brief (e.g. the example businesses) is replaced
  with the lead's own business name before anything is rendered.
- Briefs tagged ``service-blueprint`` are backend builds, not websites: they
  are stored and matchable for future use but NEVER alter a website concept.
- Trades with no matching brief keep the current family treatment.
- Brief colours are stored as palette hints only; the business's observed
  brand always wins at render time (see web/concept.build_theme).
- A brief's "use mock data" style escape hatches are refused: figures come
  only from the business's real system.
"""
import json
import os
import re

_STORE = os.path.join(os.path.dirname(__file__), 'prompts_v1.json')
_CACHE = None


def load_memory(path=None):
    """Return the versioned memory store {'memory_version', 'prompts'}."""
    global _CACHE
    if path is None and _CACHE is not None:
        return _CACHE
    with open(path or _STORE, encoding='utf-8') as fh:
        data = json.load(fh)
    if path is None:
        _CACHE = data
    return data


def list_prompts(kind=None):
    """All stored briefs, optionally filtered by kind ('website' / 'service-blueprint')."""
    prompts = load_memory()['prompts']
    if kind:
        prompts = [p for p in prompts if p.get('kind') == kind]
    return prompts


def match_prompt(category, name=''):
    """First brief whose keywords appear in the lead's category/name.

    File order is precedence: specific multi-word trades sort before generic
    ones. Returns the brief dict or None. Service blueprints match too — the
    composer is what refuses to build websites from them.
    """
    haystack = f'{category or ""} {name or ""}'.lower()
    for entry in load_memory()['prompts']:
        if any(key in haystack for key in entry.get('match', [])):
            return entry
    return None


def _sub_placeholders(text, entry, business_name):
    """Swap every example-business placeholder for the real business name."""
    out = text or ''
    for holder in entry.get('placeholders', []):
        if holder:
            out = re.sub(re.escape(holder), business_name, out, flags=re.IGNORECASE)
    return out


def _section_title(feature):
    """Short block label from a feature line ('Gallery with …' -> 'Gallery')."""
    head = (feature or '').split(' with ')[0].split(' (')[0].strip()
    head = (head[:1].upper() + head[1:]) if head else (feature or '').strip()
    return head[:60]


def apply_prompt(entry, lead):
    """Compose promise + sections for a website brief. Business facts win.

    Raises ValueError for non-website briefs — the caller falls back to the
    family template instead.
    """
    if (entry or {}).get('kind') != 'website':
        raise ValueError('service blueprints never produce website concepts')
    name = (lead or {}).get('name') or 'this business'
    purpose = _sub_placeholders(entry.get('purpose', ''), entry, name).strip()
    promise = (purpose[:1].upper() + purpose[1:]).rstrip('.') + '.'
    sections = []
    for feature in entry.get('features', []):
        body = _sub_placeholders(feature, entry, name).strip().rstrip('.')
        body = (body[:1].upper() + body[1:]) if body else body
        sensible = 'figures come only from your real system' if entry.get('mock_data_requested') \
            else 'built only from material you supply and confirm'
        sections.append({'title': _section_title(feature),
                         'body': f'{body[:220]} — {sensible}.'[:400]})
    return {'promise': promise[:300], 'sections': sections,
            'theme_family': entry.get('theme_family') or 'generic',
            'label': entry.get('label') or entry.get('trade') or 'local business',
            'memory': {'prompt_id': entry.get('id'), 'trade': entry.get('trade'),
                       'kind': entry.get('kind'),
                       'memory_version': load_memory().get('memory_version'),
                       'palette_hint': entry.get('colors', ''),
                       'vibes': entry.get('vibes', ''),
                       'mock_data_refused': bool(entry.get('mock_data_requested')),
                       'applied': True}}
