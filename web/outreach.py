"""Reachmark Digital outreach orchestration.

Reachmark owns campaign state and CRM identity. Email execution is delegated to
Instantly or Smartlead through a small provider adapter layer.
"""
from __future__ import annotations
import hashlib, hmac, os, uuid
from datetime import datetime, timezone
from typing import Any
import requests
from flask import jsonify, request
from web.i18n import t as _t, locale_now

PROVIDERS = ("instantly", "smartlead")

def _now(): return datetime.now(timezone.utc).isoformat()
class ProviderError(RuntimeError): pass
class OutreachProvider:
    name=""; base_url=""
    def __init__(self,api_key): self.api_key=api_key.strip()
    def _request(self,method,path,json_body=None,params=None):
        if not self.api_key: raise ProviderError(f"{self.name.title()} API key is not configured.")
        url=self.base_url.rstrip("/")+"/"+path.lstrip("/"); headers={"Accept":"application/json","Content-Type":"application/json"}
        if self.name=="instantly": headers["Authorization"]=f"Bearer {self.api_key}"
        else: params={**(params or {}),"api_key":self.api_key}
        try:r=requests.request(method,url,json=json_body,params=params,headers=headers,timeout=20)
        except requests.RequestException as exc:raise ProviderError(f"{self.name.title()} request failed: {exc}") from exc
        if r.status_code>=400:raise ProviderError(f"{self.name.title()} returned HTTP {r.status_code}: {r.text[:600]}")
        if not r.content:return {}
        try:return r.json()
        except ValueError:return {"raw":r.text[:2000]}
    def create_campaign(self,name):raise NotImplementedError
    def add_leads(self,campaign_id,leads):raise NotImplementedError
    def start(self,campaign_id):raise NotImplementedError
    def pause(self,campaign_id):raise NotImplementedError
class InstantlyProvider(OutreachProvider):
    name="instantly"; base_url=os.getenv("INSTANTLY_API_BASE","https://api.instantly.ai/api/v2")
    def create_campaign(self,name):return self._request("POST","/campaigns",json_body={"name":name})
    def add_leads(self,campaign_id,leads):return self._request("POST","/leads/list",json_body={"leads":[{"email":x.get("email"),"first_name":x.get("first_name") or "","last_name":x.get("last_name") or "","company_name":x.get("company_name") or "","phone":x.get("phone") or "","website":x.get("website") or "","campaign":campaign_id} for x in leads]})
    def start(self,campaign_id):return self._request("POST",f"/campaigns/{campaign_id}/activate")
    def pause(self,campaign_id):return self._request("POST",f"/campaigns/{campaign_id}/pause")
class SmartleadProvider(OutreachProvider):
    name="smartlead"; base_url=os.getenv("SMARTLEAD_API_BASE","https://server.smartlead.ai/api/v1")
    def create_campaign(self,name):return self._request("POST","/campaigns/create",json_body={"name":name})
    def add_leads(self,campaign_id,leads):return self._request("POST",f"/campaigns/{campaign_id}/leads",json_body={"lead_list":[{"email":x.get("email"),"first_name":x.get("first_name") or "","last_name":x.get("last_name") or "","company_name":x.get("company_name") or "","phone_number":x.get("phone") or "","website":x.get("website") or "","location":x.get("location") or ""} for x in leads]})
    def start(self,campaign_id):return self._request("PATCH",f"/campaigns/{campaign_id}/status",json_body={"status":"START"})
    def pause(self,campaign_id):return self._request("PATCH",f"/campaigns/{campaign_id}/status",json_body={"status":"PAUSED"})
def provider_for(name):
    name=name.lower().strip()
    if name=="instantly":return InstantlyProvider(os.getenv("INSTANTLY_API_KEY",""))
    if name=="smartlead":return SmartleadProvider(os.getenv("SMARTLEAD_API_KEY",""))
    raise ProviderError("Unsupported email provider.")
def _provider_campaign_id(payload):
    if isinstance(payload,dict):
        for key in ("id","campaign_id","campaignId"):
            if payload.get(key) is not None:return str(payload[key])
        for value in payload.values():
            found=_provider_campaign_id(value)
            if found:return found
    return None
def _verify_webhook(provider):
    expected=os.getenv(f"{provider.upper()}_WEBHOOK_SECRET","").strip()
    if not expected:return os.getenv("APP_ENV")!="production"
    supplied=request.headers.get("X-Reachmark-Webhook-Secret") or request.headers.get("X-Webhook-Secret") or ""
    return hmac.compare_digest(supplied,expected)
def _event_id(provider,body):
    raw=str(body.get("event_id") or body.get("id") or body.get("eventId") or "")
    return f"{provider}:{raw or hashlib.sha256(request.get_data()).hexdigest()}"
