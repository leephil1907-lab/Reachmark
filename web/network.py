"""Network: in-person lead capture loop (cards, events, scan, booking, webhooks).

Popl-style networking without Popl-style invention: every contact detail here is
either typed by a human, read from a photo the owner confirms, or measured live.
Nothing is enriched from thin air and nothing is sent without an explicit tap.

Tiers: 1 card + QR free · events / scanner / booking on Starter ·
qualifiers / follow-up / webhooks / revenue attribution on Pro.
"""
import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

from web.i18n import t as _t, locale_now

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPLOAD_DIR = os.path.join(ROOT, 'uploads', 'scans')
LOGO_PNG = os.path.join(ROOT, 'static', 'icon-192.png')
EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')
CARD_THEMES = ('charcoal', 'paper', 'lime')
HOOK_EVENTS = ('lead.created', 'response.received', 'booking.created')
SCAN_EXTS = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}
SCAN_MAX_BYTES = 3 * 1024 * 1024


def ensure_tables(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS cards(id TEXT PRIMARY KEY, owner TEXT, name TEXT, role TEXT,
            org TEXT, phone TEXT, email TEXT, website TEXT, links TEXT, theme TEXT,
            token TEXT UNIQUE, views INTEGER DEFAULT 0, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, owner TEXT, name TEXT,
            location TEXT, starts_at TEXT, ends_at TEXT, goal INTEGER DEFAULT 0,
            token TEXT UNIQUE, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS event_leads(event_id TEXT, lead_id TEXT, answers TEXT,
            scan_id TEXT, created TEXT, PRIMARY KEY(event_id, lead_id));
        CREATE TABLE IF NOT EXISTS qualifiers(id TEXT PRIMARY KEY, event_id TEXT, question TEXT,
            kind TEXT, options TEXT, position INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS scans(id TEXT PRIMARY KEY, owner TEXT, lead_id TEXT,
            filename TEXT, extracted TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS availability(id TEXT PRIMARY KEY, owner TEXT, weekday INTEGER,
            start TEXT, end TEXT);
        CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY, owner TEXT, slot_start TEXT,
            slot_end TEXT, name TEXT, email TEXT, note TEXT, status TEXT, token TEXT UNIQUE,
            ip_hash TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS webhooks(id TEXT PRIMARY KEY, owner TEXT, url TEXT,
            secret TEXT, events TEXT, active INTEGER DEFAULT 1, created TEXT, updated TEXT);
        ''')
        cols = {r[1] for r in c.execute('PRAGMA table_info(users)')}
        for col, typ in [('booking_token', 'TEXT'), ('oauth_google_sub', 'TEXT'), ('oauth_ms_sub', 'TEXT')]:
            if col not in cols:
                c.execute(f'ALTER TABLE users ADD COLUMN {col} {typ}')
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def row(db, table, rid, owner=None):
    with db() as c:
        r = c.execute(f'SELECT * FROM {table} WHERE id=?', (rid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    if owner is not None and d.get('owner') != owner:
        return None
    return d


def dispatch(db, now, log, owner, event, payload):
    """Best-effort HMAC-signed webhook POST. Never raises."""
    if event not in HOOK_EVENTS or not owner:
        return
    try:
        with db() as c:
            hooks = [dict(r) for r in c.execute(
                "SELECT * FROM webhooks WHERE owner=? AND active=1", (owner,))]
    except Exception:
        return
    try:
        import requests
    except ImportError:
        return
    body = json.dumps({'event': event, 'created': now(), 'payload': payload})
    for hook in hooks:
        try:
            wanted = json.loads(hook.get('events') or '[]')
        except Exception:
            wanted = []
        if event not in wanted:
            continue
        try:
            sig = hmac.new((hook.get('secret') or '').encode(), body.encode(),
                           hashlib.sha256).hexdigest()
            requests.post(hook['url'], data=body,
                          headers={'Content-Type': 'application/json',
                                   'X-Reachmark-Event': event,
                                   'X-Reachmark-Signature': 'sha256=' + sig},
                          timeout=5)
        except Exception as exc:
            try:
                log('webhook', f'Hook {hook["id"][:8]} failed: {type(exc).__name__}')
            except Exception:
                pass


def qr_png_bytes(url, brand=True):
    """Branded QR PNG. Raises RuntimeError when the qrcode package is missing."""
    try:
        import qrcode
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError('QR needs the qrcode + pillow packages.') from exc
    qr = qrcode.QRCode(box_size=12, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color='#0f1a0a', back_color='#ffffff').convert('RGB')
    if brand and os.path.exists(LOGO_PNG):
        logo = Image.open(LOGO_PNG).convert('RGBA')
        side = max(48, img.size[0] // 5)
        logo.thumbnail((side, side))
        pad = Image.new('RGBA', (logo.size[0] + 24, logo.size[1] + 24), (255, 255, 255, 255))
        pad.alpha_composite(logo, (12, 12))
        img.paste(pad.convert('RGB'), ((img.size[0] - pad.size[0]) // 2,
                                      (img.size[1] - pad.size[1]) // 2))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def vcard_text(card):
    lines = ['BEGIN:VCARD', 'VERSION:3.0', f'FN:{card.get("name") or ""}']
    if card.get('org'):
        lines.append(f'ORG:{card["org"]}')
    if card.get('role'):
        lines.append(f'TITLE:{card["role"]}')
    if card.get('phone'):
        lines.append(f'TEL;TYPE=WORK:{card["phone"]}')
    if card.get('email'):
        lines.append(f'EMAIL;TYPE=WORK:{card["email"]}')
    if card.get('website'):
        lines.append(f'URL:{card["website"]}')
    lines.append('END:VCARD')
    return '\r\n'.join(lines) + '\r\n'


def ics_text(booking, studio):
    def stamp(value):
        return re.sub(r'[-:]', '', value)[:15]
    return ('BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Reachmark//Booking//EN\r\n'
            'BEGIN:VEVENT\r\n'
            f'UID:{booking["token"]}@reachmark\r\n'
            f'DTSTAMP:{stamp(datetime.now(timezone.utc).isoformat())}Z\r\n'
            f'DTSTART:{stamp(booking["slot_start"])}\r\n'
            f'DTEND:{stamp(booking["slot_end"])}\r\n'
            f'SUMMARY:{studio} — meeting with {booking["name"]}\r\n'
            'END:VEVENT\r\nEND:VCALENDAR\r\n')


def open_slots(windows, booked, days=14, slot_min=30):
    """Half-open slots from weekly windows minus overlapping bookings. All local naive ISO."""
    booked_ranges = [(b['slot_start'], b['slot_end']) for b in booked if b['status'] != 'cancelled']
    out, day = [], datetime.now().date()
    for ahead in range(days):
        current = day + timedelta(days=ahead)
        for window in windows:
            if int(window['weekday']) != current.weekday():
                continue
            start = datetime.combine(current, datetime.strptime(window['start'], '%H:%M').time())
            end = datetime.combine(current, datetime.strptime(window['end'], '%H:%M').time())
            cursor = start
            while cursor + timedelta(minutes=slot_min) <= end:
                slot = (cursor.isoformat(timespec='minutes'),
                        (cursor + timedelta(minutes=slot_min)).isoformat(timespec='minutes'))
                if slot[0] > datetime.now().isoformat(timespec='minutes') and not any(
                        not (slot[1] <= low or slot[0] >= high) for low, high in booked_ranges):
                    out.append({'start': slot[0], 'end': slot[1]})
                cursor += timedelta(minutes=slot_min)
    return out


def register_network(app, db, now, log, settings):
    from flask import request, jsonify, render_template, abort, session, Response, send_file
    ensure_tables(db)

    def uid():
        if session.get('owner'):
            return 'owner'
        return session.get('client_id')

    def guard():
        current = uid()
        if not current:
            return None, (jsonify(error=_t('er_010', locale_now())), 401)
        return current, None

    def tier_ok(need):
        if session.get('owner'):
            return True
        from web.billing import tier_status
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE id=?', (session.get('client_id'),)).fetchone()
        tier, active, _ = tier_status(dict(r) if r else None)
        order = {'free': 0, 'starter': 1, 'pro': 2}
        return active and order.get(tier, 0) >= order[need]

    def need_tier(need):
        if tier_ok(need):
            return None
        from web.billing import tier_status
        with db() as c:
            r = c.execute('SELECT * FROM users WHERE id=?', (session.get('client_id'),)).fetchone()
        tier, _, _ = tier_status(dict(r) if r else None)
        return jsonify(error=_t('er_138', locale_now(), p=need.title()),
                       upgrade='/pricing', required=need, tier=tier), 402

    # -- digital cards ---------------------------------------------------- #
    @app.get('/api/cards')
    def cards_list():
        current, err = guard()
        if err:
            return err
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT * FROM cards WHERE owner=? ORDER BY created', (current,))]
        return jsonify(cards=rows)

    @app.post('/api/cards')
    def cards_create():
        current, err = guard()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        name = str(body.get('name', '')).strip()
        if not name:
            return jsonify(error=_t('nw.e_name', locale_now())), 400
        theme = str(body.get('theme', 'charcoal'))
        if theme not in CARD_THEMES:
            return jsonify(error=_t('nw.e_theme', locale_now())), 400
        links = body.get('links') or []
        if not isinstance(links, list) or len(links) > 8:
            return jsonify(error=_t('nw.e_links', locale_now())), 400
        for link in links:
            if not isinstance(link, dict) or not str(link.get('label', '')).strip() \
                    or not str(link.get('url', '')).startswith(('https://', 'http://', 'mailto:', 'tel:')):
                return jsonify(error=_t('nw.e_links', locale_now())), 400
        with db() as c:
            count = c.execute('SELECT count(*) FROM cards WHERE owner=?', (current,)).fetchone()[0]
        if count >= 1 and not tier_ok('starter'):
            denied = need_tier('starter')
            if denied:
                return denied
        cid, token, stamp = uuid.uuid4().hex, secrets.token_urlsafe(12), now()
        with db() as c:
            c.execute('INSERT INTO cards VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (cid, current, name[:120], str(body.get('role', ''))[:120],
                       str(body.get('org', ''))[:160], str(body.get('phone', ''))[:100],
                       str(body.get('email', ''))[:250], str(body.get('website', ''))[:500],
                       json.dumps([{'label': str(x.get('label', ''))[:60],
                                    'url': str(x.get('url', ''))[:500]} for x in links]),
                       theme, token, 0, stamp, stamp))
        log('network', f'Digital card created for {name}')
        return jsonify(ok=True, id=cid, token=token), 201

    @app.put('/api/cards/<cid>')
    def cards_update(cid):
        current, err = guard()
        if err:
            return err
        card = row(db, 'cards', cid, current)
        if not card:
            return jsonify(error=_t('er_077', locale_now())), 404
        body = request.get_json(silent=True) or {}
        fields = {k: str(body[k])[:500] for k in
                  ('name', 'role', 'org', 'phone', 'email', 'website') if k in body}
        if 'theme' in body:
            if body['theme'] not in CARD_THEMES:
                return jsonify(error=_t('nw.e_theme', locale_now())), 400
            fields['theme'] = body['theme']
        if 'links' in body:
            links = body['links']
            if not isinstance(links, list) or len(links) > 8:
                return jsonify(error=_t('nw.e_links', locale_now())), 400
            fields['links'] = json.dumps(links)[:4000]
        if not fields:
            return jsonify(error=_t('er_080', locale_now())), 400
        fields['updated'] = now()
        with db() as c:
            c.execute('UPDATE cards SET {} WHERE id=?'.format(
                ','.join(f'{k}=?' for k in fields)), (*fields.values(), cid))
        return jsonify(ok=True)

    @app.delete('/api/cards/<cid>')
    def cards_delete(cid):
        current, err = guard()
        if err:
            return err
        with db() as c:
            cur = c.execute('DELETE FROM cards WHERE id=? AND owner=?', (cid, current))
        if not cur.rowcount:
            return jsonify(error=_t('er_077', locale_now())), 404
        return jsonify(ok=True)

    @app.get('/c/<token>')
    def card_page(token):
        with db() as c:
            r = c.execute('SELECT * FROM cards WHERE token=?', (token,)).fetchone()
        if not r:
            abort(404)
        card = dict(r)
        with db() as c:
            c.execute('UPDATE cards SET views=views+1 WHERE id=?', (card['id'],))
            has_booking = c.execute('SELECT 1 FROM availability WHERE owner=?',
                                    (card['owner'],)).fetchone()
            booking_token = None
            if card['owner'] == 'owner':
                booking_token = (settings().get('booking_token') or '')
            else:
                u = c.execute('SELECT booking_token FROM users WHERE id=?',
                              (card['owner'],)).fetchone()
                booking_token = (u['booking_token'] if u else '') or ''
        try:
            card['links'] = json.loads(card.get('links') or '[]')
        except Exception:
            card['links'] = []
        studio = (settings().get('agency') or 'Reachmark').strip()
        return render_template('card.html', card=card, studio=studio,
                               book_url=f'/book/{booking_token}' if has_booking and booking_token else '')

    @app.get('/c/<token>.vcf')
    def card_vcf(token):
        with db() as c:
            r = c.execute('SELECT * FROM cards WHERE token=?', (token,)).fetchone()
        if not r:
            abort(404)
        name = (dict(r).get('name') or 'contact').lower().replace(' ', '-')[:40]
        return Response(vcard_text(dict(r)), mimetype='text/vcard',
                        headers={'Content-Disposition': f'attachment; filename="{name}.vcf"'})

    # -- branded QR ------------------------------------------------------- #
    @app.get('/api/qr.png')
    def qr_image():
        target = (request.args.get('u') or '').strip()
        if not target or len(target) > 1000:
            return jsonify(error=_t('nw.e_qr', locale_now())), 400
        allowed = False
        if target.startswith('/') and not target.startswith('//'):
            allowed = True
        elif re.match(r'https?://', target):
            host = re.sub(r'^https?://', '', target).split('/')[0].lower()
            own = (request.host or '').split(':')[0].lower()
            configured = re.sub(r'^https?://', '', (settings().get('public_base_url') or '')).split('/')[0].lower()
            allowed = host in {own, configured} - {''}
        if not allowed:
            return jsonify(error=_t('nw.e_qr_host', locale_now())), 400
        try:
            blob = qr_png_bytes(target, brand=request.args.get('logo', '1') == '1')
        except RuntimeError:
            return jsonify(error=_t('nw.e_qr_lib', locale_now())), 500
        return Response(blob, mimetype='image/png',
                        headers={'Cache-Control': 'public, max-age=86400'})

    # -- events ----------------------------------------------------------- #
    @app.get('/api/events')
    def events_list():
        current, err = guard()
        if err:
            return err
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT e.*,(SELECT count(*) FROM event_leads WHERE event_id=e.id) AS captured '
                'FROM events e WHERE owner=? ORDER BY created DESC', (current,))]
        return jsonify(events=rows)

    @app.post('/api/events')
    def events_create():
        current, err = guard()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        name = str(body.get('name', '')).strip()
        if not name:
            return jsonify(error=_t('nw.e_name', locale_now())), 400
        try:
            goal = max(0, min(int(body.get('goal') or 0), 100000))
        except (TypeError, ValueError):
            return jsonify(error=_t('nw.e_goal', locale_now())), 400
        eid, stamp = uuid.uuid4().hex, now()
        with db() as c:
            c.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (eid, current, name[:160], str(body.get('location', ''))[:200],
                       str(body.get('starts_at', ''))[:32], str(body.get('ends_at', ''))[:32],
                       goal, secrets.token_urlsafe(10), stamp, stamp))
        log('network', f'Event created: {name}')
        return jsonify(ok=True, id=eid), 201

    @app.get('/api/events/<eid>')
    def events_detail(eid):
        current, err = guard()
        if err:
            return err
        event = row(db, 'events', eid, current)
        if not event:
            return jsonify(error=_t('er_077', locale_now())), 404
        with db() as c:
            leads = [dict(r) for r in c.execute(
                'SELECT l.*,el.answers,el.scan_id,el.created AS captured_at FROM leads l '
                'JOIN event_leads el ON el.lead_id=l.id WHERE el.event_id=? ORDER BY el.created DESC',
                (eid,))]
            quals = [dict(r) for r in c.execute(
                'SELECT * FROM qualifiers WHERE event_id=? ORDER BY position', (eid,))]
        return jsonify(event=event, leads=leads, qualifiers=quals)

    @app.delete('/api/events/<eid>')
    def events_delete(eid):
        current, err = guard()
        if err:
            return err
        with db() as c:
            c.execute('DELETE FROM event_leads WHERE event_id=?', (eid,))
            c.execute('DELETE FROM qualifiers WHERE event_id=?', (eid,))
            cur = c.execute('DELETE FROM events WHERE id=? AND owner=?', (eid, current))
        if not cur.rowcount:
            return jsonify(error=_t('er_077', locale_now())), 404
        return jsonify(ok=True)

    @app.post('/api/events/<eid>/qualifiers')
    def qualifiers_add(eid):
        current, err = guard()
        if err:
            return err
        denied = need_tier('pro')
        if denied:
            return denied
        if not row(db, 'events', eid, current):
            return jsonify(error=_t('er_077', locale_now())), 404
        body = request.get_json(silent=True) or {}
        question = str(body.get('question', '')).strip()
        kind = str(body.get('kind', 'text'))
        options = body.get('options') or []
        if not question or kind not in ('text', 'choice') or \
                (kind == 'choice' and (not isinstance(options, list) or not 2 <= len(options) <= 8)):
            return jsonify(error=_t('nw.e_qual', locale_now())), 400
        with db() as c:
            position = c.execute('SELECT count(*) FROM qualifiers WHERE event_id=?', (eid,)).fetchone()[0]
            qid = uuid.uuid4().hex
            c.execute('INSERT INTO qualifiers VALUES(?,?,?,?,?,?)',
                      (qid, eid, question[:300], kind,
                       json.dumps([str(o)[:120] for o in options]) if kind == 'choice' else '[]',
                       position))
        return jsonify(ok=True, id=qid), 201

    @app.delete('/api/events/<eid>/qualifiers/<qid>')
    def qualifiers_delete(eid, qid):
        current, err = guard()
        if err:
            return err
        if not row(db, 'events', eid, current):
            return jsonify(error=_t('er_077', locale_now())), 404
        with db() as c:
            c.execute('DELETE FROM qualifiers WHERE id=? AND event_id=?', (qid, eid))
        return jsonify(ok=True)

    @app.post('/api/events/<eid>/capture')
    def events_capture(eid):
        current, err = guard()
        if err:
            return err
        event = row(db, 'events', eid, current)
        if not event:
            return jsonify(error=_t('er_077', locale_now())), 404
        body = request.get_json(silent=True) or {}
        name = str(body.get('name', '')).strip()
        if not name:
            return jsonify(error=_t('er_012', locale_now())), 400
        email = str(body.get('email', '')).strip().lower()
        if email and not EMAIL_RE.fullmatch(email):
            return jsonify(error=_t('er_045', locale_now())), 400
        from web.app import add_lead
        owner_col = None if current == 'owner' else current
        value = {'name': name[:200], 'category': str(body.get('category', ''))[:100],
                 'city': str(body.get('city', ''))[:200] or (event.get('location') or '')[:200],
                 'address': str(body.get('address', ''))[:500],
                 'phone': str(body.get('phone', ''))[:100], 'email': email[:250],
                 'website': str(body.get('website', ''))[:1000], 'source': f'Event: {event["name"]}'[:120],
                 'owner_user_id': owner_col,
                 'source_key': f'event:{eid}:' + (email or hashlib.sha256(
                     (name + str(body.get('phone', ''))).encode()).hexdigest()[:16])}
        key = value['source_key']
        with db() as c:
            found = c.execute('SELECT id FROM leads WHERE source_key=?', (key,)).fetchone()
        lid = found['id'] if found else None
        if not lid:
            add_lead(value)
            with db() as c:
                lid = c.execute('SELECT id FROM leads WHERE source_key=?', (key,)).fetchone()['id']
        answers = body.get('answers') or {}
        if not isinstance(answers, dict):
            return jsonify(error=_t('nw.e_qual', locale_now())), 400
        with db() as c:
            quals = {r['id']: dict(r) for r in c.execute(
                'SELECT * FROM qualifiers WHERE event_id=?', (eid,))}
            clean = {}
            for qid, val in list(answers.items())[:20]:
                spec = quals.get(qid)
                if not spec:
                    continue
                text = str(val)[:500]
                if spec['kind'] == 'choice':
                    try:
                        allowed = json.loads(spec['options'] or '[]')
                    except Exception:
                        allowed = []
                    if text not in allowed:
                        continue
                clean[qid] = text
            scan_id = str(body.get('scan_id') or '')
            if scan_id:
                scan = c.execute('SELECT id FROM scans WHERE id=? AND owner=?',
                                 (scan_id, current)).fetchone()
                if not scan:
                    scan_id = ''
                else:
                    c.execute('UPDATE scans SET lead_id=? WHERE id=?', (lid, scan_id))
            c.execute('INSERT OR IGNORE INTO event_leads VALUES(?,?,?,?,?)',
                      (eid, lid, json.dumps(clean), scan_id or None, now()))
            captured = c.execute('SELECT count(*) FROM event_leads WHERE event_id=?', (eid,)).fetchone()[0]
        with db() as c:
            lead = dict(c.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone())
        try:
            dispatch(db, now, log, current, 'lead.created',
                     {'lead_id': lid, 'event_id': eid, 'name': lead['name'], 'email': lead['email']})
        except Exception:
            pass
        return jsonify(ok=True, lead_id=lid, lead=lead, captured=captured,
                       goal=event.get('goal') or 0), 201

    @app.get('/api/events/<eid>/stats')
    def events_stats(eid):
        current, err = guard()
        if err:
            return err
        event = row(db, 'events', eid, current)
        if not event:
            return jsonify(error=_t('er_077', locale_now())), 404
        with db() as c:
            stages = {r['stage']: r['n'] for r in c.execute(
                'SELECT l.stage AS stage,count(*) AS n FROM leads l '
                'JOIN event_leads el ON el.lead_id=l.id WHERE el.event_id=? GROUP BY l.stage', (eid,))}
            captured = c.execute('SELECT count(*) FROM event_leads WHERE event_id=?', (eid,)).fetchone()[0]
            answered = c.execute(
                'SELECT count(DISTINCT el.lead_id) FROM event_leads el '
                'JOIN review_links rl ON rl.lead_id=el.lead_id WHERE el.event_id=? AND rl.status=?',
                (eid, 'answered')).fetchone()[0]
        revenue = None
        if tier_ok('pro'):
            with db() as c:
                contracts = {r['currency']: r['n'] for r in c.execute(
                    'SELECT currency,sum(amount_minor) AS n FROM contracts c '
                    'JOIN event_leads el ON el.lead_id=c.lead_id WHERE el.event_id=? GROUP BY currency', (eid,))}
                invoices = {r['currency']: r['n'] for r in c.execute(
                    'SELECT currency,sum(total_minor) AS n FROM invoices i '
                    'JOIN event_leads el ON el.lead_id=i.lead_id '
                    "WHERE el.event_id=? AND i.status='Paid' GROUP BY currency", (eid,))}
            revenue = {'contracts': contracts, 'paid_invoices': invoices}
        return jsonify(event={'id': eid, 'name': event['name'], 'goal': event.get('goal') or 0},
                       captured=captured, stages=stages, answered=answered,
                       revenue=revenue, revenue_required=None if revenue is not None else 'pro')

    # -- paper-card scanner ------------------------------------------------- #
    @app.post('/api/scans')
    def scans_upload():
        current, err = guard()
        if err:
            return err
        file = request.files.get('photo')
        if not file or not file.filename:
            return jsonify(error=_t('nw.e_photo', locale_now())), 400
        ext = os.path.splitext(file.filename.lower())[1]
        if ext not in SCAN_EXTS:
            return jsonify(error=_t('nw.e_photo', locale_now())), 400
        blob = file.read()
        if not blob or len(blob) > SCAN_MAX_BYTES:
            return jsonify(error=_t('nw.e_photo_big', locale_now())), 400
        if ext == '.jpg' and not blob.startswith(b'\xff\xd8'):
            return jsonify(error=_t('nw.e_photo', locale_now())), 400
        if ext == '.png' and not blob.startswith(b'\x89PNG'):
            return jsonify(error=_t('nw.e_photo', locale_now())), 400
        sid, filename = uuid.uuid4().hex, uuid.uuid4().hex + ext
        with open(os.path.join(UPLOAD_DIR, filename), 'wb') as handle:
            handle.write(blob)
        with db() as c:
            c.execute('INSERT INTO scans VALUES(?,?,?,?,?,?)',
                      (sid, current, None, filename, '', now()))
        return jsonify(ok=True, id=sid), 201

    @app.get('/api/scans/<sid>/photo')
    def scans_photo(sid):
        current, err = guard()
        if err:
            return err
        scan = row(db, 'scans', sid, current)
        if not scan:
            return jsonify(error=_t('er_077', locale_now())), 404
        path = os.path.join(UPLOAD_DIR, os.path.basename(scan['filename'] or ''))
        if not os.path.exists(path):
            return jsonify(error=_t('er_077', locale_now())), 404
        ext = os.path.splitext(path)[1]
        return send_file(path, mimetype=SCAN_EXTS.get(ext, 'application/octet-stream'))

    @app.post('/api/scans/<sid>/extract')
    def scans_extract(sid):
        current, err = guard()
        if err:
            return err
        scan = row(db, 'scans', sid, current)
        if not scan:
            return jsonify(error=_t('er_077', locale_now())), 404
        path = os.path.join(UPLOAD_DIR, os.path.basename(scan['filename'] or ''))
        if not os.path.exists(path):
            return jsonify(error=_t('er_077', locale_now())), 404
        from web.ai_provider import resolve_provider, ProviderUnavailable
        try:
            provider, _key, model, base = resolve_provider()
        except ProviderUnavailable as exc:
            return jsonify(ok=True, available=False, reason=str(exc))
        if provider != 'ollama':
            return jsonify(ok=True, available=False,
                           reason=_t('nw.e_vision_provider', locale_now(), p=provider))
        try:
            import requests
        except ImportError:
            return jsonify(ok=True, available=False, reason='requests is not installed.')
        with open(path, 'rb') as handle:
            image_b64 = base64.b64encode(handle.read()).decode()
        prompt = ('Read this business-card photo. Reply with JSON only: '
                  '{"name":"","role":"","org":"","phone":"","email":"","website":""}. '
                  'Empty string for anything not clearly visible. Never guess.')
        try:
            timeout = float(os.getenv('CREW_LLM_TIMEOUT', '25') or 25)
            response = requests.post(
                base + '/api/chat', timeout=timeout + 35,
                json={'model': model, 'stream': False, 'format': 'json',
                      'messages': [{'role': 'user', 'content': prompt, 'images': [image_b64]}]})
            response.raise_for_status()
            text = (response.json().get('message') or {}).get('content', '')
            data = json.loads(text)
            if not isinstance(data, dict):
                raise ValueError('bad shape')
            suggestions = {k: str(data.get(k, ''))[:250] for k in
                           ('name', 'role', 'org', 'phone', 'email', 'website')}
        except Exception as exc:
            return jsonify(ok=True, available=False,
                           reason=_t('nw.e_vision_failed', locale_now(),
                                     d=f'{type(exc).__name__}: {exc}'[:160]))
        with db() as c:
            c.execute('UPDATE scans SET extracted=? WHERE id=?', (json.dumps(suggestions), sid))
        return jsonify(ok=True, available=True, suggestions=suggestions,
                       provider=provider, model=model)

    # -- instant follow-up -------------------------------------------------- #
    @app.post('/api/leads/<lid>/followup')
    def leads_followup(lid):
        current, err = guard()
        if err:
            return err
        denied = need_tier('pro')
        if denied:
            return denied
        from web.app import lead as fetch_lead
        try:
            lead = fetch_lead(lid)
        except Exception:
            return jsonify(error=_t('er_077', locale_now())), 404
        if current != 'owner' and lead.get('owner_user_id') != current:
            return jsonify(error=_t('er_022', locale_now())), 403
        body = request.get_json(silent=True) or {}
        if not body.get('approved') or not body.get('basis'):
            return jsonify(error=_t('er_028', locale_now())), 400
        loc = locale_now()
        event_name = ''
        with db() as c:
            r = c.execute('SELECT e.name FROM events e JOIN event_leads el ON el.event_id=e.id '
                          'WHERE el.lead_id=? ORDER BY el.created DESC LIMIT 1', (lid,)).fetchone()
            if r:
                event_name = r['name']
        subject = _t('oc.f_sub', loc, n=lead['name'])
        text = _t('oc.f_body', loc, n=lead['name'],
                  e=event_name or _t('oc.f_noevent', loc),
                  w=settings().get('sender_name') or _t('oc.who', loc),
                  a=settings().get('agency') or _t('oc.ag', loc))
        from web.crew_mail import send_email
        result = send_email(db, now, log, lead, subject, text, settings(), run_id='followup')
        if not result.get('ok'):
            return jsonify(error=result.get('detail') or _t('er_002', locale_now())), 502
        return jsonify(ok=True, state=result.get('state'))

    # -- booking ------------------------------------------------------------ #
    def booking_token_for(owner_uid):
        if owner_uid == 'owner':
            data = settings()
            token = (data.get('booking_token') or '').strip()
            if not token:
                token = secrets.token_urlsafe(10)
                data['booking_token'] = token
                with db() as c:
                    c.execute('INSERT OR REPLACE INTO settings VALUES(1,?)', (json.dumps(data),))
            return token
        with db() as c:
            r = c.execute('SELECT booking_token FROM users WHERE id=?', (owner_uid,)).fetchone()
            token = (r['booking_token'] if r else '') or ''
            if not token:
                token = secrets.token_urlsafe(10)
                c.execute('UPDATE users SET booking_token=? WHERE id=?', (token, owner_uid))
            return token

    @app.get('/api/booking/availability')
    def booking_windows():
        current, err = guard()
        if err:
            return err
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT * FROM availability WHERE owner=? ORDER BY weekday,start', (current,))]
        return jsonify(windows=rows, book_url=f'/book/{booking_token_for(current)}')

    @app.post('/api/booking/availability')
    def booking_windows_save():
        current, err = guard()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        windows = body.get('windows')
        if not isinstance(windows, list) or len(windows) > 21:
            return jsonify(error=_t('nw.e_windows', locale_now())), 400
        clean = []
        for window in windows:
            try:
                weekday = int(window.get('weekday'))
                start = str(window.get('start', ''))
                end = str(window.get('end', ''))
                datetime.strptime(start, '%H:%M')
                datetime.strptime(end, '%H:%M')
                assert 0 <= weekday <= 6 and start < end
            except Exception:
                return jsonify(error=_t('nw.e_windows', locale_now())), 400
            clean.append((uuid.uuid4().hex, current, weekday, start, end))
        with db() as c:
            c.execute('DELETE FROM availability WHERE owner=?', (current,))
            c.executemany('INSERT INTO availability VALUES(?,?,?,?,?)', clean)
        return jsonify(ok=True, book_url=f'/book/{booking_token_for(current)}')

    @app.get('/api/bookings')
    def bookings_list():
        current, err = guard()
        if err:
            return err
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT * FROM bookings WHERE owner=? ORDER BY slot_start DESC LIMIT 200', (current,))]
        return jsonify(bookings=rows)

    @app.post('/api/bookings/<bid>/status')
    def bookings_status(bid):
        current, err = guard()
        if err:
            return err
        body = request.get_json(silent=True) or {}
        if str(body.get('status')) not in ('confirmed', 'cancelled'):
            return jsonify(error=_t('er_116', locale_now())), 400
        with db() as c:
            cur = c.execute('UPDATE bookings SET status=? WHERE id=? AND owner=?',
                            (body['status'], bid, current))
        if not cur.rowcount:
            return jsonify(error=_t('er_077', locale_now())), 404
        return jsonify(ok=True)

    @app.get('/book/<token>')
    def booking_page(token):
        with db() as c:
            r = c.execute('SELECT id FROM users WHERE booking_token=?', (token,)).fetchone()
            owner_uid = r['id'] if r else ('owner' if (settings().get('booking_token') or '') == token else '')
        if not owner_uid or not token:
            abort(404)
        with db() as c:
            windows = [dict(x) for x in c.execute('SELECT * FROM availability WHERE owner=?', (owner_uid,))]
            booked = [dict(x) for x in c.execute(
                'SELECT slot_start,slot_end,status FROM bookings WHERE owner=? AND slot_start>=?',
                (owner_uid, datetime.now().isoformat(timespec='minutes')))]
        studio = (settings().get('agency') or 'Reachmark').strip()
        return render_template('booking.html', studio=studio, token=token,
                               slots=open_slots(windows, booked))

    @app.post('/api/book/<token>')
    def booking_submit(token):
        with db() as c:
            r = c.execute('SELECT id FROM users WHERE booking_token=?', (token,)).fetchone()
            owner_uid = r['id'] if r else ('owner' if (settings().get('booking_token') or '') == token else '')
        if not owner_uid or not token:
            return jsonify(error=_t('er_077', locale_now())), 404
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error=_t('er_109', locale_now())), 400
        if body.get('company_url'):
            return jsonify(error=_t('nw.e_trap', locale_now())), 400
        name = str(body.get('name', '')).strip()
        email = str(body.get('email', '')).strip().lower()
        slot = str(body.get('slot_start', ''))
        if len(name) < 2 or not EMAIL_RE.fullmatch(email or ''):
            return jsonify(error=_t('nw.e_book_fields', locale_now())), 400
        ip_hash = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()[:32]
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with db() as c:
            windows = [dict(x) for x in c.execute('SELECT * FROM availability WHERE owner=?', (owner_uid,))]
            booked = [dict(x) for x in c.execute(
                'SELECT slot_start,slot_end,status FROM bookings WHERE owner=? AND slot_start>=?',
                (owner_uid, datetime.now().isoformat(timespec='minutes')))]
            recent = c.execute('SELECT count(*) FROM bookings WHERE ip_hash=? AND created>?',
                               (ip_hash, cutoff)).fetchone()[0]
        if recent >= 5:
            return jsonify(error=_t('nw.e_book_many', locale_now())), 429
        match = next((s for s in open_slots(windows, booked) if s['start'] == slot), None)
        if not match:
            return jsonify(error=_t('nw.e_slot', locale_now())), 409
        bid, stamp = uuid.uuid4().hex, now()
        with db() as c:
            try:
                c.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (bid, owner_uid, match['start'], match['end'], name[:120], email[:250],
                           str(body.get('note', ''))[:1000], 'booked', secrets.token_urlsafe(10),
                           ip_hash, stamp))
            except sqlite3.IntegrityError:
                return jsonify(error=_t('nw.e_slot', locale_now())), 409
            booking = dict(c.execute('SELECT * FROM bookings WHERE id=?', (bid,)).fetchone())
        try:
            from web.accounts import get_base_url, send_branded
            _base = get_base_url()
            _bloc = locale_now()
            _studio = (settings().get('agency') or 'Reachmark').strip()
            _slot = f"{match['start'].replace('T', ' ')} – {match['end'].replace('T', ' ')}"
            _ics = f"{_base}/api/bookings/{booking['token']}.ics"
            send_branded(email, _t('nw.m_bk_sub', _bloc, studio=_studio),
                         _t('nw.m_bk_body', _bloc, slot=_slot, studio=_studio),
                         html_title=_t('nw.m_bk_title', _bloc), cta_url=_ics,
                         cta_label=_t('nw.m_bk_cta', _bloc), db=db)
            _owner_email = ''
            if owner_uid == 'owner':
                _owner_email = (settings().get('reply_email') or '').strip()
            else:
                with db() as c:
                    _r = c.execute('SELECT email FROM users WHERE id=?', (owner_uid,)).fetchone()
                    _owner_email = (_r['email'] if _r else '') or ''
            if _owner_email and '@' in _owner_email:
                send_branded(_owner_email, _t('nw.m_bko_sub', _bloc, name=name, slot=_slot),
                             _t('nw.m_bko_body', _bloc, name=name, email=email, slot=_slot),
                             html_title=_t('nw.m_bko_title', _bloc), cta_url=f'{_base}/workspace',
                             cta_label=_t('nw.m_bko_cta', _bloc), db=db)
        except Exception:
            pass
        try:
            dispatch(db, now, log, owner_uid, 'booking.created',
                     {'booking_id': bid, 'slot_start': match['start'], 'name': name, 'email': email})
        except Exception:
            pass
        return jsonify(ok=True, booking=booking, ics=f'/api/bookings/{booking["token"]}.ics'), 201

    @app.get('/api/bookings/<token>.ics')
    def booking_ics(token):
        with db() as c:
            r = c.execute('SELECT * FROM bookings WHERE token=?', (token,)).fetchone()
        if not r:
            abort(404)
        studio = (settings().get('agency') or 'Reachmark').strip()
        return Response(ics_text(dict(r), studio), mimetype='text/calendar',
                        headers={'Content-Disposition': 'attachment; filename="meeting.ics"'})

    # -- webhooks ----------------------------------------------------------- #
    @app.get('/api/webhooks')
    def webhooks_list():
        current, err = guard()
        if err:
            return err
        with db() as c:
            rows = [dict(r) for r in c.execute(
                'SELECT id,url,events,active,created FROM webhooks WHERE owner=? ORDER BY created', (current,))]
        return jsonify(webhooks=rows, events=list(HOOK_EVENTS))

    @app.post('/api/webhooks')
    def webhooks_add():
        current, err = guard()
        if err:
            return err
        denied = need_tier('pro')
        if denied:
            return denied
        body = request.get_json(silent=True) or {}
        url = str(body.get('url', '')).strip()
        events = body.get('events') or []
        host = re.sub(r'^https?://', '', url).split('/')[0].split(':')[0].lower()
        local = host in ('localhost', '127.0.0.1')
        if not re.match(r'https?://', url) or len(url) > 500 \
                or (url.startswith('http://') and not local) \
                or not isinstance(events, list) or not events \
                or any(e not in HOOK_EVENTS for e in events):
            return jsonify(error=_t('nw.e_hook', locale_now())), 400
        wid, stamp = uuid.uuid4().hex, now()
        with db() as c:
            c.execute('INSERT INTO webhooks VALUES(?,?,?,?,?,?,?,?)',
                      (wid, current, url, secrets.token_urlsafe(24),
                       json.dumps(sorted(set(events))), 1, stamp, stamp))
        return jsonify(ok=True, id=wid), 201

    @app.delete('/api/webhooks/<wid>')
    def webhooks_delete(wid):
        current, err = guard()
        if err:
            return err
        with db() as c:
            cur = c.execute('DELETE FROM webhooks WHERE id=? AND owner=?', (wid, current))
        if not cur.rowcount:
            return jsonify(error=_t('er_077', locale_now())), 404
        return jsonify(ok=True)

    return {'dispatch': dispatch, 'qr_png_bytes': qr_png_bytes, 'open_slots': open_slots}
