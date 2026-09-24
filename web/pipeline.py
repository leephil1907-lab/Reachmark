"""The sending pipeline: a controlled first batch, open/reply measurement, and the
polite follow-up sequence that turns a reply into a customer.

Everything here obeys the same guardrails as the rest of the crew:

* a **hard cap** on every run (20 for the first batch, 10 for follow-ups),
* **one message per business per day** and **no second first-contact**,
* **permanent opt-out** (the suppression list) and the unsubscribe token,
* follow-ups **stop the moment a business answers** or opts out,
* nothing is ever reported as *sent* unless the mail server accepted it.

Measurement is honest and minimal: a 1x1 pixel records an *open* (a real signal, not
a verdict), the answer buttons record a *reply*, and the console shows the rates.
"""
import html
import os
import re
import ssl
import smtplib
import uuid
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

from web.i18n import t as _t, locale_now
from web.agent_tools import owner_locked

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')
FIRST_BATCH_CAP = 20
FOLLOWUP_CAP = 10
FOLLOWUP_STEPS = (2, 3)
FOLLOWUP_DELAY_DAYS = {2: 3, 3: 7}
# A 1x1 transparent GIF, served for the open-tracking pixel.
PIXEL = (b'GIF89a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff!'
         b'\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00'
         b'\x00\x02\x02D\x01\x00;')


