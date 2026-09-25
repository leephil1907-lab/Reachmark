"""Private, branded PDF exports from saved records. No invented legal terms or prices."""
import io,os
from decimal import Decimal
from xml.sax.saxutils import escape
from flask import Response,abort, session
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,KeepTogether,Image
from reportlab.lib.units import mm
from web.operations import CURRENCIES
from web.i18n import t as _t, locale_now
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTDIR=os.path.join(ROOT,'static','pdf-fonts')
pdfmetrics.registerFont(TTFont('Reachmark',os.path.join(FONTDIR,'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('ReachmarkBold',os.path.join(FONTDIR,'DejaVuSans-Bold.ttf')))
pdfmetrics.registerFontFamily('Reachmark',normal='Reachmark',bold='ReachmarkBold',italic='Reachmark',boldItalic='ReachmarkBold')
# Branded logo for PDFs — primary wordmark; fallback to icon if missing
LOGOPATH_PRIMARY=os.path.join(ROOT,'static','reachmark-logo.png')
LOGOPATH_FALLBACK=os.path.join(ROOT,'static','icon-512.png')
LOGOPATH=LOGOPATH_PRIMARY if os.path.exists(LOGOPATH_PRIMARY) else LOGOPATH_FALLBACK
def amount(value,currency,loc='en'):return _t('pdf.tailored',loc) if value is None else f'{currency} {Decimal(value)/(10**CURRENCIES[currency]):,.{CURRENCIES[currency]}f}'
def pdf(title,subtitle,sections,stamp,studio,loc='en'):
    buf=io.BytesIO();styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='RMBody',fontName='Reachmark',fontSize=9.5,leading=15,spaceAfter=9,textColor=colors.HexColor('#30382c'),wordWrap='CJK'))
    styles.add(ParagraphStyle(name='RMTitle',fontName='ReachmarkBold',fontSize=26,leading=32,spaceAfter=14,textColor=colors.HexColor('#26351e')))
    styles.add(ParagraphStyle(name='RMHeading',fontName='ReachmarkBold',fontSize=12,leading=17,spaceBefore=14,spaceAfter=7))
    styles.add(ParagraphStyle(name='RMStudio',fontName='ReachmarkBold',fontSize=10,leading=13,textColor=colors.HexColor('#26351e'),spaceAfter=2))
    def text(value):return escape(str(value or _t('pdf.notrec',loc))).replace('\n','<br/>')
    story=[]
    # Branded header: logo + studio name
    try:
        # Use PNG logo; height ~14mm keeps aspect
        logo=Image(LOGOPATH, width=42*mm, height=10*mm)
        logo.hAlign='LEFT'
        story.append(logo)
        story.append(Spacer(1,4))
    except Exception:
        pass
    story.extend([Paragraph(text(title),styles['RMTitle']),Paragraph(text(subtitle),styles['RMBody']),Paragraph(_t('pdf.gen',loc,s=text(stamp)),styles['RMBody'])])
    for heading,value in sections:story.extend([Paragraph(text(heading),styles['RMHeading']),Paragraph(text(value),styles['RMBody'])])
    def page(canvas,doc):
        # Footer rule and branding
        canvas.setStrokeColor(colors.HexColor('#cce57b'));canvas.setLineWidth(3);canvas.line(42,43,553,43);canvas.setFont('Reachmark',8);canvas.setFillColor(colors.HexColor('#56644a'));canvas.drawString(42,28,'REACHMARK · '+_t('pdf.foot',loc)+' · '+os.getenv('SUPPORT_EMAIL','reachmarkofficial@gmail.com'));canvas.drawRightString(553,28,_t('pdf.page',loc,n=doc.page))
    doc=SimpleDocTemplate(buf,pagesize=(595,842),rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=60,title=title,author=studio)
    doc.build(story,onFirstPage=page,onLaterPages=page);return buf.getvalue()
def register_documents(app,db,now,settings):
    @app.get('/api/documents/<kind>/<record_id>.pdf')
    def export_pdf(kind,record_id):
        loc=locale_now()
        if kind not in ('audit','proposal','contract','brief','invoice'):abort(404)
        if kind=='audit':
            table='leads'
        elif kind=='contract':
            table='contracts'
        elif kind=='invoice':
            table='invoices'
        else:
            table='projects'
        with db() as c:
            row=c.execute('SELECT * FROM '+table+' WHERE id=?',(record_id,)).fetchone()
            if not row:abort(404)
            r=dict(row)
            # Client access check for invoice/proposal/brief
            if session.get('client_id') and session.get('role')=='client' and not session.get('owner'):
                cid=session.get('client_id')
                u=c.execute('SELECT email FROM users WHERE id=?',(cid,)).fetchone()
                user_email=u['email'].lower() if u else ''
                allowed=False
                if kind=='invoice':
                    if r.get('client_user_id')==cid or (not r.get('client_user_id') and r.get('client_email','').lower()==user_email):
                        allowed=True
                elif kind in ('proposal','brief'):
                    if r.get('client_user_id')==cid:
                        allowed=True
                    elif not r.get('client_user_id') and r.get('lead_id'):
                        lead=c.execute('SELECT email FROM leads WHERE id=?',(r.get('lead_id'),)).fetchone()
                        if lead and lead['email'] and lead['email'].strip().lower()==user_email:
                            allowed=True
                elif kind=='audit':
                    own=c.execute('SELECT owner_user_id FROM leads WHERE id=?',(record_id,)).fetchone()
                    if own and own['owner_user_id']==cid:
                        allowed=True
                if not allowed:
                    abort(404)
            client=c.execute('SELECT name,city,address,email FROM leads WHERE id=?',(r.get('lead_id',''),)).fetchone() if kind in ('proposal','brief') and r.get('lead_id') else None
            # If project assigned to a client user, fetch that user's details when lead not linked
            if kind in ('proposal','brief') and r.get('client_user_id') and not client:
                u=c.execute('SELECT name,email FROM users WHERE id=?',(r['client_user_id'],)).fetchone()
                if u:
                    client={'name': u['name'] or r.get('title','Client'), 'city':'', 'address':'', 'email': u['email']}
            review=c.execute('SELECT * FROM lead_reviews WHERE lead_id=?',(record_id,)).fetchone() if kind=='audit' else None
            invoice_items=[]
            if kind=='invoice':
                invoice_items=[dict(x) for x in c.execute('SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY created',(record_id,))]
        if kind=='audit':
            title=_t('pdf.a_title',loc);subtitle=_t('pdf.a_sub',loc,n=r['name'])
            sections=[(_t('pdf.a_s1',loc),f"{r['name']}\n{r['city']}\n{r['address']}\n{_t('pdf.a_src',loc,s=r['source'])}\n{r['source_url']}\n{_t('pdf.a_seen',loc,d=r['source_seen_at'])}"),(_t('pdf.a_s2',loc),f"{_t('pdf.a_url',loc,u=r['website'] or _t('pdf.a_nourl',loc))}\n{_t('pdf.a_status',loc,s=r['status'])}\n{_t('pdf.a_obs',loc,o=r['audit_status'] or _t('wsj.ap_a0',loc))}\n{_t('pdf.a_checked',loc,c=r['checked_at'] or _t('wsj.ap_a0',loc))}\n{r['audit_reason'] or _t('pdf.a_nocheck',loc)}"),(_t('pdf.a_s3',loc),f"{review['verification']}\n{review['note']}\n{review['evidence_url']}\n{_t('pdf.a_rev',loc,d=review['reviewed_at'])}" if review else _t('wsj.pd_norev',loc)),(_t('pdf.a_s4',loc),_t('pdf.a_lim',loc))]
        elif kind=='contract':
            title=_t('pdf.c_title',loc);subtitle=r['title']+' · '+(_t('pdf.c_draft',loc) if r['status'] in ('Draft','Sent') else _t('pdf.c_man',loc,s=r['status']))
            sections=[(_t('pdf.c_s1',loc),r['client']+'\n'+r['email']),(_t('pdf.c_s2',loc),f"{_t('pdf.c_status',loc,s=r['status'])}\n{_t('pdf.c_value',loc,v=amount(r['amount_minor'],r['currency'],loc))}\n{_t('pdf.c_paid',loc,p=amount(r['paid_minor'],r['currency'],loc))}"),(_t('pdf.c_s3',loc),r['notes']),(_t('pdf.c_s4',loc),_t('pdf.c_imp',loc))]
        elif kind=='invoice':
            title=_t('pdf.i_title',loc);subtitle=r['number']+' · '+r['status'] + (_t('pdf.i_draft',loc) if r['status']=='Draft' else '')
            lines=[]
            for idx,it in enumerate(invoice_items,1):
                decimals=CURRENCIES[r['currency']]
                unit = Decimal(it['unit_minor']) / (10**decimals) if decimals else Decimal(it['unit_minor'])
                amt = Decimal(it['amount_minor']) / (10**decimals) if decimals else Decimal(it['amount_minor'])
                unit_str = f"{r['currency']} {unit:,.{decimals}f}" if decimals else f"{r['currency']} {unit:,}"
                amt_str = f"{r['currency']} {amt:,.{decimals}f}" if decimals else f"{r['currency']} {amt:,}"
                lines.append(f"{idx}. {it['description']}  —  {it['quantity']} × {unit_str} = {amt_str}")
            items_text='\n'.join(lines) if lines else _t('pdf.i_noitems',loc)
            sub = amount(r['subtotal_minor'], r['currency'], loc)
            disc = amount(r['discount_minor'], r['currency'], loc)
            tax = amount(r['tax_minor'], r['currency'], loc)
            total = amount(r['total_minor'], r['currency'], loc)
            sections=[(_t('pdf.i_s1',loc),f"{r['client_name']}\n{r['client_email']}\n{r['client_address']}"),(_t('pdf.i_s2',loc),f"{_t('pdf.i_num',loc,n=r['number'])}\n{_t('pdf.i_status',loc,s=r['status'])}\n{_t('pdf.i_cur',loc,c=r['currency'])}\n{_t('pdf.i_issue',loc,d=r['issue_date'] or _t('wsj.iv_notset',loc))}\n{_t('pdf.i_due',loc,d=r['due_date'] or _t('wsj.iv_notset',loc))}\n{_t('pdf.i_proj',loc,p=r['project_id'] or _t('ws.iv_nolink',loc))}\n{_t('pdf.i_biz',loc,b=r['lead_id'] or _t('ws.iv_nolink',loc))}"),(_t('pdf.i_s3',loc),items_text),(_t('pdf.i_s4',loc),f"{_t('pdf.i_sub',loc,s=sub)}\n{_t('pdf.i_disc',loc,t=r['discount_type'],v=r['discount_value'],d=disc)}\n{_t('pdf.i_tax',loc,r=r['tax_rate'],t=tax)}\n{_t('pdf.i_total',loc,t=total)}"),(_t('pdf.i_s5',loc),r['notes'] or '—'),(_t('pdf.i_s6',loc),r['terms'] or _t('pdf.i_terms',loc))]
        else:
            title=_t('pdf.p_title',loc) if kind=='proposal' else _t('pdf.p_brief',loc);subtitle=r['title']+' · '+_t('pdf.p_draft',loc)
            client_text=f"{client['name']}\n{client['city']}\n{client['address']}\n{client['email']}" if client else _t('pdf.p_nobiz',loc)
            sections=[(_t('pdf.p_s1',loc),client_text),(_t('pdf.p_s2',loc),f"{_t('pdf.p_stage',loc,s=r['stage'])}\n{_t('pdf.p_lead',loc,r=r['lead_id'] or _t('ws.iv_nolink',loc))}\n{_t('pdf.p_contract',loc,r=r['contract_id'] or _t('ws.iv_nolink',loc))}\n{_t('pdf.p_assigned',loc,c=r.get('client_user_id') or _t('pdf.p_noassign',loc))}"),(_t('pdf.p_s3',loc),r['scope']),(_t('pdf.p_s4',loc),amount(r['quote_minor'],r['currency'],loc)),(_t('pdf.p_s5',loc),f"{r['next_action'] or _t('wsj.iv_notset',loc)}\n{_t('pdf.p_due',loc,d=r['due_date'] or _t('wsj.iv_notset',loc))}"),(_t('pdf.p_s6',loc),_t('pdf.p_terms',loc))]
        content=pdf(title,subtitle,sections,now(),settings()['agency'] or 'Reachmark Studio',loc=loc)
        return Response(content,mimetype='application/pdf',headers={'Content-Disposition':f'attachment; filename="reachmark-{kind}-{record_id[:12]}.pdf"','Cache-Control':'no-store'})
