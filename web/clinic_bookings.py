"""Database-backed clinic appointment availability and consent-aware intake.

Only owner-configured slots are advertised. This module never invents open times
and does not claim an appointment is confirmed unless a configured slot is atomically
reserved. Clinical language is routed to staff; it is not diagnosis or triage.
"""
import hashlib
import re
import uuid
from datetime import datetime, timezone
from flask import jsonify, request, session


def _parse_time(value):
    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def register_clinic_bookings(app, db, now, log):
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS clinic_slots(
            id TEXT PRIMARY KEY, start TEXT NOT NULL, end TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'available', created TEXT NOT NULL)""")
        c.execute("CREATE INDEX IF NOT EXISTS clinic_slots_status_start ON clinic_slots(status,start)")
        c.execute("""CREATE TABLE IF NOT EXISTS clinic_appointments(
            id TEXT PRIMARY KEY, slot_id TEXT, name TEXT NOT NULL, email TEXT NOT NULL,
            phone TEXT DEFAULT '', service TEXT DEFAULT '', note TEXT DEFAULT '',
            consent INTEGER NOT NULL, consent_at TEXT NOT NULL, status TEXT NOT NULL,
            route TEXT NOT NULL, fingerprint TEXT NOT NULL, created TEXT NOT NULL,
            updated TEXT NOT NULL, FOREIGN KEY(slot_id) REFERENCES clinic_slots(id))""")
        c.execute("CREATE INDEX IF NOT EXISTS clinic_appt_email_created ON clinic_appointments(email,created)")
        c.execute("CREATE INDEX IF NOT EXISTS clinic_appt_status_created ON clinic_appointments(status,created)")

    @app.route('/api/clinic/availability', methods=['GET'])
    def clinic_availability():
        start = datetime.now(timezone.utc).isoformat()
        with db() as c:
            slots = [dict(r) for r in c.execute(
                "SELECT id,start,end FROM clinic_slots WHERE status='available' AND start>? ORDER BY start LIMIT 100",
                (start,))]
        return jsonify(ok=True, configured=bool(slots), slots=slots,
                       message=None if slots else
                       "No future appointment slots are configured. Contact the clinic to confirm availability.")

    @app.route('/api/clinic/slots', methods=['POST'])
    def clinic_create_slot():
        if not session.get('owner'):
            return jsonify(error="Owner sign-in required."), 401
        data = request.get_json(silent=True) or {}
        start, end = _parse_time(data.get('start')), _parse_time(data.get('end'))
        if not start or not end or start <= datetime.now(timezone.utc) or end <= start:
            return jsonify(error="Provide a future start and a later end, including timezone."), 400
        sid = uuid.uuid4().hex
        stamp = now()
        with db() as c:
            clash = c.execute("""SELECT 1 FROM clinic_slots
                WHERE status='available' AND start < ? AND end > ? LIMIT 1""",
                (end.isoformat(), start.isoformat())).fetchone()
            if clash:
                return jsonify(error="This time overlaps an available slot."), 409
            c.execute("INSERT INTO clinic_slots(id,start,end,status,created) VALUES(?,?,?,'available',?)",
                      (sid, start.isoformat(), end.isoformat(), stamp))
        return jsonify(ok=True, slot={"id": sid, "start": start.isoformat(), "end": end.isoformat()}), 201

    @app.route('/api/clinic/appointments', methods=['POST'])
    def clinic_book_appointment():
        data = request.get_json(silent=True) or {}
        consent = data.get('consent') is True
        if not consent:
            return jsonify(error="Explicit consent is required before submitting an appointment request."), 400
        name = str(data.get('name') or '').strip()[:120]
        email = str(data.get('email') or '').strip().lower()[:250]
        phone = str(data.get('phone') or '').strip()[:40]
        service = str(data.get('service') or '').strip()[:160]
        note = str(data.get('note') or '').strip()[:1000]
        slot_id = str(data.get('slot_id') or '').strip()[:64]
        message = " ".join((service, note))
        if len(name) < 2 or not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", email):
            return jsonify(error="Enter a valid name and email address."), 400

        from web.clinic_qualifier import qualify_clinic_enquiry
        result = qualify_clinic_enquiry(message=message, service=service, contact=email,
                                        contact_permission=True)
        # Safety handoff is never silently turned into a normal booking.
        if result['route'] == 'emergency_protocol':
            return jsonify(ok=False, handoff=True, route=result['route'],
                           next_action=result['next_action'], clinical_assessment=False), 202

        stamp = now()
        fingerprint = hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest()[:32]
        appointment_id = uuid.uuid4().hex
        try:
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
                existing = c.execute("""SELECT id,status FROM clinic_appointments
                    WHERE lower(email)=? AND slot_id=? AND status IN ('pending','confirmed')
                    ORDER BY created DESC LIMIT 1""", (email, slot_id)).fetchone()
                if existing:
                    c.rollback()
                    return jsonify(ok=True, duplicate=True, appointment_id=existing['id'],
                                   status=existing['status'],
                                   message="An appointment request for this email and slot already exists."), 200
                slot = c.execute("SELECT * FROM clinic_slots WHERE id=? AND status='available'", (slot_id,)).fetchone()
                if not slot or (_parse_time(slot['start']) or datetime.min.replace(tzinfo=timezone.utc)) <= datetime.now(timezone.utc):
                    c.rollback()
                    return jsonify(error="That slot is no longer available. Refresh availability and choose another time.",
                                   code="slot_unavailable"), 409
                c.execute("UPDATE clinic_slots SET status='reserved' WHERE id=? AND status='available'", (slot_id,))
                if c.execute("SELECT changes()").fetchone()[0] != 1:
                    c.rollback()
                    return jsonify(error="That slot was just taken. Refresh availability.", code="slot_unavailable"), 409
                c.execute("""INSERT INTO clinic_appointments
                    (id,slot_id,name,email,phone,service,note,consent,consent_at,status,route,fingerprint,created,updated)
                    VALUES(?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)""",
                    (appointment_id, slot_id, name, email, phone, service, note, 1, stamp,
                     'booking_team', fingerprint, stamp, stamp))
                c.commit()
        except Exception:
            try:
                c.rollback()
            except Exception:
                pass
            raise
        log('clinic_booking', 'Appointment request saved for staff confirmation')
        return jsonify(ok=True, appointment_id=appointment_id, status='pending',
                       message="Your request is received, not yet confirmed. The clinic must confirm it."), 201

    @app.route('/api/clinic/staff-queue', methods=['GET'])
    def clinic_staff_queue():
        if not session.get('owner'):
            return jsonify(error="Owner sign-in required."), 401
        with db() as c:
            rows = [dict(r) for r in c.execute("""SELECT id,slot_id,name,email,phone,service,note,
                consent,consent_at,status,route,created,updated FROM clinic_appointments
                ORDER BY created DESC LIMIT 100""")]
        return jsonify(appointments=rows)

    @app.route('/api/clinic/appointments/<appointment_id>', methods=['PATCH'])
    def clinic_update_appointment(appointment_id):
        if not session.get('owner'):
            return jsonify(error="Owner sign-in required."), 401
        data = request.get_json(silent=True) or {}
        status = str(data.get('status') or '')
        if status not in ('confirmed', 'cancelled', 'completed'):
            return jsonify(error="Status must be confirmed, cancelled, or completed."), 400
        with db() as c:
            row = c.execute("SELECT * FROM clinic_appointments WHERE id=?", (appointment_id,)).fetchone()
            if not row:
                return jsonify(error="Appointment request not found."), 404
            c.execute("UPDATE clinic_appointments SET status=?,updated=? WHERE id=?", (status, now(), appointment_id))
            if status == 'cancelled' and row['slot_id']:
                c.execute("UPDATE clinic_slots SET status='available' WHERE id=? AND status='reserved'", (row['slot_id'],))
        return jsonify(ok=True, appointment_id=appointment_id, status=status)
