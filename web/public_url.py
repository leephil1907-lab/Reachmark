"""Canonical public origin for sitemap, Open Graph, mail, and host redirects.

Railway's *.up.railway.app hostname is a deploy target, not the brand URL.
When PUBLIC_BASE_URL is missing or still points at Railway, use the owned
domain. An explicit https:// URL on any other host still wins.
"""
import os
from urllib.parse import urlparse

BRAND_PUBLIC_URL = 'https://reachmarkdigital.xyz'
# Search Console HTML-tag tokens. First token is reachmarkdigital.xyz (2026-10-08).
GOOGLE_SITE_TOKENS = (
    'zVYthfXOcAda_Sxphe3f8dYmVrRZ66cogYgTHWeaq7c',
    'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg',
)


def is_ephemeral_public_url(url):
    try:
        host = (urlparse(url or '').hostname or '').lower()
    except ValueError:
        host = ''
    if not host:
        return True
    return (
        host.endswith('.railway.app')
        or host in ('localhost', '127.0.0.1', '0.0.0.0')
        or host.endswith('.local')
    )


def resolve_public_base_url(configured=''):
    for candidate in (
        os.getenv('PUBLIC_BASE_URL', '').strip().rstrip('/'),
        (configured or '').strip().rstrip('/'),
        BRAND_PUBLIC_URL,
    ):
        if candidate.startswith('https://') and not is_ephemeral_public_url(candidate):
            return candidate
    return BRAND_PUBLIC_URL


def google_site_tokens():
    tokens = []
    extra = os.getenv('GOOGLE_SITE_VERIFICATION', '').strip()
    for token in ((extra,) if extra else ()) + GOOGLE_SITE_TOKENS:
        if token and token not in tokens:
            tokens.append(token)
    return tokens
