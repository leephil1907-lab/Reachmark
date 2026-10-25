from web.clinic_qualifier import qualify_clinic_enquiry


def test_appointment_ready_requires_intent_contact_and_permission():
    result = qualify_clinic_enquiry(
        message="I'd like to book a dental cleaning appointment",
        service="Dental cleaning",
        preferred_time="Tomorrow morning",
        contact="patient@example.test",
        contact_permission=True,
    )
    assert result["tier"] == "appointment_ready"
    assert result["route"] == "booking_team"
    assert result["score"] == 100
    assert result["clinical_assessment"] is False


def test_missing_permission_prevents_booking_ready_classification():
    result = qualify_clinic_enquiry(
        message="Please book an appointment for a dental check-up",
        service="Dental check-up",
        preferred_time="Friday afternoon",
        contact="patient@example.test",
        contact_permission=False,
    )
    assert result["tier"] != "appointment_ready"
    assert "contact_permission" in result["missing"]


def test_possible_emergency_bypasses_normal_scoring():
    result = qualify_clinic_enquiry(message="I have chest pain and difficulty breathing")
    assert result["tier"] == "urgent_safety_handoff"
    assert result["route"] == "emergency_protocol"
    assert result["priority"] == "immediate"
    assert result["score"] == 0


def test_urgent_request_routes_to_staff_without_claiming_availability():
    result = qualify_clinic_enquiry(
        message="I need an appointment today, please",
        contact="patient@example.test",
        contact_permission=True,
    )
    assert result["route"] == "clinic_staff"
    assert "do not promise availability" in result["next_action"]


def test_incomplete_enquiry_explains_what_is_missing():
    result = qualify_clinic_enquiry(message="Hello, I have a question")
    assert result["tier"] == "incomplete"
    assert "appointment_intent" in result["missing"]
    assert result["clinical_assessment"] is False
