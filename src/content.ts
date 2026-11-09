export type Project={slug:string;name:string;type:string;summary:string;metric:string;tags:string[];accent:string;kind:'web3'|'business'|'concept'};
export const projects:Project[]=[
{slug:'mycoincard',name:'MyCoinCard',type:'Web3 · Payments',summary:'A clearer path from token discovery to everyday utility.',metric:'Product concept',tags:['Web3','Payments','UX'],accent:'violet',kind:'concept'},
{slug:'nexusfi',name:'NexusFi',type:'DeFi · Product UI',summary:'A focused interface concept for complex financial actions.',metric:'Product concept',tags:['DeFi','Dashboard','React'],accent:'blue',kind:'concept'},
{slug:'porshure-green',name:'Porshure Green',type:'Business · Sustainability',summary:'A confident digital presence for a modern green business.',metric:'Brand concept',tags:['Corporate','Responsive','SEO'],accent:'mint',kind:'concept'},
{slug:'reachmark-audit',name:'Reachmark Audit',type:'Internal · Website review',summary:'A practical report experience that turns observations into next steps.',metric:'Product experience',tags:['Audit','Evidence','Conversion'],accent:'amber',kind:'concept'},
{slug:'estate-collective',name:'Estate Collective',type:'Real estate · Website',summary:'A premium property discovery experience built around clear enquiries.',metric:'Industry concept',tags:['Real estate','Lead flow','UX'],accent:'rose',kind:'concept'},
{slug:'forge-industries',name:'Forge Industries',type:'Manufacturing · Website',summary:'A structured product and capability story for a technical business.',metric:'Industry concept',tags:['Manufacturing','B2B','Content'],accent:'slate',kind:'concept'}
];
export const services=[
{number:'01',name:'Business websites',price:'Scoped to the brief',description:'Corporate, real estate, manufacturing, service and e-commerce websites built to make the next step obvious.',items:['UX and responsive design','Website development','Technical SEO foundations','Analytics and enquiry flow']},
{number:'02',name:'Web3 product builds',price:'Scoped to the product',description:'Clear, credible digital experiences for Web3 teams, protocols and products.',items:['Product and token websites','dApp interfaces','Wallet-connected experiences','Frontend integration']},
{number:'03',name:'Website gap reviews',price:'Free first review',description:'Find the friction in your existing website with evidence-led observations and a practical fix plan.',items:['Public-page review','Performance and UX signals','Prioritised recommendations','Optional implementation support']}
];
export const process=[['01','Audit','We inspect the public experience and identify the issues worth investigating.'],['02','Design','We shape a clear, accessible experience around your customers and goals.'],['03','Build','We develop, test and refine the real website or product experience.'],['04','Launch & grow','We release carefully and help you keep improving.']];
export const faqs=[
['What does the free site review include?','A review of the public page signals available to us, with observable findings and practical next steps. It is not a guarantee of rankings or revenue.'],
['Do you work outside Web3?','Yes. Reachmark works with businesses across real estate, manufacturing, professional services, e-commerce and technology.'],
['How much does a website cost?','Pricing depends on scope, integrations, content, and delivery requirements. We agree a clear proposal before work begins.'],
['Who owns the finished website?','Ownership, source-code handover, hosting and third-party subscriptions are defined in the project agreement before work starts.'],
['Can you work with my existing developer?','Yes. We can provide an evidence-led fix plan or collaborate with your existing team.'],
['Where will the website be hosted?','We can deploy to Render or another suitable host, or prepare a static build for your existing hosting provider.']
];