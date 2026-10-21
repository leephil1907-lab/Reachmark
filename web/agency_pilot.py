"""Public landing page for Reachmark's bounded agency pilot offer."""
from flask import render_template, request


def register_agency_pilot(app, settings):
    @app.get("/agency-pilot")
    def agency_pilot():
        configured = (settings().get("public_base_url") or "").rstrip("/")
        base = configured or request.url_root.rstrip("/")
        seo = {
            "title": "Agency Prospecting Pilot | Reachmark Digital",
            "description": (
                "Find local businesses with verifiable website issues, create "
                "evidence-backed opportunity reports, and manage approval-first "
                "outreach with Reachmark Digital."
            ),
            "canonical": base + "/agency-pilot",
            "noindex": False,
        }
        return render_template("agency-pilot.html", seo=seo)
