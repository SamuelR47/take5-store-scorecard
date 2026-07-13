"""V3 pure math: section-9 forecast + all payload builders. No Streamlit/network."""
import datetime as dt, statistics, math
from config import (HOURS, DOW, DOW_FULL, RECENCY_W, MAD_K, PACE_CLAMP, ARO_TARGET,
                    LHPC_TARGET, BIG4_TARGETS, DIFF_TARGET, BIG4_GOAL, BIG4_AMBER)

# ---------- row parsing ----------
def row_date(r):
    p=(r.get("pull_hour") or "").split("-"); return "-".join(p[:3]) if len(p)>=3 else None
def row_hour(r):
    p=(r.get("pull_hour") or "").split("-")
    try: return int(p[3]) if len(p)>=4 else None
    except ValueError: return None
def labor_block(r):
    d=r.get("data") or {}; return d.get("labor") or r.get("labor") or {}
def hour_label(h): return f"{h%12 or 12}{'a' if h<12 else 'p'}"

def get_metric(r,key):
    if key=="aro":
        c=r.get("cars") or 0; n=r.get("net_sales"); return (n/c) if (c and n is not None) else None
    if key=="labor_hours": return labor_block(r).get("hours")
    return r.get(key)

def cum_by_hour(rows,key):
    out={}
    for r in sorted(rows,key=lambda x:x.get("pull_time") or ""):
        h=row_hour(r)
        if h is None: continue
        v=get_metric(r,key)
        if v is not None: out[h]=float(v)
    return out
def to_per_period(cum):
    if not cum: return {}
    pp={}; prev=0.0
    for h in sorted(cum): pp[h]=cum[h]-prev; prev=cum[h]
    return pp

# ---------- holidays ----------
def _nth(y,m,wd,n):
    if n>0:
        d=dt.date(y,m,1); return d+dt.timedelta(days=((wd-d.weekday())%7)+7*(n-1))
    d=(dt.date(y,12,31) if m==12 else dt.date(y,m+1,1)-dt.timedelta(days=1))
    return d-dt.timedelta(days=((d.weekday()-wd)%7))
def _holidays(y):
    fixed=[dt.date(y,1,1),dt.date(y,6,19),dt.date(y,7,4),dt.date(y,11,11),dt.date(y,12,25)]
    fl=[_nth(y,1,0,3),_nth(y,2,0,3),_nth(y,5,0,-1),_nth(y,9,0,1),_nth(y,10,0,2),_nth(y,11,3,4)]
    out=set(fixed)|set(fl)
    for d in fixed:
        if d.weekday()==5: out.add(d-dt.timedelta(days=1))
        elif d.weekday()==6: out.add(d+dt.timedelta(days=1))
    return out
def is_holiday(d): return bool(d) and d in _holidays(d.year)

def _reject(vals,k=MAD_K):
    if not vals: return [],[]
    med=statistics.median(vals); th=k*statistics.median([abs(x-med) for x in vals])
    keep=[(i,x) for i,x in enumerate(vals) if abs(x-med)<=th]
    return ([x for _,x in keep],[i for i,_ in keep]) if keep else (list(vals),list(range(len(vals))))

def _same_wd(hist,weekday,exclude_date):
    byd={}
    for r in hist:
        d=row_date(r)
        if d: byd.setdefault(d,[]).append(r)
    dated=[]
    for d,rows in byd.items():
        if exclude_date and d==exclude_date: continue
        try: date=dt.date.fromisoformat(d)
        except (ValueError,TypeError): continue
        if date.weekday()==weekday and not is_holiday(date): dated.append((date,rows))
    dated.sort(key=lambda t:t[0],reverse=True)
    return dated[:len(RECENCY_W)]

def simple_norm(hist,weekday,key,exclude_date=None):
    """Pace baseline: simple mean of the last 4 same-weekday per-hour increments."""
    dated=_same_wd(hist,weekday,exclude_date)
    pps=[to_per_period(cum_by_hour(rows,key)) for _,rows in dated]
    out={}
    for h in sorted({h for pp in pps for h in pp}):
        vals=[pp[h] for pp in pps if h in pp]
        if vals: out[h]=statistics.fmean(vals)
    return out

