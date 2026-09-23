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
