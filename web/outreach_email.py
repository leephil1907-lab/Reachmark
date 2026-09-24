"""The branded proposal e-mail that carries the website link.

The website a business opens (``/r/<token>``) is a clean, finished one-page site for
that business — nothing on it asks a question or pitches. The proposal and the single
question live *here*, in the e-mail that carries the link:

* a **Reachmark-branded** HTML message (the logo, the studio line, the lime CTA),
* the **write-up** — what we noticed, what the concept is, what it would give them,
* the **website link** (one clear button to open the finished concept),
* the **one question** with three answer buttons, each a plain link to
  ``/r/<token>/answer/<choice>`` so a tap is all it takes.

When the business taps an answer, ``notify_owner_of_response`` e-mails the owner
straight away, so the reply arrives in the owner's inbox like any other e-mail.

Nothing here invents a fact: the write-up is built from the business's own saved
fields and the measured audit, exactly like the website itself.
"""
import html
import os
import re

from web.i18n import t as _t, locale_now

# The three answers, in the order they are offered. Keys match review_links.RESPONSES.
CHOICES = ('want', 'later', 'have')
EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')


def _base(settings):
    """Public base URL for links and the logo, from env first, then settings."""
    base = (os.getenv('PUBLIC_BASE_URL') or (settings or {}).get('public_base_url') or '').strip()
    return base.rstrip('/')


def site_url(base, token):
    return f'{base}/r/{token}' if base else f'/r/{token}'


def answer_url(base, token, choice):
    return f'{base}/r/{token}/answer/{choice}' if base else f'/r/{token}/answer/{choice}'


def _observations(lead, audit):
    """The measured, checkable things we can honestly say about the business online.

    Only ever quotes what an audit actually recorded (the gaps list) or a plain fact
    about the listing. Never a verdict, never invented.
    """
    lines = []
    gaps = ((audit or {}).get('gaps') or {}).get('gaps') or []
    for gap in gaps[:4]:
        reason = (gap.get('reason') or '').strip()
        if reason:
            lines.append(reason)
    if not lines:
        status = ((audit or {}).get('status') or lead.get('audit_status') or '').upper()
        if not (lead.get('website') or '').strip():
            lines.append('Your public listing does not show a website, so people searching '
                         'for you land on directories instead of your own page.')
        elif status in ('SOCIAL_ONLY',):
            lines.append('The only link on your listing is a social profile, which is hard '
                         'for a new customer to read.')
        elif status in ('DNS_UNRESOLVED', 'UNREACHABLE'):
            lines.append('The website on your listing did not load when we checked it.')
        elif status in ('HTTP_ERROR', 'BLOCKED', 'PARKED', 'FAILED'):
            lines.append('The website on your listing returned an error when we checked it.')
    return lines


def _write_up(lead, site, audit, settings, locale):
    """The proposal paragraphs, built only from saved fields and measured facts."""
    name = (lead.get('name') or 'your business').strip()
    studio = ((settings or {}).get('agency') or 'Reachmark').strip()
    sender = ((settings or {}).get('sender_name') or studio).strip()
    category = (lead.get('category') or _t('rv.cat', locale)).lower()
    city = (lead.get('city') or '').strip()
    where = f' in {city}' if city else ''
    tag = ((site or {}).get('copy') or {}).get('tag') or ''
    about = ((site or {}).get('copy') or {}).get('about') or ''

    greeting = _t('oe.greet', locale, n=name)
    intro = _t('oe.intro', locale, s=sender, a=studio, c=category, w=where)
    observations = _observations(lead, audit)
    concept = _t('oe.concept', locale, n=name)
    if tag:
        concept += ' ' + _t('oe.concept_tag', locale, t=tag)
    if about:
        concept += ' ' + about
    give = _t('oe.give', locale)
    return {'greeting': greeting, 'intro': intro, 'observations': observations,
            'concept': concept, 'give': give, 'name': name, 'studio': studio,
            'sender': sender}


def _text_body(lead, link, site, settings, audit, locale):
    """Plain-text alternative — same facts, same links, readable anywhere."""
    base = _base(settings)
    token = link.get('token', '')
    w = _write_up(lead, site, audit, settings, locale)
    lines = [w['greeting'], '', w['intro']]
    if w['observations']:
        lines += ['', _t('oe.noticed', locale)]
        lines += [f'  \u2022 {line}' for line in w['observations']]
    lines += ['', w['concept'], '', w['give']]
    lines += ['', _t('oe.see', locale) + ': ' + site_url(base, token)]
    lines += ['', _t('oe.question', locale, n=w['name'])]
    for choice in CHOICES:
        lines.append(f'  \u2022 {_t("rv." + choice, locale)}: ' + answer_url(base, token, choice))
    lines += ['', _t('oe.optout', locale)]
    lines += ['', w['sender'], w['studio']]
    reply = (settings or {}).get('reply_email')
    if reply:
        lines.append(reply)
    return '\n'.join(lines)


