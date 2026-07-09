"""V2 dashboard component: dense HTML/Chart.js app driven by an injected JSON
payload. One template renders store view + admin/regional view + client-side
roller & drill-in. Returned as a string for st.components.v1.html."""
import json

CSS = """
<style>
 :root{--navy:#14273F;--red:#D0342C;--blue:#2E6FB7;--green:#158A5A;--amber:#B57611;--teal:#0E7490;
  --purple:#6C4FB6;--ink:#0F172A;--mute:#5B6472;--label:#8A93A2;--bg:#EBEEF3;--card:#FFFFFF;--soft:#F5F7FA;
  --line:#E2E7EE;--steel:#C2CCDA;--gbg:#E9F5EF;--rbg:#FBECEA;--abg:#FBF3E4;
  --hair:inset 0 0 0 1px rgba(15,23,42,.07);--sh:0 1px 2px rgba(15,23,42,.05);}
 *{box-sizing:border-box;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif}
 body{margin:0;background:var(--bg);color:var(--ink);font-size:13px;-webkit-font-smoothing:antialiased}
 .wrap{max-width:1280px;margin:0 auto;padding:10px 12px 30px}
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
 h3.sh{margin:0 0 8px;font-size:.66rem;text-transform:uppercase;letter-spacing:.07em;color:var(--label);font-weight:700}
 .kbar{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:10px}
 .kc{border-radius:7px;padding:10px 12px;box-shadow:var(--hair);border:1.5px solid var(--steel);background:var(--card)}
 .kc.g{border-color:var(--green);background:var(--gbg)}.kc.r{border-color:var(--red);background:var(--rbg)}.kc.a{border-color:var(--amber);background:var(--abg)}
 .kc .l{font-size:.63rem;text-transform:uppercase;letter-spacing:.05em;color:var(--mute);font-weight:700}
 .kc .v{font-size:1.46rem;font-weight:800;letter-spacing:-.6px;line-height:1.1;margin-top:2px}
 .kc .d{font-size:.71rem;font-weight:800;margin-top:2px}
 .up{color:var(--green)}.down{color:var(--red)}.flat{color:var(--amber)}
 .row2{display:grid;grid-template-columns:1.6fr 1fr 1fr;gap:10px;margin-bottom:10px}
 .drivers{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
 .drv{border-radius:6px;padding:9px 10px;box-shadow:var(--hair)}
 .drv.g{background:var(--gbg)}.drv.r{background:var(--rbg)}.drv.a{background:var(--abg)}
 .drv .t{font-size:.8rem;font-weight:700}.drv .m{font-size:.75rem;font-weight:800;margin-top:1px}.drv .s{font-size:.69rem;color:var(--mute)}
 .snap{display:flex;flex-direction:column;justify-content:space-between}.snap .big{font-size:.93rem;font-weight:800;color:var(--navy)}
 .pacebox{font-size:.73rem;color:var(--mute);line-height:1.45}.pacebox b{color:var(--ink)}
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
 .bullet{display:grid;grid-template-columns:100px 1fr 82px;align-items:center;gap:9px;margin:7px 0}
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
 .foot{font-size:.72rem;color:var(--mute);line-height:1.5}.foot b{color:var(--ink)}
 .scbtn{display:inline-block;background:var(--navy);color:#fff!important;text-decoration:none;border-radius:7px;padding:10px 16px;font-weight:700;font-size:.82rem;box-shadow:var(--sh)}
 .scsel{border:1px solid var(--line);border-radius:7px;padding:9px 11px;font-size:.82rem;font-weight:600;color:var(--ink);background:#fff}
</style>
"""

SKELETON = """
<div class="wrap">
  <div class="head">
    <div class="l"><div class="tick"></div><div class="name">VantEdge Auto<span>TAKE 5 · TIME REPORT</span></div></div>
    <div class="r"><b id="scope"></b><br><span id="datel"></span> · <span class="liv" id="asof"></span></div>
  </div>
  <div class="tabs" id="tabs"></div>
  <div id="view"></div>
</div>
"""

def html(payload):
    data = json.dumps(payload)
    return CSS + SKELETON + (
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>'
        '<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-annotation/3.0.1/chartjs-plugin-annotation.min.js"></script>'
        '<script>const P=' + data + ';\n' + JS + '</script>')

