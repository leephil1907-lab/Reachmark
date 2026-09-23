"""Reachmark AI crew — a team of agents that runs the find → verify → build → ask loop.

The crew is deliberately boring where it matters:

* **Every step leaves receipts.** Measured observations, source URLs and timestamps
  are stored with the step, so nothing in the console is a claim without evidence.
* **Nothing outbound happens without a human decision.** Steps that would contact a
  business stop at an approval gate; the owner approves or rejects each item.
* **It runs with no API key.** Each agent has a deterministic engine; a configured
  language model only helps with phrasing (see ``ai_provider``).
* **One run at a time, bounded.** Step count, runtime, leads touched and
  language-model calls are all capped, and a run can be cancelled between steps.

Agent implementations live in ``agents/agent_*.py`` and are imported lazily so a missing
optional piece can never stop the app from booting.
"""
import importlib, json, os, threading, time, traceback, uuid
from datetime import datetime, timezone

from crew import business as brand_brain

# --------------------------------------------------------------------------- #
# Crew roster. `handler` is resolved lazily: module:function
# --------------------------------------------------------------------------- #
AGENTS = [
    {
        'id': 'scout', 'name': 'Scout', 'symbol': '◎', 'tier': 'Prospects',
        'role': 'Lead gathering & web research',
        'mission': 'Find real businesses from public sources, and read the public pages they publish '
                   'to collect the contact details they already made public.',
        'tools': ['OpenStreetMap · Nominatim + Overpass', 'Bounded public-page contact harvest (robots-aware)',
                  'CSV import', 'Offline fixtures (demo only)'],
        'skills': ['prospecting'], 'handler': 'agents.agent_scout:run',
        'inputs': ['location(s), category, or your own CSV', 'optional: existing lead id'],
        'outputs': ['saved businesses with source receipts', 'public contact fields found on their own site'],
        'guardrails': ['No private, login-walled or non-HTTP destinations',
                       'robots.txt honoured, one page at a time, ≤3 pages per business',
                       'Never invents an e-mail or phone number'],
    },
    {
        'id': 'auditor', 'name': 'Auditor', 'symbol': '⌁', 'tier': 'Intelligence',
        'role': 'Measured website observation',
        'mission': 'Re-check the listed website and record what was actually observed — status, timing, '
                   'page basics — as dated evidence instead of an invented quality score.',
        'tools': ['SSRF-safe bounded GET', 'On-page signal reader (viewport, title, forms, bytes)',
                  'robots.txt / sitemap.xml probe'],
        'skills': ['seo-audit'], 'handler': 'agents.agent_auditor:run',
        'inputs': ['a lead with a listed website, or a whole shortlist'],
        'outputs': ['dated observations per lead', 'priority reasons, each with its source'],
        'guardrails': ['Observation is never presented as proof a business needs work',
                       'BLOCKED / UNREACHABLE are reported as inconclusive, not as failure'],
    },
    {
        'id': 'builder', 'name': 'Builder', 'symbol': '◨', 'tier': 'Intelligence',
        'role': 'Concept + quick review link',
        'mission': 'Turn a saved business record into a fast, mobile-first concept page and one '
                   'un-guessable review link that asks the simple question: do you want this website?',
        'tools': ['Concept composer (category themes)', 'Review-link issuer with view + response tracking',
                  'CRO pass over the reply path'],
        'skills': ['copywriting', 'cro'], 'handler': 'agents.agent_builder:run',
        'inputs': ['a lead record'],
        'outputs': ['/r/<token> review link', 'share message for e-mail, WhatsApp or SMS'],
        'guardrails': ['Page is labelled an independent concept, never the official website',
                       'No invented reviews, hours, prices, photos or certifications',
                       'Noindex, un-guessable token, no contact form behind it'],
    },
    {
        'id': 'scribe', 'name': 'Scribe', 'symbol': '✦', 'tier': 'Conversations',
        'role': 'Outreach drafting',
        'mission': 'Write the short, specific first message and its follow-ups, in the owner’s own voice, '
                   'using only the facts saved about that business.',
        'tools': ['Deterministic tone engine', 'Follow-up cadence', 'Optional model phrasing'],
        'skills': ['cold-email', 'copywriting'], 'handler': 'agents.agent_scribe:run',
        'inputs': ['a lead with contact details or a review link'],
        'outputs': ['draft e-mail 1 + 2 follow-ups + a short SMS/WhatsApp note'],
        'guardrails': ['Drafts only — sending needs a separate human approval',
                       'No invented claims, no fake familiarity, no invented prices',
                       'Unsubscribe and contact-basis lines are always present'],
    },
    {
        'id': 'closer', 'name': 'Closer', 'symbol': '↗', 'tier': 'Conversations',
        'role': 'Approval queue, sequencing & dispatch',
        'mission': 'Hold every outbound message until a human approves it, then send it through the '
                   'studio’s own mail provider and schedule the follow-up.',
        'tools': ['Approval queue', 'Suppression check', 'SMTP dispatch with hard caps', 'Follow-up schedule'],
        'skills': ['cold-email', 'prospecting'], 'handler': 'agents.agent_closer:run',
        'inputs': ['approved drafts / review links from a run'],
        'outputs': ['send receipts', 'follow-up calendar', 'suppression-safe state changes'],
        'guardrails': ['One message per business per day; cap of 5 dispatches per run',
                       'Opt-outs and suppressed addresses are never contacted',
                       'No SMTP configured → queued in the outbox, never faked as sent'],
    },
    {
        'id': 'receptionist', 'name': 'Receptionist', 'symbol': '☎', 'tier': 'Conversations',
        'role': 'Always-on front desk',
        'mission': 'Answer visitors and business owners on the public pages, from a facts-only knowledge '
                   'base, and turn every conversation into a captured enquiry rather than a guess.',
        'tools': ['Knowledge base (verified facts only)', 'Intent routing', 'Lead capture + human handoff',
                  'Inline review-link offer'],
        'skills': ['cro'], 'handler': 'agents.agent_receptionist:run',
        'inputs': ['visitor message', 'knowledge base', 'saved settings'],
        'outputs': ['grounded answer', 'captured enquiry', 'handoff queue item'],
        'guardrails': ['Answers only from the knowledge base and saved records',
                       'Never quotes a price, date or guarantee that is not published',
                       'Hands off to a human when unsure, and says so plainly'],
    },
    {
        'id': 'brag', 'name': 'Brag', 'symbol': '★', 'tier': 'Opportunities',
        'role': 'Launch kit for won work',
        'mission': 'When a business says yes, turn the delivery into a short shareable launch kit — '
                   'plan, brief, share copy and a self-contained card — so the win brings the next one.',
        'tools': ['brag playbook (tone presets + brief format)', 'Share copy writer', 'CSS card generator'],
        'skills': ['brag', 'ai-seo'], 'handler': 'agents.agent_brag:run',
        'inputs': ['a project, or a lead that responded yes'],
        'outputs': ['plan.json', 'composition-brief.md', 'share-copy.md', 'brag-card.html'],
        'guardrails': ['Video rendering is an external step and is never claimed as done here',
                       'No invented metrics in the share copy — real observations only'],
    },
]

