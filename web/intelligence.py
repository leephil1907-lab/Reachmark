"""Evidence-backed website fit intelligence API for Reachmark."""
import json
from flask import jsonify, session

FIT_MAP = {
    'restaurant': ('Editorial hospitality','Reservations / calls',['Home','Menu','About','Gallery','Reservations','Contact'],['Sticky booking CTA','Menu highlights','Location + hours','Gallery']),
    'cafe': ('Editorial hospitality','Visits / orders',['Home','Menu','Story','Gallery','Visit'],['Menu highlights','Location + hours','Order/booking CTA','Gallery']),
    'clinic': ('Clinical trust','Appointments',['Home','Treatments','Team','Patient information','FAQ','Contact'],['Appointment CTA','Treatment pathways','Team profiles','Verified trust signals']),
    'dental': ('Clinical editorial','Appointments',['Home','Treatments','Dentists','Reviews','FAQ','Contact'],['Book appointment CTA','Treatment pathways','Team profiles','FAQ']),
    'law': ('Editorial authority','Consultation enquiries',['Home','Practice Areas','People','Insights','About','Contact'],['Consultation CTA','Practice-area pathways','Attorney profiles','Insights']),
    'real estate': ('Immersive property editorial','Property enquiries / viewings',['Home','Properties','Agents','Neighbourhoods','About','Contact'],['Property search','Map','Property cards','Viewing CTA']),
    'saas': ('Product-led conversion','Demo / signup',['Home','Product','Features','Pricing','Security','FAQ'],['Interactive product preview','Feature grid','Pricing','FAQ']),
    'finance': ('Trust-first fintech','Signup / enquiry',['Home','Product','Security','How it works','FAQ','Contact'],['Product walkthrough','Trust/security section','Live data only when sourced','Conversion CTA']),
}

def _fit(category):
    text = (category or '').lower()
    for key, value in FIT_MAP.items():
        if key in text:
            direction, goal, pages, modules = value
            return {'direction':direction,'goal':goal,'pages':pages,'modules':modules}
    return {'direction':'Modern service-led','goal':'Qualified enquiry','pages':['Home','Services','About','FAQ','Contact'],'modules':['Clear value proposition','Service pathways','Verified proof','Contact CTA']}

def _allowed(db, lead_id):
    row = db().execute('SELECT * FROM leads WHERE id=?', (lead_id,)).fetchone()
    if not row:
        return None
    client_id = session.get('client_id') if session.get('role') == 'client' else None
    if client_id and row['owner_user_id'] != client_id:
        return None
    return dict(row)

def _table(c, name):
    return bool(c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())

def register_intelligence(app, db, now):
    @app.route('/api/intelligence/lead/<lid>')
    def lead_intelligence(lid):
        lead = _allowed(db, lid)
        if not lead:
            return jsonify(error='Lead not found.'), 404
        audit = None
        with db() as c:
            if _table(c, 'site_audits'):
                row = c.execute('SELECT * FROM site_audits WHERE lead_id=? ORDER BY created DESC LIMIT 1', (lid,)).fetchone()
                if row:
                    audit = dict(row)
                    for key in ('signals','observations','gaps'):
                        try: audit[key] = json.loads(audit.get(key) or '{}')
                        except (TypeError, ValueError): audit[key] = {}
        fit = _fit(lead.get('category'))
        gaps = ((audit or {}).get('gaps') or {}).get('gaps') or []
        recommendations = []
        if not lead.get('website'):
            recommendations.append('No website URL is recorded. Treat website need as unknown until independently verified.')
        elif not audit:
            recommendations.append('Run a live website observation before making a redesign claim.')
        else:
            recommendations.extend(g.get('reason','') for g in gaps[:5] if g.get('reason'))
        return jsonify(
            lead={k:lead.get(k) for k in ('id','name','category','city','website','stage')},
            observation={'status':audit.get('status') if audit else 'NOT_ANALYZED',
                         'checked_at':audit.get('created') if audit else None,
                         'score':audit.get('score') if audit else None,
                         'tier':audit.get('tier') if audit else None,
                         'signals':(audit or {}).get('signals') or {},
                         'gaps':gaps[:8]},
            fit={**fit,'mobile_priority':'high','evidence_state':'measured' if audit else 'not measured'},
            recommendations=recommendations[:6],
            next_actions=['Review measured gaps','Approve the website direction','Generate the concept blueprint']
        )

    @app.route('/api/intelligence/crew')
    def crew_intelligence():
        with db() as c:
            leads=c.execute('SELECT count(*) FROM leads').fetchone()[0]
            analyzed=c.execute('SELECT count(DISTINCT lead_id) FROM site_audits').fetchone()[0] if _table(c,'site_audits') else 0
            pending=c.execute("SELECT count(*) FROM crew_approvals WHERE state='pending'").fetchone()[0] if _table(c,'crew_approvals') else 0
            running=c.execute("SELECT count(*) FROM crew_runs WHERE status IN ('running','queued')").fetchone()[0] if _table(c,'crew_runs') else 0
        return jsonify(leads=leads,analyzed=analyzed,pending_approvals=pending,active_runs=running)
