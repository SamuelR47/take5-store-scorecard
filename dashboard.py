"""V3 dashboard component: dense HTML/Chart.js app driven by an injected JSON payload.
One template renders the store view + admin/regional view + client-side roller & drill-in.
Returned as a string for st.components.v1.html.

V3 changes vs V2:
- "Big 4/5" -> "Big 4" everywhere; the Big 4 chart is now % of goal (0-100, target 100).
- "Pace" -> "Last 4-Week Comparison"; "Estimated" -> "Projected", each with its own plain
  explainer.
- Clearer KPI titles; LHPC chart gets a day-band + hour ticks and a y-axis capped at 5.
- Heat map gains explicit "Before open" / "After close" roll-up buckets.
- "What's driving value" is dynamic (server-computed biggest movers).
- Richer hover tooltips on every chart; hover help on every KPI tile (title attr).
- Score-card PDFs are no longer embedded here (moved to the app shell -> smaller payload).
- Empty-state guard so a store login can never render blank.
- Optional mobile layout (single-column) via mobile=True.
"""
import json

CSS = """
<style>
 :root{--navy:#14273F;--red:#D0342C;--blue:#2E6FB7;--green:#158A5A;--amber:#B57611;--teal:#0E7490;
  --purple:#6C4FB6;--ink:#0F172A;--mute:#5B6472;--label:#8A93A2;--bg:#EBEEF3;--card:#FFFFFF;--soft:#F5F7FA;
  --line:#E2E7EE;--steel:#C2CCDA;--gbg:#E9F5EF;--rbg:#FBECEA;--abg:#FBF3E4;
  --hair:inset 0 0 0 1px rgba(15,23,42,.07);--sh:0 1px 2px rgba(15,23,42,.05);}
 *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}
 body{margin:0;background:var(--bg);color:var(--ink);font-size:13px;-webkit-font-smoothing:antialiased}
 .wrap{max-width:1480px;margin:0 auto;padding:10px 14px 30px}
 .card{background:var(--card);border-radius:8px;box-shadow:var(--hair),var(--sh);padding:12px 14px;margin-bottom:10px}
 .head{background:var(--navy);border-radius:8px;padding:12px 18px;display:flex;align-items:center;justify-content:space-between;color:#fff;margin-bottom:10px}
 .head .l{display:flex;align-items:center;gap:11px}
 .head .tick{width:6px;height:30px;background:var(--red);border-radius:2px}
 .head .name{font-size:1.16rem;font-weight:800}
 .head .name span{display:block;color:#9FB4CC;font-weight:500;font-size:.7rem;margin-top:2px;letter-spacing:.04em}
 .head .r{text-align:right;color:#C6D3E4;font-size:.78rem;line-height:1.5}.head .r b{color:#fff}
 .head .liv{color:#7FE0B0;font-weight:600}
 .tabs{display:flex;gap:6px;overflow-x:auto;padding:4px 2px 8px;margin-bottom:8px}
 .tab{flex:0 0 auto;border:1px solid var(--line);background:var(--card);border-radius:18px;padding:6px 13px;font-size:.8rem;font-weight:700;color:var(--mute);cursor:pointer;white-space:nowrap}
 .tab.on{background:var(--navy);color:#fff;border-color:var(--navy)}
 .tab.reg{color:var(--teal)}.tab.on.reg{background:var(--teal);border-color:var(--teal);color:#fff}
 .tab.st{color:var(--label);font-weight:600}.tsep{flex:0 0 auto;width:1px;background:var(--line);margin:3px 3px}
 .tab.on.st{background:var(--navy);color:#fff;border-color:var(--navy)}
 .tabs.sub{margin-top:-2px;padding:2px 2px 8px 8px;border-left:2px solid var(--line);border-radius:0}
 h3.sh{margin:0 0 8px;font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--label);font-weight:700}
 .kbar{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:10px}
 .kc{border-radius:7px;padding:10px 12px;box-shadow:var(--hair);border:1.5px solid var(--steel);background:var(--card);cursor:help}
 .kc.g{border-color:var(--green);background:var(--gbg)}.kc.r{border-color:var(--red);background:var(--rbg)}.kc.a{border-color:var(--amber);background:var(--abg)}
 .kc .l{font-size:.63rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);font-weight:700}
 .kc .v{font-size:1.46rem;font-weight:800;letter-spacing:-.6px;line-height:1.1;margin-top:2px}
 .kc .d{font-size:.71rem;font-weight:800;margin-top:2px}
 .up{color:var(--green)}.down{color:var(--red)}.flat{color:var(--amber)}
 .row2{display:grid;grid-template-columns:1.6fr 1fr;gap:10px;margin-bottom:10px}
 .drivers{display:grid;grid-template-columns:repeat(2,1fr);gap:9px}
 .drv{border-radius:6px;padding:9px 10px;box-shadow:var(--hair)}
 .drv.g{background:var(--gbg)}.drv.r{background:var(--rbg)}.drv.a{background:var(--abg)}.drv.flat{background:var(--soft)}
 .drv .t{font-size:.8rem;font-weight:700}.drv .m{font-size:.78rem;font-weight:800;margin-top:1px}.drv .s{font-size:.7rem;color:var(--mute);margin-top:2px;line-height:1.35}
 .expl2{display:grid;grid-template-columns:1fr 1fr;gap:9px}
 .pacebox{font-size:.73rem;color:var(--mute);line-height:1.45}.pacebox b{color:var(--ink)}
 .pacebox .h{font-size:.66rem;text-transform:uppercase;letter-spacing:.06em;color:var(--label);font-weight:700;margin-bottom:3px}
 .sechead{display:flex;align-items:center;gap:9px;margin-bottom:10px}
 .accent{width:4px;height:20px;border-radius:2px}.st{font-size:1rem;font-weight:800;color:var(--navy)}.sn{font-size:.74rem;color:var(--mute)}
 .mrow{display:grid;grid-template-columns:186px 1fr;gap:14px;align-items:start}
 .kbox{display:flex;flex-direction:column;gap:7px}
 .tile{border-radius:6px;padding:9px 11px;box-shadow:var(--hair);background:var(--soft)}
 .tile.g{background:var(--gbg)}.tile.r{background:var(--rbg)}.tile.a{background:var(--abg)}
 .tile .l{font-size:.61rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);font-weight:700}
 .tile .v{font-size:1.24rem;font-weight:800;letter-spacing:-.5px;margin-top:1px}.tile .s{font-size:.69rem;font-weight:800;margin-top:1px}
 .dayband{display:grid;grid-template-columns:5fr 5fr 4fr;gap:3px;margin-bottom:5px}
 .dayband div{font-size:.61rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);font-weight:700;text-align:center;background:var(--soft);border-radius:4px;padding:2px 0;box-shadow:var(--hair)}
 .bullet{display:grid;grid-template-columns:100px 1fr 92px;align-items:center;gap:9px;margin:7px 0;cursor:help}
 .bullet .bn{font-size:.75rem;font-weight:600}
 .track{position:relative;height:7px;background:#E7ECF2;border-radius:4px;box-shadow:var(--hair)}
 .track .act{position:absolute;top:-3px;width:3px;height:13px;border-radius:1px}
 .track .tgt{position:absolute;top:-4px;width:2px;height:15px;background:#111;opacity:.55;border-radius:1px}
 .track .fill{position:absolute;top:0;left:0;height:7px;border-radius:4px;opacity:.30}
 .bullet .bv{font-size:.71rem;font-weight:800;text-align:right}
 .ops{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}
 .ops .o{border-radius:6px;padding:9px 11px;box-shadow:var(--hair);background:var(--soft)}
 .ops .o .l{font-size:.61rem;text-transform:uppercase;letter-spacing:.04em;color:var(--mute);font-weight:700}
 .ops .o .v{font-size:1.16rem;font-weight:800;margin-top:1px}.ops .o .s{font-size:.67rem;color:var(--mute)}
 .expl{font-size:.71rem;color:var(--mute);line-height:1.5;margin-top:9px;background:var(--soft);border-radius:6px;padding:8px 11px;box-shadow:var(--hair)}
 .expl b{color:var(--ink)}
 table{width:100%;border-collapse:collapse}
 thead th{background:var(--navy);color:#fff;font-size:.63rem;text-transform:uppercase;letter-spacing:.04em;padding:8px 9px;text-align:right;font-weight:700}
 thead th:nth-child(-n+3){text-align:left}
 tbody td{padding:7px 9px;text-align:right;border-bottom:1px solid var(--line);font-size:.8rem}
 tbody td:nth-child(-n+3){text-align:left}
 tbody tr{cursor:pointer}tbody tr:hover{background:var(--soft)}
 .sid{color:var(--label);font-weight:500}.pace{font-weight:800}
 .heat{overflow-x:auto}.hgrid{display:grid;gap:2px}
 .hcell{font-size:.66rem;text-align:center;padding:4px 2px;border-radius:3px}
 .hhdr{font-size:.6rem;font-weight:700;color:var(--mute);text-align:center;padding:2px 0;line-height:1.15}
 .hrl{font-size:.63rem;color:var(--mute);text-align:right;padding-right:5px;font-weight:600;display:flex;align-items:center;justify-content:flex-end}
 .hrl.edge{color:var(--navy);font-weight:800}
 .foot{font-size:.72rem;color:var(--mute);line-height:1.5}.foot b{color:var(--ink)}
 .warn{background:#FFF7E6;border:1px solid #F0D68A;border-radius:8px;padding:10px 13px;font-size:.72rem;color:#7A5B12;line-height:1.5;margin-bottom:10px}
 .warn b{color:#5E4406}
</style>
"""