AGENTS_BY_ID = {a['id']: a for a in AGENTS}

PIPELINES = {
    'campaign': {'label': 'Full campaign run', 'steps': ['scout', 'auditor', 'builder', 'scribe', 'closer'],
                 'description': 'Find businesses, verify them, build a concept + review link, draft the outreach, then wait for your approval.'},
    'research': {'label': 'Research shortlist', 'steps': ['scout', 'auditor'],
                 'description': 'Gather and verify only — no concept pages and no drafting.'},
    'prepare': {'label': 'Prepare proposals', 'steps': ['auditor', 'builder', 'scribe', 'closer'],
                'description': 'Work on leads you already have: re-verify, build concepts, draft the outreach.'},
    'review': {'label': 'Single-lead review', 'steps': ['auditor', 'builder', 'scribe'],
               'description': 'One business end-to-end, stopping before anything outbound.'},
    'launch': {'label': 'Launch kit', 'steps': ['brag'],
               'description': 'For a won project: plan, brief, share copy and a shareable card.'},
}

LIMITS = {'max_steps': 14, 'max_seconds': 240, 'max_leads': 25, 'max_dispatches': 5,
          'max_events': 400}


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def ensure_tables(db):
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS crew_runs(
            id TEXT PRIMARY KEY, mode TEXT, pipeline TEXT, agent TEXT, status TEXT,
            params TEXT, summary TEXT, steps_total INTEGER DEFAULT 0, steps_done INTEGER DEFAULT 0,
            started_by TEXT, tokens INTEGER DEFAULT 0, lease TEXT, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS crew_steps(
            id TEXT PRIMARY KEY, run_id TEXT, seq INTEGER, agent TEXT, title TEXT, status TEXT,
            summary TEXT, receipts TEXT, data TEXT, error TEXT, ms INTEGER,
            started TEXT, finished TEXT);
        CREATE TABLE IF NOT EXISTS crew_approvals(
            id TEXT PRIMARY KEY, run_id TEXT, step_id TEXT, lead_id TEXT, kind TEXT, title TEXT,
            payload TEXT, state TEXT, decided_by TEXT, decided_at TEXT, note TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS crew_events(
            id TEXT PRIMARY KEY, run_id TEXT, agent TEXT, level TEXT, message TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS crew_artifacts(
            id TEXT PRIMARY KEY, run_id TEXT, agent TEXT, lead_id TEXT, kind TEXT, title TEXT,
            body TEXT, meta TEXT, created TEXT);
        CREATE TABLE IF NOT EXISTS followups(
            id TEXT PRIMARY KEY, lead_id TEXT, run_id TEXT, kind TEXT, channel TEXT, due TEXT,
            state TEXT DEFAULT 'planned', payload TEXT, created TEXT, updated TEXT);
        CREATE TABLE IF NOT EXISTS crew_dispatch(
            id TEXT PRIMARY KEY, run_id TEXT, lead_id TEXT, approval_id TEXT, channel TEXT,
            recipient TEXT, subject TEXT, body TEXT, state TEXT, detail TEXT, created TEXT, updated TEXT);
        ''')
        c.execute('CREATE INDEX IF NOT EXISTS crew_steps_run ON crew_steps(run_id, seq)')
        c.execute('CREATE INDEX IF NOT EXISTS crew_approvals_state ON crew_approvals(state)')
        c.execute('CREATE INDEX IF NOT EXISTS crew_artifacts_run ON crew_artifacts(run_id)')


# --------------------------------------------------------------------------- #
# Run context handed to every agent
# --------------------------------------------------------------------------- #
class CrewError(Exception):
    """Raised by an agent to fail its step with a readable reason."""


class Ctx:
    def __init__(self, run, cfg):
        self.run = run
        self.params = run['params']
        self.db = cfg['db']
        self.now = cfg['now']
        self.log = cfg['log']
        self.settings = cfg['settings']
        self.add_lead = cfg.get('add_lead')
        self.categories = cfg.get('categories') or []
        self.deadline = cfg['deadline']
        self.crew = cfg.get('crew')
        self.brand = brand_brain
        self.receipts = []
        self.artifacts = []
        self.events = []
        self.started = time.monotonic()

    # -- evidence ---------------------------------------------------------- #
    def receipt(self, kind, detail, evidence=None, url=None, when=None):
        item = {'kind': kind, 'detail': str(detail)[:600]}
        if url:
            item['url'] = url
        if evidence is not None:
            item['evidence'] = str(evidence)[:600]
        item['at'] = when or self.now()
        self.receipts.append(item)
        return item

    def artifact(self, kind, title, body, meta=None, lead_id=None):
        item = {'kind': kind, 'title': title[:200], 'body': body if isinstance(body, str) else json.dumps(body, indent=2),
                'meta': meta or {}, 'lead_id': lead_id or (self.params.get('lead_id') or '')}
        self.artifacts.append(item)
        return item

    def emit(self, message, level='info', agent=None):
        self.events.append({'level': level, 'message': str(message)[:400], 'agent': agent or self.run.get('agent') or 'crew'})

    def llm(self, system, user, **kwargs):
        """Optional phrasing pass. Returns None when no provider is configured."""
        from web.ai_provider import safe_complete, provider_status
        if not provider_status()['configured']:
            return None
        text, _meta = safe_complete(system, user, **kwargs)
        return text

    # -- lead helpers ------------------------------------------------------ #
    def load_leads(self):
        """Leads this step should work on: explicit ids, or the run's own new leads."""
        ids = self.params.get('lead_ids') or []
        if self.params.get('lead_id'):
            ids = [self.params['lead_id']] + list(ids)
        if not ids:
            ids = self.run.get('lead_ids') or []
        if not ids:
            return []
        placeholders = ','.join('?' for _ in ids)
        with self.db() as c:
            rows = [dict(r) for r in c.execute(f'SELECT * FROM leads WHERE id IN ({placeholders})', tuple(ids))]
        order = {lid: i for i, lid in enumerate(ids)}
        rows.sort(key=lambda r: order.get(r['id'], 999))
        return rows[:LIMITS['max_leads']]

    def expired(self):
        return time.monotonic() > self.deadline


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
class Crew:
    def __init__(self, app, db, now, log, settings, add_lead=None, categories=None):
        self.app = app
        self.db = db
        self.now = now
        self.log = log
        self.settings = settings
        self.add_lead = add_lead
        self.categories = categories or []
        self.lock = threading.Lock()
        self.active_run = None
        ensure_tables(db)

    # -- helpers ----------------------------------------------------------- #
    def cfg(self, deadline):
        return {'db': self.db, 'now': self.now, 'log': self.log, 'settings': self.settings,
                'add_lead': self.add_lead, 'categories': self.categories, 'deadline': deadline,
                'crew': self}

    def event(self, run_id, agent, message, level='info'):
        with self.db() as c:
            c.execute('INSERT INTO crew_events VALUES(?,?,?,?,?,?)',
                      (uuid.uuid4().hex, run_id, agent, level, str(message)[:400], self.now()))

    def get_run(self, run_id):
        with self.db() as c:
            row = c.execute('SELECT * FROM crew_runs WHERE id=?', (run_id,)).fetchone()
        if not row:
            return None
        run = dict(row)
        run['params'] = json.loads(run['params'] or '{}')
        with self.db() as c:
            run['steps'] = [dict(r) for r in c.execute('SELECT * FROM crew_steps WHERE run_id=? ORDER BY seq', (run_id,))]
        for step in run['steps']:
            step['receipts'] = json.loads(step['receipts'] or '[]')
            step['data'] = json.loads(step['data'] or '{}')
        return run

    def stats(self):
        with self.db() as c:
            runs = c.execute('SELECT count(*) FROM crew_runs').fetchone()[0]
            done = c.execute("SELECT count(*) FROM crew_runs WHERE status='completed'").fetchone()[0]
            artifacts = c.execute('SELECT count(*) FROM crew_artifacts').fetchone()[0]
            pending = c.execute("SELECT count(*) FROM crew_approvals WHERE state='pending'").fetchone()[0]
            events = c.execute('SELECT count(*) FROM crew_events').fetchone()[0]
            steps = c.execute("SELECT count(*) FROM crew_steps WHERE status='ok'").fetchone()[0]
        return {'runs': runs, 'completed': done, 'artifacts': artifacts, 'pending_approvals': pending,
                'events': events, 'steps_ok': steps, 'active': self.active_run}

    # -- planning ---------------------------------------------------------- #
    def plan(self, mode, agent_id=None):
        if mode == 'single' and agent_id and agent_id in AGENTS_BY_ID:
            return [agent_id]
        pipeline = PIPELINES.get(mode) or PIPELINES['campaign']
        return list(pipeline['steps'])

    def start(self, mode='campaign', params=None, agent_id=None, started_by='owner'):
        params = params or {}
        steps = self.plan(mode, agent_id)
        if not steps:
            raise CrewError('Choose a crew member or a known pipeline.')
        if self.active_run and self._alive(self.active_run):
            raise CrewError('A crew run is already working. Wait for it to finish or cancel it.')
        run_id = uuid.uuid4().hex
        stamp = self.now()
        with self.db() as c:
            c.execute('INSERT INTO crew_runs(id,mode,pipeline,agent,status,params,summary,steps_total,steps_done,started_by,created,updated) '
                      'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                      (run_id, mode, json.dumps(steps), agent_id or '', 'running', json.dumps(params),
                       'Starting…', len(steps), 0, started_by, stamp, stamp))
        self.active_run = run_id
        self.event(run_id, steps[0], f'Run started ({mode}): ' + ' → '.join(AGENTS_BY_ID[s]['name'] for s in steps))
        thread = threading.Thread(target=self._drive, args=(run_id, steps, 0, params), name=f'crew-{run_id[:6]}', daemon=True)
        thread.start()
        return run_id

    def _alive(self, run_id):
        run = self.get_run(run_id)
        return bool(run and run['status'] in ('running', 'awaiting_approval', 'dispatching'))

    def resume(self, run_id, from_index=None, params=None):
        run = self.get_run(run_id)
        if not run:
            raise CrewError('Run not found.')
        if run['status'] == 'cancelled':
            raise CrewError('This run was cancelled.')
        steps = run['pipeline'] if isinstance(run['pipeline'], list) else json.loads(run['pipeline'] or '[]')
        steps = [s for s in steps if s in AGENTS_BY_ID]
        index = from_index if from_index is not None else run['steps_done']
        params = params or run['params']
        with self.db() as c:
            c.execute("UPDATE crew_runs SET status='running',updated=? WHERE id=?", (self.now(), run_id))
        self.active_run = run_id
        threading.Thread(target=self._drive, args=(run_id, steps, index, params), name=f'crew-{run_id[:6]}', daemon=True).start()
        return run_id

    # -- execution --------------------------------------------------------- #
    def _drive(self, run_id, steps, start_index, params):
        if not self.lock.acquire(blocking=False):
            self._finish(run_id, 'failed', 'Another crew run was executing; this one was not started.')
            return
        deadline = time.monotonic() + LIMITS['max_seconds']
        try:
            for index in range(start_index, len(steps)):
                run = self.get_run(run_id)
                if run and run['status'] == 'cancelled':
                    self.event(run_id, steps[index], 'Run cancelled before this step started.', 'warn')
                    return
                if time.monotonic() > deadline:
                    self._finish(run_id, 'failed', f'Time limit reached ({LIMITS["max_seconds"]}s). Nothing was sent; re-run when the sources are responsive.')
                    return
                agent_id = steps[index]
                outcome = self._run_step(run_id, index, agent_id, params, deadline)
                if outcome == 'stop':
                    return
                if outcome == 'gate':
                    with self.db() as c:
                        c.execute("UPDATE crew_runs SET status='awaiting_approval',steps_done=?,updated=? WHERE id=?",
                                  (index, self.now(), run_id))
                    self.active_run = None
                    return
            last = self.get_run(run_id)
            steps_done = (last or {}).get('steps') or []
            blocked = [step for step in steps_done if step.get('status') in ('blocked', 'failed')]
            if blocked:
                # A run that got nowhere must say so — "all steps finished" would be a lie.
                reason = (blocked[0].get('summary') or 'a step could not run').strip()
                extra = '' if len(blocked) == 1 else f' ({len(blocked)} steps blocked)'
                self._finish(run_id, 'blocked', f'Stopped early{extra}: {reason}')
                return
            last_summary = steps_done[-1].get('summary') if steps_done else ''
            tail = 'Anything outbound is waiting in your approval queue.'
            if last_summary and ('sent' in last_summary or 'queued' in last_summary or 'ready' in last_summary):
                tail = last_summary
            self._finish(run_id, 'completed', 'All crew steps finished. ' + tail)
        except Exception as exc:  # never leave a run silently running
            traceback.print_exc()
            self._finish(run_id, 'failed', f'Unexpected crew error: {type(exc).__name__}')
        finally:
            self.lock.release()

    def _run_step(self, run_id, index, agent_id, params, deadline):
        agent = AGENTS_BY_ID.get(agent_id)
        if not agent:
            self._finish(run_id, 'failed', f'Unknown crew member "{agent_id}".')
            return 'stop'
        started = time.monotonic()
        with self.db() as c:
            earlier = c.execute("SELECT id FROM crew_steps WHERE run_id=? AND seq=? AND status='awaiting_approval'",
                                (run_id, index)).fetchone()
            if earlier:
                step_id = earlier['id']
                c.execute("UPDATE crew_steps SET status='running',started=?,finished=NULL WHERE id=?", (self.now(), step_id))
            else:
                step_id = uuid.uuid4().hex
                c.execute('INSERT INTO crew_steps(id,run_id,seq,agent,title,status,started) VALUES(?,?,?,?,?,?,?)',
                          (step_id, run_id, index, agent_id, agent['role'], 'running', self.now()))
        self.event(run_id, agent_id, f'{agent["name"]} started: {agent["role"]}')

        ctx = Ctx(self.get_run(run_id), self.cfg(deadline))
        ctx.run['lead_ids'] = []
        try:
            module_name, function_name = agent['handler'].split(':')
            handler = getattr(importlib.import_module(module_name), function_name)
            result = handler(ctx) or {}
            status = 'ok'
            summary = str(result.get('summary', 'Done.'))[:400]
            data = result.get('data', {})
            gate = result.get('gate')
            error = ''
        except CrewError as exc:
            status, summary, data, gate, error = 'blocked', str(exc)[:400], {}, None, str(exc)[:400]
        except Exception as exc:
            traceback.print_exc()
            status, summary, data, gate = 'failed', f'{type(exc).__name__}: {exc}'[:400], {}, None
            error = f'{type(exc).__name__}: {exc}'[:900]

        ms = int((time.monotonic() - started) * 1000)
        with self.db() as c:
            c.execute('UPDATE crew_steps SET status=?,summary=?,receipts=?,data=?,error=?,ms=?,finished=? WHERE id=?',
                      (status, summary, json.dumps(ctx.receipts)[:60000], json.dumps(data)[:60000], error, ms,
                       self.now(), step_id))
            for artifact in ctx.artifacts:
                c.execute('INSERT INTO crew_artifacts VALUES(?,?,?,?,?,?,?,?,?)',
                          (uuid.uuid4().hex, run_id, agent_id, artifact['lead_id'], artifact['kind'],
                           artifact['title'], artifact['body'][:40000], json.dumps(artifact['meta'])[:8000], self.now()))
            for event in ctx.events[:LIMITS['max_events']]:
                c.execute('INSERT INTO crew_events VALUES(?,?,?,?,?,?)',
                          (uuid.uuid4().hex, run_id, event['agent'], event['level'], event['message'], self.now()))
            c.execute('UPDATE crew_runs SET steps_done=?,updated=?,summary=? WHERE id=?',
                      (index + 1, self.now(), summary[:300], run_id))
        self.event(run_id, agent_id, f'{agent["name"]} {status}: {summary}',
                   'warn' if status in ('blocked', 'failed') else 'info')

        if isinstance(data.get('lead_ids'), list) and data['lead_ids']:
            # Carry the leads this step created forward to the next crew member.
            params['lead_ids'] = [str(x)[:64] for x in data['lead_ids']][:LIMITS['max_leads']]
            with self.db() as c:
                c.execute('UPDATE crew_runs SET params=? WHERE id=?', (json.dumps(params), run_id))
        if gate and gate.get('items'):
            self._open_gate(run_id, step_id, agent_id, gate)
            return 'gate'
        if status == 'failed' and not params.get('continue_on_error'):
            self._finish(run_id, 'failed', summary)
            return 'stop'
        if ctx.expired():
            self.event(run_id, agent_id, 'Step budget reached; stopping before the next step.', 'warn')
            return 'stop'
        return None

    def _open_gate(self, run_id, step_id, agent_id, gate):
        stamp = self.now()
        with self.db() as c:
            c.execute("UPDATE crew_steps SET status='awaiting_approval',summary=? WHERE id=?",
                      ('Waiting for your decision on ' + str(len(gate['items'])) + ' item(s).', step_id))
        with self.db() as c:
            for item in gate['items'][:LIMITS['max_dispatches'] + 10]:
                c.execute('INSERT INTO crew_approvals VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                          (uuid.uuid4().hex, run_id, step_id, item.get('lead_id', ''), item.get('kind') or gate['kind'],
                           str(item.get('title', ''))[:200], json.dumps(item)[:20000], 'pending', '', '', '', stamp))
        self.event(run_id, agent_id, f'{len(gate["items"])} item(s) need your decision — nothing is sent until you approve.',
                   'warn')

    def _finish(self, run_id, status, summary):
        with self.db() as c:
            c.execute('UPDATE crew_runs SET status=?,summary=?,updated=? WHERE id=?',
                      (status, summary[:400], self.now(), run_id))
        self.event(run_id, 'crew', summary, 'error' if status == 'failed' else 'info')
        if self.active_run == run_id:
            self.active_run = None

    def cancel(self, run_id):
        with self.db() as c:
            c.execute("UPDATE crew_runs SET status='cancelled',updated=?,summary=? WHERE id=? AND status IN ('running','awaiting_approval')",
                      (self.now(), 'Cancelled by the owner before the next step.', run_id))
        self.event(run_id, 'crew', 'Cancelled by the owner. Nothing further will run.', 'warn')
        if self.active_run == run_id:
            self.active_run = None

    # -- approvals --------------------------------------------------------- #
    def pending_approvals(self, run_id=None):
        query = "SELECT * FROM crew_approvals WHERE state='pending'"
        args = ()
        if run_id:
            query += ' AND run_id=?'
            args = (run_id,)
        with self.db() as c:
            rows = [dict(r) for r in c.execute(query + ' ORDER BY created', args)]
        for row in rows:
            row['payload'] = json.loads(row['payload'] or '{}')
        return rows

    def decide(self, approval_id, decision, note='', decided_by='owner'):
        if decision not in ('approve', 'reject'):
            raise CrewError('Decision must be approve or reject.')
        with self.db() as c:
            row = c.execute("SELECT * FROM crew_approvals WHERE id=? AND state='pending'", (approval_id,)).fetchone()
            if not row:
                raise CrewError('That item has already been decided.')
            c.execute('UPDATE crew_approvals SET state=?,decided_by=?,decided_at=?,note=? WHERE id=?',
                      ('approved' if decision == 'approve' else 'rejected', decided_by, self.now(), str(note)[:500], approval_id))
        approval = dict(row)
        self.event(approval['run_id'], 'crew',
                   f"{'Approved' if decision == 'approve' else 'Rejected'}: {approval['title']}" +
                   (f' — {note}' if note else ''), 'info')
        self.log('crew', f'Crew item {"approved" if decision == "approve" else "rejected"}: {approval["title"][:80]}')
        return approval

    def maybe_resume(self, run_id):
        run = self.get_run(run_id)
        if not run or run['status'] != 'awaiting_approval':
            return False
        if self.pending_approvals(run_id):
            return False
        self.resume(run_id)
        return True


# --------------------------------------------------------------------------- #
# Flask routes
# --------------------------------------------------------------------------- #
def _playbook_version():
    """The vendored marketingskills plugin version, read once from its manifest."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, 'skills', 'vendor', 'VENDOR.json'), encoding='utf-8') as handle:
            manifest = json.load(handle)
        for source in manifest.get('sources', []):
            if source.get('upstream_version'):
                return str(source['upstream_version']).split(' ')[0]
        return 'vendored'
    except Exception:
        return 'vendored'


def register_crew(app, db, now, log, settings, add_lead=None, categories=None):
    from flask import request, jsonify, session
    crew = Crew(app, db, now, log, settings, add_lead, categories)
    try:  # the Auditor's observation table belongs to the crew runtime, so create it at boot
        from agents.agent_auditor import ensure_tables as ensure_audits
        ensure_audits(db)
    except Exception:
        pass
    app.extensions['reachmark_crew'] = crew

    from web.ai_provider import provider_status, health as llm_health
    from crew.skills_loader import playbook_index

    def owner_only():
        if session.get('owner'):
            return None
        if session.get('client_id') and session.get('role') == 'client':
            from web.billing import tier_status
            with db() as c:
                row = c.execute('SELECT * FROM users WHERE id=?', (session.get('client_id'),)).fetchone()
            tier, active, _ = tier_status(dict(row) if row else None)
            if tier == 'pro' and active:
                return None
            return jsonify(error='The Pro plan runs the AI crew.', upgrade='/pricing', required='pro'), 402
        return None

    @app.get('/api/crew')
    def crew_state():
        guard = owner_only()
        if guard:
            return guard
        with db() as c:
            runs = [dict(r) for r in c.execute('SELECT * FROM crew_runs ORDER BY created DESC LIMIT 12')]
            approvals = [dict(r) for r in c.execute("SELECT * FROM crew_approvals WHERE state='pending' ORDER BY created DESC LIMIT 50")]
            artifacts = [dict(r) for r in c.execute('SELECT id,run_id,agent,lead_id,kind,title,created FROM crew_artifacts ORDER BY created DESC LIMIT 40')]
            events = [dict(r) for r in c.execute('SELECT * FROM crew_events ORDER BY rowid DESC LIMIT 60')]
            followups = [dict(r) for r in c.execute("SELECT * FROM followups WHERE state='planned' ORDER BY due LIMIT 25")]
            dispatch = [dict(r) for r in c.execute('SELECT * FROM crew_dispatch ORDER BY created DESC LIMIT 25')]
        from web.review_links import link_overview
        from web.receptionist import threads as receptionist_threads
        for run in runs:
            run['params'] = json.loads(run['params'] or '{}')
            run['pipeline'] = json.loads(run['pipeline'] or '[]')
        for item in approvals:
            item['payload'] = json.loads(item['payload'] or '{}')
        return jsonify(
            agents=AGENTS, pipelines=PIPELINES, limits=LIMITS, categories=list(crew.categories),
            brain={'version': brand_brain.BRAIN_VERSION, 'tagline': brand_brain.TAGLINE,
                   'tiers': {key: {'name': row['name'], 'price': row['price'], 'unit': row['unit']}
                             for key, row in brand_brain.TIERS.items()},
                   'lifecycle': brand_brain.lifecycle()},
            playbook_version=_playbook_version(),
            runs=runs, approvals=approvals, artifacts=artifacts, events=list(reversed(events)),
            followups=followups, dispatch=dispatch,
            stats=crew.stats(), provider=llm_health(), playbook=playbook_index(),
            review_links=link_overview(db),
            threads=receptionist_threads(db, limit=20),
            guardrails={
                'autopilot_scope': 'internal steps only — drafting, research, concept pages',
                'outbound_rule': 'Every e-mail, review-link share or SMS text needs a separate owner approval.',
                'caps': f"{LIMITS['max_dispatches']} dispatches per run · 1 message per business per day",
                'suppression': 'Opt-outs are checked on every dispatch and kept after a lead is deleted.',
            })

    @app.post('/api/crew/run')
    def crew_start():
        guard = owner_only()
        if guard:
            return guard
        body = request.get_json(silent=True) or {}
        mode = str(body.get('mode', 'campaign'))
        agent_id = str(body.get('agent', '')).strip() or None
        params = {
            'location': str(body.get('location', ''))[:120].strip(),
            'category': str(body.get('category', ''))[:80].strip(),
            'fixtures': bool(body.get('fixtures')),
            'limit': max(1, min(int(body.get('limit') or 8), 25)),
            'tone': str(body.get('tone', 'Professional'))[:40],
            'lead_id': str(body.get('lead_id', ''))[:64],
            'lead_ids': [str(x)[:64] for x in (body.get('lead_ids') or [])][:25],
            'include_review_link': body.get('include_review_link', True) is not False,
            'sms_note': bool(body.get('sms_note')),
            'continue_on_error': True,
        }
        if mode == 'single' and (not agent_id or agent_id not in AGENTS_BY_ID):
            return jsonify(error='Choose which crew member should run.'), 400
        if mode != 'single' and mode not in PIPELINES:
            return jsonify(error='Unknown crew pipeline.'), 400
        if mode in ('campaign', 'research') and not params['fixtures'] and not params['location'] and not params['lead_ids'] and not params['lead_id']:
            return jsonify(error='Give the crew a location ("City, Country"), a saved lead, or switch on the offline demo.'), 400
        try:
            run_id = crew.start(mode, params, agent_id, 'owner')
        except CrewError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, run_id=run_id)

    @app.get('/api/crew/runs/<run_id>')
    def crew_run_detail(run_id):
        guard = owner_only()
        if guard:
            return guard
        run = crew.get_run(run_id)
        if not run:
            return jsonify(error='Run not found.'), 404
        run['pipeline'] = json.loads(run['pipeline'] or '[]') if isinstance(run['pipeline'], str) else run['pipeline']
        with db() as c:
            run['approvals'] = [dict(r) for r in c.execute('SELECT * FROM crew_approvals WHERE run_id=? ORDER BY created', (run_id,))]
            run['events'] = [dict(r) for r in c.execute('SELECT * FROM crew_events WHERE run_id=? ORDER BY rowid', (run_id,))]
            run['artifacts'] = [dict(r) for r in c.execute('SELECT * FROM crew_artifacts WHERE run_id=? ORDER BY created DESC', (run_id,))]
        for item in run['approvals']:
            item['payload'] = json.loads(item['payload'] or '{}')
        return jsonify(run=run, agents=AGENTS_BY_ID)

    @app.post('/api/crew/runs/<run_id>/cancel')
    def crew_cancel(run_id):
        guard = owner_only()
        if guard:
            return guard
        crew.cancel(run_id)
        return jsonify(ok=True)

    @app.post('/api/crew/approvals/<approval_id>')
    def crew_decide(approval_id):
        guard = owner_only()
        if guard:
            return guard
        body = request.get_json(silent=True) or {}
        decision = 'approve' if str(body.get('decision')) == 'approve' else 'reject'
        try:
            approval = crew.decide(approval_id, decision, str(body.get('note', '')), 'owner')
        except CrewError as exc:
            return jsonify(error=str(exc)), 409
        resumed = crew.maybe_resume(approval['run_id'])
        return jsonify(ok=True, decision=decision, resumed=resumed)

    @app.post('/api/crew/approvals/<approval_id>/dispatch')
    def crew_dispatch_one(approval_id):
        """Dispatch one approved item immediately (still requires an approved state)."""
        guard = owner_only()
        if guard:
            return guard
        with db() as c:
            row = c.execute('SELECT * FROM crew_approvals WHERE id=?', (approval_id,)).fetchone()
        if not row:
            return jsonify(error='Approval not found.'), 404
        if row['state'] != 'approved':
            return jsonify(error='Approve the item first — nothing is sent without your decision.'), 409
        from agents.agent_closer import dispatch_item
        result = dispatch_item(crew, dict(row), now=now)
        return jsonify(result), (200 if result.get('ok') else 502)

    @app.post('/api/crew/demo/purge')
    def crew_demo_purge():
        guard = owner_only()
        if guard:
            return guard
        with db() as c:
            ids = [r[0] for r in c.execute("SELECT id FROM leads WHERE source='Fixture (offline demo)'")]
            for lid in ids:
                c.execute('DELETE FROM leads WHERE id=?', (lid,))
                c.execute('DELETE FROM review_links WHERE lead_id=?', (lid,))
                c.execute('DELETE FROM site_audits WHERE lead_id=?', (lid,))
        log('crew', f'Offline demo records removed ({len(ids)})')
        return jsonify(ok=True, removed=len(ids))

    @app.get('/api/crew/playbook')
    def crew_playbook():
        guard = owner_only()
        if guard:
            return guard
        return jsonify(playbook_index())

    return crew
