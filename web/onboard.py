"""Post-signup city + niche: find up to 10 businesses and score stored evidence.

Does not live-fetch every listing (slow, SSRF-heavy). Scores come from the
listing fields already saved — the same stored-evidence path as the queue.
"""
from __future__ import annotations

from flask import jsonify, redirect, render_template, request, session

ONBOARD_CAP = 10


def _who():
    if session.get('owner'):
        return None, True
    if session.get('client_id') and session.get('role') == 'client':
        return session.get('client_id'), True
    return None, False


def register_onboard(app, db, now, log, search_save, categories):
    names = list(categories.keys()) if isinstance(categories, dict) else list(categories)

    @app.route('/onboard')
    def onboard_page():
        _uid, ok = _who()
        if not ok:
            return redirect('/signup')
        return render_template('onboard.html', categories=names)

    @app.post('/api/onboard')
    def onboard_run():
        uid, ok = _who()
        if not ok:
            return jsonify(error='Sign in first.'), 401
        body = request.get_json(silent=True) or {}
        city = str(body.get('city') or '').strip()[:80]
        category = str(body.get('category') or '').strip()[:80]
        if not city or not category:
            return jsonify(error='City and niche are required.'), 400
        if category not in names:
            return jsonify(error='Pick a niche from the list.'), 400
        try:
            _result, _rows = search_save(city, category, include_websites=False, owner=uid)
        except Exception:
            log('onboard', f'{city}/{category}: source unavailable')
            return jsonify(error='The map source was unavailable. Try again in a minute.'), 502
        with db() as c:
            if uid:
                rows = c.execute(
                    '''SELECT * FROM leads WHERE owner_user_id=? AND city=? AND category=?
                       ORDER BY created DESC LIMIT ?''',
                    (uid, city, category, ONBOARD_CAP),
                ).fetchall()
            else:
                rows = c.execute(
                    '''SELECT * FROM leads WHERE city=? AND category=?
                       ORDER BY created DESC LIMIT ?''',
                    (city, category, ONBOARD_CAP),
                ).fetchall()
        leads = [dict(r) for r in rows]
        scored = []
        try:
            from web.opportunity import build_report, save_report
        except Exception:
            build_report = save_report = None
        if build_report:
            for lead in leads:
                payload = build_report(db, lead, now, observe_live=False)
                saved = save_report(db, lead, payload, now)
                scored.append({
                    'id': lead['id'],
                    'name': lead.get('name'),
                    'city': lead.get('city'),
                    'category': lead.get('category'),
                    'website': lead.get('website') or '',
                    'score': saved.get('score'),
                    'priority': saved.get('priority'),
                    'leaks': saved.get('leaks') or [],
                })
        empty = not scored
        log('onboard', f'{city}/{category}: {len(scored)} scored from stored evidence')
        return jsonify(
            city=city,
            category=category,
            added=len(leads),
            scored=scored,
            empty=empty,
            next='/dashboard#leads' if not empty else '/dashboard#overview',
            checklist=[
                {'id': 'discover', 'label': 'Find businesses in your city', 'done': not empty},
                {'id': 'audit', 'label': 'Audit a listed website', 'done': False},
                {'id': 'report', 'label': 'Review the Digital Opportunity Report', 'done': False},
                {'id': 'draft', 'label': 'Draft the outreach', 'done': False},
                {'id': 'approve', 'label': 'Approve a send (required)', 'done': False},
            ],
        )
