"""V4 admin/DM 'website' view — a data-driven single-page component (embedded HTML/JS).

Render path parallel to dashboard.py (which still serves the store-login view). This one
is full-width, professional, and interactive: left SVG nav, Overview with a
ranking/graphs/table toggle + metric sub-toggle fleet bar chart + Big 4-by-store + district
pills, Store detail with the redesigned metric sections (target line, click-to-expand
drill-ins, ARO drivers, 4-wk avg shown next to the actual), and Historical (last 7 days +
today highlighted, hover shows % vs today). No emojis. Blue/red lean, performance coloring.

`html(payload)` returns the component markup; app.py injects it via components.html and
renders the native targets editor separately (writes stay server-side).

Payload contract (all built in app.py / calc):
  P = {
    tier, scopeName, asof, sourced,
    kpis:{stores,cars,carsPace,net,aro,big4},
    regions:{name:[ids]},
    rows:[{id,name,region,cars,net,aro,lhpc,big4,pace,status}],   # overview, one per store
    detail:{ id: {name,id,region,open,
                  kpi:{cars,carsNorm,carsPace,aro,aroGap,net,netNorm,netPace,big4,lhpc,
                       carsStatus,aroStatus,netStatus,big4Status,lhpcStatus},
                  hours:[...], now:"1p",
                  cars:{actual:[],est:[],target:[],sofar,est_close,norm,pace,tgt,tgtSrc,wk:[{date,val,capped}]},
                  net:{...same shape...},
                  aro:{run:[],sofar,gap,target},
                  big4:{run:[],pct,units,target,items:[{name,attach,target,units}]},
                  lhpc:{roll:[],hours:[],day,now,target,variance},
                  drivers:[{title,status,message,chart:{type,data}}] } },
    hist:{days:[...], today:"Today", series:[{id,name,color,data:[]}], metric}
  }
"""
import json


def html(payload):
    P = json.dumps(payload).replace("</", "<\\/")
    return _TMPL.replace("/*__PAYLOAD__*/", P)


