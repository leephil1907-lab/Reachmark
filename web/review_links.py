"""Quick review links — the concept page a business is asked to answer.

The Builder agent creates one un-guessable link per business. The page shows the
concept and asks three plain questions:

    Yes — build my website   ·   Not right now   ·   I already have a website

Views, first/last view and the answer are recorded, the owner's console shows them,
and a reply that leaves an e-mail address also lands in the normal enquiry inbox.
Nothing here publishes anything under the business's name: the page is labelled an
independent concept prepared by the studio, and it is ``noindex`` and un-linked.
"""
import hashlib, json, re, secrets, uuid
from datetime import datetime, timezone, timedelta
from web.i18n import t, locale_now

RESPONSES = {'want': 'Yes — build my website', 'later': 'Not right now', 'have': 'I already have a website'}
EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')


def _build_site_for(db, lead, link):
    """Build the business-specific one-page website spec for the review page.

    Uses the newest measured audit (for the harvested brand) when one exists, and
    always falls back to a complete, renderable spec so the page never breaks.
    """
    audit = None
    try:
        from agents.agent_auditor import latest_audit, ensure_tables as ensure_audit_tables
        ensure_audit_tables(db)
        audit = latest_audit(db, lead.get('id'))
    except Exception:
        audit = None
    try:
        from web.sitegen import build_site
        site = build_site(lead, audit, locale=locale_now())
        if site:
            return site
    except Exception:
        pass
    # Deterministic fallback: still a real, themed page built from saved fields.
    from web.concept import detect_archetype, concept_copy, build_theme
    arch = detect_archetype(lead.get('category') or lead.get('name'))
    concept = link.get('concept') or {}
    return {'archetype': arch, 'theme': build_theme(arch, {}),
            'copy': concept_copy(arch, locale_now()), 'brandmark': '',
            'brandmark_generated': False, 'images': [],
            'facts': concept.get('facts') or [], 'profile': {}, 'generated': False}