MOBILE_CSS = """
<style>
 .wrap{max-width:100%;padding:8px 8px 26px}
 .kbar{grid-template-columns:1fr 1fr;gap:7px}
 .row2{grid-template-columns:1fr}
 .drivers{grid-template-columns:1fr}
 .expl2{grid-template-columns:1fr}
 .mrow{grid-template-columns:1fr;gap:9px}
 .ops{grid-template-columns:1fr 1fr}
 .head{flex-direction:column;align-items:flex-start;gap:6px}
 .head .r{text-align:left}
 .big4grid{grid-template-columns:1fr !important}
</style>
"""

SKELETON = """
<div class="wrap">
  <div class="head">
    <div class="l"><div class="tick"></div><div class="name">VantEdge Auto<span>TAKE 5 · TIME REPORT</span></div></div>
    <div class="r"><b id="scope"></b><br><span id="datel"></span> · <span class="liv" id="asof"></span></div>
  </div>
  <div class="tabs" id="tabs"></div>
  <div class="tabs sub" id="subtabs" style="display:none"></div>
  <div id="view"></div>
</div>
"""

def html(payload, mobile=False):
    # Escape "</" so a scraped value containing </script> can't break out of the
    # inline <script> (review M2).
    data = json.dumps(payload).replace("</", "<\\/")
    css = CSS + (MOBILE_CSS if mobile else "")
    return css + SKELETON + (
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>'
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-annotation/3.0.1/chartjs-plugin-annotation.min.js"></script>'
        '<script>const P=' + data + ';const MOBILE=' + ('true' if mobile else 'false') + ';\n' + JS + '</script>')

