"""Owner-only agent tools for the AI receptionist.

Public visitors keep the plain Q&A chat. When the studio owner is signed
in, the same front desk can also run these tools: read and change leads,
handle enquiries, check invoices/contracts/projects, run website audits,
send approved outreach and start discovery. Writes reuse the exact same
code as the workspace buttons (internal dispatch), so guardrails cannot
drift. Every run is logged.
"""
import os
from web.i18n import t as _t, locale_now
import uuid

LEAD_STAGES = ['New', 'Drafted', 'Contacted', 'Replied', 'Won', 'Not a fit']
ENQUIRY_STATUSES = ['New', 'In progress', 'Answered', 'Closed']


class ToolError(Exception):
    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


def owner_locked():
    """True when owner login is configured: agent tools then need it."""
    return bool(os.getenv('OWNER_PASSWORD_HASH') or os.getenv('DASHBOARD_PASSWORD'))


def _dispatch(app, view_fn, path, body, *args):
    """Run an existing POST view in-process. Returns (status, json_dict)."""
    from werkzeug.exceptions import HTTPException
    with app.test_request_context(path, method='POST', json=body or {}):
        try:
            rv = view_fn(*args)
        except HTTPException as e:
            return e.code or 400, {'error': getattr(e, 'description', 'Request failed.')}
    if isinstance(rv, tuple):
        resp, code = (list(rv) + [200])[:2]
    else:
        resp, code = rv, 200
    try:
        data = resp.get_json()
    except Exception:
        data = {'result': str(resp)}
    if not isinstance(data, dict):
        data = {'result': data}
    return code, data


def _raise_for_status(code, data):
    if code != 200:
        raise ToolError((data or {}).get('error') or 'That action failed.', code)


def tool_stats(db, now, log, p, ctx):
    with db() as c:
        leads = c.execute('SELECT COUNT(*) FROM leads').fetchone()[0]
        new_eq = c.execute("SELECT COUNT(*) FROM enquiries WHERE status='New'").fetchone()[0]
        inv = c.execute('SELECT status,COUNT(*) FROM invoices GROUP BY status').fetchall()
        proj = c.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        open_threads = c.execute(
            "SELECT COUNT(*) FROM receptionist_threads WHERE status='open'").fetchone()[0]
    return {'leads': leads, 'new_enquiries': new_eq,
            'invoices_by_status': {r[0] or 'unset': r[1] for r in inv},
            'projects': proj, 'open_threads': open_threads}


def tool_lead_list(db, now, log, p, ctx):
    q = '%' + str(p.get('q', ''))[:120].lower() + '%'
    try:
        lim = max(1, min(int(p.get('limit', 10) or 10), 50))
    except (TypeError, ValueError):
        lim = 10
    with db() as c:
        rows = [dict(r) for r in c.execute(
            'SELECT id,name,email,phone,city,website,stage,status,updated FROM leads '
            'WHERE lower(name) LIKE ? OR lower(email) LIKE ? OR lower(city) LIKE ? '
            'ORDER BY updated DESC LIMIT ?', (q, q, q, lim))]
    return {'leads': rows}


def tool_lead_get(db, now, log, p, ctx):
    with db() as c:
        row = c.execute('SELECT * FROM leads WHERE id=?', (str(p.get('id', '')),)).fetchone()
    if not row:
        raise ToolError(_t('er_061', locale_now()), 404)
    return {'lead': dict(row)}


def tool_lead_create(db, now, log, p, ctx):
    from web.app import add_lead
    name = str(p.get('name', '')).strip()
    if not name:
        raise ToolError(_t('er_012', locale_now()))
    key = 'agent:' + uuid.uuid4().hex
    v = {'name': name[:200], 'email': str(p.get('email', '')).strip()[:250],
         'phone': str(p.get('phone', '')).strip()[:100],
         'website': str(p.get('website', '')).strip()[:1000],
         'city': str(p.get('city', '')).strip()[:200],
         'source': 'Owner agent', 'source_key': key}
    if add_lead(v) != 1:
        raise ToolError(_t('er_032', locale_now()))
    note = str(p.get('note', ''))[:2000]
    with db() as c:
        if note:
            c.execute('UPDATE leads SET note=? WHERE source_key=?', (note, key))
        row = c.execute('SELECT * FROM leads WHERE source_key=?', (key,)).fetchone()
    log('agent', f'Owner agent added {name}')
    return {'lead': dict(row)}


