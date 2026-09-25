#!/usr/bin/env python3
"""Offline end-to-end smoke test for the Reachmark AI crew.

Runs the whole loop against a disposable database with the network switched off:

    python scripts/crew_smoke.py

It proves, in one command, that: the crew roster loads · the offline pipeline runs
scout → auditor → builder → scribe → closer · drafts pass their guardrails · the run
stops at an approval gate · approving queues rather than sends without SMTP · the
review link renders and records an answer · the receptionist answers from the
knowledge base and captures an enquiry · Brag refuses to invent a story.

Nothing here touches a real business, a real mailbox or a public endpoint.
"""
import os, sys, tempfile, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

BOLD, DIM, RESET = '\033[1m', '\033[2m', '\033[0m'
OK, WARN, BAD = '\033[32m✓\033[0m', '\033[33]•\033[0m', '\033[31m✗\033[0m'
failures = []


def check(label, condition, detail=''):
    print(f'  {OK if condition else BAD} {label}' + (f' {DIM}{detail}{RESET}' if detail else ''))
    if not condition:
        failures.append(label)


def main():
    tmp = tempfile.TemporaryDirectory()
    os.environ['DATABASE_PATH'] = os.path.join(tmp.name, 'crew-smoke.sqlite3')
    os.environ['SMTP_HOST'] = ''
    os.environ['SMTP_FROM'] = ''
    os.environ.pop('DASHBOARD_PASSWORD', None)
    os.environ['ALLOW_CREW_DEMO'] = '1'  # smoke proves the loop on fixtures, never the network
    os.chdir(ROOT)

    import web.app as application
    client = application.app.test_client()

    print(f'{BOLD}Reachmark AI crew — offline smoke test{RESET}')
    print(f'{DIM}database: {os.environ["DATABASE_PATH"]}{RESET}\n')

    print(f'{BOLD}1. Console state{RESET}')
    state = client.get('/api/crew').get_json()
    check('crew roster loaded', len(state['agents']) >= 7, ', '.join(a['id'] for a in state['agents']))
    check('playbooks vendored with licence files', all(
        os.path.exists(os.path.join(ROOT, 'skills', 'vendor', source['license_file'])) for source in state['playbook']['sources']))
    check('guardrail text published to the console', 'approval' in state['guardrails']['outbound_rule'].lower())
    check('no provider configured → deterministic mode', state['provider']['configured'] is False)

    print(f'\n{BOLD}2. Full campaign run (offline demo, no network){RESET}')
    client.post('/api/settings', json={'sender_name': 'Lee Phil', 'agency': 'Reachmark',
                                       'reply_email': 'lee@example.test', 'postal_address': '1 Test Street',
                                       'public_base_url': 'https://reachmark.example'})
    started = client.post('/api/crew/run', json={'mode': 'campaign', 'fixtures': True, 'limit': 4,
                                                 'tone': 'Professional', 'include_review_link': True, 'sms_note': True})
    check('run accepted', started.status_code == 200, started.get_json().get('error', ''))
    run_id = started.get_json().get('run_id', '')
    run = {}
    for _ in range(120):
        time.sleep(0.25)
        runs = client.get('/api/crew').get_json()['runs']
        if runs and runs[0]['status'] in ('completed', 'awaiting_approval', 'failed', 'cancelled'):
            run = runs[0]
            break
    check('the crew stops at the approval gate', run.get('status') == 'awaiting_approval', run.get('status', 'timeout'))

    detail = client.get(f'/api/crew/runs/{run_id}').get_json()['run']
    agents = [step['agent'] for step in detail['steps']]
    check('pipeline order scout → auditor → builder → scribe → closer',
          agents[:5] == ['scout', 'auditor', 'builder', 'scribe', 'closer'], ' → '.join(agents))
    check('every completed step carries receipts',
          all(step['receipts'] for step in detail['steps'] if step['status'] == 'ok'))
    check('no dispatch happened before a decision', client.get('/api/crew').get_json()['dispatch'] == [])
    approvals = detail['approvals']
    check('outbound items raised for a decision', len(approvals) >= 1, f'{len(approvals)} items')

    scribe = [step for step in detail['steps'] if step['agent'] == 'scribe'][0]
    held = [receipt for receipt in scribe['receipts'] if receipt['kind'] == 'guardrail']
    check('drafts passed the writing guardrails', not held, '; '.join(r['detail'] for r in held[:2]))

    state = client.get('/api/crew').get_json()
    check('follow-ups scheduled for drafted leads', bool(state['followups']), f"{len(state['followups'])} planned")
    links = state['review_links']['links']
    check('review links issued', len(links) == 4, f'{len(links)} links')

    print(f'\n{BOLD}3. The owner decides{RESET}')
    for approval in approvals:
        client.post(f"/api/crew/approvals/{approval['id']}", json={'decision': 'approve', 'note': 'smoke test'})
    for _ in range(120):
        time.sleep(0.25)
        runs = client.get('/api/crew').get_json()['runs']
        if runs and runs[0]['status'] in ('completed', 'failed'):
            break
    state = client.get('/api/crew').get_json()
    check('run completed after the decisions', state['runs'][0]['status'] == 'completed', state['runs'][0]['summary'][:90])
    states = {row['state'] for row in state['dispatch']}
    check('nothing reported as sent without SMTP', 'sent' not in states, 'states: ' + ', '.join(sorted(states)))
    check('approved e-mail queued in the outbox instead', 'queued' in states or not states)
    check('records without an e-mail got a copy-ready share message',
          any(row['channel'] == 'manual' and row['state'] == 'ready' for row in state['dispatch']))

    print(f'\n{BOLD}4. The review link a business is sent{RESET}')
    token = links[0]['token']
    page = client.get('/r/' + token)
    check('review page renders', page.status_code == 200, f'{len(page.data)} bytes')
    check('page says it is not the official website', b'not the official website' in page.data)
    check('page includes the live contact form', b'id="w-form"' in page.data)
    check('single tawk bubble on the page', b'embed.tawk.to' in page.data and b'Ask the studio' not in page.data)
    check('unknown token 404s', client.get('/r/not-a-real-token').status_code == 404)
    answered = client.post(f'/api/r/{token}/respond',
                           json={'choice': 'want', 'name': 'Demo Owner', 'email': 'owner@example.test',
                                 'note': 'Yes please, and the phone number is out of date.'})
    check('answer accepted', answered.status_code == 201, answered.get_json().get('response', {}).get('label', ''))
    check('views recorded', client.get('/api/crew').get_json()['review_links']['opened'] >= 1)
    with application.db() as c:
        stage = c.execute("SELECT stage FROM leads WHERE id=(SELECT lead_id FROM review_links WHERE token=?)", (token,)).fetchone()
        enquiry = c.execute("SELECT count(*) FROM enquiries WHERE kind='Review link reply'").fetchone()
    check('lead stage moved on a real answer', stage and stage['stage'] == 'Won', stage['stage'] if stage else '')
    check('answer landed in the enquiry inbox', enquiry[0] == 1)

    print(f'\n{BOLD}5. The receptionist{RESET}')
    for question, expect in (('how much does a website cost?', '1,250'),
                             ('how long does it take?', '7 days'),
                             ('can I talk to a real person?', 'studio owner')):
        reply = client.post('/api/receptionist/message', json={'message': question}).get_json()
        check(f'answers "{question}" from the knowledge base', expect.lower() in reply['reply'].lower(),
              f"intent={reply['intent']}")
    unknown = client.post('/api/receptionist/message', json={'message': 'do you sell llamas on credit?'}).get_json()
    check('refuses to guess an unknown question', 'handoff' in unknown['actions'])
    captured = client.post('/api/receptionist/message',
                           json={'message': 'My bakery needs a website, my e-mail is ada@example.test',
                                 'name': 'Ada', 'business': 'Ada Bakery'}).get_json()
    check('captures a real enquiry instead of a dead end', 'enquiry_created' in captured['actions'])
    with application.db() as c:
        check('receptionist lead stored with its source',
              c.execute("SELECT count(*) FROM leads WHERE source='Website receptionist'").fetchone()[0] == 1)

    print(f'\n{BOLD}6. Honesty checks{RESET}')
    from agents.agent_brag import run as brag_run
    from crew.crew import Ctx, CrewError
    with application.db() as c:
        c.execute("INSERT INTO leads(id,source_key,name,token,created,updated) VALUES('BRAG','brag','Bare Listing','tb',?,?)",
                  (application.now(), application.now()))
    ctx = Ctx({'id': 'smoke', 'params': {'lead_id': 'BRAG'}, 'agent': 'brag'},
              {'db': application.db, 'now': application.now, 'log': application.log,
               'settings': application.settings, 'deadline': time.time() + 10})
    try:
        brag_run(ctx)
        check('Brag refuses to invent a story', False, 'it produced one anyway')
    except CrewError as exc:
        check('Brag refuses to invent a story', 'invent' in str(exc).lower())
    from web.receptionist import answer as receptionist_answer
    grounded = receptionist_answer(application.db, application.now, 'do you offer refunds?', settings=lambda: {})
    check('a question the site never published is never invented',
          'handoff' in grounded['actions'] or 'no published refund' in grounded['reply'].lower())
    invented = receptionist_answer(application.db, application.now,
                                   'do you offer a refund if i am unhappy with the llama?', settings=lambda: {})
    check('an unanswerable question is handed to a human',
          'handoff' in invented['actions'] and 'will not guess' in invented['reply'])

    print()
    if failures:
        print(f'{BAD} {len(failures)} check(s) failed: ' + '; '.join(failures))
        tmp.cleanup()
        return 1
    print(f'{OK} All checks passed — the crew, the review link and the front desk behave as documented.')
    tmp.cleanup()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
