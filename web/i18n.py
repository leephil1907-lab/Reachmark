"""Six-locale UI translation: English, Spanish, French, German, Portuguese, Simplified Chinese.

Single source of truth: ``static/locales/<code>.json`` (flat ``section.key`` strings),
read by Python here and fetched by ``static/i18n.js`` in the browser. English is the
fallback everywhere: a missing key renders the English string, never a raw key.

Not translated, by standing rule: the PWA manifest (application title/description),
icons, ``templates/about.html`` (byte-identical), page <title> tags and meta/OG
descriptions. Owner notification e-mails stay English (the owner must be able to
read them); client-facing e-mails use the recipient's stored locale.
"""
import json
import os

LOCALES = ('en', 'es', 'fr', 'de', 'pt', 'zh')
LOCALE_NAMES = {'en': 'English', 'es': 'Español', 'fr': 'Français',
                'de': 'Deutsch', 'pt': 'Português', 'zh': '简体中文'}
COOKIE = 'rm_locale'

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'static', 'locales')
_cache = {}


def strings(locale):
    if locale not in LOCALES:
        locale = 'en'
    if locale not in _cache:
        with open(os.path.join(DIR, locale + '.json'), encoding='utf-8') as handle:
            _cache[locale] = json.load(handle)
    return _cache[locale]


def t(key, locale='en', **vars):
    s = strings(locale).get(key, strings('en').get(key, key))
    for name, value in vars.items():
        s = s.replace('{' + name + '}', str(value))
    return s


def resolve_locale(cookie_val, accept_language):
    if cookie_val in LOCALES:
        return cookie_val
    for part in (accept_language or '').split(','):
        tag = part.split(';')[0].strip().lower().split('-')[0]
        if tag in LOCALES:
            return tag
    return 'en'


def locale_now(default='en'):
    """Visitor locale inside a request; plain default outside one (tests, jobs)."""
    try:
        from flask import has_app_context, g
        return g.get('locale', default) if has_app_context() else default
    except Exception:
        return default
