"""Focused public landing page for Reachmark's HVAC growth retainer."""
from flask import request, render_template


def register_hvac_growth(app, settings):
    @app.get("/hvac-growth")
    def hvac_growth():
        configured = (settings().get("public_base_url") or "").rstrip("/")
        base = configured or request.url_root.rstrip("/")
        seo = {
            "title": "HVAC Lead Generation & Conversion | Reachmark Digital",
            "description": (
                "Reachmark Digital helps independent HVAC contractors improve local "
                "search visibility, enquiry conversion, and lead follow-up with a "
                "measured monthly growth system."
            ),
            "canonical": base + "/hvac-growth",
            "noindex": False,
        }
        return render_template("hvac-growth.html", seo=seo)