def weighted_norm(hist,weekday,key,exclude_date=None):
    """Estimate baseline: recency-weighted (40/30/20/10) + MAD, per hour."""
    dated=_same_wd(hist,weekday,exclude_date)
    pps=[to_per_period(cum_by_hour(rows,key)) for _,rows in dated]
    out={}
    for h in sorted({h for pp in pps for h in pp}):
        vo,wo=[],[]
        for i,pp in enumerate(pps):
            if h in pp: vo.append(pp[h]); wo.append(RECENCY_W[i] if i<len(RECENCY_W) else RECENCY_W[-1])
        if not vo: continue
        _,idx=_reject(vo)
        num=sum(wo[i]*vo[i] for i in idx); den=sum(wo[i] for i in idx)
        out[h]=(num/den) if den else statistics.fmean(vo)
    return out

def _clamp(x): return max(PACE_CLAMP[0],min(PACE_CLAMP[1],x))

# ---------- status helpers ----------
def st_pace(pct):        # +/- % vs pace
    if pct is None: return "flat"
    return "g" if pct>=3 else ("r" if pct<=-3 else "a")
def st_aro(v):
    if v is None: return "flat"
    return "g" if v>=ARO_TARGET else ("a" if v>=ARO_TARGET*0.94 else "r")
def st_big4(pct):   # pct = overall Big 4 attach % (units/cars)
    if pct is None: return "flat"
    return "g" if pct>=BIG4_GOAL else ("a" if pct>=BIG4_AMBER else "r")
def st_lhpc(v):
    if v is None: return "flat"
    return "g" if v<=LHPC_TARGET else ("a" if v<=1.25 else "r")

def day_grade(aro, big4, lhpc):
    """Daily letter grade from the target-bearing KPIs only: ARO vs $125, Big 4 vs 53%,
    LHPC vs 1.10 (lower is better, so inverted). Each metric's achievement is capped at
    100% of its target so over-performing one can't paper over a miss on another. Average
    the available ones; at/above target = A, then one letter per full 10% below (B, C, D,
    ... continuing the alphabet). Returns None if nothing is gradeable yet."""
    ach=[]
    if aro is not None:  ach.append(min(aro/ARO_TARGET, 1.0))
    if big4 is not None: ach.append(min(big4/BIG4_GOAL, 1.0))
    if lhpc:             ach.append(min(LHPC_TARGET/lhpc, 1.0))
    if not ach: return None
    avg=sum(ach)/len(ach)*100
    if avg>=99.95: return "A"
    return chr(ord("A")+min(math.ceil((100-avg)/10), 25))

def grade_status(letter):
    """Color band for a letter grade: A/B green, C/D amber, else red."""
    if not letter: return "flat"
    return "g" if letter in ("A","B") else ("a" if letter in ("C","D") else "r")

# ---------- differentials & big4 ----------
def differentials(line_items):
    u=0; a=0.0
    for li in (line_items or []):
        if "differential" in (li.get("description") or "").lower():
            u+=li.get("units") or 0; a+=li.get("amount") or 0
    return {"units":u,"amount":round(a,2)}
def big4_attach(latest):
    b=latest.get("big4") or {}; cars=latest.get("cars") or 0
    units=latest.get("big4_total_units")
    if units is None: units=sum((b.get(n) or {}).get("units") or 0 for n in b)
    order=["Air Filter","Cabin Filter","Wiper Blade","Coolant Exchange"]
    br={n:((b.get(n) or {}).get("attach_pct") or 0) for n in order}
    return {"pct":(units/cars*100) if cars else None,"units":units,"breakdown":br}

def big4_avg(breakdown):
    """Headline Big 4 = the AVERAGE of the four items' attach rates (units/cars per item),
    so a multi-item car doesn't stack the number and it stays on a per-item ~0-20% scale.
    None when there's no data. (Equals the summed units/cars rate / 4.)"""
    if not breakdown: return None
    vals=[breakdown[n] for n in BIG4_TARGETS if n in breakdown]
    return round(statistics.fmean(vals),1) if vals else None

def open_time(latest):
    """Real store open time = 'TIME OPENED' from the report body, captured by the
    parser into the `data` blob. NOT report_timestamp (that's the report's as-of
    time and changes every pull). Normalize '5:57AM' -> '5:57 AM'; fall back to
    report_timestamp only if TIME OPENED is missing."""
    t=((latest.get("data") or {}).get("time_opened") or "").strip()
    if not t: return latest.get("report_timestamp") or "—"
    u=t.upper()
    return (t[:-2].rstrip()+" "+u[-2:]) if (u.endswith("AM") or u.endswith("PM")) else t

