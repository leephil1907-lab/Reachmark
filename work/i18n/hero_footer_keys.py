import json, collections, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
K = {
'home.hx_live': ["Live website audits for designers, studios and freelancers","Auditorías web en vivo para diseñadores, estudios y freelancers","Audits de sites en direct pour designers, studios et freelances","Live-Website-Audits für Designer, Studios und Freelancer","Auditorias de sites ao vivo para designers, estúdios e freelancers","面向设计师、工作室和自由职业者的实时网站审查"],
'home.hx_h1a': ["Turn weak local websites","Convierte webs locales débiles","Transformez les sites locaux faibles","Machen Sie aus schwachen lokalen Websites","Transforme sites locais fracos","把薄弱的本地网站"],
'home.hx_h1b': ["into your next clients.","en tus próximos clientes.","en vos prochains clients.","Ihre nächsten Kunden.","nos seus próximos clientes.","变成你的下一个客户。"],
'home.hx_sub': ["Reachmark finds local businesses whose websites are costing them customers, measures exactly what is broken, and hands you a clear report and a ready-to-send email. Nothing goes out until you approve it.",
 "Reachmark encuentra negocios locales cuya web les está costando clientes, mide exactamente qué falla y te entrega un informe claro y un correo listo para enviar. Nada sale sin tu aprobación.",
 "Reachmark trouve les entreprises locales dont le site leur fait perdre des clients, mesure précisément ce qui ne va pas et vous remet un rapport clair et un e-mail prêt à envoyer. Rien ne part sans votre accord.",
 "Reachmark findet lokale Unternehmen, deren Website sie Kunden kostet, misst genau, was nicht funktioniert, und liefert Ihnen einen klaren Bericht und eine versandfertige E-Mail. Nichts wird ohne Ihre Freigabe gesendet.",
 "A Reachmark encontra empresas locais cujo site está custando clientes, mede exatamente o que está errado e entrega a você um relatório claro e um e-mail pronto para enviar. Nada é enviado sem a sua aprovação.",
 "Reachmark 帮你找到网站正在流失客户的本地商家，精确测量问题所在，并为你准备清晰的报告和可直接发送的邮件。未经你批准，任何内容都不会发出。"],
'home.hx_cta': ["Run a free website check","Haz una revisión web gratis","Lancer une vérification gratuite","Kostenlosen Website-Check starten","Fazer uma verificação gratuita","免费检查一个网站"],
'home.hx_t1': ["Public data only","Solo datos públicos","Données publiques uniquement","Nur öffentliche Daten","Apenas dados públicos","仅使用公开数据"],
'home.hx_t2': ["You approve every email","Tú apruebas cada correo","Vous validez chaque e-mail","Sie geben jede E-Mail frei","Você aprova cada e-mail","每封邮件由你批准"],
'home.hx_t3': ["Free plan available","Plan gratuito disponible","Formule gratuite disponible","Kostenloser Plan verfügbar","Plano gratuito disponível","提供免费方案"],
'home.hx_panel': ["Live audit","Auditoría en vivo","Audit en direct","Live-Audit","Auditoria ao vivo","实时审查"],
'home.hx_demo': ["Example data","Datos de ejemplo","Données d’exemple","Beispieldaten","Dados de exemplo","示例数据"],
'home.hx_scan': ["Scanning","Analizando","Analyse","Scan läuft","Analisando","扫描中"],
'home.hx_score': ["Opportunity score","Puntuación de oportunidad","Score d’opportunité","Chancen-Score","Pontuação de oportunidade","机会评分"],
'home.hx_ready': ["Report ready","Informe listo","Rapport prêt","Bericht bereit","Relatório pronto","报告已生成"],
'home.hx_draft': ["Outreach email drafted — waiting for your approval","Correo de contacto redactado — esperando tu aprobación","E-mail de prospection rédigé — en attente de votre accord","Akquise-E-Mail entworfen — wartet auf Ihre Freigabe","E-mail de contato redigido — aguardando sua aprovação","外联邮件已起草 —— 等待你的批准"],
'home.hx_approve': ["Review","Revisar","Relire","Prüfen","Revisar","查看"],
'home.hx_f1': ["Contact form","Formulario de contacto","Formulaire de contact","Kontaktformular","Formulário de contato","联系表单"],
'home.hx_f1v': ["Missing","No encontrado","Absent","Fehlt","Ausente","缺失"],
'home.hx_f2': ["Call button on phones","Botón de llamada en móvil","Bouton d’appel sur mobile","Anruf-Button auf Smartphones","Botão de ligar no celular","手机端拨号按钮"],
'home.hx_f2v': ["Hidden","Oculto","Masqué","Verdeckt","Oculto","被遮挡"],
'home.hx_f3': ["Mobile load time","Carga en móvil","Chargement mobile","Mobile Ladezeit","Carregamento no celular","移动端加载时间"],
'home.hx_f4': ["Secure connection","Conexión segura","Connexion sécurisée","Sichere Verbindung","Conexão segura","安全连接"],
'home.hx_f4v': ["OK","OK","OK","OK","OK","正常"],
'home.hx_c1': ["Dental clinic","Clínica dental","Cabinet dentaire","Zahnarztpraxis","Clínica odontológica","牙科诊所"],
'home.hx_c2': ["Family law firm","Despacho de derecho familiar","Cabinet de droit de la famille","Familienrechtskanzlei","Escritório de direito de família","家事律师事务所"],
'home.hx_c3': ["Neighbourhood café","Cafetería de barrio","Café de quartier","Café im Viertel","Café de bairro","街区咖啡馆"],
'foot.product': ["Product","Producto","Produit","Produkt","Produto","产品"],
'foot.company': ["Company","Empresa","Entreprise","Unternehmen","Empresa","公司"],
'foot.trust': ["Trust & legal","Confianza y legal","Confiance et mentions légales","Vertrauen & Rechtliches","Confiança e jurídico","信任与法律"],
'foot.how': ["How it works","Cómo funciona","Comment ça marche","So funktioniert es","Como funciona","工作原理"],
'foot.check': ["Free website check","Revisión web gratis","Vérification gratuite","Kostenloser Website-Check","Verificação gratuita","免费网站检查"],
'foot.top': ["Back to top","Volver arriba","Retour en haut","Nach oben","Voltar ao topo","返回顶部"],
'foot.wa_cta': ["Chat on WhatsApp","Escríbenos por WhatsApp","Discuter sur WhatsApp","Auf WhatsApp schreiben","Conversar no WhatsApp","WhatsApp 聊天"],
'foot.email_cta': ["Email us","Escríbenos","Écrivez-nous","Schreiben Sie uns","Envie um e-mail","发邮件给我们"],
'foot.made': ["Made for people who build the web.","Hecho para quienes construyen la web.","Conçu pour celles et ceux qui construisent le web.","Gemacht für Menschen, die das Web bauen.","Feito para quem constrói a web.","为构建网络的人而打造。"],
}
LOCS = ['en','es','fr','de','pt','zh']
for i, loc in enumerate(LOCS):
    p = ROOT/'static'/'locales'/f'{loc}.json'
    raw = p.read_text(encoding='utf-8')
    d = json.loads(raw, object_pairs_hook=collections.OrderedDict)
    for k, v in K.items(): d[k] = v[i]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ('\n' if raw.endswith('\n') else ''), encoding='utf-8')
print('added', len(K), 'keys x', len(LOCS))
