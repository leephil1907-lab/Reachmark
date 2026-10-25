"""Integration tests for clinic availability, consent, duplicates and staff routing."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import tests.test_app as test_app


class ClinicBookingTests(test_app.ProspectTests):
    def _future_slot(self):
        start = datetime.now(timezone.utc) + timedelta(days=3)
        end = start + timedelta(minutes=30)
        with test_app.module.db() as c:
            c.execute("INSERT INTO clinic_slots(id,start,end,status,created) VALUES(?,?,?,'available',?)",
                      ("test-slot", start.isoformat(), end.isoformat(), start.isoformat()))
        return start, end

    def test_availability_never_invents_slots(self):
        response = self.client.get('/api/clinic/availability')
        assert response.status_code == 200
        assert response.json['slots'] == []
        assert response.json['configured'] is False

    def test_booking_requires_explicit_consent(self):
        self._future_slot()
        response = self.client.post('/api/clinic/appointments', json={
            'slot_id':'test-slot','name':'Test Patient','email':'patient@example.test',
            'service':'Dental check-up','consent':False
        })
        assert response.status_code == 400
        with test_app.module.db() as c:
            assert c.execute("SELECT count(*) FROM clinic_appointments").fetchone()[0] == 0

    def test_slot_is_reserved_and_duplicate_request_is_idempotent(self):
        self._future_slot()
        payload = {'slot_id':'test-slot','name':'Test Patient','email':'patient@example.test',
                   'service':'Dental cleaning','consent':True}
        first = self.client.post('/api/clinic/appointments', json=payload)
        assert first.status_code == 201
        assert first.json['status'] == 'pending'
        assert 'not yet confirmed' in first.json['message']
        second = self.client.post('/api/clinic/appointments', json=payload)
        assert second.status_code == 200
        assert second.json['duplicate'] is True
        with test_app.module.db() as c:
            assert c.execute("SELECT count(*) FROM clinic_appointments").fetchone()[0] == 1
            assert c.execute("SELECT status FROM clinic_slots WHERE id='test-slot'").fetchone()[0] == 'reserved'

    def test_taken_slot_cannot_be_booked_by_another_patient(self):
        self._future_slot()
        first = self.client.post('/api/clinic/appointments', json={
            'slot_id':'test-slot','name':'Patient One','email':'one@example.test',
            'service':'Consultation','consent':True})
        assert first.status_code == 201
        second = self.client.post('/api/clinic/appointments', json={
            'slot_id':'test-slot','name':'Patient Two','email':'two@example.test',
            'service':'Consultation','consent':True})
        assert second.status_code == 409
        assert second.json['code'] == 'slot_unavailable'

    def test_staff_queue_requires_owner_and_can_confirm_booking(self):
        self._future_slot()
        result = self.client.post('/api/clinic/appointments', json={
            'slot_id':'test-slot','name':'Test Patient','email':'patient@example.test',
            'service':'Dental cleaning','consent':True})
        assert result.status_code == 201
        assert self.client.get('/api/clinic/staff-queue').status_code == 401
        with self.client.session_transaction() as sess:
            sess['owner'] = True
        queue = self.client.get('/api/clinic/staff-queue')
        assert queue.status_code == 200
        assert queue.json['appointments'][0]['consent'] == 1
        confirm = self.client.patch('/api/clinic/appointments/' + result.json['appointment_id'],
                                    json={'status':'confirmed'})
        assert confirm.status_code == 200
        assert confirm.json['status'] == 'confirmed'

    def test_emergency_language_bypasses_normal_booking(self):
        self._future_slot()
        result = self.client.post('/api/clinic/appointments', json={
            'slot_id':'test-slot','name':'Test Patient','email':'patient@example.test',
            'service':'Dental cleaning','note':'I have chest pain and difficulty breathing',
            'consent':True})
        assert result.status_code == 202
        assert result.json['handoff'] is True
        with test_app.module.db() as c:
            assert c.execute("SELECT count(*) FROM clinic_appointments").fetchone()[0] == 0


    def test_urgent_request_is_saved_for_staff_not_auto_booked(self):
        self._future_slot()
        result = self.client.post('/api/clinic/appointments', json={
            'slot_id':'test-slot','name':'Test Patient','email':'patient@example.test',
            'service':'Dental consultation','note':'I need this today',
            'consent':True})
        assert result.status_code == 202
        assert result.json['handoff'] is True
        assert result.json['route'] == 'clinic_staff'
        with test_app.module.db() as c:
            assert c.execute("SELECT count(*) FROM clinic_appointments").fetchone()[0] == 0
            assert c.execute("SELECT count(*) FROM clinic_handoffs WHERE route='clinic_staff'").fetchone()[0] == 1

    def test_public_booking_page_renders(self):
        response = self.client.get('/clinic/book')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert 'clinic-booking.js' in html
        assert 'not confirmed until clinic staff confirm it' in html
        assert 'name="consent"' in html


    def test_owner_configures_slot_and_public_availability_reads_it(self):
        start = datetime.now(timezone.utc) + timedelta(days=5)
        end = start + timedelta(minutes=30)
        with self.client.session_transaction() as sess:
            sess['owner'] = True
        created = self.client.post('/api/clinic/slots', json={
            'start':start.isoformat(),'end':end.isoformat()})
        assert created.status_code == 201
        availability = self.client.get('/api/clinic/availability')
        assert availability.status_code == 200
        assert len(availability.json['slots']) == 1
        assert availability.json['slots'][0]['id'] == created.json['slot']['id']

    def test_slot_configuration_rejects_overlapping_open_times(self):
        start, end = self._future_slot()
        with self.client.session_transaction() as sess:
            sess['owner'] = True
        result = self.client.post('/api/clinic/slots', json={
            'start':(start + timedelta(minutes=10)).isoformat(),
            'end':(end + timedelta(minutes=10)).isoformat()})
        assert result.status_code == 409