def tool_lead_update(db, now, log, p, ctx):
    from web.app import classify
    lid = str(p.get('id', ''))
    with db() as c:
        cur = c.execute('SELECT * FROM leads WHERE id=?', (lid,)).fetchone()
    if not cur:
        raise ToolError(_t('er_061', locale_now()), 404)
    cur = dict(cur)
    allowed = {'name', 'email', 'phone', 'website', 'note', 'stage', 'subject', 'body'}
    data = {k: str(v)[:10000] for k, v in (p or {}).items() if k in allowed and isinstance(v, str)}
    if 'name' in data and not data['name'].strip():
        raise ToolError(_t('er_012', locale_now()))
    if 'stage' in data and data['stage'] not in LEAD_STAGES:
        raise ToolError(_t('er_057', locale_now()))
    if not data:
        raise ToolError(_t('er_080', locale_now()))
    if 'website' in data:
        data['status'] = classify(data['website'])
        if data['website'] != cur['website']:
            data.update(audit_status=None, audit_reason=None, http_code=None, checked_at=None)
            with db() as c:
                c.execute('DELETE FROM lead_reviews WHERE lead_id=?', (lid,))
    data['updated'] = now()
    with db() as c:
        c.execute('UPDATE leads SET ' + ','.join(k + '=?' for k in data) + ' WHERE id=?',
                  [*data.values(), lid])
    log('agent', f"Owner agent updated {cur['name']}")
    return {'ok': True}


def tool_lead_delete(db, now, log, p, ctx):
    with db() as c:
        cur = c.execute('SELECT name FROM leads WHERE id=?', (str(p.get('id', '')),)).fetchone()
        if not cur:
            raise ToolError(_t('er_061', locale_now()), 404)
        c.execute('DELETE FROM leads WHERE id=?', (str(p.get('id', '')),))
    log('agent', f"Owner agent deleted {cur['name']}")
    return {'ok': True}


def tool_lead_send(db, now, log, p, ctx):
    from web.app import send as send_view
    basis = str(p.get('basis', '')).strip()
    if len(basis) < 10:
        raise ToolError(_t('er_034', locale_now()))
    lid = str(p.get('id', ''))
    code, data = _dispatch(ctx['app'], send_view, f'/api/leads/{lid}/send',
                           {'approved': True, 'basis': basis}, lid)
    _raise_for_status(code, data)
    return {'sent': True}


def tool_lead_audit(db, now, log, p, ctx):
    from web.app import audit_lead
    lid = str(p.get('id', ''))
    code, data = _dispatch(ctx['app'], audit_lead, f'/api/leads/{lid}/audit', {}, lid)
    _raise_for_status(code, data)
    return {'audit': data}


def tool_discover_run(db, now, log, p, ctx):
    from web.app import discover
    city = str(p.get('city', '')).strip()
    category = str(p.get('category', '')).strip()
    code, data = _dispatch(ctx['app'], discover, '/api/discover',
                           {'city': city, 'category': category})
    _raise_for_status(code, data)
    return {'discovery': data}


def tool_job_cancel(db, now, log, p, ctx):
    from web.app import cancel_job
    jid = str(p.get('id', ''))
    code, data = _dispatch(ctx['app'], cancel_job, f'/api/jobs/{jid}/cancel', {}, jid)
    _raise_for_status(code, data)
    return {'ok': True}


def _enquiry_row(db, eid):
    with db() as c:
        return c.execute('SELECT * FROM enquiries WHERE id=?', (eid,)).fetchone()


def tool_enquiry_list(db, now, log, p, ctx):
    status = str(p.get('status', '')).strip()
    with db() as c:
        if status:
            rows = [dict(r) for r in c.execute(
                'SELECT id,name,email,business,kind,status,created FROM enquiries '
                'WHERE status=? ORDER BY created DESC LIMIT 50', (status,))]
        else:
            rows = [dict(r) for r in c.execute(
                'SELECT id,name,email,business,kind,status,created FROM enquiries '
                'ORDER BY created DESC LIMIT 50')]
    return {'enquiries': rows}


def tool_enquiry_get(db, now, log, p, ctx):
    row = _enquiry_row(db, str(p.get('id', '')))
    if not row:
        raise ToolError(_t('er_040', locale_now()), 404)
    return {'enquiry': dict(row)}


def tool_enquiry_update(db, now, log, p, ctx):
    eid = str(p.get('id', ''))
    if not _enquiry_row(db, eid):
        raise ToolError(_t('er_040', locale_now()), 404)
    status = str(p.get('status', '')).strip()
    notes = str(p.get('notes', ''))
    if status not in ENQUIRY_STATUSES or len(notes) > 5000:
        raise ToolError(_t('er_019', locale_now()))
    with db() as c:
        c.execute('UPDATE enquiries SET status=?,notes=?,updated=? WHERE id=?',
                  (status, notes, now(), eid))
    log('agent', 'Owner agent updated an enquiry')
    return {'ok': True}