def ensure_tables(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS email_events(
            id TEXT PRIMARY KEY, lead_id TEXT, link_id TEXT, kind TEXT, detail TEXT, created TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS pipeline_followups(
            id TEXT PRIMARY KEY, lead_id TEXT, link_id TEXT, step INTEGER, state TEXT,
            due TEXT, sent_at TEXT, created TEXT, updated TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS email_events_lead ON email_events(lead_id, kind)')
        c.execute('CREATE INDEX IF NOT EXISTS followups_due ON pipeline_followups(state, due)')


def record_event(db, now, lead_id, link_id, kind, detail=''):
    ensure_tables(db)
    with db() as c:
        c.execute('INSERT INTO email_events(id,lead_id,link_id,kind,detail,created) VALUES(?,?,?,?,?,?)',
                  (uuid.uuid4().hex, lead_id, link_id, kind, detail[:120], now()))


def track_open(db, now, token):
    """Record an e-mail open for the link behind ``token``. Returns True when found."""
    ensure_tables(db)
    with db() as c:
        row = c.execute('SELECT id, lead_id FROM review_links WHERE token=?', (token,)).fetchone()
        if not row:
            return False
        c.execute('INSERT INTO email_events(id,lead_id,link_id,kind,detail,created) VALUES(?,?,?,?,?,?)',
                  (uuid.uuid4().hex, row['lead_id'], row['id'], 'open', '', now()))
    return True


def pixel_html(base, token):
    if not base or not token:
        return ''
    return (f'<img src="{base}/t/{token}/o.gif" width="1" height="1" alt="" '
            'style="display:none;border:0;outline:none" />')


def _inject_pixel(body, base, token):
    px = pixel_html(base, token)
    if not px or not body:
        return body
    if '</body>' in body:
        return body.replace('</body>', px + '</body>', 1)
    return body + px


def _deliver(db, now, log, settings, lead, subject, text, body_html, step):
    """Send one message over SMTP and record it. Never raises for expected failures."""
    from web.crew_mail import smtp_ready
    recipient = (lead.get('email') or '').strip().lower()
    if not EMAIL_RE.fullmatch(recipient):
        return {'ok': False, 'state': 'blocked', 'detail': 'No valid e-mail address on this record.'}
    if not smtp_ready():
        return {'ok': False, 'state': 'blocked', 'detail': 'SMTP is not configured.'}
    send_id = uuid.uuid4().hex
    message = EmailMessage()
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = recipient
    reply = (settings or {}).get('reply_email') or ''
    if reply:
        message['Reply-To'] = reply
    message['Subject'] = subject
    message['Message-ID'] = f'<{send_id}@{os.environ["SMTP_FROM"].split("@")[-1]}>'
    message.set_content(text)
    if body_html:
        message.add_alternative(body_html, subtype='html')
    try:
        port = int(os.getenv('SMTP_PORT', '587'))
        mode = os.getenv('SMTP_SECURITY', 'starttls')
        client = smtplib.SMTP_SSL if mode == 'ssl' else smtplib.SMTP
        with client(os.environ['SMTP_HOST'], port, timeout=25) as server:
            if mode == 'starttls':
                server.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'):
                server.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD', ''))
            server.send_message(message)
    except Exception as exc:
        if log:
            log('error', f'Pipeline send failed for {lead.get("name")}: {type(exc).__name__}')
        return {'ok': False, 'state': 'failed', 'detail': type(exc).__name__}
    record_event(db, now, lead.get('id'), '', 'sent', step)
    with db() as c:
        c.execute('INSERT INTO sends VALUES(?,?,?,?,?,?)',
                  (send_id, lead.get('id'), recipient, 'sent', '', now()))
        c.execute("UPDATE leads SET stage='Contacted',updated=? WHERE id=?", (now(), lead.get('id')))
    if log:
        log('sent', f'Pipeline {step} message sent to {lead.get("name")}')
    return {'ok': True, 'state': 'sent', 'detail': 'Accepted by the mail server.'}


def schedule_followups(db, now, lead, link):
    """Queue the polite 2nd and 3rd touch after a first contact. Idempotent."""
    ensure_tables(db)
    if not lead or not lead.get('id'):
        return 0
    link_id = (link or {}).get('id', '')
    created = 0
    with db() as c:
        existing = {r[0] for r in c.execute('SELECT step FROM pipeline_followups WHERE lead_id=?', (lead['id'],))}
        for step in FOLLOWUP_STEPS:
            if step in existing:
                continue
            due = (datetime.now(timezone.utc) + timedelta(days=FOLLOWUP_DELAY_DAYS[step])).isoformat()
            c.execute('INSERT INTO pipeline_followups(id,lead_id,link_id,step,state,due,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?)',
                      (uuid.uuid4().hex, lead['id'], link_id, step, 'scheduled', due, now(), now()))
            created += 1
    return created


def _mark_followup(db, now, fid, state):
    with db() as c:
        c.execute('UPDATE pipeline_followups SET state=?,sent_at=?,updated=? WHERE id=?',
                  (state, now() if state == 'sent' else None, now(), fid))


def _followup_email(lead, link, settings, step, locale):
    """A shorter, softer branded note that still carries the link and the question."""
    from web.outreach_email import _base, site_url, answer_url, CHOICES, _button
    base = _base(settings)
    token = (link or {}).get('token', '')
    name = (lead.get('name') or 'your business').strip()
    studio = ((settings or {}).get('agency') or 'Reachmark').strip()
    sender = ((settings or {}).get('sender_name') or studio).strip()
    reply = (settings or {}).get('reply_email') or ''
    subject = _t(f'oe.fu{step}_subject', locale, n=name)
    intro = _t(f'oe.fu{step}_intro', locale, n=name)
    url = site_url(base, token)
    text = '\n'.join([intro, '', _t('oe.see', locale) + ': ' + url, '',
                      _t('oe.question', locale, n=name)])
    for choice in CHOICES:
        text += '\n  \u2022 ' + _t('rv.' + choice, locale) + ': ' + answer_url(base, token, choice)
    text += '\n\n' + _t('oe.optout', locale) + '\n\n' + sender + ' \u00b7 ' + studio
    if reply:
        text += '\n' + reply
    answers = ''.join(_button(answer_url(base, token, c), _t('rv.' + c, locale),
                              primary=(c == 'want')) for c in CHOICES)
    logo = f'{base}/static/logo-primary.png' if base else '/static/logo-primary.png'
    body_html = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body style="margin:0;background:#eef6d1;font-family:Manrope,Arial,sans-serif;color:#1a2315">
<div style="max-width:600px;margin:0 auto;padding:28px">
<div style="background:#ffffff;border:1px solid #e2e7d6;border-radius:16px;padding:30px">
<div style="margin-bottom:20px"><img src="{logo}" alt="Reachmark" style="height:36px" onerror="this.style.display='none'"><div style="font-weight:800;letter-spacing:-0.5px;font-size:18px;color:#0f1a0a">Reachmark</div><div style="font-size:11px;letter-spacing:1.2px;color:#8c9c77">FIND POTENTIAL &middot; MAKE YOUR MARK</div></div>
<div style="line-height:1.7;color:#33402a;font-size:14px"><p style="margin:0 0 12px">{html.escape(intro)}</p></div>
<p style="margin:20px 0 10px">{_button(url, _t('oe.see', locale), primary=True)}</p>
<div style="margin-top:22px;padding-top:18px;border-top:1px solid #eef1e4">
<p style="margin:0 0 12px;font-size:15px;font-weight:800;color:#0f1a0a">{html.escape(_t('oe.question', locale, n=name))}</p>
<p style="margin:0 0 14px;color:#33402a;font-size:13.5px">{html.escape(_t('oe.pick', locale))}</p>
{answers}
</div>
<div style="margin-top:22px;padding-top:16px;border-top:1px solid #eef1e4;font-size:12px;color:#8a9976;line-height:1.6">
{html.escape(_t('oe.optout', locale))}<br>{html.escape(sender)} &middot; {html.escape(studio)}{(' &middot; ' + html.escape(reply)) if reply else ''}
</div>
</div></div></body></html>"""
    return subject, text, body_html


def send_first_batch(db, now, log, settings, limit=FIRST_BATCH_CAP):
    """Send the branded proposal to a controlled first batch of businesses.

    Every send passes the same preflight the Outreach studio uses (valid address,
    complete sender profile, no suppression, no prior send). The batch is capped and
    each success schedules the follow-up sequence.
    """
    ensure_tables(db)
    try:
        limit = max(1, min(int(limit or FIRST_BATCH_CAP), FIRST_BATCH_CAP))
    except (TypeError, ValueError):
        limit = FIRST_BATCH_CAP
    from web.outreach_email import build_outreach_email_for, _base
    from web.crew_mail import preflight
    with db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM leads WHERE email IS NOT NULL AND TRIM(email)!='' "
            "AND (stage IS NULL OR stage NOT IN ('Contacted','Won','Not a fit')) "
            "AND id NOT IN (SELECT lead_id FROM sends WHERE state IN ('sending','sent','unknown')) "
            "ORDER BY created DESC LIMIT ?", (limit * 3,))]
    results = []
    sent = 0
    for lead in rows:
        if sent >= limit:
            break
        if not EMAIL_RE.fullmatch((lead.get('email') or '').strip().lower()):
            continue
        ok, reason = preflight(db, now, lead, settings)
        if not ok:
            results.append({'lead': lead.get('name'), 'state': 'skipped', 'detail': reason})
            continue
        try:
            email = build_outreach_email_for(db, now, lead, settings)
        except Exception as exc:
            results.append({'lead': lead.get('name'), 'state': 'error', 'detail': type(exc).__name__})
            continue
        base = _base(settings)
        token = (email.get('link') or {}).get('token', '')
        body_html = _inject_pixel(email.get('html', ''), base, token)
        outcome = _deliver(db, now, log, settings, lead, email['subject'], email['text'],
                           body_html, 'first')
        if outcome['ok']:
            sent += 1
            schedule_followups(db, now, lead, email.get('link') or {})
        results.append({'lead': lead.get('name'), 'state': outcome['state'], 'detail': outcome['detail']})
    return {'sent': sent, 'attempted': len(results), 'results': results, 'cap': FIRST_BATCH_CAP}


def run_followups(db, now, log, settings, limit=5):
    """Send every due follow-up that has not been answered or opted out."""
    ensure_tables(db)
    try:
        limit = max(1, min(int(limit or 5), FOLLOWUP_CAP))
    except (TypeError, ValueError):
        limit = 5
    stamp = now()
    with db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT f.id AS fid, f.step AS fstep, f.link_id AS flink, l.* "
            "FROM pipeline_followups f JOIN leads l ON l.id=f.lead_id "
            "WHERE f.state='scheduled' AND f.due<=? ORDER BY f.due LIMIT ?", (stamp, limit * 3))]
    results = []
    sent = 0
    for row in rows:
        if sent >= limit:
            break
        fid, step = row['fid'], row['fstep']
        lead = row
        with db() as c:
            link_row = c.execute('SELECT * FROM review_links WHERE id=?', (row.get('flink'),)).fetchone()
            answered = c.execute('SELECT 1 FROM review_responses WHERE lead_id=? LIMIT 1',
                                 (lead['id'],)).fetchone()
            suppressed = c.execute('SELECT 1 FROM suppression WHERE email=?',
                                   ((lead.get('email') or '').strip().lower(),)).fetchone()
        if answered or suppressed or not link_row:
            _mark_followup(db, now, fid, 'cancelled')
            results.append({'lead': lead.get('name'), 'step': step, 'state': 'cancelled'})
            continue
        link = dict(link_row)
        locale = locale_now()
        subject, text, body_html = _followup_email(lead, link, settings, step, locale)
        from web.outreach_email import _base
        body_html = _inject_pixel(body_html, _base(settings), link.get('token', ''))
        outcome = _deliver(db, now, log, settings, lead, subject, text, body_html, f'followup-{step}')
        _mark_followup(db, now, fid, 'sent' if outcome['ok'] else 'skipped')
        if outcome['ok']:
            sent += 1
        results.append({'lead': lead.get('name'), 'step': step, 'state': outcome['state'],
                        'detail': outcome.get('detail', '')})
    return {'sent': sent, 'attempted': len(results), 'results': results}


def pipeline_metrics(db):
    """The honest scoreboard: how many were contacted, opened, and replied."""
    ensure_tables(db)
    with db() as c:
        contacted = c.execute("SELECT count(DISTINCT lead_id) FROM email_events WHERE kind='sent'").fetchone()[0]
        opened = c.execute("SELECT count(DISTINCT lead_id) FROM email_events WHERE kind='open'").fetchone()[0]
        replied = c.execute('SELECT count(DISTINCT lead_id) FROM review_responses').fetchone()[0]
        followups_sent = c.execute("SELECT count(*) FROM pipeline_followups WHERE state='sent'").fetchone()[0]
        scheduled = c.execute("SELECT count(*) FROM pipeline_followups WHERE state='scheduled'").fetchone()[0]
        recent = [dict(r) for r in c.execute(
            'SELECT e.kind, e.detail, e.created, l.name AS business FROM email_events e '
            'LEFT JOIN leads l ON l.id=e.lead_id ORDER BY e.created DESC LIMIT 20')]

    def rate(n):
        return round(n / contacted * 100, 1) if contacted else 0.0
    return {'contacted': contacted, 'opened': opened, 'replied': replied,
            'open_rate': rate(opened), 'reply_rate': rate(replied),
            'followups_sent': followups_sent, 'followups_scheduled': scheduled,
            'recent': recent}


def register_pipeline(app, db, now, log, settings):
    from flask import request, jsonify, Response, session
    ensure_tables(db)

    def _denied():
        if owner_locked() and not session.get('owner'):
            return jsonify(error=_t('er_083', locale_now())), 403
        return None

    @app.get('/t/<token>/o.gif')
    def pipeline_open_pixel(token):
        track_open(db, now, token)
        return Response(PIXEL, mimetype='image/gif',
                        headers={'Cache-Control': 'no-store, no-cache, must-revalidate',
                                 'Pragma': 'no-cache'})

    @app.get('/api/pipeline')
    def pipeline_status():
        if (denied := _denied()):
            return denied
        return jsonify(metrics=pipeline_metrics(db))

    @app.post('/api/pipeline/send-batch')
    def pipeline_send_batch():
        if (denied := _denied()):
            return denied
        body = request.get_json(silent=True) or {}
        result = send_first_batch(db, now, log, settings(), body.get('limit') or FIRST_BATCH_CAP)
        return jsonify(ok=True, **result)

    @app.post('/api/pipeline/followups')
    def pipeline_run_followups():
        if (denied := _denied()):
            return denied
        body = request.get_json(silent=True) or {}
        result = run_followups(db, now, log, settings(), body.get('limit') or 5)
        return jsonify(ok=True, **result)

    return {'send_first_batch': send_first_batch, 'run_followups': run_followups,
            'pipeline_metrics': pipeline_metrics, 'track_open': track_open}
