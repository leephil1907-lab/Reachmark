"""Unsigned public URL check: three measured leaks, full report gated.

Reuses web_probe.observe + gaps_from and opportunity.LEAK_COPY. Does not invent
a score, a revenue figure, or a diagnosis beyond what was read from the page.
"""
from __future__ import annotations

import hashlib
import os
import uuid

from flask import jsonify, render_template, request, session

from web.opportunity import LEAK_COPY
from web.web_probe import gaps_from, observe

PUBLIC_TIMEOUT = 8
PUBLIC_MAX_BYTES = 65536
PUBLIC_RATE_HOUR = 8


def ensure_tables(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS public_audit_log(
            id TEXT PRIMARY KEY,
            ip_hash TEXT NOT NULL,
            created TEXT NOT NULL)''')
        c.execute('CREATE INDEX IF NOT EXISTS public_audit_ip ON public_audit_log(ip_hash, created)')


def _client_ip():
    return (request.headers.get('X-Forwarded-For') or request.remote_addr or '').split(',')[0].strip()


def _ip_hash():
    raw = _client_ip()
    salt = os.getenv('SECRET_KEY') or os.getenv('ADMIN_PASSWORD') or 'reachmark'
    return hashlib.sha256((salt + '|' + raw).encode()).hexdigest()[:32]


def _rate_limited(db, now):
    stamp = now()
    hour_ago = stamp[:11]  # keep same date prefix; compare ISO strings below
    # ISO timestamps sort lexicographically. Cut at 19 chars then subtract via string compare
    # using created >= now minus 1 hour by slicing is fragile; store and compare full ISO.
    from datetime import datetime, timedelta, timezone
    try:
        dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
    except ValueError:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    cutoff = (dt - timedelta(hours=1)).isoformat()
    iph = _ip_hash()
    with db() as c:
        n = c.execute(
            'SELECT count(*) FROM public_audit_log WHERE ip_hash=? AND created>=?',
            (iph, cutoff),
        ).fetchone()[0]
        if int(n) >= PUBLIC_RATE_HOUR:
            return True
        c.execute(
            'INSERT INTO public_audit_log(id,ip_hash,created) VALUES(?,?,?)',
            (uuid.uuid4().hex, iph, stamp),
        )
    return False


def _normalize_url(raw):
    url = (raw or '').strip()
    if not url:
        return ''
    if ' ' in url and '://' not in url:
        return ''
    if not url.lower().startswith(('http://', 'https://')):
        url = 'https://' + url
    return url[:500]


def preview_leaks(url, observe_fn=None):
    """Return the public payload for one URL. Pure enough to unit-test with a stub."""
    from web.services import classify
    observe_fn = observe_fn or observe
    lead = {
        'website': url,
        'status': classify(url),
        'name': '',
        'email': '',
        'phone': '',
        'social_url': '',
    }
    observations = observe_fn(
        url, timeout=PUBLIC_TIMEOUT, max_bytes=PUBLIC_MAX_BYTES,
        respect_robots=True, verify_links=False,
    )
    packed = gaps_from(observations, lead)
    leaks = []
    for gap in packed.get('gaps') or []:
        key = gap.get('key')
        copy = LEAK_COPY.get(key) or {}
        leaks.append({
            'key': key,
            'title': copy.get('title') or key,
            'leak': copy.get('leak') or gap.get('reason') or '',
            'weight': int(gap.get('weight') or 0),
            'source': gap.get('source') or 'observation',
        })
    leaks.sort(key=lambda row: -row['weight'])
    top = leaks[:3]
    blocked = False
    reason = observations.get('reason') or ''
    status = observations.get('status')
    if status in (401, 403, 429) or 'blocked this check' in reason.lower() or 'access restricted' in reason.lower():
        blocked = True
    return {
        'ok': bool(observations.get('ok')) and not blocked,
        'blocked': blocked,
        'url': observations.get('final_url') or url,
        'observed': bool(observations.get('ok')),
        'reason': reason if not observations.get('ok') else '',
        'leaks': top,
        'leak_count': len(top),
        'measured': True,
        'full_report': False,
        'label': 'Measured observations from this check. Not a revenue forecast.',
    }


def register_public_audit(app, db, now, log):
    ensure_tables(db)

    @app.get('/sourcing')
    def sourcing_page():
        base = (os.getenv('PUBLIC_BASE_URL') or '').rstrip('/')
        seo = {
            'title': 'Where listings come from · Reachmark',
            'description': 'Reachmark finds businesses from OpenStreetMap. Overpass limits, measured page checks, and what stays unknown.',
            'canonical': (base + '/sourcing') if base else None,
        }
        return render_template('sourcing.html', seo=seo)

    @app.get('/sending')
    def sending_page():
        base = (os.getenv('PUBLIC_BASE_URL') or '').rstrip('/')
        seo = {
            'title': 'How email is sent · Reachmark',
            'description': 'Every Reachmark email needs your approval, an unsubscribe link, and a suppression check. Nothing sends on its own.',
            'canonical': (base + '/sending') if base else None,
        }
        return render_template('sending.html', seo=seo)

    @app.post('/api/public/audit')
    def public_audit():
        from web.funnel import record as funnel_record
        body = request.get_json(silent=True) or {}
        url = _normalize_url(body.get('url') or request.form.get('url') or '')
        if not url:
            return jsonify(error='Enter a public website URL.', blocked=False), 400
        if _rate_limited(db, now):
            return jsonify(
                error='This check is limited to a few tries per hour from one network. Try again later.',
                blocked=True, rate_limited=True,
            ), 429
        funnel_record(db, now, 'audit_started', {'url_host': url.split('/')[2] if '://' in url else ''})
        try:
            payload = preview_leaks(url)
        except Exception:
            log('public-audit', 'public audit failed')
            return jsonify(
                error='This check could not finish. The site may have blocked it.',
                blocked=True,
            ), 502
        funnel_record(db, now, 'audit_completed', {
            'observed': payload.get('observed'),
            'leak_count': payload.get('leak_count'),
            'blocked': payload.get('blocked'),
        })
        if payload.get('blocked'):
            payload['error'] = payload.get('reason') or 'This site blocked the check. That is inconclusive, not a fault.'
        # Full Digital Opportunity Report stays behind an account.
        payload['signup'] = '/signup'
        payload['gate'] = 'Create an account to run the full Digital Opportunity Report on a saved business.'
        return jsonify(payload)