def tool_invoice_list(db, now, log, p, ctx):
    status = str(p.get('status', '')).strip()
    with db() as c:
        q = ('SELECT id,number,client_name,client_email,currency,total_minor,status,due_date '
             'FROM invoices')
        rows = ([dict(r) for r in c.execute(q + ' WHERE status=? ORDER BY created DESC LIMIT 50', (status,))]
                if status else
                [dict(r) for r in c.execute(q + ' ORDER BY created DESC LIMIT 50')])
    return {'invoices': rows}


def tool_invoice_get(db, now, log, p, ctx):
    with db() as c:
        row = c.execute('SELECT * FROM invoices WHERE id=?', (str(p.get('id', '')),)).fetchone()
    if not row:
        raise ToolError(_t('er_059', locale_now()), 404)
    return {'invoice': dict(row)}


def tool_contract_list(db, now, log, p, ctx):
    with db() as c:
        rows = [dict(r) for r in c.execute(
            'SELECT id,title,client,email,currency,amount_minor,paid_minor,status,updated '
            'FROM contracts ORDER BY updated DESC LIMIT 50')]
    return {'contracts': rows}


def tool_contract_get(db, now, log, p, ctx):
    with db() as c:
        row = c.execute('SELECT * FROM contracts WHERE id=?', (str(p.get('id', '')),)).fetchone()
    if not row:
        raise ToolError(_t('er_029', locale_now()), 404)
    return {'contract': dict(row)}


def tool_project_list(db, now, log, p, ctx):
    with db() as c:
        rows = [dict(r) for r in c.execute(
            'SELECT id,title,stage,next_action,updated FROM projects ORDER BY updated DESC LIMIT 50')]
    return {'projects': rows}


def tool_project_update(db, now, log, p, ctx):
    from web.workflow import STAGES
    pid = str(p.get('id', ''))
    with db() as c:
        if not c.execute('SELECT 1 FROM projects WHERE id=?', (pid,)).fetchone():
            raise ToolError(_t('er_091', locale_now()), 404)
    data = {}
    if 'stage' in (p or {}) and isinstance(p.get('stage'), str):
        if p['stage'] not in STAGES:
            raise ToolError(_t('er_057', locale_now()))
        data['stage'] = p['stage']
    if 'next_action' in (p or {}) and isinstance(p.get('next_action'), str):
        if len(p['next_action']) > 500:
            raise ToolError(_t('er_060', locale_now()))
        data['next_action'] = p['next_action']
    if not data:
        raise ToolError(_t('er_080', locale_now()))
    data['updated'] = now()
    with db() as c:
        c.execute('UPDATE projects SET ' + ','.join(k + '=?' for k in data) + ' WHERE id=?',
                  [*data.values(), pid])
    log('agent', 'Owner agent updated a project')
    return {'ok': True}


ACT_TOOLS = {
    'stats': (tool_stats, 'Workspace counts: leads, new enquiries, invoices, projects, open chats.'),
    'lead_list': (tool_lead_list, 'Search leads. Params: q, limit.'),
    'lead_get': (tool_lead_get, 'One lead. Params: id.'),
    'lead_create': (tool_lead_create, 'Add a lead. Params: name*, email, phone, website, city, note.'),
    'lead_update': (tool_lead_update, 'Change a lead. Params: id*, name, email, phone, website, note, stage, subject, body.'),
    'lead_delete': (tool_lead_delete, 'Delete a lead. Params: id*.'),
    'lead_send': (tool_lead_send, 'Send approved outreach. Params: id*, basis* (10+ chars). Same guardrails as the workspace button.'),
    'lead_audit': (tool_lead_audit, 'Re-check a website. Params: id*.'),
    'discover_run': (tool_discover_run, 'Run business discovery. Params: city*, category*.'),
    'job_cancel': (tool_job_cancel, 'Cancel a discovery job. Params: id*.'),
    'enquiry_list': (tool_enquiry_list, 'List enquiries. Params: status.'),
    'enquiry_get': (tool_enquiry_get, 'One enquiry. Params: id*.'),
    'enquiry_update': (tool_enquiry_update, 'Set enquiry status/notes. Params: id*, status*, notes.'),
    'invoice_list': (tool_invoice_list, 'List invoices. Params: status.'),
    'invoice_get': (tool_invoice_get, 'One invoice. Params: id*.'),
    'contract_list': (tool_contract_list, 'List contracts.'),
    'contract_get': (tool_contract_get, 'One contract. Params: id*.'),
    'project_list': (tool_project_list, 'List projects.'),
    'project_update': (tool_project_update, 'Set project stage/next action. Params: id*, stage, next_action.'),
}


def run_tool(app, db, now, log, tool, params):
    if tool not in ACT_TOOLS:
        raise ToolError(_t('er_148', locale_now(), v=', '.join(sorted(ACT_TOOLS))))
    fn, _ = ACT_TOOLS[tool]
    return fn(db, now, log, params or {}, {'app': app})