_TMPL = r"""
<div id="root"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--navy:#14273F;--red:#D0342C;--blue:#2E6FB7;--green:#158A5A;--amber:#B57611;
 --teal:#0E7490;--purple:#6C4FB6;--ink:#0F172A;--mute:#5B6472;--line:#E2E7EE;
 --bg:#F4F6F9;--card:#fff;--soft:#F7F9FC;--gbg:#E7F3EC;--rbg:#FBEAE9;--abg:#FBF1DF;}
*{box-sizing:border-box}
#root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;color:var(--ink);font-size:14px}
.app{display:flex;min-height:640px;background:#fff}
.side{width:206px;flex:0 0 206px;background:var(--navy);color:#fff;padding:16px 12px;display:flex;flex-direction:column}
.brand{font-weight:800;font-size:1.05rem;padding:6px 8px}
.brand small{display:block;color:#9FB4CC;font-weight:500;font-size:.7rem;margin-top:2px}
.side nav{margin-top:16px;display:flex;flex-direction:column;gap:3px}
.side nav button{display:flex;align-items:center;gap:10px;background:transparent;border:0;color:#C6D3E4;
 font-size:.9rem;font-weight:600;padding:10px 12px;border-radius:8px;cursor:pointer;text-align:left}
.side nav button:hover{background:rgba(255,255,255,.08);color:#fff}
.side nav button.on{background:#fff;color:var(--navy)}
.side nav svg{width:17px;height:17px;flex:0 0 17px}
.side .sfoot{margin-top:auto;color:#8FA2B8;font-size:.72rem;padding:8px}
.main{flex:1;min-width:0;padding:16px 24px 40px}
.topbar{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.scopeName{font-size:1.16rem;font-weight:800;letter-spacing:-.3px}
.meta{margin-left:auto;color:var(--mute);font-size:.78rem;display:flex;gap:14px;align-items:center}
.dot{width:7px;height:7px;border-radius:50%;background:#37D08A;display:inline-block;margin-right:5px}
.view{display:none}.view.on{display:block}
.pills{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}
.pills button{border:1px solid var(--line);background:#fff;color:var(--ink);font-size:.8rem;font-weight:600;padding:6px 13px;border-radius:20px;cursor:pointer}
.pills button.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.seg{display:inline-flex;background:#E7ECF2;border-radius:9px;padding:3px}
.seg button{border:0;background:transparent;font-size:.8rem;font-weight:700;color:var(--mute);padding:7px 13px;border-radius:7px;cursor:pointer}
.seg button.on{background:#fff;color:var(--navy);box-shadow:0 1px 2px rgba(0,0,0,.08)}
.row{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0}
h2.sh{font-size:1rem;font-weight:800;margin:20px 0 10px}.sub{color:var(--mute);font-weight:500;font-size:.8rem;margin-left:8px}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.kpi .l{font-size:.6rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);font-weight:800}
.kpi .v{font-size:1.3rem;font-weight:800;letter-spacing:-.5px;margin-top:1px}
.kpi .vsub{font-size:.78rem;color:var(--mute);font-weight:700;letter-spacing:0}
.storesel{margin-left:auto;padding:7px 11px;border:1px solid var(--line);border-radius:8px;font-weight:700;font-size:.82rem;background:#fff;color:var(--ink);cursor:pointer}
.kpi .d{font-size:.68rem;font-weight:700;margin-top:1px}
.kpi.bt{border-top:3px solid var(--blue)}.kpi.gt{border-top:3px solid var(--green)}.kpi.at{border-top:3px solid var(--amber)}
.kpi.tt{border-top:3px solid var(--teal)}.kpi.nt{border-top:3px solid var(--navy)}.kpi.rt{border-top:3px solid var(--red)}
.kpi.sg{background:var(--gbg);border-color:#BFE0CC}.kpi.sr{background:var(--rbg);border-color:#F0C9C6}.kpi.sa{background:var(--abg);border-color:#EBD9AE}
.drivers{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.drv{border:1px solid var(--line);border-radius:9px;padding:9px 11px;background:var(--soft)}
.drv.g{background:var(--gbg)}.drv.r{background:var(--rbg)}.drv.a{background:var(--abg)}
.drv .dt{font-weight:800;font-size:.82rem}.drv .dm{font-weight:800;font-size:.8rem;margin-top:1px}.drv .ds{font-size:.72rem;color:var(--mute);margin-top:2px}
.pos{color:var(--green)}.neg{color:var(--red)}.amb{color:var(--amber)}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(248px,1fr));gap:13px}
.scard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 15px;cursor:pointer;transition:box-shadow .12s,transform .12s;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.scard:hover{box-shadow:0 8px 22px rgba(15,23,42,.11);transform:translateY(-2px);border-color:#CBD5E1}
.scard .top{display:flex;justify-content:space-between;align-items:flex-start}
.scard .nm{font-weight:800;font-size:.96rem}.scard .id{color:var(--mute);font-size:.73rem;font-weight:600}
.pill{font-size:.72rem;font-weight:800;padding:3px 9px;border-radius:20px}
.pill.g{background:var(--gbg);color:var(--green)}.pill.r{background:var(--rbg);color:var(--red)}.pill.a{background:var(--abg);color:var(--amber)}
.mini{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:11px}
.mini .ml{font-size:.59rem;text-transform:uppercase;color:var(--mute);font-weight:700}.mini .mv{font-size:.92rem;font-weight:800}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 16px;box-shadow:0 1px 2px rgba(15,23,42,.04);margin-bottom:10px}
.chartbox{position:relative;height:230px}.chartbox.sm{height:150px}.chartbox.tall{height:430px}
.mhead{display:flex;align-items:center;gap:9px;margin-bottom:13px}
.acc{width:5px;height:18px;border-radius:3px}.mhead .t{font-weight:800;font-size:1rem}.mhead .n{color:var(--mute);font-size:.8rem}
.mrow{display:grid;grid-template-columns:210px 1fr;gap:16px}
.boxes{display:flex;flex-direction:column;gap:8px}
.box{border:1px solid var(--line);border-radius:9px;padding:7px 10px;background:var(--soft)}
.box .bl{font-size:.58rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);font-weight:800}
.box .bsub{font-size:.66rem;color:var(--mute);margin-top:1px}
.triple{display:grid;grid-template-columns:1fr 1fr 1fr;text-align:center;align-items:end;margin-top:6px}
.triple .big{font-size:1.1rem;font-weight:800;letter-spacing:-.5px}.triple .mid{font-size:.88rem;font-weight:800}.triple .cap{font-size:.6rem;color:var(--mute);font-weight:600}
.clickable{cursor:pointer}.clickable:hover{border-color:#CBD5E1;background:#fff}
.chev{font-size:.64rem;color:var(--blue);font-weight:800}
.expand{display:none;margin-top:10px;border-top:1px dashed var(--line);padding-top:10px}.expand.open{display:block}
.tgt{border-color:#F0C9B8;background:#FBF1EC}.tgt .bl{color:#993C1D}.tgt .val{color:#993C1D;font-size:1.1rem;font-weight:800}
.badge{background:#F1D6C8;color:#8A3617;border-radius:4px;padding:1px 6px;font-size:.63rem;font-weight:800}
.legend{display:flex;gap:16px;justify-content:center;margin-bottom:6px;font-size:.72rem;font-weight:700}
.lg span{display:inline-block;width:15px;height:2px;vertical-align:middle;margin-right:5px}
.band{display:grid;grid-template-columns:5fr 5fr 4fr;gap:4px;margin-bottom:6px}
.band div{font-size:.61rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);font-weight:800;text-align:center;background:var(--soft);border-radius:5px;padding:3px 0}
.driver{border:1px solid var(--line);border-radius:9px;padding:7px 10px;background:var(--soft)}
.driver .dt{font-weight:800;font-size:.78rem}.driver .dm{font-size:.73rem;margin-top:2px}
.tag{font-size:.62rem;font-weight:800;padding:2px 7px;border-radius:5px;margin-left:6px}
.tag.r{background:var(--rbg);color:var(--red)}.tag.a{background:var(--abg);color:var(--amber)}.tag.g{background:var(--gbg);color:var(--green)}
.crumb{font-size:.8rem;color:var(--mute);margin-bottom:2px}.crumb a{color:var(--blue);cursor:pointer;font-weight:600}
.big4grid{display:grid;grid-template-columns:1.1fr .9fr;gap:14px}
.bulletlabel{font-size:.61rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);font-weight:800;margin:0 0 10px}
.bullet{display:grid;grid-template-columns:78px 1fr 64px;align-items:center;gap:8px;margin:8px 0}
.bn{font-size:.72rem;color:var(--ink);font-weight:600}
.track{position:relative;height:9px;background:#EEF1F5;border-radius:5px}
.fill{position:absolute;left:0;top:0;height:9px;border-radius:5px}
.tmark{position:absolute;top:-2px;width:2px;height:13px;background:var(--ink)}
.bv{font-size:.7rem;font-weight:800;text-align:right}
.ops{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.o{border:1px solid var(--line);border-radius:8px;padding:9px 11px;background:var(--soft)}
.ol{font-size:.61rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);font-weight:800}
.ov{font-size:1.05rem;font-weight:800;margin-top:2px}
.os{font-size:.68rem;color:var(--mute)}
@media(max-width:820px){.big4grid{grid-template-columns:1fr}}
.heatscroll{overflow-x:auto}
table.heat{border-collapse:collapse;font-size:.64rem}
table.heat th,table.heat td{border:1px solid #EEF1F5;padding:2px 5px;text-align:center;white-space:nowrap;min-width:34px}
table.heat th{background:var(--soft);color:var(--mute);font-weight:700;font-size:.58rem}
.heat .hh{text-align:left;color:var(--mute);font-weight:700;background:var(--soft)}
.heat .hid{color:var(--mute);font-weight:500;font-size:.62rem}
.picker{margin:4px 0 12px}
.pickrow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.rpill{border:1px solid var(--line);background:#fff;border-radius:20px;padding:5px 12px;font-size:.78rem;font-weight:700;cursor:pointer;color:var(--mute)}
.rpill.on{background:var(--navy);color:#fff;border-color:var(--navy)}
.spill{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 11px;font-size:.78rem;font-weight:600;cursor:pointer;color:var(--ink)}
.spill.on{background:var(--blue);color:#fff;border-color:var(--blue)}
.detailwrap{display:grid;grid-template-columns:1fr 300px;gap:16px;align-items:start}
.detailwrap.nomsg{grid-template-columns:1fr}
.navhead{background:var(--navy);color:#fff;border-radius:12px;padding:15px 20px;display:flex;justify-content:space-between;align-items:center;border-left:5px solid var(--red);margin-bottom:6px}
.navhead .brand2{font-weight:800;font-size:1.2rem;letter-spacing:-.3px}
.navhead .sub2{color:#9FB4CC;font-size:.68rem;font-weight:700;letter-spacing:.09em;text-transform:uppercase;display:block;margin-top:2px}
.navhead .rt{text-align:right;font-size:.82rem;line-height:1.5}
.navhead .rt b{font-size:.95rem}
.navhead .rt small{color:#9FB4CC}
.navhead .live{color:#37D08A;font-weight:800}
.subline{color:var(--mute);font-size:.76rem;font-weight:600;margin:0 0 12px 2px}
.row2{display:grid;grid-template-columns:1.15fr 1fr;gap:12px;margin-bottom:12px}
.card2{background:#fff;border:1px solid var(--line);border-radius:12px;padding:13px 16px}
.card2 .sh2{font-weight:800;font-size:1rem;margin-bottom:10px}.card2 .sh2 .sub{font-weight:600}
.expl2{display:grid;gap:9px}
.pbox .h2{font-weight:800;color:var(--navy);font-size:.74rem;text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px}
.pbox{font-size:.79rem;color:var(--ink);line-height:1.4}
.dmsg{position:sticky;top:8px}
.msgbox{background:#FBF4E9;border:1px solid #E9D9BE;border-radius:12px;padding:14px 16px}
.msgh{font-weight:800;font-size:.9rem;margin-bottom:10px;color:#8A5A12}
.msg{border-left:3px solid #B57611;background:#fff;border-radius:0 8px 8px 0;padding:8px 10px;margin-bottom:8px}
.msgb{font-size:.82rem;color:var(--ink)}
.msgm{font-size:.68rem;color:var(--mute);margin-top:4px}
.msgempty{color:var(--mute);font-size:.8rem}
.chipbtn{border:1px solid var(--line);background:#fff;border-radius:8px;padding:5px 11px;font-size:.76rem;font-weight:700;cursor:pointer;color:var(--navy)}
.sctiles{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:12px}
.sctile{border:1px solid var(--line);border-radius:8px;padding:9px 11px;background:var(--soft)}
.sctile.pos{background:var(--gbg)}.sctile.neg{background:var(--rbg)}.sctile.amb{background:var(--abg)}
.sctile .l{font-size:.6rem;text-transform:uppercase;color:var(--mute);font-weight:800}
.sctile .v{font-size:1.15rem;font-weight:800;margin-top:2px}
.scrow{display:flex;gap:10px;flex-wrap:wrap}
.scbtn{background:var(--navy);color:#fff;border-radius:8px;padding:9px 16px;font-size:.82rem;font-weight:800;text-decoration:none;cursor:pointer}
.scbtn.dis{background:#CBD5E1;color:#fff;cursor:default}
@media(max-width:820px){.sctiles{grid-template-columns:1fr 1fr}}
@media(max-width:900px){.detailwrap{grid-template-columns:1fr}.dmsg{position:static}}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{padding:9px 12px;font-size:.82rem;text-align:right;border-bottom:1px solid var(--line)}
th:first-child,td:first-child{text-align:left}
th{background:var(--soft);color:var(--mute);font-size:.65rem;text-transform:uppercase;letter-spacing:.04em}
tbody tr{cursor:pointer}tbody tr:hover{background:var(--soft)}tr:last-child td{border-bottom:0}
.empty{color:var(--mute);font-size:.85rem;padding:22px;text-align:center}
@media(max-width:820px){.app{flex-direction:column}.side{width:100%;flex-direction:row;overflow:auto}
 .side .brand,.side .sfoot{display:none}.side nav{flex-direction:row;margin:0}.side nav button{white-space:nowrap}
 .kpis{grid-template-columns:1fr 1fr}.mrow{grid-template-columns:1fr}}
</style>
<script>
const P=/*__PAYLOAD__*/;
const C={navy:'#14273F',red:'#D0342C',blue:'#2E6FB7',green:'#158A5A',amber:'#B57611',teal:'#0E7490',purple:'#6C4FB6',mute:'#5B6472',line:'#E2E7EE'};
const ch={};const STORE=(P.mode==='store');let OVMODE='table',OVMETRIC='cars',SEL=(P.rows[0]||{}).id,PICKREG=null;
const ICON={overview:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
 detail:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/></svg>',
 hist:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V5M4 19h16M8 15l3-4 3 2 4-6"/></svg>'};
const fmt={cars:v=>Math.round(v),net:v=>'$'+Math.round(v).toLocaleString(),aro:v=>'$'+Math.round(v),big4:v=>Math.round(v)+'%',lhpc:v=>(+v).toFixed(2)};
const stCol={g:C.green,a:C.amber,r:C.red,flat:C.mute};
function pc(v){return v==null?'—':((v>=0?'+':'')+(+v).toFixed(1)+'%');}
function scls(s){return s==='g'?'pos':(s==='r'?'neg':(s==='a'?'amb':''));}
function kcls(s){return s==='g'?'sg':(s==='r'?'sr':(s==='a'?'sa':''));}
function mk(id,cfg){const el=document.getElementById(id);if(!el)return;if(ch[id])ch[id].destroy();ch[id]=new Chart(el,cfg);}
const G={responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},elements:{point:{radius:0}}};

function shell(){
 document.getElementById('root').innerHTML=`
 <div class="app">
  <main class="main">
   <div class="topbar"><div class="scopeName" id="scopeName">${STORE?'':(P.scopeName||'')}</div>
    <div class="meta" id="freshMeta"><span><span class="dot"></span>live · ${P.asof||''}</span><span>${P.sourced||''}</span></div></div>
   <section class="view on" id="v_overview"></section>
   <section class="view" id="v_detail"></section>
   <section class="view" id="v_hist"></section>
  </main>
 </div>`;
}
function nav(v){document.querySelectorAll('.view').forEach(s=>s.classList.toggle('on',s.id==='v_'+v));
 document.querySelectorAll('.side nav button').forEach(b=>b.classList.toggle('on',b.getAttribute('data-v')===v));
 render(v);}
function render(v){if(v==='overview')overview();else if(v==='detail')detail();else if(v==='hist')hist();
 // detail carries its own live+source stamp in the navy header — hide the topbar one so
 // "live" isn't shown twice and the header is the topmost element (tops align).
 const fm=document.getElementById('freshMeta');if(fm)fm.style.display=(v==='detail')?'none':'flex';}

/* ---------- overview ---------- */
function overview(){const k=P.kpis||{};
 document.getElementById('v_overview').innerHTML=`
  <div class="pills">${['All'].concat(Object.keys(P.regions||{})).map((r,i)=>`<button class="${i===0?'on':''}" onclick="regfilter(this,'${r}')">${r==='All'?('All · '+P.rows.length):r}</button>`).join('')}</div>
  <div class="kpis">
   <div class="kpi nt" title="Stores currently reporting data in this scope"><div class="l">Stores reporting</div><div class="v">${k.stores||P.rows.length}</div><div class="d">live</div></div>
   <div class="kpi bt" title="Total cars so far across the scope · ${pc(k.carsPace)} vs the cars-weighted 4-week average"><div class="l">Total cars</div><div class="v">${k.cars!=null?Math.round(k.cars):'—'}</div><div class="d ${k.carsPace>=0?'pos':'neg'}">${pc(k.carsPace)} vs 4-wk</div></div>
   <div class="kpi gt" title="Total net sales so far across the scope"><div class="l">Total net</div><div class="v">${k.net!=null?fmt.net(k.net):'—'}</div><div class="d">so far</div></div>
   <div class="kpi at" title="Cars-weighted average ARO (total net ÷ total cars) vs the $125 target"><div class="l">Avg ARO</div><div class="v">${k.aro!=null?fmt.aro(k.aro):'—'}</div><div class="d ${k.aro>=125?'pos':'neg'}">vs $125</div></div>
   <div class="kpi tt" title="Cars-weighted Big 4 attach % across the scope vs the 53% goal"><div class="l">Big 4 attach</div><div class="v">${k.big4!=null?fmt.big4(k.big4):'—'}</div><div class="d ${k.big4>=53?'pos':'amb'}">goal 53%</div></div>
  </div>
  <div class="row" style="margin-top:16px">
   <div class="seg"><button onclick="ovv(this,'rank')">Store ranking</button><button onclick="ovv(this,'graph')">Graphs</button><button class="on" onclick="ovv(this,'table')">Table</button></div>
   <div class="seg" id="ovm" style="display:none">${['cars','big4','aro','net','lhpc'].map((m,i)=>`<button class="${i===0?'on':''}" onclick="ovmet(this,'${m}')">${m==='aro'?'ARO':m==='lhpc'?'LHPC':m==='big4'?'Big 4':m[0].toUpperCase()+m.slice(1)}</button>`).join('')}</div>
   <span class="sub" id="ovmNote" style="display:none">current hour · click a bar to open the store</span>
  </div>
  <div id="ov_body"></div>
  <h2 class="sh">Big 4 by store <span class="sub">attach % of cars · goal line 53%</span></h2>
  <div class="panel"><div class="chartbox tall"><canvas id="c_b4store"></canvas></div></div>
  <h2 class="sh">Heat map <span class="sub">cars per hour · darker = busier · absolute scale across stores</span></h2>
  <div id="ov_heat"></div>`;
 ovBody();b4store();renderHeat();
}
let REGION='All';
function regfilter(b,r){b.parentElement.querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');REGION=r;ovBody();b4store();renderHeat();}
function renderHeat(){const el=document.getElementById('ov_heat');if(el)el.innerHTML=heatmap();}
function heatmap(){const R=rowsF().filter(s=>s.heat&&s.heat.length);const hh=P.heatHours||[];
 if(!R.length||!hh.length)return '<div class="empty">No heat data.</div>';
 const allv=R.flatMap(s=>s.heat.filter(v=>v!=null));const mx=Math.max(1,...allv);
 const cell=v=>{if(v==null||v==='')return '<td style="background:#F9FAFB"></td>';const a=Math.min(1,v/mx);return `<td style="background:rgba(46,111,183,${(0.06+a*0.72).toFixed(2)});color:${a>0.5?'#fff':'#0F172A'}" title="${v} cars">${v||''}</td>`;};
 let h='<div class="panel" style="padding:10px"><div class="heatscroll"><table class="heat"><thead><tr><th class="hh">Hour</th>'+R.map(s=>`<th title="${s.name} #${s.id}">${s.name} <span class="hid">#${s.id}</span></th>`).join('')+'</tr></thead><tbody>';
 hh.forEach((lab,i)=>{h+='<tr><td class="hh">'+lab+'</td>'+R.map(s=>cell(s.heat[i])).join('')+'</tr>';});
 h+='</tbody></table></div></div>';return h;}
function ovv(b,m){b.parentElement.querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');OVMODE=m;
 document.getElementById('ovm').style.display=m==='graph'?'inline-flex':'none';
 document.getElementById('ovmNote').style.display=m==='graph'?'inline':'none';ovBody();}
function ovmet(b,m){b.parentElement.querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');OVMETRIC=m;ovBody();}
function rowsF(){return P.rows.filter(r=>REGION==='All'||(P.regions[REGION]||[]).includes(r.id));}
function ovBody(){const el=document.getElementById('ov_body');const R=rowsF();
 if(OVMODE==='rank'){el.innerHTML='<div class="cards">'+R.map(s=>`
   <div class="scard" onclick="openStore('${s.id}')" title="${s.name} #${s.id} · cars ${s.cars??'—'} · net ${s.net!=null?'$'+Math.round(s.net).toLocaleString():'—'} · ARO ${s.aro!=null?'$'+Math.round(s.aro):'—'} · Big 4 ${s.big4!=null?Math.round(s.big4)+'%':'—'} · LHPC ${s.lhpc??'—'} · ${pc(s.pace)} vs 4-wk. Click to open."><div class="top"><div><div class="nm">${s.name}</div><div class="id">#${s.id}</div></div><span class="pill ${s.status||'a'}">${pc(s.pace)}</span></div>
   <div class="mini"><div><div class="ml">Cars</div><div class="mv">${s.cars!=null?s.cars:'—'}</div></div><div><div class="ml">ARO</div><div class="mv">${s.aro!=null?'$'+Math.round(s.aro):'—'}</div></div><div><div class="ml">Big 4</div><div class="mv">${s.big4!=null?Math.round(s.big4)+'%':'—'}</div></div><div><div class="ml">LHPC</div><div class="mv">${s.lhpc!=null?(+s.lhpc).toFixed(2):'—'}</div></div></div></div>`).join('')+'</div>';}
 else if(OVMODE==='table'){el.innerHTML='<table><thead><tr><th>Store</th><th>Cars</th><th>Net</th><th>ARO</th><th>Big 4</th><th>LHPC</th><th>vs 4-wk</th></tr></thead><tbody>'+R.map(s=>`<tr onclick="openStore('${s.id}')"><td>${s.name} #${s.id}</td><td>${s.cars??'—'}</td><td>${s.net!=null?'$'+Math.round(s.net).toLocaleString():'—'}</td><td>${s.aro!=null?'$'+Math.round(s.aro):'—'}</td><td>${s.big4!=null?Math.round(s.big4)+'%':'—'}</td><td>${s.lhpc!=null?(+s.lhpc).toFixed(2):'—'}</td><td class="${scls(s.status)}">${pc(s.pace)}</td></tr>`).join('')+'</tbody></table>';}
 else{el.innerHTML='<div class="panel"><div class="chartbox tall"><canvas id="c_fleet"></canvas></div></div>';fleet();}
 fitLater();
}
function fleet(){const m=OVMETRIC,goal={big4:53,aro:125,lhpc:1.10}[m]||null;
 const arr=rowsF().map(s=>({n:s.name+' '+s.id,v:s[m],id:s.id})).filter(a=>a.v!=null).sort((a,b)=>m==='lhpc'?a.v-b.v:b.v-a.v);
 mk('c_fleet',{type:'bar',data:{labels:arr.map(a=>a.n),datasets:[{data:arr.map(a=>a.v),
   backgroundColor:arr.map(a=>goal?((m==='lhpc'?a.v<=goal:a.v>=goal)?C.green:((m==='lhpc'?a.v<=goal*1.25:a.v>=goal*0.6)?C.amber:C.red)):C.blue),borderRadius:4}]},
  options:{...G,indexAxis:'y',onClick:(e,el)=>{if(el[0])openStore(arr[el[0].index].id);},
   plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>fmt[m](c.parsed.x)}}},
   scales:{x:{grid:{color:C.line}},y:{grid:{display:false},ticks:{font:{size:10}}}}}});
}
function b4store(){const arr=rowsF().map(s=>({n:s.name+' '+s.id,v:s.big4,id:s.id})).filter(a=>a.v!=null).sort((a,b)=>a.v-b.v);
 mk('c_b4store',{type:'bar',data:{labels:arr.map(a=>a.n),datasets:[{data:arr.map(a=>a.v),backgroundColor:arr.map(a=>a.v>=53?C.green:(a.v>=32?C.amber:C.red)),borderRadius:4}]},
  options:{...G,indexAxis:'y',onClick:(e,el)=>{if(el[0])openStore(arr[el[0].index].id);},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>'Big 4: '+Math.round(c.parsed.x)+'%'}}},scales:{x:{grid:{color:C.line},suggestedMax:100},y:{grid:{display:false},ticks:{font:{size:10}}}}}});
}
function openStore(id){SEL=id;PICKREG=null;nav('detail');}

/* ---------- detail ---------- */
function detail(){const d=(P.detail||{})[SEL];const el=document.getElementById('v_detail');
 if(!d){el.innerHTML='<div class="empty">Select a store from Overview.</div>';return;}
 const k=d.kpi;
 const crumb=STORE?'':`<div class="crumb"><a onclick="nav('overview')">Overview</a> › <b>${d.name} · #${d.id}</b></div>`;
 const navhead=`<div class="navhead"><div><span class="brand2">VantEdge Auto</span><span class="sub2">Take 5 · Time Report</span></div>
  <div class="rt"><b>${d.name} · #${d.id}</b><br>${P.date||''} · <span class="live">● live</span> · ${P.asof||''}${P.sourced?`<br><small>${P.sourced}</small>`:''}</div></div>`;
 el.innerHTML=`${crumb}${STORE?'':`<div id="picker">${storePicker()}</div>`}
  ${navhead}
  <div class="subline">${d.region||''} · opened ${d.open||'—'}</div>
  <div class="detailwrap ${STORE?'nomsg':''}"><div class="dmain">
  <div class="kpis">
   <div class="kpi ${kcls(k.carsStatus)}" title="Cars so far ${k.cars} · 4-week average by this hour ${k.carsNorm!=null?Math.round(k.carsNorm):'—'} (holidays excluded, outliers capped) · ${pc(k.carsPace)} vs that average"><div class="l">Cars</div><div class="v">${k.cars} <span class="vsub">/ ${k.carsNorm!=null?Math.round(k.carsNorm):'—'} 4-wk</span></div><div class="d ${scls(k.carsStatus)}">${pc(k.carsPace)} vs 4-wk</div></div>
   <div class="kpi ${kcls(k.aroStatus)}" title="ARO = net ÷ cars = $${Math.round(k.aro)}, vs the $125 target (${pc(k.aroGap)})"><div class="l">ARO ($/car)</div><div class="v">$${Math.round(k.aro)}</div><div class="d ${scls(k.aroStatus)}">${pc(k.aroGap)} vs $125</div></div>
   <div class="kpi ${kcls(k.netStatus)}" title="Net so far $${Math.round(k.net).toLocaleString()} · 4-week average by this hour $${k.netNorm!=null?Math.round(k.netNorm).toLocaleString():'—'} · ${pc(k.netPace)} vs that average"><div class="l">Net revenue</div><div class="v">$${Math.round(k.net).toLocaleString()} <span class="vsub">/ $${k.netNorm!=null?Math.round(k.netNorm).toLocaleString():'—'} 4-wk</span></div><div class="d ${scls(k.netStatus)}">${pc(k.netPace)} vs 4-wk</div></div>
   <div class="kpi ${kcls(k.big4Status)}" title="Big 4 units ÷ cars, as % of cars = ${Math.round(k.big4)}%, vs the 53% goal"><div class="l">Big 4 attach</div><div class="v">${Math.round(k.big4)}%</div><div class="d ${scls(k.big4Status)}">goal 53%</div></div>
   <div class="kpi ${kcls(k.lhpcStatus)}" title="Labor hours per car (cumulative) = ${(+k.lhpc).toFixed(2)}. Lower is leaner. Target 1.10"><div class="l">LHPC</div><div class="v">${(+k.lhpc).toFixed(2)}</div><div class="d ${scls(k.lhpcStatus)}">target 1.10</div></div>
   ${(()=>{const tk=Math.round(k.task||0);const st=tk>=80?'sg':(tk>=50?'sa':'sr');const dc=tk>=80?'pos':(tk>=50?'amb':'neg');return `<div class="kpi ${st}" title="Today's daily-task completion for this store"><div class="l">Task</div><div class="v">${tk}%</div><div class="d ${dc}">done today</div></div>`;})()}
  </div>
  ${moversSection(d)}
  ${cumSection('Cars',d.cars,C.blue,'cars',d)}
  ${aroSection(d)}
  ${cumSection('Net revenue',d.net,C.green,'net',d)}
  ${big4Section(d)}
  ${lhpcSection(d)}
  ${scoreSection(d)}
  ${opsSection(d)}
  </div>${STORE?'':`<aside class="dmsg">${msgPanel(d)}</aside>`}</div>`;
 drawMain(d);
}
function scoreSection(d){const sc=d.scorecards||{};const k=d.kpi;
 const dl=(b64,fn,label)=>b64?`<a class="scbtn" href="data:application/pdf;base64,${b64}" download="${fn}">${label}</a>`:`<span class="scbtn dis">${label} (n/a)</span>`;
 const tiles=[['Cars',k.cars,scls(k.carsStatus)],['ARO','$'+Math.round(k.aro),scls(k.aroStatus)],['Net','$'+Math.round(k.net).toLocaleString(),scls(k.netStatus)],['Big 4',Math.round(k.big4)+'%',scls(k.big4Status)],['LHPC',(+k.lhpc).toFixed(2),scls(k.lhpcStatus)]]
  .map(t=>`<div class="sctile ${t[2]}"><div class="l">${t[0]}</div><div class="v">${t[1]}</div></div>`).join('');
 return `<div class="panel"><div class="mhead"><div class="acc" style="background:${C.navy}"></div><span class="t">Score cards</span><span class="n">today's KPIs + printable cards</span></div>
  <div class="sctiles">${tiles}</div>
  <div class="scrow">${dl(sc.today,d.id+'_today.pdf','Today')}${dl(sc.yesterday,d.id+'_yesterday.pdf','Yesterday'+(sc.ylabel||''))}${dl(sc.week,d.id+'_week.pdf','Last 7 days')}</div></div>`;
}
function storePicker(){if(STORE)return '';const regs=P.regions||{};let cur=PICKREG;
 if(!cur){for(const r in regs){if((regs[r]||[]).map(String).includes(String(SEL))){cur=r;break;}}cur=cur||Object.keys(regs)[0];}
 const nameOf=id=>{const row=(P.rows||[]).find(x=>String(x.id)===String(id));return row?row.name:id;};
 const regbar=Object.keys(regs).map(r=>`<button class="rpill ${r===cur?'on':''}" onclick="pickReg('${r}')">${r}</button>`).join('');
 const stores=(regs[cur]||[]).map(id=>`<button class="spill ${String(id)===String(SEL)?'on':''}" onclick="openStore('${id}')">${nameOf(id)} #${id}</button>`).join('');
 return `<div class="picker"><div class="pickrow">${regbar}</div><div class="pickrow">${stores}</div></div>`;
}
function pickReg(r){PICKREG=r;const p=document.getElementById('picker');if(p)p.innerHTML=storePicker();}
function msgPanel(d){const m=d.messages||[];
 return `<div class="msgbox"><div class="msgh">Messages</div>${m.length?m.map(x=>`<div class="msg"><div class="msgb">${x.body}</div><div class="msgm">${x.from||''} · ${x.when||''}</div></div>`).join(''):'<div class="msgempty">No messages yet.</div>'}</div>`;
}
function band(){return '<div class="band"><div>Morning</div><div>Afternoon</div><div>Evening</div></div>';}
function cumSection(title,m,color,key,d){
 const fv=v=>key==='net'?'$'+Math.round(v||0).toLocaleString():Math.round(v||0);
 const isAdm=(P.tier==='admin'||P.tier==='district');
 const tgtSrc=isAdm&&m.tgtSrc?`<span class="badge">${m.tgtSrc}</span>`:'';
 const tToday=`${title} so far ${fv(m.sofar)} · 4-week average by this hour ${fv(m.norm)} · ${pc(m.pace)} vs that average (same weekday, holidays excluded, outliers capped). Click for the 4 days.`;
 const tProj=`Projected close ${fv(m.est_close)} = banked so far + a pace-scaled 4-week normal for the remaining hours (clamped 0.7–1.5×). Excludes the admin boost.`;
 const tTgt=m.tgt!=null?(isAdm?`Target ${fv(m.tgt)} = ${m.tgtSrc}`:`Store target ${fv(m.tgt)}`):'No target set';
 return `<div class="panel"><div class="mhead"><div class="acc" style="background:${color}"></div><span class="t">${title}</span><span class="n">cumulative today vs projected close</span></div>
  <div class="mrow"><div class="boxes">
   <div class="box clickable" onclick="tog('${key}wk')" title="${tToday}"><div class="bl">Today · as of ${d.now}</div>
    <div class="triple"><div><div class="big">${fv(m.sofar)}</div><div class="cap">so far</div></div>
     <div><div class="mid ${scls(m.status)}">${pc(m.pace)}</div><div class="cap">vs 4-wk</div></div>
     <div><div class="big">${fv(m.norm)}</div><div class="cap">4-wk avg <span class="chev">▾</span></div></div></div>
    <div class="expand" id="${key}wk"><div class="sub">Last 4 same-weekdays by this hour + today</div><div class="chartbox sm"><canvas id="c_${key}wk"></canvas></div></div></div>
   <div class="box" title="${tProj}"><div class="bl">Projected finish</div><div class="bsub">pace-scaled</div><div class="triple" style="grid-template-columns:1fr"><div class="big" style="color:${color}">${fv(m.est_close)}</div></div></div>
   <div class="box tgt" title="${tTgt}"><div class="bl">Target</div><div class="bsub">${m.tgt!=null?tgtSrc:'—'}</div><div class="val">${m.tgt!=null?fv(m.tgt):'—'}</div></div>
  </div>
  <div><div class="legend"><span class="lg"><span style="background:${C.blue}"></span>Actual</span><span class="lg" style="color:${C.green}"><span style="border-top:2px dashed ${C.green};background:none;height:0"></span>Projected</span><span class="lg" style="color:${C.red}"><span style="border-top:2px dotted ${C.red};background:none;height:0"></span>Target</span></div>
   ${band()}<div class="chartbox"><canvas id="c_${key}"></canvas></div></div></div></div>`;
}
function moversSection(d){const mv=d.movers||[];
 const wd=(P.date||'').split(',')[0]||'day';
 const mov=`<div class="card2"><div class="sh2">What's driving value <span class="sub sub-mute">— biggest movers</span></div>`+
   (mv.length?`<div class="drivers">${mv.map(x=>`<div class="drv ${x.st}" title="${x.s}"><div class="dt">${x.t}</div><div class="dm ${scls(x.st)}">${x.m}</div><div class="ds">${x.s}</div></div>`).join('')}</div>`:`<div class="sub">Nothing notable yet.</div>`)+`</div>`;
 const how=`<div class="card2"><div class="sh2">How to read this</div><div class="expl2">
   <div class="pbox"><div class="h2">4-Week Comparison</div>Today so far vs a <b>normal ${wd}</b> — the simple average of the last 4 same-weekdays at this same time. <b>+%</b> ahead, <b>−%</b> behind.</div>
   <div class="pbox"><div class="h2">Projected</div>Where the day is trending by close: <b>today's banked total</b> plus the rest of a typical day, nudged by how today is pacing. An estimate, not a promise.</div></div></div>`;
 return `<div class="row2">${mov}${how}</div>`;
}
function aroSection(d){const a=d.aro;
 return `<div class="panel"><div class="mhead"><div class="acc" style="background:${C.amber}"></div><span class="t">ARO — average repair order</span><span class="n">running revenue per car vs target</span></div>
  <div class="mrow"><div class="boxes">
   <div class="box" title="ARO so far $${Math.round(a.sofar||0)} = net ÷ cars · target $${Math.round(a.target||125)} (${pc(a.gap)} gap)"><div class="bl">Today</div><div class="triple"><div><div class="big">$${Math.round(a.sofar||0)}</div><div class="cap">so far</div></div><div><div class="mid ${a.gap>=0?'pos':'neg'}">${pc(a.gap)}</div><div class="cap">gap</div></div><div><div class="big">$${Math.round(a.target||125)}</div><div class="cap">target</div></div></div></div>
  </div><div>${band()}<div class="chartbox" style="height:266px"><canvas id="c_aro"></canvas></div></div></div></div>`;
}
function big4Section(d){const b=d.big4;
 return `<div class="panel"><div class="mhead"><div class="acc" style="background:${C.teal}"></div><span class="t">Big 4 attachment</span><span class="n">attach % of cars vs the 53% goal</span></div>
  <div class="mrow"><div class="boxes"><div class="box" title="Big 4 attach ${Math.round(b.pct||0)}% = ${b.units} Big 4 units ÷ cars, as a % of cars · goal ${b.target}% (sum of the four item targets). Click units for per-item."><div class="bl">Attach</div><div class="triple"><div><div class="big">${Math.round(b.pct||0)}%</div><div class="cap">of cars</div></div><div><div class="mid">${b.target}%</div><div class="cap">goal</div></div><div><div class="big clickable" onclick="tog('b4u')">${b.units}<span class="chev"> ▾</span></div><div class="cap">units</div></div></div><div class="expand" id="b4u"><div class="sub">Units per item</div><div class="chartbox sm"><canvas id="c_b4units"></canvas></div></div></div></div>
   <div><div class="big4grid"><div>${band()}<div class="chartbox" style="height:200px"><canvas id="c_big4"></canvas></div></div>
    <div><div class="bulletlabel">Attach % by item vs target</div><div id="bul">${buildBullets(b.items)}</div></div></div></div></div></div>`;
}
function buildBullets(items){items=items||[];const vals=items.flatMap(it=>[it.attach||0,it.target||0]);
 const MX=Math.max(30,...vals)*1.15;const pos=v=>Math.min(100,v/MX*100);const IC=[C.teal,C.blue,C.purple,C.amber];
 return items.map((it,i)=>{const r=it.target?it.attach/it.target:0,sc=r>=1?C.green:(r>=.6?C.amber:C.red);
  return `<div class="bullet" title="${it.name}: ${Math.round(it.attach)}% attach vs ${it.target}% target · ${it.units||0} units"><span class="bn">${it.name}</span><div class="track"><span class="fill" style="width:${pos(it.attach)}%;background:${IC[i%4]}"></span><span class="tmark" style="left:${pos(it.target)}%"></span></div><span class="bv" style="color:${sc}">${Math.round(it.attach)}% / ${it.target}%</span></div>`;}).join('');}
function lhpcSection(d){const l=d.lhpc;
 return `<div class="panel"><div class="mhead"><div class="acc" style="background:${C.purple}"></div><span class="t">Labor · LHPC</span><span class="n">rolling labor per car vs target</span></div>
  <div class="mrow"><div class="boxes"><div class="box clickable" onclick="tog('lhx')" title="Rolling ${(+l.day).toFixed(2)} = cumulative labor hours ÷ cumulative cars for the day · variance ${l.variance>0?'+':''}${(+l.variance).toFixed(2)} vs the ${(+l.target).toFixed(2)} target. Lower is leaner."><div class="bl">Rolling <span class="chev">▾</span></div><div class="triple"><div><div class="big">${(+l.day).toFixed(2)}</div><div class="cap">rolling</div></div><div><div class="mid ${l.variance<=0?'pos':'neg'}">${l.variance>0?'+':''}${(+l.variance).toFixed(2)}</div><div class="cap">variance</div></div><div><div class="big">${(+l.target).toFixed(2)}</div><div class="cap">target</div></div></div><div class="expand" id="lhx"><div class="sub">Rolling = cumulative labor hours ÷ cumulative cars for the day. Lower is leaner.</div></div></div></div>
   <div>${band()}<div class="chartbox" style="height:196px"><canvas id="c_lhpc"></canvas></div></div></div></div>`;
}
function opsSection(d){const ops=d.ops||[];if(!ops.length)return '';
 return `<div class="panel"><div class="mhead"><div class="acc" style="background:${C.mute}"></div><span class="t">Operational detail</span><span class="n">the numbers behind the day</span></div>
  <div class="ops">${ops.map(o=>`<div class="o"><div class="ol">${o[0]}</div><div class="ov">${o[1]}</div><div class="os">${o[2]||''}</div></div>`).join('')}</div></div>`;
}
// Clicking a KPI box only draws its own pop-out mini-chart — never re-renders the main charts.
function tog(id){const e=document.getElementById(id);if(!e)return;const open=!e.classList.contains('open');e.classList.toggle('open');
 const d=(P.detail||{})[SEL];
 if(open){ if(id==='carswk')drawWk(d,'cars'); else if(id==='netwk')drawWk(d,'net');
           else if(id.indexOf('arod')===0)drawDriver(d,+id.slice(4)); else if(id==='b4u')drawB4units(d); }
 fitLater();}

function lineTgt(v){return {type:'line',label:'Target',data:v,borderColor:C.red,borderDash:[2,3],borderWidth:1.6,pointRadius:0};}

// The five main section charts — drawn once when the detail view renders.
function drawMain(d){const L=d.hours;
 ['cars','net'].forEach(key=>{const m=d[key];if(!document.getElementById('c_'+key))return;
  mk('c_'+key,{data:{labels:L,datasets:[
   {type:'line',label:'Actual',data:m.actual,borderColor:C.blue,backgroundColor:'rgba(46,111,183,.10)',fill:true,borderWidth:2.6,tension:.35},
   {type:'line',label:'Projected',data:m.est,borderColor:C.green,borderDash:[6,4],borderWidth:2.2,tension:.35},
   (m.target&&m.target.length)?lineTgt(m.target):{data:[]}]},
   options:{...G,plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false}},scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:C.line}}}}});
 });
 const a=d.aro;if(document.getElementById('c_aro'))mk('c_aro',{data:{labels:L,datasets:[
   {type:'line',label:'ARO',data:a.run,borderColor:C.blue,backgroundColor:'rgba(46,111,183,.08)',fill:true,borderWidth:2.4,tension:.35},
   lineTgt(L.map(()=>a.target||125))]},options:{...G,plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false}},scales:{x:{grid:{display:false}},y:{grid:{color:C.line}}}}});
 const b=d.big4;if(document.getElementById('c_big4'))mk('c_big4',{data:{labels:L,datasets:[
   {type:'line',label:'Big 4 %',data:b.run,borderColor:C.teal,backgroundColor:'rgba(14,116,144,.10)',fill:true,borderWidth:2.4,tension:.35},
   {type:'line',label:'goal',data:L.map(()=>b.target),borderColor:C.green,borderDash:[4,3],borderWidth:1.4,pointRadius:0}]},options:{...G,scales:{x:{grid:{display:false}},y:{beginAtZero:true,grid:{color:C.line}}}}});
 const l=d.lhpc;if(document.getElementById('c_lhpc'))mk('c_lhpc',{data:{labels:L,datasets:[
   {type:'line',label:'rolling',data:l.roll,borderColor:C.purple,borderWidth:2.4,tension:.35},
   {type:'line',label:'target',data:L.map(()=>l.target),borderColor:C.red,borderDash:[2,3],borderWidth:1.4,pointRadius:0}]},
   options:{...G,plugins:{legend:{display:false},tooltip:{mode:'index',intersect:false}},scales:{x:{grid:{display:false}},y:{min:0,max:5,grid:{color:C.line}}}}});
}

// 4-week drill-in: value labels on every bar + a dashed average line through the historical bars.
function drawWk(d,key){const m=d[key];const wk=m.wk||[];const hv=wk.map(x=>x.val);
 const wl=wk.map(x=>x.date).concat(['Today']);const wv=hv.concat([m.sofar]);
 const avg=hv.length?hv.reduce((a,b)=>a+b,0)/hv.length:0;
 const lab=v=>key==='net'?Math.round(v).toLocaleString():Math.round(v);
 const plug={id:'wk',afterDatasetsDraw:c=>{const{ctx}=c;const meta=c.getDatasetMeta(0).data;ctx.save();
   ctx.font='700 10px -apple-system,sans-serif';ctx.fillStyle='#0F172A';ctx.textAlign='center';
   meta.forEach((bar,i)=>{if(wv[i]!=null)ctx.fillText(lab(wv[i]),bar.x,bar.y-4);});
   if(hv.length){const y=c.scales.y.getPixelForValue(avg);const x0=meta[0].x-16,x1=meta[hv.length-1].x+16;
     ctx.strokeStyle='#14273F';ctx.setLineDash([5,4]);ctx.lineWidth=1.3;ctx.beginPath();ctx.moveTo(x0,y);ctx.lineTo(x1,y);ctx.stroke();
     ctx.setLineDash([]);ctx.fillStyle='#14273F';ctx.textAlign='left';ctx.fillText('avg '+lab(avg),x1+3,y-2);}
   ctx.restore();}};
 mk('c_'+key+'wk',{type:'bar',data:{labels:wl,datasets:[{data:wv,backgroundColor:wl.map((_,i)=>i===wl.length-1?C.blue:'#B5D4F4'),borderRadius:3}]},
  options:{...G,layout:{padding:{top:16,right:40}},plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{font:{size:9}}},y:{display:false,beginAtZero:true}}},plugins:[plug]});
}

function drawDriver(d,i){const x=(d.drivers||[])[i];if(!x||!document.getElementById('c_arod'+i))return;const c=x.chart||{};
 if(c.type==='bars')mk('c_arod'+i,{type:'bar',data:{labels:(c.data||[]).map(z=>z.name),datasets:[{label:'attach',data:(c.data||[]).map(z=>z.attach),backgroundColor:C.teal},{label:'target',data:(c.data||[]).map(z=>z.target),backgroundColor:C.line}]},options:{...G,scales:{x:{grid:{display:false},ticks:{font:{size:9}}},y:{display:false}}}});
 else if(c.type==='pair')mk('c_arod'+i,{type:'bar',data:{labels:(c.data||[]).map(z=>z.name),datasets:[{data:(c.data||[]).map(z=>z.val),backgroundColor:C.amber}]},options:{...G,indexAxis:'y',scales:{x:{display:false},y:{grid:{display:false}}}}});
 else mk('c_arod'+i,{type:'bar',data:{labels:['now','target'],datasets:[{data:[(c.data||{}).val||0,(c.data||{}).target||0],backgroundColor:[C.amber,C.line]}]},options:{...G,scales:{x:{grid:{display:false}},y:{display:false}}}});
}

function drawB4units(d){const b=d.big4;if(!document.getElementById('c_b4units'))return;
 mk('c_b4units',{type:'bar',data:{labels:(b.items||[]).map(x=>x.name),datasets:[{data:(b.items||[]).map(x=>x.units||0),backgroundColor:C.teal,borderRadius:3}]},options:{...G,scales:{x:{grid:{display:false},ticks:{font:{size:9}}},y:{display:false}}}});
}

/* ---------- historical ---------- */
const HKEY={Cars:'cars',Net:'net',ARO:'aro','Big 4':'big4',LHPC:'lhpc',Task:'task'};
let HMETRIC='cars',HSTORES=null;
function hist(){const h=P.hist||{stores:[],days:[]};const el=document.getElementById('v_hist');
 if(HSTORES===null)HSTORES=(h.stores||[]).slice(0,Math.min(3,(h.stores||[]).length)).map(s=>s.id);
 el.innerHTML=`<div class="scopeName">Historical performance <span class="sub">last 7 days + today · hover a day for its gap vs today</span></div>
  <div class="row"><div class="seg" id="hmetric">${Object.keys(HKEY).map(m=>`<button class="${HKEY[m]===HMETRIC?'on':''}" onclick="hm(this,'${HKEY[m]}')">${m}</button>`).join('')}</div>
   <button class="chipbtn" onclick="hAll()">All</button><button class="chipbtn" onclick="hClear()">Clear all</button></div>
  <div class="pills" id="hchips">${(h.stores||[]).map(s=>`<button class="${HSTORES.includes(s.id)?'on':''}" onclick="hchip('${s.id}')">${s.name}</button>`).join('')}</div>
  <div class="panel"><div class="chartbox" style="height:320px"><canvas id="c_hist"></canvas></div></div>
  <h2 class="sh">Selected stores <span class="sub">last-week average vs today</span></h2>
  <div id="htab"></div>`;
 drawHist();fitLater();
}
function hm(b,m){b.parentElement.querySelectorAll('button').forEach(x=>x.classList.remove('on'));b.classList.add('on');HMETRIC=m;drawHist();}
function hchip(id){const i=HSTORES.indexOf(id);if(i>=0)HSTORES.splice(i,1);else HSTORES.push(id);hist();}
function hAll(){HSTORES=((P.hist||{}).stores||[]).map(s=>s.id);hist();}
function hClear(){HSTORES=[];hist();}
function drawHist(){const h=P.hist||{stores:[],days:[]};const sel=(h.stores||[]).filter(s=>HSTORES.includes(s.id));
 if(!document.getElementById('c_hist'))return;
 if(!sel.length){if(ch['c_hist'])ch['c_hist'].destroy();document.getElementById('htab').innerHTML='<div class="empty">Select at least one store.</div>';return;}
 const days=(h.days||[]).concat([h.today||'Today']);
 const box={id:'box',afterDraw:c=>{const{ctx,chartArea:{top,bottom},scales:{x}}=c;const p=x.getPixelForValue(days[days.length-1]);ctx.save();ctx.fillStyle='rgba(46,111,183,.10)';ctx.strokeStyle='rgba(46,111,183,.55)';ctx.lineWidth=1.5;ctx.fillRect(p-24,top,48,bottom-top);ctx.strokeRect(p-24,top,48,bottom-top);ctx.restore();}};
 const isTask=HMETRIC==='task';
 mk('c_hist',{type:'line',data:{labels:days,datasets:sel.map(s=>({label:s.name,data:s.metrics[HMETRIC],borderColor:s.color,borderWidth:2.4,tension:.35,spanGaps:true,pointRadius:days.map((d,i)=>i===days.length-1?5:3),pointBackgroundColor:s.color,_items:isTask?(s.taskItems||[]):null}))},
  options:{...G,plugins:{legend:{display:true,position:'top',align:'end'},tooltip:{callbacks:{
    label:c=>{if(isTask)return c.dataset.label+': '+Math.round(c.parsed.y)+'% done';const arr=c.dataset.data;const t=arr[arr.length-1];const df=t?(((c.parsed.y-t)/t)*100).toFixed(0):0;return c.dataset.label+': '+(c.parsed.y==null?'—':Math.round(c.parsed.y))+' ('+(df>=0?'+':'')+df+'% vs today)';},
    afterLabel:c=>{if(!isTask)return '';const it=(c.dataset._items||[])[c.dataIndex]||[];return it.length?('Done: '+it.join(', ')):'None done';}}}},
   scales:{x:{grid:{display:false}},y:{grid:{color:C.line},suggestedMax:isTask?100:undefined,beginAtZero:isTask}}},plugins:[box]});
 document.getElementById('htab').innerHTML='<table><thead><tr><th>Store</th><th>Last-week avg</th><th>Today</th><th>Δ vs last wk</th></tr></thead><tbody>'+sel.map(s=>{const arr=s.metrics[HMETRIC];const t=arr[arr.length-1];const prev=arr.slice(0,-1).filter(v=>v!=null);const avg=prev.length?prev.reduce((a,b)=>a+b,0)/prev.length:0;const df=avg?(((t-avg)/avg)*100).toFixed(0):0;return `<tr><td>${s.name}</td><td>${Math.round(avg)}</td><td>${t==null?'—':Math.round(t)}</td><td class="${df>=0?'pos':'neg'}">${df>=0?'+':''}${df}%</td></tr>`;}).join('')+'</tbody></table>';
}
function fit(){try{if(window.frameElement){window.frameElement.style.height=Math.max(680,document.documentElement.scrollHeight+8)+'px';}}catch(e){}}
function fitLater(){setTimeout(fit,90);}
const _render=render;render=function(v){_render(v);fitLater();};
shell();nav(STORE?'detail':(P.startView||'overview'));fitLater();
</script>
"""
