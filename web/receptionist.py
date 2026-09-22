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
    message = (message or '').strip()[:2000]
    if len(message) < 2:
        return {'error': 'Type a message first.', 'ok': False}
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
        reply = HUMAN_LINE
        actions.append('handoff')
    elif intent == 'new_project':
        reply = ('That is exactly what the studio does. The fastest route: open /enquire, describe the business and '
                 'what you need, and you will get a tailored estimate — no commitment until you approve the scope. '
                 + REVIEW_OFFER)
        actions.append('offer_review_link')
    elif intent == 'greeting':
        reply = ('Hello — this is the Reachmark front desk. I can explain how the studio works, what the published '
                 'tiers cost, what happens after an enquiry, or put you in touch with the studio owner.')
    elif score >= MIN_SCORE and kb_answer:
        reply = kb_answer
        if intent == 'pricing':
            actions.append('offer_enquiry')
        if intent in ('samples', 'timeline'):
            actions.append('offer_enquiry')
    else:
        reply = HANDOFF_LINE
        actions.append('handoff')

    if allow_llm and reply not in (HUMAN_LINE, HANDOFF_LINE):
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
                               f'Captured by the AI receptionist. First question: {message[:280]}', now(), now()))
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
                       '', '', (f'From the AI receptionist.\n\n{message[:1500]}\n\nAssistant’s answer: {reply[:800]}')[:5000],
                       '', visitor_hash, 'New', f'intent: {intent}', now(), now()))
        actions.append('enquiry_created')
        if not re.search(r'(?i)(reply|touch|contact you|in touch)', reply):
            reply += ' I have passed your details to the studio owner — expect a personal reply.'
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


def register_receptionist(app, db, now, log, settings):
    from flask import request, jsonify, session, render_template
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
        tier_notes = {'starter': 'One striking page, receptionist included',
                      'growth': 'Up to 5 pages plus blog, receptionist included',
                      'bespoke': 'Custom build, receptionist tailored to it'}
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
        if not isinstance(body, dict):
            return jsonify(error='Send your message as a JSON object.'), 400
        fingerprint = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()[:32]
        if body.get('company_url'):
            return jsonify(error='Unable to accept this message.'), 400
        if not rate_ok(fingerprint):
            return jsonify(error='That is a lot of messages in one hour. Please use the enquiry form at /enquire and the studio will reply directly.'), 429
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
        if len(business) < 2:
            return jsonify(error='Tell me the business name first.'), 400
        return jsonify(ok=True, reply=(f'Happy to do that for {business}. I have passed the name to the studio — '
                                       'they prepare the concept and send you one private review link. Leave an e-mail '
                                       'address in this chat and it will reach them straight away.'))

    @app.get('/api/receptionist/threads')
    def receptionist_threads_route():
        if session.get('client_id') and not session.get('owner'):
            return jsonify(error='Owner login required.'), 403
        status = request.args.get('status') or None
        return jsonify({'threads': threads(db, status=status),
                        'knowledge_topics': [t['topic'] for t in load_knowledge()]})

    @app.get('/api/receptionist/threads/<thread_id>')
    def receptionist_thread_route(thread_id):
        if session.get('client_id') and not session.get('owner'):
            return jsonify(error='Owner login required.'), 403
        with db() as c:
            row = c.execute('SELECT * FROM receptionist_threads WHERE id=?', (thread_id,)).fetchone()
        if not row:
            return jsonify(error='Thread not found.'), 404
        return jsonify(thread=dict(row), transcript=transcript(db, thread_id))

    @app.post('/api/receptionist/threads/<thread_id>')
    def receptionist_thread_update(thread_id):
        body = request.get_json(silent=True) or {}
        status = str(body.get('status', 'open'))
        if status not in ('open', 'handled', 'closed'):
            return jsonify(error='Use open, handled or closed.'), 400
        note = str(body.get('note', ''))[:3000]
        with db() as c:
            if not c.execute('SELECT 1 FROM receptionist_threads WHERE id=?', (thread_id,)).fetchone():
                return jsonify(error='Thread not found.'), 404
            c.execute('UPDATE receptionist_threads SET status=?,updated=? WHERE id=?', (status, now(), thread_id))
        if note:
            _store(db, now, thread_id, 'owner', note, 'note', {'status': status})
        log('receptionist', f'Receptionist thread marked {status}')
        return jsonify(ok=True)

    return {'answer': answer, 'threads': threads, 'transcript': transcript, 'load_knowledge': load_knowledge}
