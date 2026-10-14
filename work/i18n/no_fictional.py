"""Replace 'fictional' wording in every locale (honest wording kept: concept / sample / not client work)."""
import json, re, collections, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
T = {
'enq.f2a': {
 'en':"No. The gallery shows clearly labelled design concepts to help you choose a direction. They are kept separate from the real business discovery database.",
 'es':"No. La galería muestra conceptos de diseño claramente etiquetados para ayudarte a elegir una dirección. Se mantienen separados de la base de datos real de negocios.",
 'fr':"Non. La galerie présente des concepts de design clairement identifiés pour vous aider à choisir une direction. Ils sont séparés de la base réelle de découverte d’entreprises.",
 'de':"Nein. Die Galerie zeigt klar gekennzeichnete Designkonzepte, die Ihnen bei der Wahl einer Richtung helfen. Sie sind von der echten Unternehmensdatenbank getrennt.",
 'pt':"Não. A galeria mostra conceitos de design claramente identificados para ajudar você a escolher uma direção. Eles ficam separados da base real de descoberta de empresas.",
 'zh':"不是。作品集展示的是明确标注的设计概念，帮助你选择方向。它们与真实的商家发现数据库完全分开。"},
'foot.base1': {
 'en':"© 2026 Reachmark · Gallery sites are design concepts, not client work.",
 'es':"© 2026 Reachmark · Los sitios de la galería son conceptos de diseño, no trabajos de clientes.",
 'fr':"© 2026 Reachmark · Les sites de la galerie sont des concepts de design, pas des projets clients.",
 'de':"© 2026 Reachmark · Die Galerie-Websites sind Designkonzepte, keine Kundenprojekte.",
 'pt':"© 2026 Reachmark · Os sites da galeria são conceitos de design, não trabalhos de clientes.",
 'zh':"© 2026 Reachmark · 作品集中的网站均为设计概念，并非客户项目。"},
'home.card1p': {
 'en':"Ten sample sites across cafés, clinics, law, retail, crypto and more — each one explorable before you enquire.",
 'es':"Diez sitios de muestra para cafeterías, clínicas, despachos, comercios, cripto y más — puedes explorar cada uno antes de consultar.",
 'fr':"Dix sites d’exemple — cafés, cliniques, cabinets, commerces, crypto et plus — à explorer avant de nous écrire.",
 'de':"Zehn Beispiel-Websites für Cafés, Praxen, Kanzleien, Handel, Krypto und mehr — jede können Sie vor Ihrer Anfrage erkunden.",
 'pt':"Dez sites de exemplo para cafés, clínicas, advocacia, varejo, cripto e mais — cada um pode ser explorado antes do seu contato.",
 'zh':"十个示例网站，涵盖咖啡馆、诊所、律所、零售、加密等行业 —— 咨询前即可逐一浏览。"},
'home.note': {
 'en':"10 design concepts · Live previews · No account needed to look around",
 'es':"10 conceptos de diseño · Vistas previas en vivo · Sin cuenta para explorar",
 'fr':"10 concepts de design · Aperçus en direct · Aucun compte requis pour explorer",
 'de':"10 Designkonzepte · Live-Vorschauen · Kein Konto zum Umsehen nötig",
 'pt':"10 conceitos de design · Prévias ao vivo · Sem conta para explorar",
 'zh':"10 个设计概念 · 实时预览 · 无需账户即可浏览"},
'home.report_k': {
 'en':"Sample report · Example business",'es':"Informe de muestra · Negocio de ejemplo",'fr':"Rapport d’exemple · Entreprise exemple",
 'de':"Beispielbericht · Beispielunternehmen",'pt':"Relatório de exemplo · Empresa de exemplo",'zh':"示例报告 · 示例商家"},
'home.report_meta': {
 'en':"Example bakery · Sample city",'es':"Panadería de ejemplo · Ciudad de muestra",'fr':"Boulangerie exemple · Ville exemple",
 'de':"Beispiel-Bäckerei · Beispielstadt",'pt':"Padaria de exemplo · Cidade de exemplo",'zh':"示例面包店 · 示例城市"},
'home.report_p2': {
 'en':"No mobile viewport is set in this example, which can make controls harder to use.",
 'es':"Este ejemplo no define un viewport móvil, lo que puede dificultar el uso de los controles.",
 'fr':"Aucun viewport mobile n’est défini dans cet exemple, ce qui peut rendre les contrôles difficiles à utiliser.",
 'de':"In diesem Beispiel ist kein mobiler Viewport gesetzt, was die Bedienung erschweren kann.",
 'pt':"Este exemplo não define um viewport móvel, o que pode dificultar o uso dos controles.",
 'zh':"此示例未设置移动端视口，可能导致控件难以操作。"},
'home.s1p': {
 'en':"Browse ten sample sites with live previews. No account, no sales call.",
 'es':"Explora diez sitios de muestra con vistas previas en vivo. Sin cuenta ni llamadas de venta.",
 'fr':"Parcourez dix sites d’exemple avec aperçus en direct. Sans compte, sans appel commercial.",
 'de':"Stöbern Sie in zehn Beispiel-Websites mit Live-Vorschau. Kein Konto, kein Verkaufsgespräch.",
 'pt':"Veja dez sites de exemplo com prévias ao vivo. Sem conta, sem ligação de vendas.",
 'zh':"浏览十个带实时预览的示例网站。无需账户，没有推销电话。"},
'home.stat1l': {'en':"design concepts",'es':"conceptos de diseño",'fr':"concepts de design",'de':"Designkonzepte",'pt':"conceitos de design",'zh':"设计概念"},
'show.card_alt': {
 'en':"Preview of the {name} website concept — {figma}",'es':"Vista previa del concepto web {name} — {figma}",
 'fr':"Aperçu du concept de site {name} — {figma}",'de':"Vorschau des Website-Konzepts {name} — {figma}",
 'pt':"Prévia do conceito de site {name} — {figma}",'zh':"{name} 网站概念预览 — {figma}"},
'show.explainer': {
 'en':"Premium Figma-inspired design concepts — not claimed client work. Ten sample brands with AI-generated concept imagery and Figma community auto-layout principles (editorial, health, commerce, grid). They demonstrate layout and styling, not real businesses, reviews or completed commissions. Each one works as a live preview, and none appear in the lead database.",
 'es':"Conceptos de diseño premium inspirados en Figma — no presentados como trabajo de clientes. Diez marcas de muestra con imágenes conceptuales generadas por IA y principios de auto-layout de la comunidad Figma (editorial, salud, comercio, cuadrícula). Muestran diseño y estilo, no negocios reales, reseñas ni encargos completados. Cada una funciona como vista previa en vivo y ninguna aparece en la base de leads.",
 'fr':"Concepts de design premium inspirés de Figma — pas présentés comme des projets clients. Dix marques d’exemple avec des visuels conceptuels générés par IA et les principes d’auto-layout de la communauté Figma (éditorial, santé, commerce, grille). Elles montrent la mise en page et le style, pas de vraies entreprises, avis ou commandes réalisées. Chacune fonctionne en aperçu direct et aucune n’apparaît dans la base de prospects.",
 'de':"Premium-Designkonzepte nach Figma-Vorbild — keine angeblichen Kundenprojekte. Zehn Beispielmarken mit KI-generierten Konzeptbildern und Auto-Layout-Prinzipien der Figma-Community (Editorial, Gesundheit, Commerce, Raster). Sie zeigen Layout und Gestaltung, keine echten Unternehmen, Bewertungen oder abgeschlossenen Aufträge. Jede funktioniert als Live-Vorschau, und keine erscheint in der Lead-Datenbank.",
 'pt':"Conceitos de design premium inspirados no Figma — não apresentados como trabalho de clientes. Dez marcas de exemplo com imagens conceituais geradas por IA e princípios de auto-layout da comunidade Figma (editorial, saúde, comércio, grade). Elas mostram layout e estilo, não empresas reais, avaliações ou encomendas concluídas. Cada uma funciona como prévia ao vivo e nenhuma aparece na base de leads.",
 'zh':"受 Figma 启发的高级设计概念 —— 并非声称的客户作品。十个示例品牌，配有 AI 生成的概念图像，并采用 Figma 社区自动布局原则（编辑、健康、电商、网格）。它们展示的是布局与风格，而不是真实商家、评价或已完成的委托。每一个都可作为实时预览使用，且都不会出现在潜在客户数据库中。"},
'ss.alt': {
 'en':"AI-generated {cat} mood imagery for this design concept",'es':"Imágenes de ambiente {cat} generadas por IA para este concepto de diseño",
 'fr':"Visuels d’ambiance {cat} générés par IA pour ce concept de design",'de':"KI-generierte {cat}-Stimmungsbilder für dieses Designkonzept",
 'pt':"Imagens de ambiente {cat} geradas por IA para este conceito de design",'zh':"为此设计概念生成的 {cat} 氛围 AI 图像"},
'ss.fic': {
 'en':"DESIGN CONCEPT · AI CONCEPT IMAGERY",'es':"CONCEPTO DE DISEÑO · IMÁGENES CONCEPTUALES CON IA",'fr':"CONCEPT DE DESIGN · VISUELS CONCEPTUELS IA",
 'de':"DESIGNKONZEPT · KI-KONZEPTBILDER",'pt':"CONCEITO DE DESIGN · IMAGENS CONCEITUAIS COM IA",'zh':"设计概念 · AI 概念图像"},
'ss.fine': {
 'en':"Sample only. {name} is a demonstration brand, not a listed lead, client endorsement, or operating business. Imagery is AI-generated. No actual prices, opening hours, credentials, testimonials, bookings, or transactions are represented. The enquiry link opens the working Reachmark project form.",
 'es':"Solo muestra. {name} es una marca de demostración, no un lead listado, un respaldo de cliente ni un negocio en funcionamiento. Las imágenes son generadas por IA. No se representan precios, horarios, credenciales, testimonios, reservas ni transacciones reales. El enlace de consulta abre el formulario de proyecto de Reachmark.",
 'fr':"Exemple uniquement. {name} est une marque de démonstration, ni un prospect référencé, ni une recommandation client, ni une entreprise en activité. Les visuels sont générés par IA. Aucun prix, horaire, diplôme, témoignage, réservation ou transaction réel n’est représenté. Le lien de demande ouvre le formulaire de projet Reachmark.",
 'de':"Nur ein Beispiel. {name} ist eine Demonstrationsmarke, kein gelisteter Lead, keine Kundenempfehlung und kein tätiges Unternehmen. Die Bilder sind KI-generiert. Es werden keine echten Preise, Öffnungszeiten, Qualifikationen, Referenzen, Buchungen oder Transaktionen dargestellt. Der Anfrage-Link öffnet das Reachmark-Projektformular.",
 'pt':"Apenas exemplo. {name} é uma marca de demonstração, não um lead listado, um endosso de cliente nem uma empresa em funcionamento. As imagens são geradas por IA. Nenhum preço, horário, credencial, depoimento, reserva ou transação real é representado. O link de contato abre o formulário de projeto da Reachmark.",
 'zh':"仅为示例。{name} 是演示品牌，并非已列出的潜在客户、客户背书或正在营业的商家。图像由 AI 生成。页面不代表任何真实价格、营业时间、资质、评价、预订或交易。咨询链接会打开 Reachmark 的项目表单。"},
'ss.p_p': {
 'en':"Like this direction? Send Reachmark your requirements or ask for an estimate. Your enquiry is about building a website — not ordering from this sample brand.",
 'es':"¿Te gusta esta dirección? Envía tus requisitos a Reachmark o pide un presupuesto. Tu consulta trata sobre crear un sitio web, no sobre comprar a esta marca de muestra.",
 'fr':"Cette direction vous plaît ? Envoyez vos besoins à Reachmark ou demandez une estimation. Votre demande concerne la création d’un site — pas une commande auprès de cette marque d’exemple.",
 'de':"Gefällt Ihnen diese Richtung? Senden Sie Reachmark Ihre Anforderungen oder fragen Sie nach einem Angebot. Ihre Anfrage betrifft den Bau einer Website — keine Bestellung bei dieser Beispielmarke.",
 'pt':"Gostou desta direção? Envie seus requisitos à Reachmark ou peça uma estimativa. Seu contato é sobre criar um site — não sobre comprar desta marca de exemplo.",
 'zh':"喜欢这个方向？把你的需求发给 Reachmark 或索取报价。你的咨询是关于建设网站，而不是向这个示例品牌下单。"},
'ss.s_p': {
 'en':"This {cat} concept demonstrates a design direction — not a completed client project. The structure, colours, imagery, and content can be adapted around your actual business, services, and goals.",
 'es':"Este concepto de {cat} muestra una dirección de diseño, no un proyecto de cliente terminado. La estructura, los colores, las imágenes y el contenido se pueden adaptar a tu negocio, servicios y objetivos reales.",
 'fr':"Ce concept {cat} illustre une direction de design — pas un projet client livré. La structure, les couleurs, les visuels et le contenu peuvent être adaptés à votre activité, vos services et vos objectifs réels.",
 'de':"Dieses {cat}-Konzept zeigt eine Designrichtung — kein abgeschlossenes Kundenprojekt. Struktur, Farben, Bilder und Inhalte lassen sich an Ihr tatsächliches Unternehmen, Ihre Leistungen und Ziele anpassen.",
 'pt':"Este conceito de {cat} mostra uma direção de design — não um projeto de cliente concluído. A estrutura, as cores, as imagens e o conteúdo podem ser adaptados ao seu negócio, serviços e objetivos reais.",
 'zh':"这个{cat}概念展示的是一种设计方向，而不是已完成的客户项目。结构、配色、图像和内容都可以根据你真实的业务、服务和目标进行调整。"},
'ws.pf_note': {
 'en':"These are website concepts with AI-generated imagery, not real leads or claimed client projects. They never count toward your discovery metrics.",
 'es':"Son conceptos de sitios web con imágenes generadas por IA, no leads reales ni proyectos de clientes. Nunca cuentan en tus métricas de descubrimiento.",
 'fr':"Ce sont des concepts de sites avec des visuels générés par IA, pas de vrais prospects ni des projets clients. Ils ne comptent jamais dans vos métriques de découverte.",
 'de':"Dies sind Website-Konzepte mit KI-generierten Bildern, keine echten Leads oder Kundenprojekte. Sie zählen nie zu Ihren Discovery-Kennzahlen.",
 'pt':"Estes são conceitos de sites com imagens geradas por IA, não leads reais nem projetos de clientes. Eles nunca contam nas suas métricas de descoberta.",
 'zh':"这些是带有 AI 生成图像的网站概念，不是真实潜在客户或客户项目，不会计入你的发现指标。"},
'ws.pf_p': {
 'en':"Three design directions. Real inspiration for your next project.",'es':"Tres direcciones de diseño. Inspiración real para tu próximo proyecto.",
 'fr':"Trois directions de design. Une vraie inspiration pour votre prochain projet.",'de':"Drei Designrichtungen. Echte Inspiration für Ihr nächstes Projekt.",
 'pt':"Três direções de design. Inspiração real para o seu próximo projeto.",'zh':"三种设计方向，为你的下一个项目带来真实灵感。"},
}
WORD = {  # remaining keys: the word means 'fake/invented' there — swap for a synonym
 'es':[(r'ficticios','inventados'),(r'ficticias','inventadas'),(r'ficticio','inventado'),(r'ficticia','inventada'),(r'Ficticio','Inventado'),(r'Ficticia','Inventada')],
 'fr':[(r'fictives','inventées'),(r'fictifs','inventés'),(r'fictive','inventée'),(r'fictif','inventé'),(r'Fictive','Inventée'),(r'Fictif','Inventé')],
 'de':[(r'fiktiven','erfundenen'),(r'fiktiver','erfundener'),(r'fiktives','erfundenes'),(r'fiktive','erfundene'),(r'fiktiv','erfunden'),(r'Fiktive','Erfundene')],
 'pt':[(r'fictícios','inventados'),(r'fictícias','inventadas'),(r'fictício','inventado'),(r'fictícia','inventada')],
 'zh':[(r'虚构的','编造的'),(r'虚构','编造')],
 'en':[],
}
pat = re.compile(r'fiction|fictí|ficti|fiktiv|虚构', re.I)
for loc in ['en','es','fr','de','pt','zh']:
    p = ROOT/'static'/'locales'/f'{loc}.json'
    raw = p.read_text(encoding='utf-8')
    d = json.loads(raw, object_pairs_hook=collections.OrderedDict)
    for k, tr in T.items():
        if k in d or loc == 'en': d[k] = tr[loc]
    for k, v in list(d.items()):
        if isinstance(v, str) and pat.search(v):
            for a, b in WORD[loc]: v = v.replace(a, b)
            d[k] = v
    left = [k for k, v in d.items() if isinstance(v, str) and pat.search(v)]
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2) + ('\n' if raw.endswith('\n') else ''), encoding='utf-8')
    print(loc, 'remaining:', left)