def _button(url, label, primary=False):
    bg = '#0f1a0a' if primary else '#ffffff'
    fg = '#d5f268' if primary else '#0f1a0a'
    border = '#0f1a0a' if primary else '#d2d8c7'
    return (f'<a href="{html.escape(url, quote=True)}" style="display:inline-block;'
            f'background:{bg};color:{fg};border:1px solid {border};padding:13px 20px;'
            f'border-radius:10px;text-decoration:none;font-weight:700;font-size:14px;'
            f'font-family:Manrope,Arial,sans-serif;margin:0 8px 10px 0">{html.escape(label)}</a>')


def _html_body(lead, link, site, settings, audit, locale):
    """The branded HTML e-mail: Reachmark logo, write-up, link, and the one question."""
    base = _base(settings)
    token = link.get('token', '')
    w = _write_up(lead, site, audit, settings, locale)
    logo = f'{base}/static/logo-primary.png' if base else '/static/logo-primary.png'
    host = base.replace('https://', '').replace('http://', '') or 'reachmark'
    reply = (settings or {}).get('reply_email') or ''

    obs_html = ''
    if w['observations']:
        items = ''.join(
            f'<li style="margin:0 0 6px">{html.escape(line)}</li>' for line in w['observations'])
        obs_html = (f'<p style="margin:16px 0 6px;font-weight:700;color:#0f1a0a">'
                    f'{html.escape(_t("oe.noticed", locale))}</p>'
                    f'<ul style="margin:0 0 4px;padding-left:20px;color:#33402a">{items}</ul>')

    answers = ''.join(_button(answer_url(base, token, choice), _t('rv.' + choice, locale),
                              primary=(choice == 'want')) for choice in CHOICES)

    # Open-tracking pixel: a 1x1 transparent image served by /t/<token>/o.gif. It
    # records a single 'open' event so the owner can measure real open rates. It is
    # invisible and degrades to nothing if images are blocked.
    try:
        from web.pipeline import pixel_html
        pixel = pixel_html(base, token)
    except Exception:
        pixel = ''

    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#eef6d1;font-family:Manrope,Arial,sans-serif;color:#1a2315">
