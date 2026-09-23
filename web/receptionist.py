"""The AI receptionist — the front desk on the public pages.

It answers visitors and business owners using a **facts-only knowledge base**
(``knowledge/reachmark.md``) plus saved records. It is deliberately narrow:

* it never invents a price, a deadline, a guarantee, a client or a statistic;
* when it is not confident it says so and hands the conversation to the owner;
* when a visitor shares an e-mail address it creates a real enquiry in the normal
  inbox and a lead record — the conversation turns into work, not a dead end;
* when someone asks about a website for their own business it can offer the
  review-link route straight away (that is the whole funnel in one message).

Everything is stored (threads + messages) so the owner can read and continue the
conversation. The widget is a small, dependency-free script, and the endpoint is
rate-limited per connection.
"""
import hashlib, json, os, re, secrets, uuid
from datetime import datetime, timezone, timedelta

# Knowledge engine + brand facts live in the shared brain; re-exported here so the
# chat API, the crew and the tests keep one import path each.
from crew.business import (BRAIN_VERSION, KB_PATH, MIN_SCORE, STOPWORDS, detect_intent, load_knowledge,
                           match_answer, public as brand_public)
from web.i18n import t as _t


def _loc():
    """Visitor locale inside a request, plain English outside one (tests, crew)."""
    try:
        from flask import has_app_context, g as _g
        return _g.get('locale', 'en') if has_app_context() else 'en'
    except Exception:
        return 'en'

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')
PHONE_RE = re.compile(r'(?:\+?\d[\d\s().\-]{7,}\d)')

HANDOFF_LINE = ('I do not have a verified answer for that one, so I will not guess. Leave your e-mail and the '
                'studio owner will reply personally — or use the enquiry form at /enquire.')
FALLBACK_TOPICS = ('pricing', 'process and timing')

REVIEW_OFFER = ('If it would help, I can have a concept page prepared for your business and send you a private '
                'review link — it takes about a minute to look at, and there is a “not right now” button.')
HUMAN_LINE = ('Of course. I have flagged this for the studio owner — they read every message themselves. '
              'Leave your e-mail address and you will get a personal reply.')


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
from web.agent_tools import (ACT_TOOLS, ToolError, owner_locked, run_tool, tool_enquiry_list,
                                 tool_invoice_list, tool_lead_list, tool_project_list, tool_stats)


