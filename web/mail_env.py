"""SMTP environment normalisation and the studio's default sender profile.

Hosting dashboards (Railway, Render, Fly) and mail providers use different variable
names for the same thing. This module maps the common aliases onto the canonical
``SMTP_*`` names the rest of the app reads, once at start-up, so a Gmail / Google
Workspace or Resend setup works without renaming anything.

Canonical names:  SMTP_HOST · SMTP_PORT · SMTP_USER · SMTP_PASSWORD · SMTP_FROM · SMTP_SECURITY
"""
import os
from email.utils import formataddr, parseaddr

ALIASES = {
    'SMTP_HOST': ('SMTP_SERVER', 'MAIL_HOST', 'MAIL_SERVER', 'EMAIL_HOST'),
    'SMTP_PORT': ('MAIL_PORT', 'EMAIL_PORT'),
    'SMTP_USER': ('SMTP_USERNAME', 'SMTP_LOGIN', 'MAIL_USERNAME', 'MAIL_USER', 'EMAIL_HOST_USER',
                  'EMAIL_USER', 'GMAIL_USER', 'GMAIL_ADDRESS'),
    'SMTP_PASSWORD': ('SMTP_PASS', 'SMTP_APP_PASSWORD', 'MAIL_PASSWORD', 'EMAIL_HOST_PASSWORD',
                      'EMAIL_PASSWORD', 'GMAIL_APP_PASSWORD', 'GMAIL_PASSWORD'),
    'SMTP_FROM': ('MAIL_FROM', 'EMAIL_FROM', 'DEFAULT_FROM_EMAIL', 'SMTP_SENDER', 'MAIL_DEFAULT_SENDER'),
}

# The studio's own published details. Settings saved in the workspace override these;
# the matching env vars (SENDER_NAME, SENDER_AGENCY, REPLY_EMAIL, SENDER_POSTAL_ADDRESS)
# override them without a code change.
PROFILE_DEFAULTS = {
    'sender_name': ('SENDER_NAME', 'Ernest Micheal'),
    'agency': ('SENDER_AGENCY', 'Reachmark'),
    'reply_email': ('REPLY_EMAIL', 'support@reachmarkdigital.xyz'),
    'postal_address': ('SENDER_POSTAL_ADDRESS', 'Lagos, Nigeria'),
}
PROFILE_KEYS = tuple(PROFILE_DEFAULTS)


def _get(name):
    return (os.environ.get(name) or '').strip()


def normalize_smtp_env(environ=None):
    """Fill canonical SMTP_* names from aliases. Never overwrites a value already set."""
    env = os.environ if environ is None else environ
    for canonical, aliases in ALIASES.items():
        if (env.get(canonical) or '').strip():
            continue
        for alias in aliases:
            value = (env.get(alias) or '').strip()
            if value:
                env[canonical] = value
                break
    host = (env.get('SMTP_HOST') or '').strip().lower()
    if host in ('gmail', 'google', 'gmail.com'):
        env['SMTP_HOST'] = host = 'smtp.gmail.com'
    # The sender address defaults to the login for Gmail / Workspace, which only
    # accepts its own address (or a verified alias) in From anyway.
    if not (env.get('SMTP_FROM') or '').strip() and '@' in (env.get('SMTP_USER') or ''):
        env['SMTP_FROM'] = env['SMTP_USER'].strip()
    if host and not (env.get('SMTP_SECURITY') or '').strip():
        port = (env.get('SMTP_PORT') or '').strip()
        ssl_flag = (env.get('SMTP_SSL') or '').strip().lower() in ('1', 'true', 'yes')
        if port == '465' or ssl_flag:
            env['SMTP_SECURITY'] = 'ssl'
    if (env.get('SMTP_SECURITY') or '').strip().lower() in ('tls', 'start_tls', 'starttls'):
        env['SMTP_SECURITY'] = 'starttls'
    if (env.get('SMTP_SECURITY') or '').strip().lower() in ('ssl', 'smtps', 'implicit'):
        env['SMTP_SECURITY'] = 'ssl'
    if env.get('SMTP_SECURITY') == 'ssl' and not (env.get('SMTP_PORT') or '').strip():
        env['SMTP_PORT'] = '465'
    return env


def profile_defaults():
    """The default sender profile, env-overridable."""
    return {key: (_get(var) or fallback) for key, (var, fallback) in PROFILE_DEFAULTS.items()}


def from_header(settings=None):
    """``"Ernest Micheal | Reachmark" <studio@gmail.com>`` built from SMTP_FROM.

    A display name already present in SMTP_FROM wins; otherwise the sender profile
    supplies one, so recipients see a person and a studio, not a bare address.
    """
    raw = _get('SMTP_FROM')
    name, address = parseaddr(raw)
    if not address:
        return raw
    if name:
        return formataddr((name, address))
    settings = settings or {}
    sender = (settings.get('sender_name') or '').strip()
    agency = (settings.get('agency') or '').strip()
    display = sender if not agency or agency.lower() == sender.lower() else (f'{sender} | {agency}' if sender else agency)
    return formataddr((display, address)) if display else address


def from_domain():
    address = parseaddr(_get('SMTP_FROM'))[1] or _get('SMTP_FROM')
    return address.split('@')[-1] if '@' in address else 'localhost'