def register_outreach(app,db,now,log):
    def owner_id():
        from flask import session
        return session.get("client_id") if session.get("role")=="client" else None
    def campaign_row(cid):
        with db() as c:r=c.execute("SELECT * FROM outreach_campaigns WHERE id=? AND owner_user_id IS ?",(cid,owner_id())).fetchone()
        return dict(r) if r else None
    @app.get("/api/outreach/providers")
    def providers():return jsonify(providers=[{"id":p,"name":p.title(),"configured":bool(os.getenv(f"{p.upper()}_API_KEY","").strip())} for p in PROVIDERS])
    @app.get("/api/outreach/campaigns")
    def campaigns():
        with db() as c:rows=c.execute("SELECT * FROM outreach_campaigns WHERE owner_user_id IS ? ORDER BY updated DESC",(owner_id(),)).fetchall()
        return jsonify(campaigns=[dict(r) for r in rows])
    @app.post("/api/outreach/campaigns")
    def create_campaign():
        body=request.get_json(silent=True) or {};name=str(body.get("name") or "").strip()[:160];pname=str(body.get("provider") or "").strip().lower()
        if not name or pname not in PROVIDERS:return jsonify(error="Campaign name and a supported provider are required."),400
        try:remote=provider_for(pname).create_campaign(name)
        except ProviderError as exc:return jsonify(error=str(exc)),502
        remote_id=_provider_campaign_id(remote)
        if not remote_id:return jsonify(error="Provider did not return a campaign id."),502
        cid,stamp=uuid.uuid4().hex,now()
        with db() as c:c.execute("INSERT INTO outreach_campaigns(id,owner_user_id,name,provider,provider_campaign_id,status,stop_on_reply,stop_on_unsubscribe,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)",(cid,owner_id(),name,pname,remote_id,"draft",1,1,stamp,stamp))
        log("outreach",f"Created {pname} campaign {name}");return jsonify(campaign=campaign_row(cid)),201
    @app.post("/api/outreach/campaigns/<cid>/leads")
    def add_leads(cid):
        campaign=campaign_row(cid)
        if not campaign:return jsonify(error="Campaign not found."),404
        body=request.get_json(silent=True) or {};lead_ids=body.get("lead_ids") or []
        if not isinstance(lead_ids,list) or not lead_ids:return jsonify(error="lead_ids must be a non-empty array."),400
        with db() as c:
            ph=",".join("?" for _ in lead_ids);rows=c.execute(f"SELECT id,name,email,phone,website,city FROM leads WHERE id IN ({ph})",tuple(str(x) for x in lead_ids)).fetchall()
        leads=[]
        for row in rows:
            if not row["email"]:continue
            first,_,last=row["name"].partition(" ");leads.append({"email":row["email"],"first_name":first,"last_name":last,"company_name":row["name"],"phone":row["phone"],"website":row["website"],"location":row["city"]})
        if not leads:return jsonify(error="Selected leads have no usable email addresses."),400
        try:provider_for(campaign["provider"]).add_leads(campaign["provider_campaign_id"],leads)
        except ProviderError as exc:return jsonify(error=str(exc)),502
        with db() as c:
            for row in rows:c.execute("INSERT OR IGNORE INTO outreach_enrollments(id,campaign_id,lead_id,status,created,updated) VALUES(?,?,?,?,?,?)",(uuid.uuid4().hex,cid,row["id"],"queued",now(),now()))
            c.execute("UPDATE outreach_campaigns SET updated=? WHERE id=?",(now(),cid))
        return jsonify(added=len(leads),skipped=len(rows)-len(leads))
    def change_status(cid,action,local_status):
        campaign=campaign_row(cid)
        if not campaign:return jsonify(error="Campaign not found."),404
        try:getattr(provider_for(campaign["provider"]),action)(campaign["provider_campaign_id"])
        except ProviderError as exc:return jsonify(error=str(exc)),502
        with db() as c:c.execute("UPDATE outreach_campaigns SET status=?,updated=? WHERE id=?",(local_status,now(),cid))
        return jsonify(campaign=campaign_row(cid))
    @app.post("/api/outreach/campaigns/<cid>/start")
    def start(cid):return change_status(cid,"start","active")
    @app.post("/api/outreach/campaigns/<cid>/pause")
    def pause(cid):return change_status(cid,"pause","paused")
    def webhook(provider):
        if not _verify_webhook(provider):return jsonify(error="Invalid webhook signature."),401
        body=request.get_json(silent=True) or {};raw_type=str(body.get("event_type") or body.get("eventType") or body.get("type") or body.get("event") or "").lower();mapping={"email_sent":"sent","sent":"sent","email_reply":"replied","reply":"replied","replied":"replied","email_bounce":"bounced","bounce":"bounced","bounced":"bounced","lead_unsubscribed":"unsubscribed","unsubscribe":"unsubscribed","unsubscribed":"unsubscribed","email_opened":"opened","opened":"opened","email_clicked":"clicked","clicked":"clicked"};event_type=mapping.get(raw_type,raw_type or "unknown");event_id=_event_id(provider,body);email=str(body.get("email") or body.get("lead_email") or "").strip().lower();campaign_id=str(body.get("campaign_id") or body.get("campaignId") or "");lead_id=str(body.get("lead_id") or body.get("leadId") or "")
        with db() as c:
            inserted=c.execute("INSERT OR IGNORE INTO outreach_events(id,provider,provider_event_id,event_type,provider_campaign_id,provider_lead_id,email,occurred_at,payload,created) VALUES(?,?,?,?,?,?,?,?,?,?)",(uuid.uuid4().hex,provider,event_id,event_type,campaign_id,lead_id,email,str(body.get("timestamp") or body.get("created_at") or now()),request.get_data(as_text=True),now())).rowcount
            if inserted and email and event_type=="unsubscribed":c.execute("INSERT OR IGNORE INTO suppression(email,created) VALUES(?,?)",(email,now()))
            if inserted and email and event_type=="replied":
                c.execute("UPDATE leads SET stage='Replied',updated=? WHERE lower(email)=lower(?)",(now(),email));c.execute("UPDATE outreach_enrollments SET status='replied',updated=? WHERE lead_id IN (SELECT id FROM leads WHERE lower(email)=lower(?))",(now(),email))
        return jsonify(ok=True,duplicate=not bool(inserted)),200
    app.post("/api/webhooks/instantly", endpoint="webhook_instantly")(lambda:webhook("instantly"));app.post("/api/webhooks/smartlead", endpoint="webhook_smartlead")(lambda:webhook("smartlead"))
    from web.revenue_ops import register_revenue_ops
    register_revenue_ops(app,db,now,log)