def ensure_tables(db):
    with db() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS receptionist_threads(
            id TEXT PRIMARY KEY, token TEXT UNIQUE, visitor_hash TEXT, name TEXT, email TEXT, business TEXT,
            intent TEXT, status TEXT DEFAULT 'open', handoff INTEGER DEFAULT 0, source TEXT, page TEXT,
            lead_id TEXT, created TEXT, updated TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS receptionist_messages(
            id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, text TEXT, intent TEXT, meta TEXT, created TEXT)''')
        c.execute('CREATE INDEX IF NOT EXISTS receptionist_msg_thread ON receptionist_messages(thread_id, created)')


def _thread(db, now, token=None, visitor_hash='', page=''):
    ensure_tables(db)
    with db() as c:
        if token:
            row = c.execute('SELECT * FROM receptionist_threads WHERE token=?', (token,)).fetchone()
            if row:
                return dict(row)
        token = token or secrets.token_urlsafe(18)
        thread_id = uuid.uuid4().hex
        c.execute('INSERT INTO receptionist_threads(id,token,visitor_hash,intent,status,source,page,created,updated) '
                  'VALUES(?,?,?,?,?,?,?,?,?)',
                  (thread_id, token, visitor_hash, 'unknown', 'open', 'website widget', page[:200], now(), now()))
        row = c.execute('SELECT * FROM receptionist_threads WHERE id=?', (thread_id,)).fetchone()
        return dict(row)


def _store(db, now, thread_id, role, text, intent='', meta=None):
    with db() as c:
        c.execute('INSERT INTO receptionist_messages VALUES(?,?,?,?,?,?,?)',
                  (uuid.uuid4().hex, thread_id, role, (text or '')[:4000], intent, json.dumps(meta or {})[:4000], now()))
        c.execute('UPDATE receptionist_threads SET updated=? WHERE id=?', (now(), thread_id))


def transcript(db, thread_id, limit=40):
    with db() as c:
        rows = [dict(r) for r in c.execute('SELECT * FROM receptionist_messages WHERE thread_id=? ORDER BY created LIMIT ?',
                                           (thread_id, limit))]
    for row in rows:
        try:
            row['meta'] = json.loads(row['meta'] or '{}')
        except ValueError:
            row['meta'] = {}
    return rows


def threads(db, limit=40, status=None):
    query = ('SELECT t.*, (SELECT count(*) FROM receptionist_messages m WHERE m.thread_id=t.id) AS messages, '
             '(SELECT text FROM receptionist_messages m WHERE m.thread_id=t.id ORDER BY m.created DESC LIMIT 1) AS last_message '
             'FROM receptionist_threads t')
    args = ()
    if status:
        query += ' WHERE t.status=?'
        args = (status,)
    with db() as c:
        return [dict(r) for r in c.execute(query + ' ORDER BY t.updated DESC LIMIT ?', args + (limit,))]


# --------------------------------------------------------------------------- #
# The answer engine
# --------------------------------------------------------------------------- #
def _llm_phrase(ctx_settings, message, answer, intent):
    """Optional warm rephrasing that may not add a single new fact."""
    from web.ai_provider import safe_complete, provider_status
    if not provider_status()['configured']:
        return None, {'used': False, 'reason': 'no provider configured'}
    system = ('You are the front desk for a small website studio. Rephrase the approved answer below, warmly and '
              'briefly, in the visitor’s language. You must not add any fact, number, price, date, promise or claim '
              'that is not in the approved answer. Keep every figure identical. Two to four sentences. No emoji.')
    text, meta = safe_complete(system, f'VISITOR: {message}\n\nAPPROVED ANSWER: {answer}', max_tokens=260, temperature=0.4)
    if not text:
        return None, {'used': False, 'reason': meta.get('reason', 'provider unavailable')}
    approved_numbers = set(re.findall(r'\d[\d,.]*', answer))
    new_numbers = set(re.findall(r'\d[\d,.]*', text)) - approved_numbers
    bad = new_numbers or re.search(r'(?i)\b(guarantee|guaranteed|100%|cheapest|always|never fails)\b', text)
    if bad:
        return None, {'used': False, 'reason': 'model text introduced unsupported figures or claims'}
    return text, {'used': True}


def answer(db, now, message, thread_token=None, visitor_hash='', page='', settings=None, allow_llm=True,
           name='', email='', business=''):
    """Answer one visitor message. Returns a dict for the widget and stores the transcript."""
    settings = settings or (lambda: {})
    loc = _loc()
    human_line, handoff_line, review_offer = _t('rx.b_human', loc), _t('rx.b_handoff', loc), _t('rx.b_review', loc)
    message = (message or '').strip()[:2000]
    if len(message) < 2:
        return {'error': _t('rx.b_type', loc), 'ok': False}
    thread = _thread(db, now, thread_token, visitor_hash, page)
    _store(db, now, thread['id'], 'visitor', message)

    topic, question, kb_answer, score = match_answer(message)
    intent = detect_intent(message, topic, score)
    reply, actions = '', []

    if email and not thread['email']:
        email = email.lower()
    elif not email:
        found = EMAIL_RE.search(message)
        email = found.group(0).lower() if found else ''
    phone_found = PHONE_RE.search(message)
    name = (name or thread.get('name') or '').strip()
    business = (business or thread.get('business') or '').strip()

    if intent == 'human':
        reply = human_line
        actions.append('handoff')
    elif intent == 'new_project':
        reply = _t('rx.b_new', loc) + ' ' + review_offer
        actions.append('offer_review_link')
    elif intent == 'greeting':
        reply = _t('rx.b_greet', loc)
    elif score >= MIN_SCORE and kb_answer:
        reply = kb_answer
        if intent == 'pricing':
            actions.append('offer_enquiry')
        if intent in ('samples', 'timeline'):
            actions.append('offer_enquiry')
    else:
        reply = handoff_line
        actions.append('handoff')

    if allow_llm and reply not in (human_line, handoff_line):
        phrased, meta = _llm_phrase(settings, message, reply, intent)
        if phrased:
            reply = phrased
            actions.append('model_phrasing')

    # Capture: an address means real work, never a dead-end chat.
    lead_id = thread.get('lead_id') or ''
    if email and not lead_id:
        try:
            with db() as c:
                existing = c.execute('SELECT id FROM leads WHERE lower(email)=?', (email,)).fetchone()
                if not existing:
                    lid = uuid.uuid4().hex
                    c.execute('INSERT INTO leads(id,source_key,name,category,city,address,phone,email,website,status,stage,source,source_url,'
                              'token,note,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                              (lid, 'receptionist:' + email, (business or name or 'Website visitor')[:200], '',
                               '', '', (phone_found.group(0) if phone_found else ''), email, '', 'NOT_LISTED', 'Replied',
                               'Website receptionist', '', uuid.uuid4().hex,
                               f"{_t('rx.b_note', loc)} {message[:280]}", now(), now()))
                    lead_id = lid
                else:
                    lead_id = existing['id']
        except Exception:
            lead_id = ''
        enquiry_id = uuid.uuid4().hex
        with db() as c:
            c.execute('INSERT INTO enquiries(id,name,email,business,kind,budget,timeline,message,sample,fingerprint,status,notes,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (enquiry_id, (name or business or 'Website visitor')[:120], email, business[:200], 'Other enquiry',
                       '', '', (f"{_t('rx.b_from', loc)}\n\n{message[:1500]}\n\n{_t('rx.b_answ', loc)} {reply[:800]}")[:5000],
                       '', visitor_hash, 'New', f'intent: {intent}', now(), now()))
        actions.append('enquiry_created')
        if not re.search(r'(?i)(reply|touch|contact you|in touch)', reply):
            reply += ' ' + _t('rx.b_passed', loc)
        if name:
            with db() as c:
                c.execute('UPDATE receptionist_threads SET email=?,name=?,business=?,lead_id=?,intent=?,updated=? WHERE id=?',
                          (email, name[:120], business[:200], lead_id, intent, now(), thread['id']))
        else:
            with db() as c:
                c.execute('UPDATE receptionist_threads SET email=?,business=?,lead_id=?,intent=?,updated=? WHERE id=?',
                          (email, business[:200], lead_id, intent, now(), thread['id']))
    else:
        with db() as c:
            c.execute('UPDATE receptionist_threads SET intent=?,handoff=MAX(handoff,?),updated=? WHERE id=?',
                      (intent, 1 if 'handoff' in actions else 0, now(), thread['id']))

    _store(db, now, thread['id'], 'assistant', reply, intent,
           {'topic': topic, 'score': round(score, 2), 'actions': actions})
    return {'ok': True, 'reply': reply, 'intent': intent, 'topic': topic or '', 'score': round(score, 2),
            'actions': actions, 'thread': thread['token'], 'handoff': 'handoff' in actions,
            'sources': ['knowledge/reachmark.md'] if kb_answer else []}


OWNER_HELP = ('Owner commands — /stats · /leads [search] · /enquiries [status] · /invoices · /projects.\n'
              'Writes (add, update, send, audit, discover) run from the owner panel below or POST /api/receptionist/act.')


def _money(minor, currency):
    try:
        return f'{(minor or 0) / 100:,.2f} {currency or ""}'.strip()
    except (TypeError, ValueError):
        return str(minor or 0)


def owner_command(db, now, text, thread_token, visitor_hash):
    """Run a `/command` from the signed-in owner inside the chat flow."""
    loc = _loc()
    parts = (text or '').split(None, 1)
    cmd = parts[0].lower() if parts else ''
    arg = parts[1].strip()[:120] if len(parts) > 1 else ''
    thread = _thread(db, now, thread_token, visitor_hash, 'owner-console')
    _store(db, now, thread['id'], 'visitor', text)
    if cmd == '/stats':
        st = tool_stats(db, now, None, {}, {})
        inv = ', '.join(f'{k}: {v}' for k, v in st['invoices_by_status'].items()) or 'none yet'
        reply = _t('rx.b_stats', loc, a=st['leads'], b=st['new_enquiries'], c=st['projects'],
                     d=st['open_threads'], e=inv)
    elif cmd == '/leads':
        rows = tool_lead_list(db, now, None, {'q': arg, 'limit': 10}, {})['leads']
        reply = (_t('rx.b_no_leads', loc) if not rows else '\n'.join(
            f"\u2022 {r['name']} — {r.get('stage') or 'New'} ({r.get('city') or 'no city'}) [{r['id'][:8]}]" for r in rows))
    elif cmd == '/enquiries':
        rows = tool_enquiry_list(db, now, None, {'status': arg or 'New'}, {})['enquiries']
        reply = (_t('rx.b_nothing', loc) if not rows else '\n'.join(
            f"\u2022 {r['name']} — {r.get('business') or r.get('email') or ''} [{r['status']}]".rstrip() for r in rows))
    elif cmd == '/invoices':
        rows = tool_invoice_list(db, now, None, {}, {})['invoices']
        reply = (_t('rx.b_no_inv', loc) if not rows else '\n'.join(
            f"\u2022 {r.get('number') or r['id'][:8]} · {r.get('client_name') or ''} · "
            f"{_money(r.get('total_minor'), r.get('currency'))} · {r.get('status') or 'unset'}" for r in rows))
    elif cmd == '/projects':
        rows = tool_project_list(db, now, None, {}, {})['projects']
        reply = (_t('rx.b_no_proj', loc) if not rows else '\n'.join(
            f"\u2022 {r['title']} — {r.get('stage') or ''}".rstrip() for r in rows))
    else:
        reply = _t('rx.b_help', loc)
    _store(db, now, thread['id'], 'assistant', reply, 'owner_command', {'command': cmd})
    return {'ok': True, 'reply': reply, 'intent': 'owner_command', 'topic': '', 'score': 1.0,
            'actions': ['owner_command'], 'thread': thread['token'], 'handoff': False, 'sources': []}


def register_receptionist(app, db, now, log, settings):
    from flask import request, jsonify, session, render_template, g
    ensure_tables(db)

    def rate_ok(fingerprint, limit=40):
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with db() as c:
            count = c.execute('SELECT count(*) FROM receptionist_threads WHERE visitor_hash=? AND updated>?',
                              (fingerprint, cutoff)).fetchone()[0]
            messages = c.execute('SELECT count(*) FROM receptionist_messages WHERE created>? AND thread_id IN '
                                 '(SELECT id FROM receptionist_threads WHERE visitor_hash=?)', (cutoff, fingerprint)).fetchone()[0]
        return count < 12 and messages < limit

    @app.route('/receptionist')
    def receptionist_page():
        """The public AI-receptionist page: demo, tones, industries and KB-driven FAQ.

        The FAQ is rendered from the same knowledge file the chat answers from, so the
        page can never promise an answer the front desk would refuse to give.
        """
        try:
            base = (settings().get('public_base_url') or '').rstrip('/') or request.url_root.rstrip('/')
        except Exception:
            base = request.url_root.rstrip('/')
        seo = {
            'title': 'AI Receptionist — Every chat, enquiry and booking, handled | Reachmark',
            'description': ('Meet the Reachmark AI receptionist: a facts-only front desk that answers visitors, '
                            'captures enquiries and hands over to a human with context. Try it live.'),
            'keywords': 'AI receptionist, website chat assistant, lead capture, Reachmark',
            'canonical': (base + '/receptionist') if base else None,
            'og_image': (base + '/static/social-card.png') if base else '/static/social-card.png',
            'noindex': False,
        }
        gsv = os.getenv('GOOGLE_SITE_VERIFICATION', 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg').strip() or 'ClnMo7q76egyEoNRIagLZrMmf8G18w1zYFjTxS3QzQg'
        ga_id = os.getenv('GOOGLE_ANALYTICS_ID', '').strip() or 'G-CPSB1EDNFE'
        gt_id = os.getenv('GOOGLE_TAG_ID', '').strip() or 'GT-M6XWG99J'
        gtm_id = os.getenv('GOOGLE_TAG_MANAGER_ID', '').strip() or 'GTM-M3SJZ8S7'
        faqs = []
        for topic in load_knowledge():
            if topic['qa']:
                faqs.append({'topic': topic['topic'], 'q': topic['qa'][0]['q'], 'a': topic['qa'][0]['a']})
        structured = [
            {'@context': 'https://schema.org', '@type': 'WebPage', 'name': 'AI Receptionist — Reachmark',
             'description': seo['description'], 'url': seo['canonical'] or request.url},
            {'@context': 'https://schema.org', '@type': 'FAQPage', 'mainEntity': [
                {'@type': 'Question', 'name': item['q'],
                 'acceptedAnswer': {'@type': 'Answer', 'text': item['a']}} for item in faqs]},
        ]
        brand = brand_public()
        tiers = {row['id']: row for row in brand['tiers']}
        loc = g.get('locale', 'en')
        tier_notes = {'starter': _t('rx.tn_starter', loc),
                      'growth': _t('rx.tn_growth', loc),
                      'bespoke': _t('rx.tn_bespoke', loc)}
        return render_template('receptionist-page.html', seo=seo, google_verification=gsv,
                               structured=structured, ga_id=ga_id, gt_id=gt_id, gtm_id=gtm_id,
                               faqs=faqs, brand=brand, tiers=tiers, tier_notes=tier_notes)

    @app.get('/api/frontdesk/status')
    def frontdesk_status():
        """Live heartbeat for the public page: what the front desk knows right now."""
        topics = load_knowledge()
        return jsonify(ok=True, brain=BRAIN_VERSION, receptionist='live', topics=len(topics),
                       questions=sum(len(topic['qa']) for topic in topics))

    @app.post('/api/receptionist/message')
    def receptionist_message():
        body = request.get_json(silent=True)
        loc = g.get('locale', 'en')
        if not isinstance(body, dict):
            return jsonify(error=_t('rx.e_json', loc)), 400
        fingerprint = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()[:32]
        if body.get('company_url'):
            return jsonify(error=_t('rx.e_trap', loc)), 400
        if session.get('owner') and str(body.get('message', '')).strip().startswith('/'):
            return jsonify(owner_command(db, now, str(body.get('message', ''))[:2000],
                                         str(body.get('thread', ''))[:64] or None, fingerprint))
        if not rate_ok(fingerprint):
            return jsonify(error=_t('rx.e_rate', loc)), 429
        result = answer(db, now, str(body.get('message', ''))[:2000], str(body.get('thread', ''))[:64] or None,
                        fingerprint, str(body.get('page', ''))[:200], settings,
                        allow_llm=True, name=str(body.get('name', ''))[:120], email=str(body.get('email', ''))[:200],
                        business=str(body.get('business', ''))[:200])
        if not result.get('ok'):
            return jsonify(result), 400
        if 'enquiry_created' in result['actions']:
            log('enquiry', 'The AI receptionist captured a new enquiry')
        if result['handoff']:
            log('receptionist', 'A visitor asked for a human — flagged for the owner')
        return jsonify(result)

    @app.post('/api/receptionist/offer-review-link')
    def receptionist_offer_link():
        """Offer the review-link route from the chat, without creating it for a stranger."""
        body = request.get_json(silent=True) or {}
        business = str(body.get('business', ''))[:200].strip()
        loc = g.get('locale', 'en')
        if len(business) < 2:
            return jsonify(error=_t('rx.e_biz', loc)), 400
        return jsonify(ok=True, reply=_t('rx.e_offer', loc, b=business))

    @app.post('/api/receptionist/act')
    def receptionist_act():
        """Owner-only agent actions: the front desk doing real work."""
        loc = g.get('locale', 'en')
        if owner_locked() and not session.get('owner'):
            return jsonify(error=_t('rx.e_owner', loc)), 403
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return jsonify(error=_t('enq.err_json', loc)), 400
        try:
            result = run_tool(app, db, now, log, str(body.get('tool', '')), body.get('params') or {})
        except ToolError as e:
            return jsonify(error=str(e)), e.code
        log('receptionist', 'Owner agent ran ' + str(body.get('tool', '')))
        return jsonify(ok=True, tool=str(body.get('tool', '')), result=result)

    @app.get('/api/receptionist/threads')
    def receptionist_threads_route():
        if session.get('client_id') and not session.get('owner'):
            return jsonify(error=_t('rx.e_owner', g.get('locale', 'en'))), 403
        status = request.args.get('status') or None
        return jsonify({'threads': threads(db, status=status),
                        'knowledge_topics': [t['topic'] for t in load_knowledge()]})

    @app.get('/api/receptionist/threads/<thread_id>')
    def receptionist_thread_route(thread_id):
        if session.get('client_id') and not session.get('owner'):
            return jsonify(error=_t('rx.e_owner', g.get('locale', 'en'))), 403
        with db() as c:
            row = c.execute('SELECT * FROM receptionist_threads WHERE id=?', (thread_id,)).fetchone()
        if not row:
            return jsonify(error=_t('rx.e_thread', g.get('locale', 'en'))), 404
        return jsonify(thread=dict(row), transcript=transcript(db, thread_id))

    @app.post('/api/receptionist/threads/<thread_id>')
    def receptionist_thread_update(thread_id):
        body = request.get_json(silent=True) or {}
        status = str(body.get('status', 'open'))
        if status not in ('open', 'handled', 'closed'):
            return jsonify(error=_t('rx.e_status', g.get('locale', 'en'))), 400
        note = str(body.get('note', ''))[:3000]
        with db() as c:
            if not c.execute('SELECT 1 FROM receptionist_threads WHERE id=?', (thread_id,)).fetchone():
                return jsonify(error=_t('rx.e_thread', g.get('locale', 'en'))), 404
            c.execute('UPDATE receptionist_threads SET status=?,updated=? WHERE id=?', (status, now(), thread_id))
        if note:
            _store(db, now, thread_id, 'owner', note, 'note', {'status': status})
        log('receptionist', f'Receptionist thread marked {status}')
        return jsonify(ok=True)

    return {'answer': answer, 'threads': threads, 'transcript': transcript, 'load_knowledge': load_knowledge}