JS = r"""
const C={navy:'#14273F',blue:'#2E6FB7',green:'#158A5A',red:'#D0342C',amber:'#B57611',teal:'#0E7490',purple:'#6C4FB6',mute:'#5B6472',line:'#E2E7EE'};
Chart.register(window['chartjs-plugin-annotation']);
Chart.defaults.font.family='-apple-system,Segoe UI,Arial,sans-serif';Chart.defaults.plugins.legend.display=false;
let CH=[];
function kill(){CH.forEach(c=>{try{c.destroy()}catch(e){}});CH=[];}
function scls(s){return s==='g'?'up':s==='r'?'down':'flat';}
function nowLine(now){return {type:'line',scaleID:'x',value:now,borderColor:'#9AA6B6',borderWidth:1.5,borderDash:[4,3],
  label:{display:true,content:'NOW',position:'start',backgroundColor:C.navy,color:'#fff',font:{size:8,weight:700},padding:{x:4,y:2},borderRadius:3}};}
function opts(now,extra){return {responsive:true,maintainAspectRatio:false,layout:{padding:{top:4,right:6}},interaction:{mode:'index',intersect:false},
  plugins:{annotation:{annotations:Object.assign({nl:nowLine(now)},extra||{})},tooltip:{backgroundColor:C.navy,padding:8,cornerRadius:6}},
  scales:{x:{grid:{display:false},border:{display:false},ticks:{color:C.mute,font:{size:10}}},
   y:{grid:{color:C.line},border:{display:false},ticks:{color:C.mute,font:{size:10}},beginAtZero:true}}};}
function ln(n,d,c,dash,f){return {label:n,data:d,borderColor:c,backgroundColor:f||c,borderDash:dash||[],borderWidth:2.4,tension:.4,pointRadius:0,pointHoverRadius:4,fill:f?'origin':false,spanGaps:false,borderCapStyle:'round'};}
function tline(v,col,txt){return {type:'line',scaleID:'y',value:v,borderColor:col,borderWidth:2,borderDash:[6,4],
  label:{display:true,content:txt,position:'end',backgroundColor:col,color:'#fff',font:{size:8,weight:700},padding:{x:4,y:2},borderRadius:3}};}
const DB='<div class="dayband"><div>Morning</div><div>Afternoon</div><div>Evening</div></div>';
const IC=['#2E6FB7','#0E7490','#6C4FB6','#B57611'];

function renderStore(sp){
  kill();
  document.getElementById('scope').textContent=sp.name+' · #'+sp.id;
  document.getElementById('datel').textContent=sp.date;
  document.getElementById('asof').textContent='● live · '+sp.asof;
  const km=[['Cars',fmt(sp.cars.sofar,0),pc(sp.cars.pace_pct)+' pace',sp.status.cars],
    ['ARO','$'+fmt(sp.aro.sofar,0),pc(sp.aro.gap_pct)+' vs $125',sp.status.aro],
    ['Net revenue','$'+fmt(sp.net.sofar,0),pc(sp.net.pace_pct)+' pace',sp.status.net],
    ['Big 4 attachment',fmt(sp.big4.sofar,0)+'%','target '+sp.big4.target+'%',sp.status.big4],
    ['LHPC',fmt(sp.lhpc.day,2),'target 1.10',sp.status.lhpc]];
  const kbar='<div class="kbar">'+km.map(m=>`<div class="kc ${m[3]}"><div class="l">${m[0]}</div><div class="v">${m[1]}</div><div class="d ${scls(m[3])}">${m[2]}</div></div>`).join('')+'</div>';
  const drv=(t,st,m,s)=>`<div class="drv ${st}"><div class="t">${t}</div><div class="m ${scls(st)}">${m}</div><div class="s">${s}</div></div>`;
  const row2='<div class="row2" style="grid-template-columns:1.6fr 1fr"><div class="card"><h3 class="sh">What\'s driving value</h3><div class="drivers">'
    +drv('Traffic',sp.status.cars,pc(sp.cars.pace_pct)+' pace',fmt(sp.cars.sofar,0)+' cars · est. ~'+fmt(sp.cars.est_close,0))
    +drv('Average ticket',sp.status.aro,pc(sp.aro.gap_pct)+' vs target','$'+fmt(sp.aro.sofar,0)+' vs $125')
    +drv('Big 4 attachment',sp.status.big4,fmt(sp.big4.sofar,0)+'% of cars','target '+sp.big4.target+'%')
    +'</div></div><div class="card"><h3 class="sh">What is pace?</h3><div class="pacebox"><b>Pace</b> = today so far vs a <b>normal day</b> by now (simple avg of the last 4 same-weekdays). <b>+%</b> ahead, <b>−%</b> behind.</div></div></div>';
  const secs=[
    {k:'cars',t:'Cars',n:'cumulative today vs estimated close',ac:C.blue,type:'cum',
     kp:[['So far',fmt(sp.cars.sofar,0),'',''],['Estimated',fmt(sp.cars.est_close,0),pc(sp.cars.pace_pct),sp.status.cars],['Pace',pc(sp.cars.pace_pct),'',sp.status.cars]]},
    {k:'aro',t:'ARO',n:'running revenue per car vs $125 target',ac:C.amber,type:'aro',
     kp:[['So far','$'+fmt(sp.aro.sofar,2),'',sp.status.aro],['Target','$125','',''],['Gap',pc(sp.aro.gap_pct),'',sp.status.aro]]},
    {k:'net',t:'Net revenue',n:'cumulative today vs estimated close',ac:C.green,type:'cum',
     kp:[['So far','$'+fmt(sp.net.sofar,0),'',sp.status.net],['Estimated','$'+fmt(sp.net.est_close,0),'',sp.status.net],['Pace',pc(sp.net.pace_pct),'',sp.status.net]]},
    {k:'big4',t:'Big 4 attachment',n:'cumulative % of cars + per-item vs target',ac:C.teal,type:'big4',
     kp:[['Attach',fmt(sp.big4.sofar,0)+'%','of cars',sp.status.big4],['Target',sp.big4.target+'%','sum of 4',''],['Units',fmt(sp.big4.units,0),'today','']]},
    {k:'lhpc',t:'Labor efficiency · LHPC',n:'per-period hours behind rolling LHPC vs 1.10',ac:C.purple,type:'lhpc',
     kp:[['Now',fmt(sp.lhpc.now,2),'hrs/car',sp.status.lhpc],['Target','1.10','',''],['Day',fmt(sp.lhpc.day,2),'',sp.status.lhpc]]}];
  let body=kbar+row2;
  secs.forEach(s=>{
    const kb=s.kp.map(k=>`<div class="tile ${k[3]||''}"><div class="l">${k[0]}</div><div class="v">${k[1]}</div><div class="s ${scls(k[3])}">${k[2]||'&nbsp;'}</div></div>`).join('');
    let ch;
    if(s.type==='big4') ch=`<div style="display:grid;grid-template-columns:1.1fr .9fr;gap:14px"><div>${DB}<div style="position:relative;height:196px"><canvas id="c_big4"></canvas></div></div><div><div class="l" style="font-size:.61rem;color:var(--label);font-weight:700;text-transform:uppercase;letter-spacing:.05em;margin:0 0 8px">Attach % by item vs target</div><div id="bul"></div></div></div>`;
    else if(s.type==='lhpc') ch=`<div><div style="position:relative;height:230px"><canvas id="c_lhpc"></canvas></div><div class="expl"><b>LHPC = labor hours per car.</b> Lower = leaner / more efficient; higher = overstaffed for the volume. The <b>1.10 target</b> is the balance — well below can mean understaffed, above means idle labor.</div></div>`;
    else ch=`<div>${DB}<div style="position:relative;height:216px"><canvas id="c_${s.k}"></canvas></div></div>`;
    body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${s.ac}"></div><span class="st">${s.t}</span><span class="sn">${s.n}</span></div><div class="mrow"><div class="kbox">${kb}</div>${ch}</div></div>`;
  });
  body+='<div class="card"><div class="sechead"><div class="accent" style="background:#14273F"></div><span class="st">Score card</span><span class="sn">one-page KPI PDF</span></div><a class="scbtn" download="scorecard_'+sp.id+'.pdf" href="data:application/pdf;base64,'+((P.pdf&&P.pdf[sp.id])||'')+'">\u2b07  Download score card (PDF)</a></div>';
  body+='<div class="card"><div class="sechead"><div class="accent" style="background:var(--mute)"></div><span class="st">Operational detail</span><span class="sn">the numbers behind the day</span></div><div class="ops">'
    +sp.ops.map(o=>`<div class="o"><div class="l">${o[0]}</div><div class="v">${o[1]}</div><div class="s">${o[2]}</div></div>`).join('')
    +'</div><div class="foot" style="margin-top:9px"><b>Pace</b> = vs the simple 4-week same-weekday average by this time. <b>Estimated close</b> = the recency-weighted 4-week average (40/30/20/10) scaled by pace (clamped 0.7–1.5×).</div></div>';
  document.getElementById('view').innerHTML=body;
  const L=sp.hours, fB='rgba(46,111,183,.10)';
  CH.push(new Chart(c_cars,{type:'line',data:{labels:L,datasets:[ln('Actual',sp.cars.actual,C.blue,[],fB),ln('Estimated',sp.cars.est,C.green,[6,4])]},options:opts(sp.now)}));
  CH.push(new Chart(c_net,{type:'line',data:{labels:L,datasets:[ln('Actual',sp.net.actual,C.blue,[],fB),ln('Estimated',sp.net.est,C.green,[6,4])]},options:opts(sp.now)}));
  CH.push(new Chart(c_aro,{type:'line',data:{labels:L,datasets:[ln('ARO',sp.aro.run,C.blue,[],fB)]},options:opts(sp.now,{t:tline(125,C.amber,'$125')})}));
  CH.push(new Chart(c_big4,{type:'line',data:{labels:L,datasets:[ln('Big 4 %',sp.big4.run,C.teal,[],'rgba(14,116,144,.10)')]},options:opts(sp.now,{t:tline(sp.big4.target,C.amber,sp.big4.target+'%')})}));
  const MX=30;
  document.getElementById('bul').innerHTML=sp.big4.items.map((it,i)=>{const r=it.attach/it.target,sc=r>=1?C.green:(r>=.6?C.amber:C.red),col=IC[i];
    return `<div class="bullet"><span class="bn">${it.name}</span><div class="track"><span class="fill" style="width:${it.attach/MX*100}%;background:${col}"></span><span class="tgt" style="left:${it.target/MX*100}%"></span><span class="act" style="left:${it.attach/MX*100}%;background:${col}"></span></div><span class="bv" style="color:${sc}">${it.attach}% / ${it.target}%</span></div>`;}).join('');
  CH.push(new Chart(c_lhpc,{data:{labels:L,datasets:[
    {type:'bar',label:'Hours',data:sp.lhpc.hours,backgroundColor:'rgba(108,79,182,.15)',yAxisID:'y1',borderRadius:3,barPercentage:.72,order:2},
    {type:'line',label:'Rolling LHPC',data:sp.lhpc.roll,borderColor:C.purple,borderWidth:2.6,tension:.4,pointRadius:0,pointHoverRadius:4,yAxisID:'y',order:1,borderCapStyle:'round'}]},
    options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
     plugins:{annotation:{annotations:{nl:nowLine(sp.now),t:tline(1.10,C.green,'1.10')}},tooltip:{backgroundColor:C.navy,padding:8,cornerRadius:6}},
     scales:{x:{grid:{display:false},border:{display:false},ticks:{color:C.mute,font:{size:10}}},
      y:{position:'left',grid:{color:C.line},border:{display:false},title:{display:true,text:'LHPC',color:C.mute,font:{size:9}},min:0,max:2.2,ticks:{color:C.mute,font:{size:10}}},
      y1:{position:'right',grid:{display:false},border:{display:false},title:{display:true,text:'hours',color:C.mute,font:{size:9}},min:0,ticks:{color:C.mute,font:{size:10}}}}}}));
}

function renderAdmin(ids,label){
  kill();
  document.getElementById('scope').textContent=label;
  document.getElementById('datel').textContent=P.date;
  document.getElementById('asof').textContent='● live · '+P.asof;
  const rows=ids.map(i=>P.rows[i]).filter(Boolean);
  const live=rows.filter(r=>r.cars!==null);
  const tc=live.reduce((a,r)=>a+r.cars,0),tn=live.reduce((a,r)=>a+r.net,0),aro=tc?tn/tc:0;
  const td=live.reduce((a,r)=>a+r.diff,0),ah=live.filter(r=>(r.pace||0)>=0).length;
  const b45n=live.filter(r=>r.b45!==null&&r.cars);const b45avg=b45n.length?b45n.reduce((a,r)=>a+r.b45*r.cars,0)/b45n.reduce((a,r)=>a+r.cars,0):0;
  const avg=live.length?Math.round(live.reduce((a,r)=>a+(r.pace||0),0)/live.length):0;
  const km=[['Stores',ids.length,'reporting','flat'],['Total cars',fmt(tc,0),(avg>=0?'+':'')+avg+'% avg pace',avg>=0?'g':'r'],
    ['Total net','$'+fmt(tn,0),'','flat'],['Avg ARO','$'+fmt(aro,0),aro>=125?'at goal':'below $125',aro>=125?'g':'r'],['Big 4/5 %',Math.round(b45avg)+'%','target 53%',b45avg>=53?'g':(b45avg>=32?'a':'r')]];
  let body='<div class="kbar">'+km.map(m=>`<div class="kc ${m[3]}"><div class="l">${m[0]}</div><div class="v">${m[1]}</div><div class="d ${scls(m[3])}">${m[2]||'&nbsp;'}</div></div>`).join('')+'</div>';
  body+='<div class="card"><h3 class="sh">What is pace?</h3><div class="pacebox"><b>Pace</b> = cars so far vs a <b>normal day</b> by this time (simple avg of the last 4 same-weekdays). <b>+%</b> ahead, <b>−%</b> behind. ARO goal is a flat $125.</div></div>';
  // ranking
  const rk=[...rows].sort((a,b)=>(b.pace===null?-1e9:b.pace)-(a.pace===null?-1e9:a.pace));
  let tr='';
  rk.forEach((r,i)=>{const pc2=r.pace===null?'':(r.pace>=0?'+':'')+r.pace+'%';const col=r.pace===null?C.mute:(r.pace>=3?C.green:r.pace<=-3?C.red:C.amber);
    const bd=r.breakdown||{};const tip=`Air ${bd['Air Filter']||0}%  Cabin ${bd['Cabin Filter']||0}%  Wiper ${bd['Wiper Blade']||0}%  Coolant ${bd['Coolant Exchange']||0}%`;
    tr+=`<tr onclick="go('st:${r.id}')"><td class="sid">${i+1}</td><td><b>${r.name}</b> <span class="sid">(${r.id})</span></td><td class="sid">${r.open}</td>
      <td>${r.cars===null?'—':r.cars}</td><td>${r.net===null?'—':'$'+fmt(r.net,0)}</td><td>${r.aro===null?'—':'$'+fmt(r.aro,0)}</td>
      <td>${r.lhpc===null?'—':fmt(r.lhpc,2)}</td><td title="${tip}" style="cursor:help">${r.b45===null?'—':r.b45+'%'}</td><td>${r.diff}</td>
      <td class="pace" style="color:${col}">${pc2||'—'}</td></tr>`;});
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.red}"></div><span class="st">Store ranking</span><span class="sn">click a store to open its scorecard</span></div>
    <table><thead><tr><th>#</th><th>Store</th><th>Open</th><th>Cars</th><th>Net</th><th>ARO</th><th>LHPC</th><th>Big 4/5 %</th><th>Diff</th><th>Pace</th></tr></thead><tbody>${tr}</tbody></table></div>`;
  // heat map
  const HR=P.hours; let gmax=1;
  rk.forEach(r=>r.heat.forEach(v=>{if(v!==null&&v>gmax)gmax=v;}));
  let hg=`<div></div>`+rk.map(r=>`<div class="hhdr">${r.name}<br>${r.id}</div>`).join('');
  HR.forEach((hl,h)=>{hg+=`<div class="hrl">${hl}</div>`+rk.map(r=>{const v=r.heat[h];const t=v===null?0:v/gmax;
    const bg=v===null?'#F5F7FA':`rgba(31,111,178,${(.08+t*.82).toFixed(2)})`;const cl=t>.55?'#fff':'#20303f';
    return `<div class="hcell" style="background:${bg};color:${cl}">${v===null?'—':Math.round(v)}</div>`;}).join('');});
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.blue}"></div><span class="st">Heat map</span><span class="sn">cars per hour · darker = busier (absolute)</span></div>
    <div class="heat"><div class="hgrid" id="hg" style="grid-template-columns:44px repeat(${rk.length},minmax(40px,1fr))">${hg}</div></div>
    <div style="display:flex;align-items:center;gap:9px;margin-top:10px;font-size:.7rem;color:var(--mute)"><span>Fewer</span><span style="flex:0 0 140px;height:9px;border-radius:5px;background:linear-gradient(90deg,rgba(31,111,178,.10),rgba(31,111,178,.92))"></span><span>More</span><span style="margin-left:auto">One absolute scale across these stores.</span></div></div>`;
  // big 4/5 attachment
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.teal}"></div><span class="st">Big 4/5 attachment</span><span class="sn">overall attach % of cars by store · incl. differentials</span></div>
    <div style="position:relative;height:${Math.max(220,rk.length*26+50)}px"><canvas id="b45"></canvas></div></div>`;
  body+=`<div class="card"><div class="sechead"><div class="accent" style="background:${C.navy}"></div><span class="st">Score card</span><span class="sn">download a store's one-page PDF</span></div><div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap"><select id="scsel" class="scsel">${ids.map(i=>`<option value="${i}">${P.stores[i].name} (${i})</option>`).join('')}</select><a id="scdl" class="scbtn" download href="#">\u2b07 Download score card (PDF)</a></div></div>`;
  body+='<div class="foot card"><b>Pace</b> = cars so far vs the simple 4-week same-weekday average by this time (+/-%). Click any store to open its full scorecard.</div>';
  document.getElementById('view').innerHTML=body;
  const bs=[...rows].filter(r=>r.b45!==null).sort((a,b)=>a.b45-b.b45);
  CH.push(new Chart(document.getElementById('b45'),{type:'bar',data:{labels:bs.map(r=>r.name+' ('+r.id+')'),
    datasets:[{data:bs.map(r=>r.b45),backgroundColor:C.teal,borderRadius:5,barPercentage:.72}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',plugins:{legend:{display:false},tooltip:{backgroundColor:C.navy,padding:8,cornerRadius:6,callbacks:{label:c=>c.parsed.x+'% of cars'}}},
     scales:{x:{grid:{color:C.line},border:{display:false},ticks:{color:C.mute,callback:v=>v+'%'}},y:{grid:{display:false},border:{display:false},ticks:{color:C.navy,font:{size:11,weight:600}}}}}}));
  var sc=document.getElementById('scsel');if(sc){var upd=function(){var v=sc.value,a=document.getElementById('scdl');a.href='data:application/pdf;base64,'+((P.pdf&&P.pdf[v])||'');a.download='scorecard_'+v+'.pdf';};sc.onchange=upd;upd();}
}

function fmt(v,dp){if(v===null||v===undefined)return '—';return Number(v).toLocaleString(undefined,{minimumFractionDigits:dp,maximumFractionDigits:dp});}
function pc(v){if(v===null||v===undefined)return '—';return (v>=0?'+':'')+v+'%';}

function go(key){
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('on',t.dataset.k===key));
  if(key==='All') renderAdmin(P.allowed,P.scope_label);
  else if(key.startsWith('reg:')){const r=key.slice(4);renderAdmin(P.regions[r].filter(i=>P.allowed.includes(i)),r);}
  else {renderStore(P.stores[key.slice(3)]);}
  window.scrollTo(0,0);
}

// init
if(P.tier==='store'){document.getElementById('tabs').style.display='none';renderStore(P.stores[P.allowed[0]]);}
else {
  const t=document.getElementById('tabs');let h='<div class="tab on" data-k="All">'+(P.tier==='district'?'All my stores':'All')+'</div><div class="tsep"></div>';
  (P.tier==='admin'?Object.keys(P.regions):[]).forEach(r=>h+=`<div class="tab reg" data-k="reg:${r}">${r}</div>`);
  if(P.tier==='admin')h+='<div class="tsep"></div>';
  P.allowed.forEach(i=>h+=`<div class="tab st" data-k="st:${i}">${P.stores[i].name} ${i}</div>`);
  t.innerHTML=h;t.querySelectorAll('.tab').forEach(tb=>tb.onclick=()=>go(tb.dataset.k));
  renderAdmin(P.allowed,P.scope_label);
}
"""