# ---------- cumulative + pace/estimate for a count metric ----------
def _cum_series(today_rows,hours,now_hour,key):
    cum=cum_by_hour(today_rows,key)
    arr=[]; last=0.0; seen=False
    for h in hours:
        if h in cum: last=cum[h]; seen=True
        arr.append(round(last,2) if (seen and h<=now_hour) else None)
    sofar=cum[max(cum)] if cum else 0.0
    return arr,sofar

def count_metric(today_rows,hist,hours,weekday,now_hour,key,today_date):
    sn=simple_norm(hist,weekday,key,today_date); wn=weighted_norm(hist,weekday,key,today_date)
    actual,sofar=_cum_series(today_rows,hours,now_hour,key)
    elapsed=[h for h in hours if h<=now_hour]; future=[h for h in hours if h>now_hour]
    exp_now=sum(sn.get(h,0) for h in elapsed)
    pace_pct=((sofar/exp_now)-1)*100 if exp_now else None
    wf=sum(wn.get(h,0) for h in elapsed)
    pf=_clamp(sofar/wf) if wf else 1.0
    est=[]; run=sofar
    for h in hours:
        if h<now_hour: est.append(None)
        elif h==now_hour: est.append(round(sofar,2))
        else: run+=wn.get(h,0)*pf; est.append(round(run,2))
    est_close=round(run,2)
    return {"actual":actual,"est":est,"sofar":round(sofar,2),"est_close":est_close,
            "pace_pct":round(pace_pct,1) if pace_pct is not None else None}

def aro_series(today_rows,hours,now_hour):
    ncum=cum_by_hour(today_rows,"net_sales"); ccum=cum_by_hour(today_rows,"cars")
    run=[]; lastn=0.0; lastc=0.0
    for h in hours:
        if h in ncum: lastn=ncum[h]
        if h in ccum: lastc=ccum[h]
        run.append(round(lastn/lastc,2) if (lastc and h<=now_hour) else None)
    sofar=(ncum[max(ncum)]/ccum[max(ccum)]) if (ncum and ccum and ccum[max(ccum)]) else None
    return {"run":run,"sofar":round(sofar,2) if sofar else None,"target":ARO_TARGET,
            "gap_pct":round((sofar/ARO_TARGET-1)*100,1) if sofar else None}

def big4_series(today_rows,hours,now_hour,latest):
    """V3: the line is the OVERALL Big 4 attach % (units/cars) hour by hour, measured
    against the 53% goal (the summed item targets). No differentials in the number."""
    nitems=len(BIG4_TARGETS)
    bcum=cum_by_hour(today_rows,"big4_total_units"); ccum=cum_by_hour(today_rows,"cars")
    run=[]; lb=0.0; lc=0.0
    for h in hours:
        if h in bcum: lb=bcum[h]
        if h in ccum: lc=ccum[h]
        # average attach across the four items = (total units / cars) / 4
        run.append(round(lb/lc*100/nitems,1) if (lc and h<=now_hour) else None)
    ba=big4_attach(latest)
    items=[{"name":n,"attach":round(ba["breakdown"][n],1),"target":BIG4_TARGETS[n]} for n in BIG4_TARGETS]
    return {"run":run,"pct":big4_avg(ba["breakdown"]),
            "target":BIG4_GOAL,"units":ba["units"],"items":items}

def lhpc_series(today_rows,hours,now_hour):
    lcum=cum_by_hour(today_rows,"labor_hours"); ccum=cum_by_hour(today_rows,"cars")
    lpp=to_per_period(lcum); cpp=to_per_period(ccum)
    hoursarr=[]; roll=[]; lc=0.0; ll=0.0
    for h in hours:
        hoursarr.append(round(lpp[h],1) if (h in lpp and h<=now_hour) else None)
        if h in lcum: ll=lcum[h]
        if h in ccum: lc=ccum[h]
        roll.append(round(ll/lc,2) if (lc and h<=now_hour) else None)
    # now = latest per-period lhpc; day = cumulative
    now=None
    for h in sorted(cpp):
        if h<=now_hour and cpp[h] and h in lpp: now=round(lpp[h]/cpp[h],2)
    day=round(lcum[max(lcum)]/ccum[max(ccum)],2) if (lcum and ccum and ccum[max(ccum)]) else None
    return {"hours":hoursarr,"roll":roll,"now":now,"day":day,"target":LHPC_TARGET}