def ensure_tables(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS review_links(
            id TEXT PRIMARY KEY, token TEXT UNIQUE, lead_id TEXT, run_id TEXT, theme TEXT,
            headline TEXT, intro TEXT, sections TEXT, concept TEXT, share_message TEXT,
            chat_message TEXT,
            status TEXT DEFAULT 'ready', views INTEGER DEFAULT 0, first_view TEXT, last_view TEXT,
            created TEXT, updated TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS review_responses(
            id TEXT PRIMARY KEY, link_id TEXT, lead_id TEXT, choice TEXT, note TEXT, name TEXT,
            email TEXT, fingerprint TEXT, handled INTEGER DEFAULT 0, rating INTEGER, created TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS review_links_lead ON review_links(lead_id, created)')
        c.execute('CREATE INDEX IF NOT EXISTS review_responses_link ON review_responses(link_id, created)')


def create_link(db, now, lead, concept, share_message, run_id='', chat_message=''):
    ensure_tables(db)
    token = secrets.token_urlsafe(18)
    link_id = uuid.uuid4().hex
    stamp = now()
    with db() as c:
        # One live link per business: a re-build refreshes the newest one instead of piling up tokens.
        old = c.execute("SELECT id FROM review_links WHERE lead_id=? AND status='ready' ORDER BY created DESC", (lead['id'],)).fetchall()
        for row in old[1:]:
            c.execute("UPDATE review_links SET status='superseded',updated=? WHERE id=?", (stamp, row['id']))
        c.execute('INSERT INTO review_links(id,token,lead_id,run_id,theme,headline,intro,sections,concept,share_message,'
                  'chat_message,status,views,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (link_id, token, lead['id'], run_id, concept.get('theme', 'charcoal'), concept.get('headline', ''),
                   concept.get('intro', ''), json.dumps(concept.get('sections', [])), json.dumps(concept)[:40000],
                   share_message[:2000], chat_message[:600], 'ready', 0, stamp, stamp))
    return get_link(db, link_id=link_id)


def get_link(db, token=None, link_id=None):
    ensure_tables(db)
    with db() as c:
        row = c.execute('SELECT * FROM review_links WHERE ' + ('token=?' if token else 'id=?'),
                        (token or link_id,)).fetchone()
    if not row:
        return None
    link = dict(row)
    for key, fallback in (('sections', []), ('concept', {})):
        try:
            link[key] = json.loads(link[key]) if link.get(key) else fallback
        except (ValueError, TypeError):
            link[key] = fallback
    return link


def record_view(db, now, token, count=True):
    """Record an open. `count=False` only refreshes the last-view stamp when a tab returns."""
    ensure_tables(db)
    stamp = now()
    with db() as c:
        row = c.execute('SELECT id,views,first_view FROM review_links WHERE token=?', (token,)).fetchone()
        if not row:
            return None
        if count:
            c.execute('UPDATE review_links SET views=views+1,first_view=COALESCE(first_view,?),last_view=?,updated=? WHERE id=?',
                      (stamp, stamp, stamp, row['id']))
        else:
            c.execute('UPDATE review_links SET last_view=?,updated=? WHERE id=?', (stamp, stamp, row['id']))
    return token


def record_response(db, now, token, payload, fingerprint=''):
    """Validate and store the business's answer. Returns (response, link) or raises ValueError."""
    ensure_tables(db)
    link = get_link(db, token=token)
    if not link:
        raise ValueError(t('er_140', locale_now()))
    choice = str(payload.get('choice', '')).strip()
    if choice not in RESPONSES:
        raise ValueError(t('er_021', locale_now()))
    label = t('rv.' + choice, locale_now())
    note = str(payload.get('note', ''))[:1200].strip()
    name = str(payload.get('name', ''))[:120].strip()
    email = str(payload.get('email', '')).strip().lower()
    if email and not EMAIL_RE.fullmatch(email):
        raise ValueError(t('er_120', locale_now()))
    try:
        rating = int(payload.get('rating') or 0)
    except (TypeError, ValueError):
        rating = 0
    rating = rating if 1 <= rating <= 5 else None
    stamp = now()
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        recent = c.execute('SELECT count(*) FROM review_responses WHERE fingerprint=? AND created>?',
                           (fingerprint, cutoff)).fetchone()[0]
        if recent >= 5:
            raise ValueError(t('er_142', locale_now()))
        response_id = uuid.uuid4().hex
        c.execute('INSERT INTO review_responses(id,link_id,lead_id,choice,note,name,email,fingerprint,rating,created) '
                  'VALUES(?,?,?,?,?,?,?,?,?,?)',
                  (response_id, link['id'], link['lead_id'], choice, note, name, email, fingerprint, rating, stamp))
        c.execute("UPDATE review_links SET status='answered',updated=? WHERE id=?", (stamp, link['id']))
        lead = c.execute('SELECT * FROM leads WHERE id=?', (link['lead_id'],)).fetchone()
        if lead:
            stage = 'Won' if choice == 'want' else ('Contacted' if choice == 'later' else 'Not a fit')
            summary = label + (f' — “{note}”' if note else '')
            c.execute('UPDATE leads SET stage=?,note=TRIM(COALESCE(note,"")||?),updated=? WHERE id=?',
                      (stage, f'\n[Review link] {summary[:400]}', stamp, lead['id']))
        if email:
            # A real, addressable reply belongs in the normal enquiry inbox as well.
            enquiry_id = uuid.uuid4().hex
            message = (f'Replied through the review link for {lead["name"] if lead else "a business"}.\n\n'
                       f'Answer: {label}\n'
                       f'Message: {note or "—"}\n'
                       f'Link: /r/{link["token"]}')
            c.execute('INSERT INTO enquiries(id,name,email,business,kind,budget,timeline,message,sample,fingerprint,status,notes,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (enquiry_id, name or (lead['name'] if lead else 'Review link visitor'), email,
                       (lead['name'] if lead else ''),
                       'Review link reply', '', '', message[:5000], '', fingerprint, 'New', '', stamp, stamp))
    return {'id': response_id, 'choice': choice, 'label': label, 'note': note, 'created': stamp}, link


def _session_owner():
    try:
        from flask import session
        if session.get('client_id') and session.get('role') == 'client' and not session.get('owner'):
            return session.get('client_id')
    except Exception:
        return None
    return None


def responses_for(db, link_id=None, limit=50, owner=None):
    if owner is None:
        owner = _session_owner()
    query = 'SELECT r.*, l.name AS lead_name, l.city AS lead_city FROM review_responses r ' \
            'LEFT JOIN leads l ON l.id=r.lead_id'
    args = ()
    conds = []
    if link_id:
        conds.append('r.link_id=?')
        args += (link_id,)
    if owner:
        conds.append('l.owner_user_id=?')
        args += (owner,)
    if conds:
        query += ' WHERE ' + ' AND '.join(conds)
    with db() as c:
        return [dict(row) for row in c.execute(query + ' ORDER BY r.created DESC LIMIT ?', args + (limit,))]


def link_overview(db, limit=40, owner=None):
    """Console view: every review link, its views and its answer."""
    if owner is None:
        owner = _session_owner()
    ensure_tables(db)
    where = 'WHERE b.owner_user_id=? ' if owner else ''
    args = (owner, limit) if owner else (limit,)
    with db() as c:
        rows = [dict(r) for r in c.execute(
            'SELECT l.id,l.token,l.lead_id,l.status,l.views,l.first_view,l.last_view,l.created,l.headline,'
            'l.share_message,l.chat_message,b.name AS business,b.city,l.lead_id,'
            '(SELECT choice FROM review_responses r WHERE r.link_id=l.id ORDER BY r.created DESC LIMIT 1) AS last_choice,'
            '(SELECT rating FROM review_responses r WHERE r.link_id=l.id ORDER BY r.created DESC LIMIT 1) AS last_rating,'
            '(SELECT count(*) FROM review_responses r WHERE r.link_id=l.id) AS response_count '
            'FROM review_links l LEFT JOIN leads b ON b.id=l.lead_id ' + where + 'ORDER BY l.created DESC LIMIT ?', args)]
    answered = sum(1 for row in rows if row['last_choice'])
    opened = sum(1 for row in rows if (row['views'] or 0) > 0)
    return {'links': rows, 'total': len(rows), 'opened': opened, 'answered': answered}


def register_review_links(app, db, now, log, settings):
    from flask import request, jsonify, render_template, abort, session, make_response
    ensure_tables(db)

    @app.route('/ads/<token>')
    def ad_stage(token):
        """The recording stage for the Brag video: the real page, framed, with overlays.

        Same privacy model as /r/<token> — unguessable token, public to whoever holds it,
        noindex, and it only ever shows saved business fields.
        """
        link = get_link(db, token=token)
        if not link:
            return jsonify(error=t('er_119', locale_now())), 404
        concept = link.get('concept') or {}
        from agents.agent_video import build_script, lead_for, DEFAULT_SECONDS
        lead = lead_for(db, link) or {'name': 'this business'}
        fmt = 'tall' if (request.args.get('fmt') or '').lower() in ('tall', 'portrait', '9:16') else 'wide'
        seconds = max(8, min(int(request.args.get('seconds') or DEFAULT_SECONDS.get(fmt, 18)), 60))
        script = build_script(lead, concept, link, settings(), seconds=seconds)
        response = make_response(render_template('ad-stage.html', token=token, fmt=fmt,
                                                business=script['business'], studio=script['studio'],
                                                category=lead.get('category') or t('ad_cat', locale_now()),
                                                place=script['place'],
                                                problem_facts=[str(f) for f in script['beats'][0]['facts']][:4],
                                                closing_facts=script['beats'][-1]['facts'],
                                                captions=script['beats'], end_note=script['end_note'],
                                                seconds=seconds))
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    @app.route('/r/<token>')
    def review_page(token):
        link = get_link(db, token=token)
        if not link or link['status'] == 'superseded':
            abort(404)
        with db() as c:
            lead = c.execute('SELECT * FROM leads WHERE id=?', (link['lead_id'],)).fetchone()
        if not lead:
            abort(404)
        record_view(db, now, token)
        studio = (settings().get('agency') or 'Reachmark').strip()
        reply_email = (settings().get('reply_email') or '').strip()
        base = (settings().get('public_base_url') or '').rstrip('/')
        log('review', 'A review link was opened')
        lead = dict(lead)
        # The link the business opens IS the finished one-page website, dressed in
        # their own trade palette (or their observed brand) and written from their
        # own saved fields. The single question is integrated into that page.
        site = _build_site_for(db, lead, link)
        digits = re.sub(r'\D', '', lead.get('phone') or '')
        wa = digits if len(digits) >= 7 else ''
        return render_template('review.html', link=link, lead=lead, studio=studio,
                              reply_email=reply_email, base=base, responses=RESPONSES,
                              site=site, wa=wa)

    @app.get('/r/<token>/answer/<choice>')
    def review_answer(token, choice):
        """One-tap answer from the branded e-mail.

        The business taps a button in the e-mail and lands here: the answer is
        recorded exactly like the in-page form, the owner is e-mailed straight away,
        and the business sees a small, branded thank-you page. No question is ever
        shown on the website itself \u2014 this is only the landing for the e-mail link.
        """
        link = get_link(db, token=token)
        if not link or link['status'] == 'superseded':
            abort(404)
        if choice not in RESPONSES:
            abort(404)
        with db() as c:
            lead_row = c.execute('SELECT * FROM leads WHERE id=?', (link['lead_id'],)).fetchone()
        if not lead_row:
            abort(404)
        lead = dict(lead_row)
        fingerprint = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()[:32]
        try:
            response, link = record_response(db, now, token, {'choice': choice}, fingerprint)
        except ValueError as exc:
            return render_template('error.html', message=str(exc)), 400
        log('review', f"Review link answered by e-mail tap: {response['label']}")
        # The owner hears about it as an e-mail, immediately.
        try:
            from web.outreach_email import notify_owner_of_response
            notify_owner_of_response(db, now, log, link, response, settings(), lead=lead)
        except Exception:
            pass
        try:
            from web.network import dispatch
            dispatch(db, now, log, lead.get('owner_user_id') or 'owner', 'response.received',
                     {'link_id': link.get('id'), 'choice': response['choice'], 'label': response['label']})
        except Exception:
            pass
        studio = (settings().get('agency') or 'Reachmark').strip()
        return render_template('review-answer.html', link=link, lead=lead, response=response,
                              studio=studio, locale=locale_now())

    @app.post('/api/r/<token>/respond')
    def review_respond(token):
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(error=t('er_109', locale_now())), 400
        fingerprint = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()[:32]
        try:
            response, link = record_response(db, now, token, payload, fingerprint)
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        log('review', f"Review link answered: {response['label']}")
        try:
            from web.outreach_email import notify_owner_of_response
            with db() as c:
                lead_row = c.execute('SELECT * FROM leads WHERE id=?', (link.get('lead_id'),)).fetchone()
            notify_owner_of_response(db, now, log, link, response, settings(),
                                     lead=dict(lead_row) if lead_row else None)
        except Exception:
            pass
        try:
            from web.network import dispatch
            with db() as c:
                lead = c.execute('SELECT owner_user_id FROM leads WHERE id=?',
                                 (link.get('lead_id'),)).fetchone()
            dispatch(db, now, log, (lead['owner_user_id'] if lead else None) or 'owner',
                     'response.received',
                     {'link_id': link.get('id'), 'choice': response['choice'],
                      'label': response['label']})
        except Exception:
            pass
        return jsonify(ok=True, response=response), 201

    @app.post('/api/r/<token>/seen')
    def review_seen(token):
        """Refresh the last-view stamp without inflating the view count."""
        record_view(db, now, token, count=False)
        return jsonify(ok=True)

    @app.get('/api/review-links')
    def review_link_list():
        if session.get('client_id') and not session.get('owner'):
            from web.billing import tier_status
            with db() as c:
                row = c.execute('SELECT * FROM users WHERE id=?', (session.get('client_id'),)).fetchone()
            tier, active, _ = tier_status(dict(row) if row else None)
            if tier != 'pro' or not active:
                return jsonify(error=t('er_124', locale_now()), upgrade='/pricing', required='pro'), 402
        return jsonify(links=link_overview(db), responses=responses_for(db))

    @app.post('/api/review-links/<link_id>/handled')
    def review_mark_handled(link_id):
        with db() as c:
            c.execute('UPDATE review_responses SET handled=1 WHERE id=?', (link_id,))
        return jsonify(ok=True)

    return {'create_link': create_link, 'get_link': get_link, 'record_view': record_view,
            'record_response': record_response, 'link_overview': link_overview}
