"""Bounded Streamable HTTP MCP client. No stdio processes, arbitrary code, or automatic retries."""
import ipaddress, json, socket, time, uuid
from web.i18n import t as _t, locale_now
from urllib.parse import urlparse
import urllib3

SUPPORTED=('2025-06-18','2025-03-26','2025-11-25')
MAX_BYTES=1024*1024
class MCPError(Exception): pass

def validate_endpoint(url):
    try: p=urlparse(url)
    except ValueError: raise MCPError(_t('er_044', locale_now()))
    try:
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or (p.port and p.port!=443):
            raise MCPError(_t('er_151', locale_now()))
    except ValueError: raise MCPError(_t('er_054', locale_now()))
    if p.hostname.lower() in ('localhost','localhost.localdomain'): raise MCPError(_t('er_066', locale_now()))
    try:
        if not ipaddress.ip_address(p.hostname).is_global: raise MCPError(_t('er_088', locale_now()))
    except ValueError: pass
    return p

def public_ip(host):
    try: addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    except OSError: raise MCPError(_t('er_123', locale_now()))
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses): raise MCPError(_t('er_089', locale_now()))
    return addresses[0]

def matching(payload, rid):
    messages=payload if isinstance(payload,list) else [payload]
    for msg in messages:
        if isinstance(msg,dict) and msg.get('id')==rid and ('result' in msg or 'error' in msg): return msg
    return None

class MCPClient:
    def __init__(self,url,token=''):
        self.url=url;self.token=token;self.session=None;self.version=SUPPORTED[0];self.server={}
    def redact(self,text): return str(text).replace(self.token,'[REDACTED]') if self.token else str(text)
    def post(self,method,params=None,notification=False):
        p=validate_endpoint(self.url);host=p.hostname.encode('idna').decode();ip=public_ip(host)
        rid=None if notification else uuid.uuid4().hex
        message={'jsonrpc':'2.0','method':method}
        if rid: message['id']=rid
        if params is not None: message['params']=params
        headers={'Host':host,'Content-Type':'application/json','Accept':'application/json, text/event-stream','Accept-Encoding':'identity','User-Agent':'Reachmark-MCP/1.0','MCP-Protocol-Version':self.version}
        if self.session: headers['Mcp-Session-Id']=self.session
        if self.token: headers['Authorization']='Bearer '+self.token
        pool=urllib3.HTTPSConnectionPool(ip,port=443,server_hostname=host,assert_hostname=host,cert_reqs='CERT_REQUIRED',retries=False,timeout=urllib3.Timeout(connect=8,read=35))
        response=None
        try:
            response=pool.urlopen('POST',p.path or '/',body=json.dumps(message).encode(),headers=headers,preload_content=False,redirect=False)
            if response.status>=300:
                if response.status in (401,403): raise MCPError(_t('er_068', locale_now()))
                if response.status in (301,302,303,307,308): raise MCPError(_t('er_039', locale_now()))
                raise MCPError(_t('er_070', locale_now(), s=response.status))
            if notification:
                if response.status not in (200,202,204): raise MCPError(_t('er_131', locale_now()))
                return None
            if response.headers.get('Mcp-Session-Id'):
                session=response.headers['Mcp-Session-Id']
                if len(session)>1024 or any(ord(c)<33 or ord(c)>126 for c in session): raise MCPError(_t('er_111', locale_now()))
                self.session=session
            content_type=response.headers.get('Content-Type','').lower()
            if 'text/event-stream' in content_type:
                buffer=b'';total=0;started=time.monotonic();found=None
                while time.monotonic()-started<60:
                    part=response.read1(4096,decode_content=False)
                    if not part: break
                    total+=len(part)
                    if total>MAX_BYTES: raise MCPError(_t('er_069', locale_now()))
                    buffer+=part;buffer=buffer.replace(b'\r\n',b'\n')
                    while b'\n\n' in buffer:
                        event,buffer=buffer.split(b'\n\n',1)
                        data=b'\n'.join(line[5:].lstrip() for line in event.split(b'\n') if line.startswith(b'data:'))
                        if not data: continue
                        found=matching(json.loads(data.decode('utf-8')),rid)
                        if found: break
                    if found: break
                if not found: raise MCPError(_t('er_075', locale_now()))
                msg=found
            elif 'application/json' in content_type:
                raw=response.read(MAX_BYTES+1,decode_content=False)
                if len(raw)>MAX_BYTES: raise MCPError(_t('er_069', locale_now()))
                msg=matching(json.loads(raw.decode('utf-8')),rid)
                if not msg: raise MCPError(_t('er_122', locale_now()))
            else: raise MCPError(_t('er_137', locale_now()))
            if 'error' in msg:
                detail=msg['error'].get('message','Protocol error') if isinstance(msg['error'],dict) else 'Protocol error'
                raise MCPError(self.redact(str(detail))[:500])
            return msg.get('result',{})
        except MCPError: raise
        except (urllib3.exceptions.HTTPError,OSError,ValueError,UnicodeError): raise MCPError(_t('er_121', locale_now()))
        finally:
            if response: response.close()
            pool.close()
    def initialize(self):
        result=self.post('initialize',{'protocolVersion':SUPPORTED[0],'capabilities':{},'clientInfo':{'name':'Reachmark','version':'1.0.0'}})
        if not isinstance(result,dict) or result.get('protocolVersion') not in SUPPORTED: raise MCPError(_t('er_132', locale_now(), v=', '.join(SUPPORTED)))
        self.version=result['protocolVersion'];self.server=result.get('serverInfo',{})
        capabilities=result.get('capabilities',{})
        if not isinstance(capabilities,dict) or 'tools' not in capabilities: raise MCPError(_t('er_141', locale_now()))
        self.post('notifications/initialized',notification=True)
        return self.server
    def list_tools(self):
        tools=[];cursor=None
        for _ in range(10):
            result=self.post('tools/list',{'cursor':cursor} if cursor else {})
            if not isinstance(result,dict) or not isinstance(result.get('tools'),list): raise MCPError(_t('er_133', locale_now()))
            tools.extend(result['tools'])
            if len(tools)>200: raise MCPError(_t('er_136', locale_now()))
            cursor=result.get('nextCursor')
            if not cursor: return tools
        raise MCPError(_t('er_145', locale_now()))
    def call(self,name,arguments):
        return self.post('tools/call',{'name':name,'arguments':arguments})