# ---------- dynamic "what's driving value" ----------
def fmt_pct(v):
    return "—" if v is None else (("+" if v>=0 else "")+f"{v:g}%")

def build_drivers(weekday, cars, aro, net, big4, lhpc):
    """Rank the store's KPIs by how far they sit from normal/target and attach a
    neutral one-line 'so what'. Biggest movers (good or bad) surface first."""
    wd=DOW_FULL[weekday]; out=[]
    p=cars["pace_pct"]
    if p is None: out.append(("Traffic","flat","no reads yet",f"Waiting on today's first cars vs a normal {wd}.",0))
    else:
        msg=("Traffic running ahead of a normal "+wd if p>=3 else
             "Traffic behind a normal "+wd if p<=-3 else "Traffic tracking a normal "+wd)
        out.append(("Traffic",st_pace(p),fmt_pct(p)+" vs normal",msg+".",abs(p)))
    g=aro["gap_pct"]; av=aro["sofar"]
    if av is None: out.append(("Average ticket","flat","—","No completed tickets yet today.",0))
    else:
        msg=("Average ticket above the $125 target" if av>=ARO_TARGET else
             "Average ticket just under the $125 target" if av>=ARO_TARGET*0.94 else
             "Average ticket below $125, capping revenue per car")
        out.append(("Average ticket",st_aro(av),"$%.0f vs $125"%av,msg+".",abs(g) if g is not None else 0))
    sc=big4["pct"]
    if sc is None: out.append(("Big 4","flat","—","No Big 4 attachment recorded yet.",0))
    else:
        g="%.0f%%"%BIG4_GOAL
        msg=("Big 4 attachment at or above the "+g+" goal" if sc>=BIG4_GOAL else
             "Big 4 attachment near the "+g+" goal" if sc>=BIG4_AMBER else
             "Big 4 attachment below the "+g+" goal - attach room on most cars")
        out.append(("Big 4",st_big4(sc),"%.0f%% avg attach"%sc,msg+".",abs(sc-BIG4_GOAL)))
    d=lhpc["day"]
    if d is None: out.append(("Labor","flat","—","No labor hours logged yet today.",0))
    else:
        msg=("Labor lean for the volume" if d<=LHPC_TARGET else
             "Labor slightly heavy for the volume" if d<=1.25 else
             "Labor heavy for the volume - hours outrunning cars")
        out.append(("Labor",st_lhpc(d),"%.2f LHPC"%d,msg+".",abs(d-LHPC_TARGET)/LHPC_TARGET*100))
    out.sort(key=lambda t:t[4],reverse=True)
    return [{"t":t,"st":s,"m":m,"s":so} for (t,s,m,so,_) in out]

# ---------- full builders ----------
def build_store(store, city, region, today_rows, hist, now):
    weekday=now.weekday(); o,c=HOURS[weekday]; hours=list(range(o,c+1))
    now_hour=min(max(now.hour,o),c)
    latest=today_rows[-1] if today_rows else {}
    td=row_date(latest) if today_rows else None
    cars=count_metric(today_rows,hist,hours,weekday,now_hour,"cars",td)
    net =count_metric(today_rows,hist,hours,weekday,now_hour,"net_sales",td)
    aro =aro_series(today_rows,hours,now_hour)
    big4=big4_series(today_rows,hours,now_hour,latest)
    lhpc=lhpc_series(today_rows,hours,now_hour)
    diff=differentials(latest.get("line_items"))
    dcars=latest.get("cars") or 0
    diff["pct"]=round(diff["units"]/dcars*100,1) if dcars else None
    lab=labor_block(latest)
    ops=[["Differentials",str(diff["units"]),f"${diff['amount']:,.0f} · {(diff['pct'] or 0):.0f}% of cars"],
         ["Materials %",f"{latest.get('materials_pct') or 0:.0f}%","of net sales"],
         ["ASA",f"${latest.get('asa') or 0:,.2f}","ancillary avg"],
         ["Coupons",f"${latest.get('coupons') or 0:,.0f}","redeemed"],
         ["Discounts",f"${latest.get('discounts') or 0:,.0f}","applied"],
         ["New / Repeat",f"{latest.get('new_customers') or 0} / {latest.get('repeat_customers') or 0}","customer split"],
         ["Gross sales",f"${latest.get('gross_sales') or 0:,.0f}","before discounts"],
         ["Labor hours",f"{lab.get('hours') or 0:,.1f}","clocked today"]]
    status={"cars":st_pace(cars["pace_pct"]),"aro":st_aro(aro["sofar"]),
            "net":st_pace(net["pace_pct"]),"big4":st_big4(big4["pct"]),"lhpc":st_lhpc(lhpc["day"])}
    drivers=build_drivers(weekday,cars,aro,net,big4,lhpc)
    grade=day_grade(aro["sofar"],big4["pct"],lhpc["day"])
    return {"id":store,"name":city,"region":region,"hours":[hour_label(h) for h in hours],
            "now":hour_label(now_hour),"date":f"{DOW_FULL[weekday]}, {now:%b %-d %Y}",
            "asof":now.strftime("%-I:%M %p"),"open":open_time(latest),
            "cars":cars,"net":net,"aro":aro,"big4":big4,"lhpc":lhpc,"diff":diff,
            "ops":ops,"status":status,"drivers":drivers,"grade":grade}