JS = r"""
const C={navy:'#14273F',blue:'#2E6FB7',green:'#158A5A',red:'#D0342C',amber:'#B57611',teal:'#0E7490',purple:'#6C4FB6',mute:'#5B6472',line:'#E2E7EE'};
Chart.register(window['chartjs-plugin-annotation']);
Chart.defaults.font.family='-apple-system,Segoe UI,Arial,sans-serif';Chart.defaults.plugins.legend.display=false;
let CH=[];
function kill(){CH.forEach(c=>{try{c.destroy()}catch(e){}});CH=[];}
function scls(s){return s==='g'?'up':s==='r'?'down':'flat';}
const HELP={
 cars:'Cars serviced so far today. The comparison is vs the average of the last 4 same-weekdays by this same hour.',
 aro:'Average Repair Order = net sales / cars. Target is a flat $125 per car.',
 net:'Net sales so far today, compared with the same 4-week average by this hour.',
 big4:'Big 4 Score = the four attachment items (Air Filter, Cabin Filter, Wiper, Coolant) each measured against its target, then averaged. 100% = every target met.',
 lhpc:'Labor Hours Per Car = labor hours / cars. Lower is leaner; 1.10 is the balance target.'};
function nowLine(now){return {type:'line',scaleID:'x',value:now,borderColor:'#9AA6B6',borderWidth:1.5,borderDash:[4,3],
  label:{display:true,content:'NOW',position:'start',backgroundColor:C.navy,color:'#fff',font:{size:8,weight:700},padding:{x:4,y:2},borderRadius:3}};}
function opts(now,extra,tip){return {responsive:true,maintainAspectRatio:false,layout:{padding:{top:4,right:6}},interaction:{mode:'index',intersect:false},
  plugins:{annotation:{annotations:Object.assign({nl:nowLine(now)},extra||{})},tooltip:{backgroundColor:C.navy,padding:9,cornerRadius:6,titleFont:{size:11},bodyFont:{size:11},callbacks:tip||{}}},
  scales:{x:{grid:{display:false},border:{display:false},ticks:{color:C.mute,font:{size:10}}},
   y:{grid:{color:C.line},border:{display:false},ticks:{color:C.mute,font:{size:10}},beginAtZero:true}}};}
function ln(n,d,c,dash,f){return {label:n,data:d,borderColor:c,backgroundColor:f||c,borderDash:dash||[],borderWidth:2.4,tension:.4,pointRadius:0,pointHoverRadius:4,fill:f?'origin':false,spanGaps:false,borderCapStyle:'round'};}
function tline(v,col,txt){return {type:'line',scaleID:'y',value:v,borderColor:col,borderWidth:2,borderDash:[6,4],
  label:{display:true,content:txt,position:'end',backgroundColor:col,color:'#fff',font:{size:8,weight:700},padding:{x:4,y:2},borderRadius:3}};}
const DB='<div class="dayband"><div>Morning</div><div>Afternoon</div><div>Evening</div></div>';
const IC=['#2E6FB7','#0E7490','#6C4FB6','#B57611'];

function warnBlock(){return '<div class="warn"><b>Heads up — this page can take a moment to refresh.</b> Use the <b>Refresh</b> button up top to force the latest numbers. If the app has been idle for a while it goes to sleep on Streamlit\'s free tier, so the first load after a quiet spell can take 20–40 seconds to wake up. Give it a moment, then refresh.</div>';}

function renderStore(sp){
  kill();
  document.getElementById('scope').textContent=sp.name+' · #'+sp.id;
  document.getElementById('datel').textContent=sp.date;
  document.getElementById('asof').textContent='● live · '+sp.asof;
  const km=[['Cars',fmt(sp.cars.sofar,0),pc(sp.cars.pace_pct)+' vs 4-wk',sp.status.cars,'cars'],
    ['ARO ($/car)','$'+fmt(sp.aro.sofar,0),pc(sp.aro.gap_pct)+' vs $125',sp.status.aro,'aro'],
    ['Net revenue','$'+fmt(sp.net.sofar,0),pc(sp.net.pace_pct)+' vs 4-wk',sp.status.net,'net'],
    ['Big 4 (% goal)',fmt(sp.big4.score,0)+'%','goal 100%',sp.status.big4,'big4'],
    ['LHPC (hrs/car)',fmt(sp.lhpc.day,2),'target 1.10',sp.status.lhpc,'lhpc']];
  const kbar='<div class="kbar">'+km.map(m=>`<div class="kc ${m[3]}" title="${HELP[m[4]]}"><div class="l">${m[0]}</div><div class="v">${m[1]}</div><div class="d ${scls(m[3])}">${m[2]}</div></div>`).join('')+'</div>';
  const drv=sp.drivers.map(d=>`<div class="drv ${d.st}" title="${d.s}"><div class="t">${d.t}</div><div class="m ${scls(d.st)}">${d.m}</div><div class="s">${d.s}</div></div>`).join('');
  const wd=sp.date.split(',')[0];
  const row2='<div class="row2"><div class="card"><h3 class="sh">What\'s driving value — biggest movers</h3><div class="drivers">'+drv+'</div></div>'
    +'<div class="card"><h3 class="sh">How to read this</h3><div class="expl2">'
    +'<div class="pacebox"><div class="h">4-Week Comparison</div>Today so far vs a <b>normal '+wd+'</b> — the simple average of the last 4 same-weekdays at this same time. <b>+%</b> ahead, <b>−%</b> behind.</div>'
    +'<div class="pacebox"><div class="h">Projected</div>Where the day is trending by close: <b>today\'s banked total</b> plus the rest of a typical day, nudged by how today is pacing. An estimate, not a promise.</div>'
    +'</div></div></div>';
  const secs=[
    {k:'cars',t:'Cars',n:'cumulative today vs projected close',ac:C.blue,type:'cum',
     kp:[['So far',fmt(sp.cars.sofar,0),'',''],['Projected',fmt(sp.cars.est_close,0),pc(sp.cars.pace_pct),sp.status.cars],['vs 4-wk',pc(sp.cars.pace_pct),'',sp.status.cars]]},
    {k:'aro',t:'ARO — average repair order',n:'running revenue per car vs $125 target',ac:C.amber,type:'aro',
     kp:[['So far','$'+fmt(sp.aro.sofar,2),'',sp.status.aro],['Target','$125','',''],['Gap',pc(sp.aro.gap_pct),'',sp.status.aro]]},
    {k:'net',t:'Net revenue',n:'cumulative today vs projected close',ac:C.green,type:'cum',
     kp:[['So far','$'+fmt(sp.net.sofar,0),'',sp.status.net],['Projected','$'+fmt(sp.net.est_close,0),'',sp.status.net],['vs 4-wk',pc(sp.net.pace_pct),'',sp.status.net]]},
    {k:'big4',t:'Big 4 attachment',n:'% of goal over the day + per-item vs target',ac:C.teal,type:'big4',
     kp:[['Score',fmt(sp.big4.score,0)+'%','of goal',sp.status.big4],['Goal','100%','all 4 met',''],['Units',fmt(sp.big4.units,0),'today','']]},
    {k:'lhpc',t:'Labor efficiency · LHPC',n:'per-period hours behind rolling LHPC vs 1.10',ac:C.purple,type:'lhpc',
     kp:[['Now',fmt(sp.lhpc.now,2),'hrs/car',sp.status.lhpc],['Target','1.10','',''],['Day',fmt(sp.lhpc.day,2),'',sp.status.lhpc]]}];
  let body=kbar+row2;
  secs.forEach(s=>{
    const kb=s.kp.map(k=>`<div class="tile ${k[3]||''}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s ${scls(k[3])}">${k[2]||'&nbsp;'}</div></div>`).join('');
    let ch;
    if(s.type==='big4') ch=`<div class="big4grid" style="display:grid;grid-template-columns:1.1fr .9fr;gap:14px"><div>${DB}<div style="position:relative;height:196px"><canvas id="c_big4"></canvas></div></div><div><div class="l" style="font-size:.61rem;color:var(--label);font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin:0 0 8px">% of goal by item</div><div id="bul"></div></div></div>`;
    else if(s.type==='lhpc') ch=`<div>${DB}<div style="position:relative;height:230px"><canvas id="c_lhpc"></canvas></div><div class="expl"><b>LHPC = labor hours per car.</b> Lower = leaner / more efficient; higher = overstaffed for the volume. The <b>1.10 target</b> is the balance — well below can mean understaffed, above means idle labor.</div></div>`;
    else ch=`<div>${DB}<div style="position:relative;height:216px"><canvas id="c_${s.k}"></canvas></div></div>`;
    body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${s.ac}"></div><span class="st">${s.t}</span><span class="sn">${s.n}</span></div><div class="mrow"><div class="kbox">${kb}</div>${ch}</div></div>`;
  });
  body+='<div class="card"><div class="sechead"><div class="accent" style="background:var(--mute)"></div><span class="st">Operational detail</span><span class="sn">the numbers behind the day</span></div><div class="ops">'
    +sp.ops.map(o=>`<div class="o"><div class="l">${o[0]}</div><div class="v">${o[1]}</div><div class="s">${o[2]}</div></div>`).join('')
    +'</div><div class="foot" style="margin-top:9px"><b>4-Week Comparison</b> = vs the simple 4-week same-weekday average by this time. <b>Projected</b> = today\'s banked total plus a recency-weighted 4-week average of the rest of the day, scaled by today\'s pacing (clamped 0.7–1.5×). Projection is an estimate and has not yet been backtested.</div></div>';
  body+=warnBlock();
  document.getElementById('view').innerHTML=body;
  const L=sp.hours, fB='rgba(46,111,183,.10)';
  const carsTip={label:c=>c.dataset.label+': '+fmt(c.parsed.y,0)+' cars'};
  const netTip={label:c=>c.dataset.label+': $'+fmt(c.parsed.y,0)};
  CH.push(new Chart(c_cars,{type:'line',data:{labels:L,datasets:[ln('Actual',sp.cars.actual,C.blue,[],fB),ln('Projected',sp.cars.est,C.green,[6,4])]},options:opts(sp.now,null,carsTip)}));
  CH.push(new Chart(c_net,{type:'line',data:{labels:L,datasets:[ln('Actual',sp.net.actual,C.blue,[],fB),ln('Projected',sp.net.est,C.green,[6,4])]},options:opts(sp.now,null,netTip)}));
  CH.push(new Chart(c_aro,{type:'line',data:{labels:L,datasets:[ln('ARO',sp.aro.run,C.blue,[],fB)]},options:opts(sp.now,{t:tline(125,C.amber,'$125')},{label:c=>'ARO: $'+fmt(c.parsed.y,2)})}));
  CH.push(new Chart(c_big4,{type:'line',data:{labels:L,datasets:[ln('Big 4 % of goal',sp.big4.run,C.teal,[],'rgba(14,116,144,.10)')]},
    options:Object.assign(opts(sp.now,{t:tline(100,C.green,'goal 100%')},{label:c=>'Big 4: '+fmt(c.parsed.y,0)+'% of goal'}),
     {scales:{x:{grid:{display:false},border:{display:false},ticks:{color:C.mute,font:{size:10}}},y:{grid:{color:C.line},border:{display:false},beginAtZero:true,max:110,ticks:{color:C.mute,font:{size:10},callback:v=>v+'%'}}}})}));
  document.getElementById('bul').innerHTML=sp.big4.items.map((it,i)=>{const sc=it.attain>=90?C.green:(it.attain>=60?C.amber:C.red),col=IC[i];
    return `<div class="bullet" title="${it.name}: ${it.attach}% attach vs ${it.target}% target — ${fmt(it.attain,0)}% of goal"><span class="bn">${it.name}</span><div class="track"><span class="fill" style="width:${Math.min(100,it.attain)}%;background:${col}"></span><span class="tgt" style="left:100%"></span><span class="act" style="left:${Math.min(100,it.attain)}%;background:${col}"></span></div><span class="bv" style="color:${sc}">${it.attach}% / ${it.target}%</span></div>`;}).join('');
  CH.push(new Chart(c_lhpc,{data:{labels:L,datasets:[
    {type:'bar',label:'Hours',data:sp.lhpc.hours,backgroundColor:'rgba(108,79,182,.15)',yAxisID:'y1',borderRadius:3,barPercentage:.72,order:2},
    {type:'line',label:'Rolling LHPC',data:sp.lhpc.roll,borderColor:C.purple,borderWidth:2.6,tension:.4,pointRadius:0,pointHoverRadius:4,yAxisID:'y',order:1,borderCapStyle:'round'}]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
     plugins:{annotation:{annotations:{nl:nowLine(sp.now),t:tline(1.10,C.green,'1.10')}},tooltip:{backgroundColor:C.navy,padding:9,cornerRadius:6,callbacks:{label:c=>c.dataset.label==='Hours'?('Hours: '+fmt(c.parsed.y,1)):('LHPC: '+fmt(c.parsed.y,2)+' hrs/car')}}},
     scales:{x:{grid:{display:false},border:{display:false},ticks:{color:C.mute,font:{size:10}}},
      y:{position:'left',grid:{color:C.line},border:{display:false},title:{display:true,text:'LHPC (hrs/car)',color:C.mute,font:{size:9}},min:0,max:5,ticks:{color:C.mute,font:{size:10}}},
      y1:{position:'right',grid:{display:false},border:{display:false},title:{display:true,text:'labor hours',color:C.mute,font:{size:9}},min:0,ticks:{color:C.mute,font:{size:10}}}}}}));
}

function renderAdmin(ids,label){
  kill();
  document.getElementById('scope').textContent=label;
  document.getElementById('datel').textContent=P.date;
  document.getElementById('asof').textContent='● live · '+P.asof;
  const rows=ids.map(i=>P.rows[i]).filter(Boolean);
  const live=rows.filter(r=>r.cars!==null);
  const tc=live.reduce((a,r)=>a+r.cars,0),tn=live.reduce((a,r)=>a+r.net,0),aro=tc?tn/tc:0;
  const b4n=live.filter(r=>r.big4!==null&&r.cars);const b4avg=b4n.length?b4n.reduce((a,r)=>a+r.big4*r.cars,0)/b4n.reduce((a,r)=>a+r.cars,0):0;
  const avg=live.length?Math.round(live.reduce((a,r)=>a+(r.pace||0),0)/live.length):0;
  const km=[['Stores',ids.length,'reporting','flat','Number of stores in this scope.'],
    ['Total cars',fmt(tc,0),(avg>=0?'+':'')+avg+'% avg vs 4-wk',avg>=0?'g':'r','Total cars serviced across the scope, and the average 4-week comparison.'],
    ['Total net','$'+fmt(tn,0),'','flat','Total net sales across the scope so far today.'],
    ['Avg ARO','$'+fmt(aro,0),aro>=125?'at goal':'below $125',aro>=125?'g':'r','Cars-weighted average repair order vs the $125 target.'],
    ['Big 4 (% goal)',Math.round(b4avg)+'%','goal 100%',b4avg>=90?'g':(b4avg>=60?'a':'r'),'Cars-weighted Big 4 Score across the scope. 100% = every item at target.']];
  let body='<div class="kbar">'+km.map(m=>`<div class="kc ${m[3]}" title="${m[4]}"><div class="l">${m[0]}</div><div class="v">${m[1]}</div><div class="d ${scls(m[3])}">${m[2]||'&nbsp;'}</div></div>`).join('')+'</div>';
  body+='<div class="card"><h3 class="sh">How to read this</h3><div class="pacebox"><b>4-Week Comparison</b> = cars so far vs a <b>normal day</b> by this time (simple average of the last 4 same-weekdays). <b>+%</b> ahead, <b>−%</b> behind. ARO goal is a flat $125. <b>Big 4</b> is scored as % of goal (average of the four items vs their targets).</div></div>';
  const rk=[...rows].sort((a,b)=>(b.pace===null?-1e9:b.pace)-(a.pace===null?-1e9:a.pace));
  let tr='';
  rk.forEach((r,i)=>{const pc2=r.pace===null?'':(r.pace>=0?'+':'')+r.pace+'%';const col=r.pace===null?C.mute:(r.pace>=3?C.green:r.pace<=-3?C.red:C.amber);
    const bd=r.breakdown||{};const tip=`Air ${bd['Air Filter']||0}%  Cabin ${bd['Cabin Filter']||0}%  Wiper ${bd['Wiper Blade']||0}%  Coolant ${bd['Coolant Exchange']||0}%`;
    const dcell=r.diff+((r.diff_pct!==null&&r.diff_pct!==undefined)?' · '+r.diff_pct+'%':'');
    tr+=`<tr onclick="go('st:${r.id}')"><td class="sid">${i+1}</td><td><b>${r.name}</b> <span class="sid">(${r.id})</span></td><td class="sid">${r.open}</td>
      <td>${r.cars===null?'—':r.cars}</td><td>${r.net===null?'—':'$'+fmt(r.net,0)}</td><td>${r.aro===null?'—':'$'+fmt(r.aro,0)}</td>
      <td>${r.lhpc===null?'—':fmt(r.lhpc,2)}</td><td title="${tip}" style="cursor:help">${r.big4===null?'—':fmt(r.big4,0)+'%'}</td><td title="differentials: units · % of cars">${dcell}</td>
      <td class="pace" style="color:${col}">${pc2||'—'}</td></tr>`;});
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.red}"></div><span class="st">Store ranking</span><span class="sn">click a store to open its full dashboard</span></div>
    <table><thead><tr><th>#</th><th>Store</th><th>Open</th><th>Cars</th><th>Net</th><th>ARO</th><th>LHPC</th><th>Big 4</th><th>Diff</th><th>vs 4-wk</th></tr></thead><tbody>${tr}</tbody></table></div>`;
  const HR=['Before open'].concat(P.hours).concat(['After close']); let gmax=1;
  rk.forEach(r=>r.heat.forEach(v=>{if(v!==null&&v>gmax)gmax=v;}));
  let hg=`<div></div>`+rk.map(r=>`<div class="hhdr">${r.name}<br>${r.id}</div>`).join('');
  HR.forEach((hl,h)=>{const edge=(h===0||h===HR.length-1)?' edge':'';hg+=`<div class="hrl${edge}">${hl}</div>`+rk.map(r=>{const v=r.heat[h];const t=v===null?0:v/gmax;
    const bg=v===null?'#F5F7FA':`rgba(31,111,178,${(.08+t*.82).toFixed(2)})`;const cl=t>.55?'#fff':'#20303f';
    return `<div class="hcell" style="background:${bg};color:${cl}" title="${r.name} · ${hl}: ${v===null?'no cars':Math.round(v)+' cars'}">${v===null?'—':Math.round(v)}</div>`;}).join('');});
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.blue}"></div><span class="st">Heat map</span><span class="sn">cars per hour · darker = busier · first/last rows roll up before-open & after-close</span></div>
    <div class="heat"><div class="hgrid" id="hg" style="grid-template-columns:78px repeat(${rk.length},minmax(40px,1fr))">${hg}</div></div>
    <div style="display:flex;align-items:center;gap:9px;margin-top:10px;font-size:.7rem;color:var(--mute)"><span>Fewer</span><span style="flex:0 0 140px;height:9px;border-radius:5px;background:linear-gradient(90deg,rgba(31,111,178,.10),rgba(31,111,178,.92))"></span><span>More</span><span style="margin-left:auto">One absolute scale across these stores.</span></div></div>`;
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.teal}"></div><span class="st">Big 4 by store</span><span class="sn">Big 4 Score (% of goal) · goal line at 100%</span></div>
    <div style="position:relative;height:${Math.max(220,rk.length*26+50)}px"><canvas id="b4"></canvas></div></div>`;
  body+='<div class="foot card"><b>4-Week Comparison</b> = cars so far vs the simple 4-week same-weekday average by this time (+/−%). Click any store to open its full dashboard.</div>';
  body+=warnBlock();
  document.getElementById('view').innerHTML=body;
  const bs=[...rows].filter(r=>r.big4!==null).sort((a,b)=>a.big4-b.big4);
  CH.push(new Chart(document.getElementById('b4'),{type:'bar',data:{labels:bs.map(r=>r.name+' ('+r.id+')'),
    datasets:[{data:bs.map(r=>r.big4),backgroundColor:bs.map(r=>r.big4>=90?C.green:(r.big4>=60?C.amber:C.red)),borderRadius:5,barPercentage:.72}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
     plugins:{legend:{display:false},tooltip:{backgroundColor:C.navy,padding:9,cornerRadius:6,callbacks:{label:c=>c.parsed.x+'% of goal'}},
      annotation:{annotations:{g:{type:'line',scaleID:'x',value:100,borderColor:C.green,borderWidth:2,borderDash:[6,4],label:{display:true,content:'goal 100%',position:'end',backgroundColor:C.green,color:'#fff',font:{size:8,weight:700},padding:{x:4,y:2},borderRadius:3}}}}},
     scales:{x:{grid:{color:C.line},border:{display:false},max:110,ticks:{color:C.mute,callback:v=>v+'%'}},y:{grid:{display:false},border:{display:false},ticks:{color:C.navy,font:{size:11,weight:600}}}}}}));
}

function fmt(v,dp){if(v===null||v===undefined)return '—';return Number(v).toLocaleString(undefined,{minimumFractionDigits:dp,maximumFractionDigits:dp});}
function pc(v){if(v===null||v===undefined)return '—';return (v>=0?'+':'')+v+'%';}

let curRegion=null;
function setTop(k){document.querySelectorAll('#tabs .tab').forEach(t=>t.classList.toggle('on',t.dataset.k===k));}
function regionOf(id){return Object.keys(P.regions).find(r=>P.regions[r].includes(id));}
function buildSub(ids,active){
  const st=document.getElementById('subtabs');
  if(!ids||!ids.length){st.style.display='none';st.innerHTML='';return;}
  st.style.display='flex';
  st.innerHTML=ids.map(i=>`<div class="tab st${i===active?' on':''}" data-k="st:${i}">${P.stores[i].name} ${i}</div>`).join('');
  st.querySelectorAll('.tab').forEach(tb=>tb.onclick=()=>go(tb.dataset.k));
}
function go(key){
  if(key==='All'){
    curRegion=null;setTop('All');
    buildSub(P.tier==='district'?P.allowed:null,null);
    renderAdmin(P.allowed,P.scope_label);
  } else if(key.startsWith('reg:')){
    const r=key.slice(4);curRegion=r;setTop(key);
    const ids=P.regions[r].filter(i=>P.allowed.includes(i));
    buildSub(ids,null);renderAdmin(ids,r);
  } else {
    const id=key.slice(3);
    if(P.tier==='district'){setTop('All');buildSub(P.allowed,id);}
    else{const r=curRegion||regionOf(id);curRegion=r;setTop(r?'reg:'+r:'All');
      buildSub(r?P.regions[r].filter(i=>P.allowed.includes(i)):null,id);}
    renderStore(P.stores[id]);
  }
  window.scrollTo(0,0);
}

// init — empty-state guard so a store login can never render blank (review H3)
function emptyState(msg){document.getElementById('tabs').style.display='none';document.getElementById('subtabs').style.display='none';
  document.getElementById('view').innerHTML='<div class="card" style="text-align:center;padding:34px 18px"><div style="font-size:1.05rem;font-weight:800;color:var(--navy);margin-bottom:6px">Data is temporarily unavailable</div><div class="foot" style="max-width:520px;margin:0 auto">'+msg+'</div></div>'+warnBlock();}
if(!P.allowed||!P.allowed.length||!P.stores||!Object.keys(P.stores).length){
  emptyState('We couldn\'t load store data for this view right now. This is usually a brief data-source hiccup or a store that hasn\'t reported yet. Use the Refresh button up top in a minute.');
}
else if(P.tier==='store'){document.getElementById('tabs').style.display='none';document.getElementById('subtabs').style.display='none';renderStore(P.stores[P.allowed[0]]);}
else {
  const t=document.getElementById('tabs');let h='<div class="tab" data-k="All">'+(P.tier==='district'?'All my stores':'All')+'</div>';
  if(P.tier==='admin'){h+='<div class="tsep"></div>';Object.keys(P.regions).forEach(r=>h+=`<div class="tab reg" data-k="reg:${r}">${r}</div>`);}
  t.innerHTML=h;t.querySelectorAll('.tab').forEach(tb=>tb.onclick=()=>go(tb.dataset.k));
  go('All');
}
"""