<div style="max-width:600px;margin:0 auto;padding:28px">
<div style="background:#ffffff;border:1px solid #e2e7d6;border-radius:16px;padding:30px">
<div style="margin-bottom:20px"><img src="{logo}" alt="Reachmark" style="height:36px" onerror="this.style.display='none'"><div style="font-weight:800;letter-spacing:-0.5px;font-size:18px;color:#0f1a0a">Reachmark</div><div style="font-size:11px;letter-spacing:1.2px;color:#8c9c77">FIND POTENTIAL &middot; MAKE YOUR MARK</div></div>
<p style="margin:0 0 12px;font-size:15px;color:#0f1a0a;font-weight:700">{html.escape(w['greeting'])}</p>
<div style="line-height:1.7;color:#33402a;font-size:14px">
<p style="margin:0 0 12px">{html.escape(w['intro'])}</p>
{obs_html}
<p style="margin:16px 0 12px">{html.escape(w['concept'])}</p>
<p style="margin:0 0 6px;font-weight:700;color:#0f1a0a">{html.escape(w['give'])}</p>
</div>
<p style="margin:20px 0 10px">{_button(site_url(base, token), _t('oe.see', locale), primary=True)}</p>
<div style="margin-top:22px;padding-top:18px;border-top:1px solid #eef1e4">
<p style="margin:0 0 12px;font-size:15px;font-weight:800;color:#0f1a0a">{html.escape(_t('oe.question', locale, n=w['name']))}</p>
<p style="margin:0 0 14px;color:#33402a;font-size:13.5px">{html.escape(_t('oe.pick', locale))}</p>
{answers}
</div>
<div style="margin-top:22px;padding-top:16px;border-top:1px solid #eef1e4;font-size:12px;color:#8a9976;line-height:1.6">
{html.escape(_t('oe.optout', locale))}<br>{html.escape(w['sender'])} &middot; {html.escape(w['studio'])}{(' &middot; ' + html.escape(reply)) if reply else ''}
</div>
</div>
<div style="text-align:center;margin-top:14px;font-size:11px;color:#8a9976">Reachmark &middot; Global &middot; {html.escape(host)}</div>
</div>{pixel}</body></html>"""


def build_outreach_email(lead, link, site, settings, audit=None, locale=None):
    """Return {'subject', 'text', 'html', 'site_url', 'answer_urls'} for one business.

    Pure function: it needs the already-built website spec and the review link, so it
    never touches the database and never invents a fact.
    """
    locale = locale or locale_now()
    name = (lead.get('name') or 'your business').strip()
    subject = _t('oe.subject', locale, n=name)
    base = _base(settings)
    token = (link or {}).get('token', '')
    return {
        'subject': subject,
        'text': _text_body(lead, link, site, settings, audit, locale),
        'html': _html_body(lead, link, site, settings, audit, locale),
        'site_url': site_url(base, token),
        'answer_urls': {choice: answer_url(base, token, choice) for choice in CHOICES},
    }


def ensure_link(db, now, lead, settings, locale=None):
    """The newest live review link for a lead, or a freshly built one.

    The e-mail always points at ``/r/<token>`` — the finished website — so a link must
    exist before the message is composed. Reuses the newest ready/answered link so a
    business never gets two different URLs.
    """
    from web.review_links import get_link, create_link
    with db() as c:
        row = c.execute("SELECT token FROM review_links WHERE lead_id=? AND status IN ('ready','answered') "
                        "ORDER BY created DESC LIMIT 1", (lead['id'],)).fetchone()
    if row:
        return get_link(db, token=row['token'])
    try:
        from agents.agent_builder import compose_concept, compose_share_message
        concept = compose_concept(lead, settings)
    except Exception:
        concept = {'theme': 'charcoal', 'headline': lead.get('name', ''), 'intro': '', 'sections': []}
    link = create_link(db, now, lead, concept, '')
    base = _base(settings)
    url = site_url(base, link['token'])
    try:
        share = compose_share_message(lead, concept, (settings.get('agency') or 'Reachmark'), base, url)
    except Exception:
        share = url
    with db() as c:
        c.execute('UPDATE review_links SET share_message=?,updated=? WHERE id=?', (share, now(), link['id']))
    link['share_message'] = share
    return link


def build_outreach_email_for(db, now, lead, settings, locale=None):
    """Convenience wrapper: find/create the link, build the site, build the e-mail."""
    from web.review_links import _build_site_for
    link = ensure_link(db, now, lead, settings, locale)
    audit = None
    try:
        from agents.agent_auditor import latest_audit, ensure_tables as ensure_audit_tables
        ensure_audit_tables(db)
        audit = latest_audit(db, lead.get('id'))
    except Exception:
        audit = None
    site = _build_site_for(db, lead, link)
    email = build_outreach_email(lead, link, site, settings, audit, locale)
    email['link'] = link
    email['site'] = site
    return email


def notify_owner_of_response(db, now, log, link, response, settings, lead=None):
    """E-mail the owner the moment a business answers, so the reply lands in their inbox.

    Uses the same branded sender as the rest of Reachmark. Returns (sent, outbox_id).
    """
    try:
        from web.accounts import send_branded, support_email
    except Exception:
        return False, ''
    if lead is None:
        try:
            with db() as c:
                row = c.execute('SELECT * FROM leads WHERE id=?', (link.get('lead_id'),)).fetchone()
            lead = dict(row) if row else {}
        except Exception:
            lead = {}
    owner = ((settings or {}).get('reply_email') or '').strip() or support_email()
    if not EMAIL_RE.fullmatch(owner):
        return False, ''
    name = (lead.get('name') or 'A business').strip()
    label = response.get('label') or response.get('choice') or ''
    note = (response.get('note') or '').strip()
    contact = ' / '.join(x for x in [lead.get('email'), lead.get('phone')] if x)
    base = _base(settings)
    token = link.get('token', '')
    dash = '\u2014'
    subject = f'Reply from {name} \u2014 {label}'
    lines = [
        f'{name} answered the website concept e-mail.',
        '',
        f'Answer: {label}',
        f'Message: {note or dash}',
        f'Contact on the listing: {contact or dash}',
        f'City: {lead.get("city") or dash}',
        '',
        f'Open the concept they saw: {site_url(base, token)}',
        f'Their answer is saved in your console under Review links.',
    ]
    text = '\n'.join(lines)
    try:
        sent, outbox_id = send_branded(owner, subject, text, html_title=f'Reply from {name}',
                                       cta_url=site_url(base, token) if base else None,
                                       cta_label='Open the concept', db=db)
        if log:
            log('review', f'Owner notified of {name}\u2019s answer: {label}')
        return sent, outbox_id
    except Exception:
        return False, ''
