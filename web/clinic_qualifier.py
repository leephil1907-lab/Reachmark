"""Clinic enquiry qualification rules.

This module classifies appointment intent and operational next steps only. It is
not a clinical triage tool, does not diagnose, and does not replace a clinic's
approved emergency protocol. Callers should collect only the minimum contact
and scheduling details they need.
"""
from __future__ import annotations

import re

# Only clear, potentially life-threatening phrases trigger the emergency handoff.
# This is a conservative safety net, not an exhaustive symptom checker.
_EMERGENCY_PATTERNS = (
    r"\bcan't breathe\b", r"\bcannot breathe\b", r"\bdifficulty breathing\b",
    r"\bnot breathing\b", r"\bunconscious\b", r"\bpassed out and won't wake\b",
    r"\bsevere bleeding\b", r"\bbleeding won't stop\b", r"\bchest pain\b",
    r"\bpossible stroke\b", r"\bface drooping\b", r"\bsudden weakness on one side\b",
)
_APPOINTMENT_PATTERNS = (
    r"\b(book|schedule|make|arrange|reschedule|cancel)\b.{0,45}\b(appointment|visit|consultation|check[- ]?up)\b",
    r"\b(appointment|visit|consultation|check[- ]?up)\b",
    r"\bsee a (doctor|dentist|specialist|clinician)\b",
)
_SERVICE_PATTERNS = (
    r"\b(dental|dentist|teeth|cleaning|check[- ]?up|consultation|physio|physiotherapy|"
    r"vaccination|vaccine|maternity|prenatal|eye test|optometry|dermatology|lab test|"
    r"blood test|screening|therapy|medical certificate|prescription review)\b",
)
_URGENT_PATTERNS = (
    r"\burgent\b", r"\bas soon as possible\b", r"\btoday\b",
    r"\bgetting worse\b", r"\bsevere pain\b",
)


def qualify_clinic_enquiry(*, message="", service="", preferred_time="", contact="",
                           contact_permission=False, urgency=""):
    """Return a deterministic qualification result without clinical diagnosis."""
    text = " ".join(str(value or "") for value in (message, service, urgency)).lower()
    appointment_intent = any(re.search(pattern, text, re.I) for pattern in _APPOINTMENT_PATTERNS)
    service_named = bool(str(service or "").strip()) or any(
        re.search(pattern, text, re.I) for pattern in _SERVICE_PATTERNS
    )
    time_named = bool(str(preferred_time or "").strip()) or bool(
        re.search(r"\b(morning|afternoon|evening|tomorrow|next week|monday|tuesday|wednesday|"
                  r"thursday|friday|saturday|sunday|\d{1,2}(:\d{2})?\s?(am|pm))\b", text, re.I)
    )
    contact_supplied = bool(str(contact or "").strip())
    permission = contact_permission is True or str(contact_permission).strip().lower() in {
        "yes", "true", "1", "granted", "consented"
    }

    emergency = any(re.search(pattern, text, re.I) for pattern in _EMERGENCY_PATTERNS)
    urgent = any(re.search(pattern, text, re.I) for pattern in _URGENT_PATTERNS)

    if emergency:
        return {
            "score": 0,
            "tier": "urgent_safety_handoff",
            "route": "emergency_protocol",
            "priority": "immediate",
            "reasons": ["Message contains language that may indicate a medical emergency."],
            "missing": [],
            "next_action": (
                "Immediately show the clinic's approved emergency instructions and route to trained staff. "
                "If the person may be in immediate danger, tell them to contact local emergency services now. "
                "Do not continue automated qualification or attempt diagnosis."
            ),
            "clinical_assessment": False,
        }

    score = (
        (30 if appointment_intent else 0)
        + (20 if service_named else 0)
        + (15 if time_named else 0)
        + (15 if contact_supplied else 0)
        + (20 if permission else 0)
    )
    missing = []
    if not appointment_intent:
        missing.append("appointment_intent")
    if not service_named:
        missing.append("service")
    if not time_named:
        missing.append("preferred_time")
    if not contact_supplied:
        missing.append("contact")
    if not permission:
        missing.append("contact_permission")

    reasons = []
    if appointment_intent:
        reasons.append("Appointment or visit intent is explicit.")
    if service_named:
        reasons.append("A service or reason for the visit was identified.")
    if time_named:
        reasons.append("A preferred time or timing window was provided.")
    if contact_supplied:
        reasons.append("A contact method was provided.")
    if permission:
        reasons.append("Permission to contact was recorded.")
    if urgent:
        reasons.append("The message requests prompt attention; staff should review timing.")

    if urgent:
        tier, route, priority = "staff_review", "clinic_staff", "high"
        next_action = "Route to trained clinic staff for prompt review; do not promise availability."
    elif score >= 70 and appointment_intent and contact_supplied and permission:
        tier, route, priority = "appointment_ready", "booking_team", "high"
        next_action = "Offer only real available booking slots, confirm the patient's details, and record the outcome."
    elif score >= 40:
        tier, route, priority = "needs_follow_up", "front_desk", "normal"
        next_action = "Ask only for the missing scheduling/contact details, then re-qualify."
    else:
        tier, route, priority = "incomplete", "front_desk", "normal"
        next_action = "Ask one concise question about the visit or the preferred next step."

    return {
        "score": score,
        "tier": tier,
        "route": route,
        "priority": priority,
        "reasons": reasons,
        "missing": missing,
        "next_action": next_action,
        "clinical_assessment": False,
    }
