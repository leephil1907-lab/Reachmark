"""Add Admin › Activity strings to every locale (idempotent)."""
import json, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2] / 'static' / 'locales'
K = {
 'ws.n_activity':   ['Activity','Actividad','Activité','Aktivität','Atividade','动态'],
 'ws.act_k':        ['Admin · live','Admin · en vivo','Admin · en direct','Admin · live','Admin · ao vivo','管理 · 实时'],
 'ws.act_h':        ['Website activity','Actividad del sitio','Activité du site','Website-Aktivität','Atividade do site','网站动态'],
 'ws.act_p':        ['Sign-ups, sign-ins, enquiries, payments and front-desk hand-offs, recorded as they happen.','Registros, inicios de sesión, consultas, pagos y derivaciones de recepción, registrados al momento.','Inscriptions, connexions, demandes, paiements et transferts de l’accueil, enregistrés en temps réel.','Registrierungen, Anmeldungen, Anfragen, Zahlungen und Übergaben vom Empfang – sofort erfasst.','Cadastros, entradas, pedidos, pagamentos e encaminhamentos da recepção, registrados na hora.','注册、登录、咨询、付款和前台转接，实时记录。'],
 'ws.act_live':     ['Live','En vivo','En direct','Live','Ao vivo','实时'],
 'ws.act_users':    ['Total users','Usuarios totales','Utilisateurs','Nutzer gesamt','Usuários no total','用户总数'],
 'ws.act_today':    ['New today','Nuevos hoy','Nouveaux aujourd’hui','Neu heute','Novos hoje','今日新增'],
 'ws.act_week':     ['New this week','Nuevos esta semana','Nouveaux cette semaine','Neu diese Woche','Novos nesta semana','本周新增'],
 'ws.act_verified': ['Verified emails','Correos verificados','E-mails vérifiés','Bestätigte E-Mails','E-mails verificados','已验证邮箱'],
 'ws.act_paying':   ['Paying customers','Clientes de pago','Clients payants','Zahlende Kunden','Clientes pagantes','付费客户'],
 'ws.act_visits':   ['Visits · 7 days','Visitas · 7 días','Visites · 7 jours','Besuche · 7 Tage','Visitas · 7 dias','访问 · 7天'],
 'ws.act_checks':   ['Free checks · 7 days','Revisiones gratis · 7 días','Analyses gratuites · 7 jours','Gratis-Checks · 7 Tage','Verificações grátis · 7 dias','免费检测 · 7天'],
 'ws.act_enquiries':['Enquiries · 7 days','Consultas · 7 días','Demandes · 7 jours','Anfragen · 7 Tage','Pedidos · 7 dias','咨询 · 7天'],
 'ws.act_signups':  ['Recent sign-ups','Registros recientes','Inscriptions récentes','Neueste Registrierungen','Cadastros recentes','最近注册'],
 'ws.act_manage':   ['Manage users','Gestionar usuarios','Gérer les utilisateurs','Nutzer verwalten','Gerir usuários','管理用户'],
 'ws.act_feed':     ['Live activity','Actividad en vivo','Activité en direct','Live-Aktivität','Atividade ao vivo','实时动态'],
 'ws.act_filter':   ['Filter activity','Filtrar actividad','Filtrer l’activité','Aktivität filtern','Filtrar atividade','筛选动态'],
 'ws.act_f_all':    ['All','Todo','Tout','Alle','Tudo','全部'],
 'ws.act_f_acct':   ['Accounts','Cuentas','Comptes','Konten','Contas','账户'],
 'ws.act_f_pay':    ['Payments','Pagos','Paiements','Zahlungen','Pagamentos','付款'],
 'ws.act_f_enq':    ['Enquiries','Consultas','Demandes','Anfragen','Pedidos','咨询'],
 'ws.act_f_site':   ['Website','Sitio web','Site web','Website','Site','网站'],
 'ws.act_now':      ['just now','ahora mismo','à l’instant','gerade eben','agora mesmo','刚刚'],
 'ws.act_min':      ['{n} min ago','hace {n} min','il y a {n} min','vor {n} Min.','há {n} min','{n} 分钟前'],
 'ws.act_hr':       ['{n} h ago','hace {n} h','il y a {n} h','vor {n} Std.','há {n} h','{n} 小时前'],
 'ws.act_day':      ['{n} d ago','hace {n} d','il y a {n} j','vor {n} T.','há {n} d','{n} 天前'],
 'ws.act_nosign_t': ['No sign-ups yet','Aún no hay registros','Pas encore d’inscriptions','Noch keine Registrierungen','Ainda sem cadastros','暂无注册'],
 'ws.act_nosign_d': ['New accounts appear here the moment someone signs up.','Las cuentas nuevas aparecen aquí en cuanto alguien se registra.','Les nouveaux comptes apparaissent ici dès qu’une personne s’inscrit.','Neue Konten erscheinen hier, sobald sich jemand registriert.','Novas contas aparecem aqui assim que alguém se cadastra.','有人注册后，新账户会立即显示在这里。'],
 'ws.act_c_who':    ['Person','Persona','Personne','Person','Pessoa','用户'],
 'ws.act_c_joined': ['Joined','Alta','Inscrit','Beigetreten','Entrou','加入时间'],
 'ws.act_c_status': ['Status','Estado','Statut','Status','Estado','状态'],
 'ws.act_free':     ['Free','Gratis','Gratuit','Kostenlos','Grátis','免费'],
 'ws.act_ver':      ['Verified','Verificado','Vérifié','Bestätigt','Verificado','已验证'],
 'ws.act_unver':    ['Unverified','Sin verificar','Non vérifié','Unbestätigt','Não verificado','未验证'],
 'ws.act_new':      ['New','Nuevo','Nouveau','Neu','Novo','新'],
 'ws.act_noname':   ['No name given','Sin nombre','Sans nom','Kein Name angegeben','Sem nome','未填写姓名'],
 'ws.act_nofeed_t': ['Nothing here yet','Aún no hay nada','Rien pour l’instant','Noch nichts hier','Ainda não há nada','暂无内容'],
 'ws.act_nofeed_d': ['Sign-ups, sign-ins, enquiries, payments and front-desk hand-offs are recorded here as they happen.','Registros, inicios de sesión, consultas, pagos y derivaciones de recepción se registran aquí al momento.','Inscriptions, connexions, demandes, paiements et transferts de l’accueil sont enregistrés ici en temps réel.','Registrierungen, Anmeldungen, Anfragen, Zahlungen und Übergaben vom Empfang werden hier sofort erfasst.','Cadastros, entradas, pedidos, pagamentos e encaminhamentos da recepção são registrados aqui na hora.','注册、登录、咨询、付款和前台转接会实时记录在这里。'],
 'ws.act_toast':    ['New sign-up: {who}','Nuevo registro: {who}','Nouvelle inscription : {who}','Neue Registrierung: {who}','Novo cadastro: {who}','新注册：{who}'],
 'ws.act_updated':  ['Live · updated {t}','En vivo · actualizado {t}','En direct · mis à jour {t}','Live · aktualisiert {t}','Ao vivo · atualizado {t}','实时 · 更新于 {t}'],
 'wsj.t_t12':      ['Website activity','Actividad del sitio','Activité du site','Website-Aktivität','Atividade do site','网站动态'],
 'wsj.t_b12':      ['Sign-ups, sign-ins, enquiries and payments appear here as they happen. The console opens on this page.','Registros, inicios de sesión, consultas y pagos aparecen aquí al momento. La consola se abre en esta página.','Inscriptions, connexions, demandes et paiements s’affichent ici en temps réel. La console s’ouvre sur cette page.','Registrierungen, Anmeldungen, Anfragen und Zahlungen erscheinen hier sofort. Die Konsole öffnet sich auf dieser Seite.','Cadastros, entradas, pedidos e pagamentos aparecem aqui na hora. O console abre nesta página.','注册、登录、咨询和付款会实时显示在这里。控制台默认打开此页面。'],
 'ws.act_refreshed':['Activity is up to date.','La actividad está al día.','L’activité est à jour.','Aktivität ist aktuell.','A atividade está atualizada.','动态已是最新。'],
}
for i, loc in enumerate(['en','es','fr','de','pt','zh']):
    p = ROOT / f'{loc}.json'
    raw = p.read_text(encoding='utf-8')
    d = json.loads(raw)
    for k, vals in K.items():
        d[k] = vals[i]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('added', len(K), 'keys to 6 locales')
