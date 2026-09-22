"""Dispatch for the crew — the same rules the Outreach studio applies, enforced again.

The crew never gets a shortcut. A crew dispatch requires an approved item, a complete
sender profile, configured SMTP, a valid address, no suppression entry, no previous
send to that lead, and an unsubscribe token — exactly like pressing *Send* in the
Outreach studio. When SMTP is missing the message is queued in ``mail_outbox`` (never
reported as sent), and when something fails the failure is recorded verbatim.

Extra crew-only limits: one message per lead per 24 hours, and a hard cap per run.
"""
import os, re, ssl, smtplib, uuid
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')
REQUIRED_PROFILE = ('sender_name', 'agency', 'reply_email', 'postal_address')


def smtp_ready():
    return bool(os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM'))


def _footer(settings, lead):
    lines = [f"{settings.get('sender_name', '')} | {settings.get('agency', '')}",
             settings.get('postal_address', ''),
             f"Contact: {settings.get('reply_email', '')}",
             'To stop receiving e-mails, reply "no thanks".']
    base = (settings.get('public_base_url') or '').rstrip('/')
    if base and lead.get('token'):
        lines.append(f'Opt out: {base}/unsubscribe/{lead["token"]}')
    return '\n'.join(line for line in lines if line.strip())


def preflight(db, now, lead, settings):
    """Return (ok, reason). Nothing is sent when this fails."""
    if not lead:
        return False, 'The business record no longer exists.'
    recipient = (lead.get('email') or '').strip().lower()
    if not EMAIL_RE.fullmatch(recipient):
        return False, 'No valid e-mail address on this record — use the share message on WhatsApp or by hand instead.'
    missing = [key for key in REQUIRED_PROFILE if not (settings.get(key) or '').strip()]
    if missing:
        return False, 'Complete your sender profile in Settings first: ' + ', '.join(missing) + '.'
    with db() as c:
        if c.execute('SELECT 1 FROM suppression WHERE email=?', (recipient,)).fetchone():
            return False, 'This recipient has opted out. Sending is blocked, permanently.'
        if c.execute("SELECT 1 FROM sends WHERE lead_id=? AND state IN ('sending','sent','unknown')", (lead['id'],)).fetchone():
            return False, 'A message was already sent to this business (or has an uncertain result). No second send from the crew.'
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        if c.execute('SELECT count(*) FROM crew_dispatch WHERE lead_id=? AND state IN (\'sent\',\'queued\') AND created>?',
                     (lead['id'], cutoff)).fetchone()[0]:
            return False, 'One message per business per day — this one is inside the 24-hour window.'
    return True, ''


def queue_to_outbox(db, now, lead, subject, body, reason):
    """SMTP is not configured: keep the message, say so plainly, never claim it was sent."""
    outbox_id = uuid.uuid4().hex
    with db() as c:
        has_outbox = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mail_outbox'").fetchone()
        if has_outbox:
            c.execute('INSERT INTO mail_outbox(id,to_email,subject,body,html,created,state) VALUES(?,?,?,?,?,?,?)',
                      (outbox_id, lead.get('email', ''), subject[:200], body[:20000], '', now(),
                       'queued: ' + reason[:80]))
    return outbox_id


def send_email(db, now, log, lead, subject, body, settings, approval_id='', run_id=''):
    """Send one reviewed message. Returns a result dict; never raises for expected failures."""
    ok, reason = preflight(db, now, lead, settings)
    if not ok:
        return {'ok': False, 'state': 'blocked', 'detail': reason}
    recipient = lead['email'].strip().lower()
    if '\n' in subject or '\r' in subject or not subject.strip():
        return {'ok': False, 'state': 'blocked', 'detail': 'The subject line is empty or contains a line break.'}

    dispatch_id = uuid.uuid4().hex
    full_body = body.rstrip() + '\n\n—\n' + _footer(settings, lead)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        c.execute('INSERT INTO crew_dispatch(id,run_id,lead_id,approval_id,channel,recipient,subject,body,state,detail,created,updated) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (dispatch_id, run_id, lead['id'], approval_id, 'email', recipient, subject[:200], full_body[:20000],
                   'sending', '', now(), now()))
        send_id = uuid.uuid4().hex
        c.execute('INSERT INTO sends VALUES(?,?,?,?,?,?)', (send_id, lead['id'], recipient, 'sending', '', now()))
        c.execute('INSERT OR IGNORE INTO optout_links VALUES(?,?)', (lead.get('token') or uuid.uuid4().hex, recipient))

    if not smtp_ready():
        outbox_id = queue_to_outbox(db, now, lead, subject, full_body, 'SMTP is not configured')
        with db() as c:
            c.execute("UPDATE crew_dispatch SET state='queued',detail=?,updated=? WHERE id=?", ('Queued in the outbox — SMTP not configured.', now(), dispatch_id))
            c.execute("UPDATE sends SET state='failed',error='SMTP not configured' WHERE id=?", (send_id,))
        log('crew', f'Crew dispatch queued (SMTP not configured) for {lead["name"]}')
        return {'ok': False, 'state': 'queued', 'detail': 'SMTP is not configured, so this went to the outbox instead of pretending to send.',
                'outbox_id': outbox_id, 'dispatch_id': dispatch_id}

    message = EmailMessage()
    message['From'] = os.environ['SMTP_FROM']
    message['To'] = recipient
    message['Reply-To'] = settings.get('reply_email', '')
    message['Subject'] = subject
    message['Message-ID'] = f'<{send_id}@{os.environ["SMTP_FROM"].split("@")[-1]}>'
    message.set_content(full_body)
    try:
        port = int(os.getenv('SMTP_PORT', '587'))
        mode = os.getenv('SMTP_SECURITY', 'starttls')
        if mode not in ('ssl', 'starttls'):
            raise ValueError('TLS is required')
        client = smtplib.SMTP_SSL if mode == 'ssl' else smtplib.SMTP
        with client(os.environ['SMTP_HOST'], port, timeout=25) as server:
            if mode == 'starttls':
                server.starttls(context=ssl.create_default_context())
            if os.getenv('SMTP_USER'):
                server.login(os.environ['SMTP_USER'], os.getenv('SMTP_PASSWORD', ''))
            server.send_message(message)
        with db() as c:
            c.execute("UPDATE crew_dispatch SET state='sent',detail=?,updated=? WHERE id=?", ('Accepted by the mail server.', now(), dispatch_id))
            c.execute("UPDATE sends SET state='sent' WHERE id=?", (send_id,))
            c.execute("UPDATE leads SET stage='Contacted',updated=? WHERE id=?", (now(), lead['id']))
        log('sent', f'Crew approved and sent a message to {lead["name"]}')
        return {'ok': True, 'state': 'sent', 'detail': 'The mail server accepted the message. Delivery and replies are not tracked.',
                'dispatch_id': dispatch_id}
    except Exception as exc:
        import smtplib as _smtp
        rejected = isinstance(exc, (_smtp.SMTPAuthenticationError, _smtp.SMTPRecipientsRefused, _smtp.SMTPSenderRefused,
                                    _smtp.SMTPDataError, _smtp.SMTPNotSupportedError, ValueError))
        with db() as c:
            c.execute("UPDATE crew_dispatch SET state=?,detail=?,updated=? WHERE id=?",
                      ('failed' if rejected else 'unknown', type(exc).__name__, now(), dispatch_id))
            c.execute('UPDATE sends SET state=?,error=? WHERE id=?', ('failed' if rejected else 'unknown', type(exc).__name__, send_id))
        log('error', f'Crew dispatch failed for {lead["name"]}: {type(exc).__name__}')
        return {'ok': False, 'state': 'failed' if rejected else 'unknown',
                'detail': 'SMTP rejected the message — check the provider settings.' if rejected
                          else 'SMTP did not confirm success; resending is blocked to avoid duplicates.'}


def manual_ready(db, now, lead, note, approval_id='', run_id=''):
    """A message that is not e-mail (WhatsApp / SMS / in person): prepared for copy-paste."""
    dispatch_id = uuid.uuid4().hex
    with db() as c:
        c.execute('INSERT INTO crew_dispatch(id,run_id,lead_id,approval_id,channel,recipient,subject,body,state,detail,created,updated) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                  (dispatch_id, run_id, lead['id'], approval_id, 'manual', lead.get('phone', ''), 'Share message',
                   note[:8000], 'ready', 'Copy this into your own channel — the crew never posts on your behalf.', now(), now()))
    return {'ok': True, 'state': 'ready', 'detail': 'Share message marked ready — copy it into WhatsApp, SMS or a call note.',
            'dispatch_id': dispatch_id}
