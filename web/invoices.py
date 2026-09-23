"""Invoice creator: original Reachmark design inspired by AllScale workflow (not copied branding). Manual PDF and payment tracking only."""
import re, uuid, json
from web.i18n import t as _t, locale_now
from datetime import datetime, timezone, date
from decimal import Decimal, InvalidOperation
from flask import request, jsonify, session, abort
from web.operations import CURRENCIES

STATUSES = ['Draft','Sent','Paid','Overdue','Cancelled']
DISCOUNT_TYPES = ['none','percent','fixed']

EMAIL_RE = re.compile(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+')

def money_minor(value, currency):
    if value is None or str(value).strip() == '':
        return None
    try:
        n = Decimal(str(value).strip())
        factor = 10 ** CURRENCIES[currency]
        if not n.is_finite() or n < 0 or n > Decimal('1000000000000') or n * factor != (n * factor).to_integral_value():
            raise ValueError()
        return int(n * factor)
    except (InvalidOperation, ValueError):
        raise ValueError(_t('er_047', locale_now(), c=currency))

def format_amount(minor, currency):
    if minor is None:
        return None
    decimals = CURRENCIES[currency]
    if decimals == 0:
        return f"{currency} {minor:,}"
    return f"{currency} {Decimal(minor) / (10 ** decimals):,.{decimals}f}"

def _session_cid():
    from flask import session
    if session.get('client_id') and session.get('role') == 'client' and not session.get('owner'):
        return session.get('client_id')
    return None


def register_invoices(app, db, now, log):
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS invoices(
            id TEXT PRIMARY KEY,
            number TEXT UNIQUE,
            client_name TEXT,
            client_email TEXT,
            client_address TEXT,
            client_user_id TEXT,
            project_id TEXT,
            lead_id TEXT,
            currency TEXT,
            status TEXT,
            issue_date TEXT,
            due_date TEXT,
            notes TEXT,
            terms TEXT,
            tax_rate REAL,
            discount_type TEXT,
            discount_value REAL,
            subtotal_minor INTEGER,
            tax_minor INTEGER,
            discount_minor INTEGER,
            total_minor INTEGER,
            created TEXT,
            updated TEXT
        );
        CREATE TABLE IF NOT EXISTS invoice_items(
            id TEXT PRIMARY KEY,
            invoice_id TEXT,
            description TEXT,
            quantity REAL,
            unit_minor INTEGER,
            amount_minor INTEGER,
            created TEXT
        );''')
        # Migration: add client_user_id to projects if missing
        proj_cols = {r[1] for r in c.execute('PRAGMA table_info(projects)')}
        if 'client_user_id' not in proj_cols and 'projects' in [r[1] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
            try:
                c.execute('ALTER TABLE projects ADD COLUMN client_user_id TEXT')
            except Exception:
                pass
        # Add client_user_id to invoices if missing (for older DBs)
        inv_cols = {r[1] for r in c.execute('PRAGMA table_info(invoices)')}
        if 'client_user_id' not in inv_cols:
            try:
                c.execute('ALTER TABLE invoices ADD COLUMN client_user_id TEXT')
            except Exception:
                pass

    def is_owner():
        return bool(session.get('owner'))

    def current_client_id():
        if session.get('client_id') and session.get('role')=='client':
            return session.get('client_id')
        return None

    def client_email_for_id(cid):
        if not cid:
            return None
        with db() as cc:
            r = cc.execute('SELECT email FROM users WHERE id=?', (cid,)).fetchone()
            return r['email'].lower() if r else None

    def can_access_invoice(row, cid, user_email):
        if is_owner():
            return True
        if not cid:
            return False
        # Direct assignment
        if row['client_user_id'] == cid:
            return True
        # Email match for unassigned invoices
        if row['client_user_id'] is None and row['client_email'] and user_email and row['client_email'].strip().lower() == user_email.lower():
            return True
        return False

    def validate_and_compute(data, currency):
        # Items validation
        items = data.get('items')
        if not isinstance(items, list) or len(items) == 0 or len(items) > 25:
            raise ValueError(_t('er_004', locale_now()))
        computed_items = []
        subtotal = 0
        for it in items:
            if not isinstance(it, dict):
                raise ValueError(_t('er_062', locale_now()))
            desc = str(it.get('description','')).strip()
            qty_raw = it.get('quantity', 1)
            price_raw = it.get('unit_price')
            if not desc or len(desc) > 500:
                raise ValueError(_t('er_037', locale_now()))
            try:
                qty = Decimal(str(qty_raw).strip())
                if not qty.is_finite() or qty <= 0 or qty > Decimal('1000000'):
                    raise ValueError()
                # Allow up to 2 decimal places for quantity
                if qty * 100 != (qty * 100).to_integral_value():
                    raise ValueError()
            except:
                raise ValueError(_t('er_098', locale_now()))
            unit_minor = money_minor(price_raw, currency)
            if unit_minor is None:
                raise ValueError(_t('er_038', locale_now()))
            amount_minor = int((Decimal(unit_minor) * qty).to_integral_value(rounding='ROUND_HALF_UP'))
            subtotal += amount_minor
            computed_items.append({'description': desc, 'quantity': float(qty), 'unit_minor': unit_minor, 'amount_minor': amount_minor, 'id': str(it.get('id') or uuid.uuid4().hex)[:32]})
        # Tax and discount
        tax_rate = data.get('tax_rate', 0)
        try:
            tax_rate = float(tax_rate) if str(tax_rate).strip() != '' else 0
            if tax_rate < 0 or tax_rate > 100:
                raise ValueError()
        except:
            raise ValueError(_t('er_118', locale_now()))
        discount_type = str(data.get('discount_type','none')).strip()
        if discount_type not in DISCOUNT_TYPES:
            discount_type = 'none'
        discount_value = data.get('discount_value', 0)
        try:
            discount_value = float(discount_value) if str(discount_value).strip() != '' else 0
            if discount_value < 0:
                raise ValueError()
            if discount_type == 'percent' and discount_value > 100:
                raise ValueError()
        except:
            raise ValueError(_t('er_035', locale_now()))
        discount_minor = 0
        if discount_type == 'percent' and discount_value:
            discount_minor = int((Decimal(subtotal) * Decimal(str(discount_value)) / Decimal('100')).to_integral_value(rounding='ROUND_HALF_UP'))
        elif discount_type == 'fixed' and discount_value:
            fixed_minor = money_minor(str(discount_value), currency)
            if fixed_minor is None:
                raise ValueError(_t('er_052', locale_now()))
            discount_minor = min(fixed_minor, subtotal)
        taxable = subtotal - discount_minor
        tax_minor = int((Decimal(taxable) * Decimal(str(tax_rate)) / Decimal('100')).to_integral_value(rounding='ROUND_HALF_UP')) if tax_rate else 0
        total = taxable + tax_minor
        return computed_items, subtotal, discount_minor, tax_minor, total, tax_rate, discount_type, discount_value

    @app.get('/api/invoices')
    def list_invoices():
        cid = current_client_id()
        is_own = is_owner()
        if not is_own and not cid:
            return jsonify(error=_t('er_010', locale_now())),401
        with db() as c:
            rows = [dict(r) for r in c.execute('SELECT * FROM invoices ORDER BY updated DESC')]
            # For clients, filter
            if cid and not is_own:
                user_email = client_email_for_id(cid)
                rows = [r for r in rows if can_access_invoice(r, cid, user_email)]
            # Attach items
            result = []
            for r in rows:
                items = [dict(it) for it in c.execute('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY created', (r['id'],))]
                # decode unit/amount for display
                r['items'] = items
                result.append(r)
        return jsonify(invoices=result, currencies=CURRENCIES, statuses=STATUSES)

    @app.get('/api/invoices/<iid>')
    def get_invoice(iid):
        cid = current_client_id()
        is_own = is_owner()
        with db() as c:
            r = c.execute('SELECT * FROM invoices WHERE id=?', (iid,)).fetchone()
            if not r:
                abort(404)
            row = dict(r)
            user_email = client_email_for_id(cid) if cid else None
            if not can_access_invoice(row, cid, user_email):
                return jsonify(error=_t('er_077', locale_now())),404
            items = [dict(it) for it in c.execute('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY created', (iid,))]
            row['items'] = items
        return jsonify(row)

    @app.post('/api/invoices')
    def create_invoice():
        if not is_owner():
            return jsonify(error=_t('er_083', locale_now())),401
        data = request.get_json(silent=True) or {}
        currency = str(data.get('currency','USD')).strip()
        if currency not in CURRENCIES:
            return jsonify(error=_t('er_018', locale_now())),400
        client_name = str(data.get('client_name','')).strip()
        client_email = str(data.get('client_email','')).strip()
        client_address = str(data.get('client_address','')).strip()
        project_id = str(data.get('project_id','')).strip()
        lead_id = str(data.get('lead_id','')).strip()
        status = str(data.get('status','Draft')).strip()
        issue_date = str(data.get('issue_date','')).strip()
        due_date = str(data.get('due_date','')).strip()
        notes = str(data.get('notes','')).strip()
        terms = str(data.get('terms','')).strip()
        if not client_name or len(client_name) > 180:
            return jsonify(error=_t('er_025', locale_now())),400
        if client_email and (not EMAIL_RE.fullmatch(client_email) or len(client_email) > 250):
            return jsonify(error=_t('er_045', locale_now())),400
        if len(client_address) > 500:
            return jsonify(error=_t('er_024', locale_now())),400
        if status not in STATUSES:
            return jsonify(error=_t('er_020', locale_now())),400
        try:
            if issue_date:
                date.fromisoformat(issue_date)
            if due_date:
                date.fromisoformat(due_date)
            if issue_date and due_date and due_date < issue_date:
                return jsonify(error=_t('er_036', locale_now())),400
        except ValueError:
            return jsonify(error=_t('er_149', locale_now())),400
        if len(notes) > 5000 or len(terms) > 5000:
            return jsonify(error=_t('er_078', locale_now())),400
        with db() as c:
            _cid = _session_cid()
            if project_id:
                _p = c.execute('SELECT client_user_id FROM projects WHERE id=?', (project_id,)).fetchone()
                if not _p or (_cid and _p['client_user_id'] != _cid):
                    return jsonify(error=_t('er_065', locale_now())),400
            if lead_id:
                _l = c.execute('SELECT owner_user_id FROM leads WHERE id=?', (lead_id,)).fetchone()
                if not _l or (_cid and _l['owner_user_id'] != _cid):
                    return jsonify(error=_t('er_063', locale_now())),400
        try:
            computed_items, subtotal, discount_minor, tax_minor, total, tax_rate, discount_type, discount_value = validate_and_compute(data, currency)
        except ValueError as e:
            return jsonify(error=str(e)),400
        # Resolve client_user_id via email
        client_user_id = None
        if client_email:
            with db() as c:
                u = c.execute('SELECT id FROM users WHERE lower(email)=lower(?)', (client_email,)).fetchone()
                if u:
                    client_user_id = u['id']
        iid = uuid.uuid4().hex
        number = f"RM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{iid[:6].upper()}"
        stamp = now()
        with db() as c:
            c.execute('INSERT INTO invoices VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (iid, number, client_name, client_email.lower() if client_email else '', client_address, client_user_id, project_id or None, lead_id or None, currency, status, issue_date or None, due_date or None, notes, terms, tax_rate, discount_type, discount_value, subtotal, tax_minor, discount_minor, total, stamp, stamp))
            for it in computed_items:
                c.execute('INSERT INTO invoice_items VALUES(?,?,?,?,?,?,?)',
                          (it['id'], iid, it['description'], it['quantity'], it['unit_minor'], it['amount_minor'], stamp))
        log('invoice', f'Invoice created: {number} · {client_name} · {currency} {total/(10**CURRENCIES[currency]):.2f}')
        return jsonify(id=iid, number=number),201

    @app.route('/api/invoices/<iid>', methods=['PATCH'])
    def update_invoice(iid):
        if not is_owner():
            return jsonify(error=_t('er_083', locale_now())),401
        data = request.get_json(silent=True) or {}
        with db() as c:
            row = c.execute('SELECT * FROM invoices WHERE id=?', (iid,)).fetchone()
            if not row:
                abort(404)
            old = dict(row)
        currency = str(data.get('currency', old['currency'])).strip()
        if currency not in CURRENCIES:
            return jsonify(error=_t('er_033', locale_now())),400
        client_name = str(data.get('client_name', old['client_name'])).strip()
        client_email = str(data.get('client_email', old['client_email'])).strip()
        client_address = str(data.get('client_address', old['client_address'])).strip()
        project_id = str(data.get('project_id', old['project_id'] or '')).strip()
        lead_id = str(data.get('lead_id', old['lead_id'] or '')).strip()
        status = str(data.get('status', old['status'])).strip()
        issue_date = str(data.get('issue_date', old['issue_date'] or '')).strip()
        due_date = str(data.get('due_date', old['due_date'] or '')).strip()
        notes = str(data.get('notes', old['notes'] or '')).strip()
        terms = str(data.get('terms', old['terms'] or '')).strip()
        if not client_name or len(client_name) > 180:
            return jsonify(error=_t('er_026', locale_now())),400
        if client_email and (not EMAIL_RE.fullmatch(client_email) or len(client_email) > 250):
            return jsonify(error=_t('er_153', locale_now())),400
        if status not in STATUSES:
            return jsonify(error=_t('er_116', locale_now())),400
        try:
            if issue_date:
                date.fromisoformat(issue_date)
            if due_date:
                date.fromisoformat(due_date)
            if issue_date and due_date and due_date < issue_date:
                return jsonify(error=_t('er_036', locale_now())),400
        except:
            return jsonify(error=_t('er_150', locale_now())),400
        if len(notes) > 5000 or len(terms) > 5000:
            return jsonify(error=_t('er_079', locale_now())),400
        with db() as c:
            _cid = _session_cid()
            if project_id:
                _p = c.execute('SELECT client_user_id FROM projects WHERE id=?', (project_id,)).fetchone()
                if not _p or (_cid and _p['client_user_id'] != _cid):
                    return jsonify(error=_t('er_065', locale_now())),400
            if lead_id:
                _l = c.execute('SELECT owner_user_id FROM leads WHERE id=?', (lead_id,)).fetchone()
                if not _l or (_cid and _l['owner_user_id'] != _cid):
                    return jsonify(error=_t('er_063', locale_now())),400
        # Items: if not provided, keep old items; if provided, replace
        if 'items' in data:
            try:
                computed_items, subtotal, discount_minor, tax_minor, total, tax_rate, discount_type, discount_value = validate_and_compute(data, currency)
            except ValueError as e:
                return jsonify(error=str(e)),400
        else:
            # Recompute with old items using new currency/tax/discount if changed
            with db() as c:
                old_items = [dict(r) for r in c.execute('SELECT * FROM invoice_items WHERE invoice_id=?', (iid,))]
            # Transform old items to expected format
            fake_data = {
                'items': [{'description': r['description'], 'quantity': r['quantity'], 'unit_price': str(Decimal(r['unit_minor']) / (10 ** CURRENCIES[old['currency']]))} for r in old_items],
                'tax_rate': data.get('tax_rate', old['tax_rate']),
                'discount_type': data.get('discount_type', old['discount_type']),
                'discount_value': data.get('discount_value', old['discount_value'])
            }
            # Need to handle currency change: unit_minor already in old currency factor; converting via amount?
            # Simplify: if currency changed and items not provided, recompute unit_minor from old amount/quantity
            if currency != old['currency']:
                # Convert unit prices using decimal amounts
                for idx, r in enumerate(old_items):
                    old_factor = 10 ** CURRENCIES[old['currency']]
                    new_factor = 10 ** CURRENCIES[currency]
                    amount_decimal = Decimal(r['unit_minor']) / Decimal(old_factor)
                    fake_data['items'][idx]['unit_price'] = str(amount_decimal)
            try:
                computed_items, subtotal, discount_minor, tax_minor, total, tax_rate, discount_type, discount_value = validate_and_compute(fake_data, currency)
            except ValueError as e:
                return jsonify(error=str(e)),400
        client_user_id = old['client_user_id']
        if client_email:
            with db() as c:
                u = c.execute('SELECT id FROM users WHERE lower(email)=lower(?)', (client_email,)).fetchone()
                client_user_id = u['id'] if u else None
        else:
            client_user_id = None
        stamp = now()
        with db() as c:
            c.execute('UPDATE invoices SET client_name=?,client_email=?,client_address=?,client_user_id=?,project_id=?,lead_id=?,currency=?,status=?,issue_date=?,due_date=?,notes=?,terms=?,tax_rate=?,discount_type=?,discount_value=?,subtotal_minor=?,tax_minor=?,discount_minor=?,total_minor=?,updated=? WHERE id=?',
                      (client_name, client_email.lower() if client_email else '', client_address, client_user_id, project_id or None, lead_id or None, currency, status, issue_date or None, due_date or None, notes, terms, tax_rate, discount_type, discount_value, subtotal, tax_minor, discount_minor, total, stamp, iid))
            if 'items' in data:
                c.execute('DELETE FROM invoice_items WHERE invoice_id=?', (iid,))
                for it in computed_items:
                    c.execute('INSERT INTO invoice_items VALUES(?,?,?,?,?,?,?)', (it['id'], iid, it['description'], it['quantity'], it['unit_minor'], it['amount_minor'], stamp))
        log('invoice', f'Invoice updated: {old["number"]}')
        return jsonify(ok=True)

    @app.delete('/api/invoices/<iid>')
    def delete_invoice(iid):
        if not is_owner():
            return jsonify(error=_t('er_083', locale_now())),401
        with db() as c:
            c.execute('DELETE FROM invoice_items WHERE invoice_id=?', (iid,))
            c.execute('DELETE FROM invoices WHERE id=?', (iid,))
        log('invoice', 'Invoice deleted')
        return jsonify(ok=True)


