"""Canonical public origin for sitemap, Open Graph, mail, and host redirects.

Railway's *.up.railway.app hostname is a deploy target, not the brand URL.
When PUBLIC_BASE_URL is missing or still points at Railway, use the owned
domain. An explicit https:// URL on any other host still wins.
"""
import os
import re
from urllib.parse import urlparse

BRAND_PUBLIC_URL = 'https://reachmarkdigital.xyz'
BRAND_SUPPORT_EMAIL = 'support@reachmarkdigital.xyz'
SEO_HOME_TITLE = 'Reachmark Digital | Website Growth & Web Design'
SEO_HOME_DESCRIPTION = (
    'Reachmark Digital helps businesses uncover website gaps, improve their online presence, and turn clear opportunities into stronger websites. Explore our tools, previews, and services.'
)
SEO_HOME_KEYWORDS = 'Reachmark, Reachmark Digital, website diagnosis, Digital Opportunity Report'
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


def support_email():
    return os.getenv('SUPPORT_EMAIL', BRAND_SUPPORT_EMAIL).strip() or BRAND_SUPPORT_EMAIL


def organization_schema(base, description=''):
    root = (base or BRAND_PUBLIC_URL).rstrip('/')
    email = support_email()
    org = {
        '@context': 'https://schema.org',
        '@type': 'ProfessionalService',
        'name': 'Reachmark Digital',
        'url': root,
        'email': email,
        'logo': root + '/static/icon.svg',
        'image': root + '/static/social-card.png',
        'foundingDate': '2026',
        'areaServed': 'Worldwide',
        'slogan': 'Find potential. Make your mark.',
        'alternateName': ['Reachmark', 'reachmarkdigital.xyz'],
        'description': description or SEO_HOME_DESCRIPTION,
        'contactPoint': [{
            '@type': 'ContactPoint',
            'contactType': 'customer support',
            'email': email,
            'availableLanguage': ['English'],
        }],
    }
    wa = whatsapp_url()
    if wa:
        org['contactPoint'][0]['url'] = wa
        org['sameAs'] = [wa]
    return org


def website_schema(base, description=''):
    """WebSite node for the owned domain. No SearchAction — /showcase does not search."""
    root = (base or BRAND_PUBLIC_URL).rstrip('/')
    return {
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': 'Reachmark Digital',
        'alternateName': ['Reachmark', 'reachmarkdigital.xyz'],
        'url': root + '/',
        'inLanguage': 'en',
        'description': description or SEO_HOME_DESCRIPTION,
        'publisher': {
            '@type': 'ProfessionalService',
            'name': 'Reachmark Digital',
            'url': root,
        },
    }


def faq_schema():
    """Honest FAQs only — published contact, plans, and process. No ratings."""
    email = support_email()
    wa = whatsapp_url()
    contact = f'Email {email}'
    if wa:
        contact += f', the WhatsApp icon ({wa})'
    contact += ', or the enquiry form at https://reachmarkdigital.xyz/enquire. No phone number or street address is published.'
    pairs = [
        (
            'What is Reachmark?',
            'Reachmark is a website diagnosis studio at https://reachmarkdigital.xyz. '
            'We read a public site, write a Digital Opportunity Report of measured observations, '
            'then build or repair the pages that lose enquiries. You approve every send.',
        ),
        (
            'What does Reachmark cost?',
            'Workspace plans: Free $0, Starter $19 per month, Pro $59 per month. '
            'Studio work: Audit $497 one-time, Build $3,500, Care $1,800 per year, '
            'Outreach $6,000 per campaign. Nothing is charged until you approve scope.',
        ),
        (
            'How do I contact Reachmark?',
            contact,
        ),
        (
            'What is a Digital Opportunity Report?',
            'A dated write-up of what a public page fetch actually showed — status, HTTPS, '
            'viewport, contact paths, and similar signals. The public leak check returns up to '
            'three measured observations and is not a revenue forecast. The full report stays behind an account.',
        ),
        (
            'Do you send email without approval?',
            'No. Every outreach message needs the owner’s approval, an unsubscribe link, '
            'and a suppression check. Autopilot never sends WhatsApp.',
        ),
    ]
    return {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'mainEntity': [
            {
                '@type': 'Question',
                'name': question,
                'acceptedAnswer': {'@type': 'Answer', 'text': answer},
            }
            for question, answer in pairs
        ],
    }


def google_maps_browser_key():
    return os.getenv('GOOGLE_MAPS_API_KEY', '').strip()


def whatsapp_url():
    raw = os.getenv('WHATSAPP_URL', '').strip()
    if raw.lower() in ('0', 'off', 'none', 'false'):
        return ''
    if not raw:
        raw = 'https://wa.me/14473227700'
    if raw.startswith(('https://wa.me/', 'https://api.whatsapp.com/send')):
        return raw.split()[0][:200]
    digits = re.sub(r'\D', '', raw)
    if 8 <= len(digits) <= 15:
        return 'https://wa.me/' + digits
    return ''


def google_site_tokens():
    tokens = []
    extra = os.getenv('GOOGLE_SITE_VERIFICATION', '').strip()
    for token in ((extra,) if extra else ()) + GOOGLE_SITE_TOKENS:
        if token and token not in tokens:
            tokens.append(token)
    return tokens