def build_admin_row(store, city, today_rows, hist, now):
    weekday=now.weekday(); o,c=HOURS[weekday]; hours=list(range(o,c+1)); now_hour=min(max(now.hour,o),c)
    if not today_rows:
        return {"id":store,"name":city,"open":"—","cars":None,"net":None,"aro":None,"lhpc":None,
                "big4":None,"diff":0,"diff_pct":None,"pace":None,"heat":[None]*(len(hours)+2),"breakdown":{}}
    latest=today_rows[-1]; td=row_date(latest)
    cm=count_metric(today_rows,hist,hours,weekday,now_hour,"cars",td)
    cars=latest.get("cars") or 0; net=latest.get("net_sales") or 0
    ba=big4_attach(latest); dd=differentials(latest.get("line_items"))
    dpct=round(dd["units"]/cars*100,1) if cars else None
    lh=lhpc_series(today_rows,hours,now_hour)
    cpp=to_per_period(cum_by_hour(today_rows,"cars"))
    # Heat map with roll-up buckets: everything before the open hour and after the
    # close hour is summed into its own bucket so early/late cars aren't hidden.
    before=sum(v for h,v in cpp.items() if h<o); after=sum(v for h,v in cpp.items() if h>c)
    heat=[before if before else None]+[cpp.get(h) for h in hours]+[after if after else None]
    # V3 (fixes review M1): admin "Big 4" is the overall attach % (units/cars), same as
    # the store view, vs the 53% goal -- differentials are NO LONGER folded into the
    # numerator (that was the >100% bug). Differentials reported separately.
    return {"id":store,"name":city,"open":open_time(latest),
            "cars":cars,"net":round(net),"aro":round(net/cars,2) if cars else None,
            "lhpc":lh["day"],"big4":big4_avg(ba["breakdown"]),
            "diff":dd["units"],"diff_pct":dpct,
            "pace":cm["pace_pct"],"heat":[round(v,1) if v is not None else None for v in heat],
            "breakdown":{n:round(ba["breakdown"][n],1) for n in ba["breakdown"]}}

# ---------- daily-close summaries (yesterday + weekly scorecards) ----------
def day_summary(day_rows):
    """End-of-day KPI snapshot for one calendar day, from that day's most complete
    (last) row. Used by the yesterday and 7-day matrix score cards."""
    if not day_rows: return None
    latest=sorted(day_rows,key=lambda r:r.get("pull_time") or "")[-1]
    cars=latest.get("cars") or 0; net=latest.get("net_sales") or 0
    ba=big4_attach(latest); lab=labor_block(latest); lh=lab.get("hours")
    dd=differentials(latest.get("line_items"))
    aro_v=round(net/cars,2) if cars else None
    big4_v=big4_avg(ba["breakdown"])
    lhpc_v=round(lh/cars,2) if (lh and cars) else None
    return {"date":row_date(latest),"cars":cars,"net":round(net),
            "aro":aro_v,"big4":big4_v,"lhpc":lhpc_v,
            "diff":dd["units"],"diff_pct":round(dd["units"]/cars*100,1) if cars else None,
            "grade":day_grade(aro_v,big4_v,lhpc_v)}

def days_back_summaries(hist_rows, n, today_date):
    """Group history rows by date and return the last `n` distinct dates strictly
    BEFORE today, newest first, each summarized (skips days with no data)."""
    byd={}
    for r in hist_rows:
        d=row_date(r)
        if d and d!=today_date: byd.setdefault(d,[]).append(r)
    dates=sorted(byd,reverse=True)[:n]
    return [day_summary(byd[d]) for d in dates]
