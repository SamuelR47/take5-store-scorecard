"""V3 pure math: section-9 forecast + all payload builders. No Streamlit/network."""
import datetime as dt, statistics
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
    # Cumulative daily metrics only ever rise, so a per-hour increment can't be negative.
    # Floor at 0 so a bad/stale reading (e.g. a stray high value that later corrects down)
    # can never render as negative cars/sales for an hour. Defense-in-depth behind the
    # scraper's stale-report guard.
    if not cum: return {}
    pp={}; prev=0.0
    for h in sorted(cum): pp[h]=max(0.0, cum[h]-prev); prev=cum[h]
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
            "norm":round(exp_now,1) if exp_now else None,
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
    bcum=cum_by_hour(today_rows,"big4_total_units"); ccum=cum_by_hour(today_rows,"cars")
    run=[]; lb=0.0; lc=0.0
    for h in hours:
        if h in bcum: lb=bcum[h]
        if h in ccum: lc=ccum[h]
        run.append(round(lb/lc*100,1) if (lc and h<=now_hour) else None)
    ba=big4_attach(latest)
    items=[{"name":n,"attach":round(ba["breakdown"][n],1),"target":BIG4_TARGETS[n]} for n in BIG4_TARGETS]
    return {"run":run,"pct":round(ba["pct"],1) if ba["pct"] is not None else None,
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
        out.append(("Big 4",st_big4(sc),"%.0f%% attach"%sc,msg+".",abs(sc-BIG4_GOAL)))
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
def build_store(store, city, region, today_rows, hist, now, targets=None):
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
    # V4 (B-3): targets, drill-in constituents, drivers. `targets=None` reproduces the flat
    # defaults exactly, so the store-login view (which passes no targets) is unchanged.
    cars["wk"]=wk_norm_at_hour(hist,weekday,"cars",now_hour,td)["days"]
    net["wk"] =wk_norm_at_hour(hist,weekday,"net_sales",now_hour,td)["days"]
    cars_fn=wk_norm_at_hour(hist,weekday,"cars",c,td)["avg"]
    net_fn =wk_norm_at_hour(hist,weekday,"net_sales",c,td)["avg"]
    tg=resolve_targets(targets,cars_fn,net_fn)
    cars["tgt"]=tg["cars"]["value"]; cars["tgtSrc"]=tg["cars"]["source"]
    net["tgt"]=tg["net"]["value"];   net["tgtSrc"]=tg["net"]["source"]
    # Non-linear target line: normal-day cumulative shape scaled to the full-day target.
    cars["target_curve"]=target_series(hist,weekday,"cars",hours,cars["tgt"],td)
    net["target_curve"] =target_series(hist,weekday,"net_sales",hours,net["tgt"],td)
    aro["target"]=tg["aro"]["value"]; aro["tgtSrc"]=tg["aro"]["source"]
    if aro["sofar"]: aro["gap_pct"]=round((aro["sofar"]/tg["aro"]["value"]-1)*100,1)
    bb=latest.get("big4") or {}
    for it in big4["items"]:
        it["units"]=(bb.get(it["name"]) or {}).get("units") or 0
        it["target"]=tg["big4"]["items"].get(it["name"],it["target"])
    big4["target"]=tg["big4"]["goal"]
    lhpc["target"]=tg["lhpc"]["value"]; lhpc["variance"]=lhpc_variance(lhpc["day"],tg["lhpc"]["value"])
    aro_norm=(net_fn/cars_fn) if (net_fn and cars_fn) else None
    aro["drivers"]=drivers_for_aro(latest,aro["sofar"],aro["target"],aro_norm,big4["items"],dcars)
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
    return {"id":store,"name":city,"region":region,"hours":[hour_label(h) for h in hours],
            "now":hour_label(now_hour),"date":f"{DOW_FULL[weekday]}, {now:%b %-d %Y}",
            "asof":now.strftime("%-I:%M %p"),"open":open_time(latest),
            "cars":cars,"net":net,"aro":aro,"big4":big4,"lhpc":lhpc,"diff":diff,
            "ops":ops,"status":status,"drivers":drivers}

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
            "lhpc":lh["day"],"big4":round(ba["pct"],1) if ba["pct"] is not None else None,
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
    big4_v=round(ba["pct"],1) if ba["pct"] is not None else None
    lhpc_v=round(lh/cars,2) if (lh and cars) else None
    return {"date":row_date(latest),"cars":cars,"net":round(net),
            "aro":aro_v,"big4":big4_v,"lhpc":lhpc_v,
            "diff":dd["units"],"diff_pct":round(dd["units"]/cars*100,1) if cars else None}

def days_back_summaries(hist_rows, n, today_date):
    """Group history rows by date and return the last `n` distinct dates strictly
    BEFORE today, newest first, each summarized (skips days with no data)."""
    byd={}
    for r in hist_rows:
        d=row_date(r)
        if d and d!=today_date: byd.setdefault(d,[]).append(r)
    dates=sorted(byd,reverse=True)[:n]
    return [day_summary(byd[d]) for d in dates]

# ---------- V4 (D): weekly history (last week vs the last-4-week average) ----------
def daily_components(hist_rows, today_date):
    """Per calendar day (before today), the RAW pieces needed to aggregate a metric
    correctly across a week: cars, net, Big 4 units, labor hours. Using raw pieces
    (not the daily % KPIs) lets weekly ARO/Big4/LHPC be volume-weighted rather than a
    mean-of-daily-ratios. One row per day = that day's last (most complete) snapshot."""
    byd={}
    for r in hist_rows:
        d=row_date(r)
        if d and d!=today_date: byd.setdefault(d,[]).append(r)
    out={}
    for d,rows in byd.items():
        latest=sorted(rows,key=lambda r:r.get("pull_time") or "")[-1]
        ba=big4_attach(latest); lab=labor_block(latest)
        out[d]={"cars":latest.get("cars") or 0,"net":latest.get("net_sales") or 0,
                "big4_units":ba["units"] or 0,"labor":lab.get("hours")}
    return out

def _week_value(metric,C,N,U,L,has_labor):
    if metric=="cars": return round(C)
    if metric=="net":  return round(N)
    if metric=="aro":  return round(N/C,2) if C else None
    if metric=="big4": return round(U/C*100,1) if C else None
    if metric=="lhpc": return round(L/C,2) if (C and has_labor) else None
    return None

def weekly_series(hist_rows, today_date, metric, weeks=5):
    """Aggregate `metric` into the last `weeks` seven-day windows ending the day before
    `today_date`, oldest first (so the last entry is 'last week'). Ratio metrics are
    volume-weighted across each window. Each entry: label, value, cars, days, is_last."""
    comp=daily_components(hist_rows,today_date)
    try: t=dt.date.fromisoformat(today_date)
    except (ValueError,TypeError): return []
    res=[]
    for k in range(weeks-1,-1,-1):                 # oldest window first
        end=t-dt.timedelta(days=7*k+1); start=t-dt.timedelta(days=7*k+7)
        C=N=U=L=0.0; has_labor=False; ndays=0
        for d,v in comp.items():
            try: dd=dt.date.fromisoformat(d)
            except (ValueError,TypeError): continue
            if start<=dd<=end:
                C+=v["cars"]; N+=v["net"]; U+=v["big4_units"]
                if v["labor"] is not None: L+=v["labor"]; has_labor=True
                ndays+=1
        lab=f"{start:%-m/%-d}"
        res.append({"label":("Last wk" if k==0 else lab),"range":f"{start:%-m/%-d}–{end:%-m/%-d}",
                    "value":_week_value(metric,C,N,U,L,has_labor),
                    "cars":round(C),"days":ndays,"is_last":k==0})
    return res

def week_vs_baseline(series):
    """(last_week_value, avg_of_prior_weeks, pct_diff) from a weekly_series list."""
    if not series: return None,None,None
    last=series[-1]["value"]
    prior=[s["value"] for s in series[:-1] if s["value"] is not None]
    base=statistics.fmean(prior) if prior else None
    pct=((last/base)-1)*100 if (last is not None and base) else None
    return last, base, (round(pct,1) if pct is not None else None)

# ================= V4 (B): store-view redesign + admin targets (pure logic) =================
# See protocol/12. All additive; nothing here is wired into the payload yet (that's B-3),
# so the current dashboard is unaffected until then.

def winsorize(vals, k=MAD_K):
    """Cap outliers to median +/- k*MAD (KEEP them, don't drop). Samuel's choice for the
    4-week average: one anomalous same-weekday is dampened, not removed. Returns
    (capped_values, flags) where flags[i] is True if vals[i] was capped."""
    vals=list(vals)
    if len(vals)<3:
        return vals,[False]*len(vals)
    med=statistics.median(vals)
    mad=statistics.median([abs(x-med) for x in vals])
    if mad==0:
        return vals,[False]*len(vals)
    lo,hi=med-k*mad,med+k*mad
    out=[]; flags=[]
    for x in vals:
        if x<lo: out.append(lo); flags.append(True)
        elif x>hi: out.append(hi); flags.append(True)
        else: out.append(x); flags.append(False)
    return out,flags

def same_wd_cum(hist, weekday, key, now_hour, exclude_date=None):
    """Up to 4 same-weekdays (holidays already excluded by _same_wd), each day's
    CUMULATIVE value AT now_hour (the latest reading at or before now_hour). Newest first."""
    out=[]
    for date,rows in _same_wd(hist,weekday,exclude_date):
        cum=cum_by_hour(rows,key)
        elapsed=[h for h in cum if h<=now_hour]
        out.append((date.isoformat(), round(cum[max(elapsed)],2) if elapsed else 0.0))
    return out

def wk_norm_at_hour(hist, weekday, key, now_hour, exclude_date=None):
    """The '4-week average at this hour' the store sees: the WINSORIZED average of the 4
    same-weekdays' cumulative-by-now values, plus the constituent days for the drill-in
    bar chart. `days` shows the RAW value and whether it was capped for the average."""
    days=same_wd_cum(hist,weekday,key,now_hour,exclude_date)
    vals=[v for _,v in days]
    capped,flags=winsorize(vals)
    avg=statistics.fmean(capped) if capped else None
    return {"avg":round(avg,1) if avg is not None else None,
            "days":[{"date":d,"val":v,"capped":f} for (d,v),f in zip(days,flags)],
            "n":len(days)}

def resolve_targets(trow, cars_norm, net_norm):
    """Per-store target values + derivation strings. `trow` = this store's saved settings
    (may be empty/None); keys: cars_boost, net_boost (percent), aro_target, lhpc_target
    (absolute), big4_<Item> (absolute % per item). `cars_norm`/`net_norm` = the full-day
    4-week averages. Cars/Net = norm x (1+boost%); ARO/LHPC/Big4 = absolute overrides that
    DEFAULT to the flat config targets when unset. `source` is the admin/DM-only derivation.
    Projection never uses any of this (it stays on the raw 4-week average)."""
    trow=trow or {}
    def _boost(kkey,norm):
        b=float(trow.get(kkey,0) or 0)
        if norm is None: return None,None
        return round(norm*(1+b/100)), f"4-wk avg {round(norm)} {'+' if b>=0 else ''}{b:g}%"
    cars_v,cars_s=_boost("cars_boost",cars_norm)
    net_v,net_s=_boost("net_boost",net_norm)
    aro_set=trow.get("aro_target"); aro_v=float(aro_set) if aro_set not in (None,"") else ARO_TARGET
    lh_set=trow.get("lhpc_target"); lh_v=float(lh_set) if lh_set not in (None,"") else LHPC_TARGET
    items={}
    for n in BIG4_TARGETS:
        v=trow.get("big4_"+n)
        items[n]=float(v) if v not in (None,"") else float(BIG4_TARGETS[n])
    goal=sum(items.values())
    return {
        "cars":{"value":cars_v,"source":cars_s},
        "net":{"value":net_v,"source":net_s},
        "aro":{"value":round(aro_v,2),
               "source":(f"${aro_v:g} set" if aro_set not in (None,"") else f"default ${ARO_TARGET:g}")},
        "lhpc":{"value":round(lh_v,2),
                "source":(f"{lh_v:g} set" if lh_set not in (None,"") else f"default {LHPC_TARGET:g}")},
        "big4":{"items":items,"goal":round(goal,1),
                "source":f"goal {goal:g}% = sum of item targets"},
    }

def lhpc_variance(rolling, target):
    """Rolling-day LHPC minus target. Negative = leaner than target (good)."""
    if rolling is None or target is None: return None
    return round(rolling-target,2)

def norm_profile(hist, weekday, key, hours, exclude_date=None):
    """Normalized 0..1 cumulative shape of a normal day for this metric, from the simple
    4-week same-weekday per-hour increments. Used to SHAPE the target line so it follows a
    typical day instead of a straight ramp."""
    sn=simple_norm(hist,weekday,key,exclude_date)
    cum=[]; run=0.0
    for h in hours:
        run+=sn.get(h,0.0); cum.append(run)
    last=cum[-1] if cum else 0.0
    return [(c/last if last else 0.0) for c in cum]

def target_series(hist, weekday, key, hours, tgt, exclude_date=None):
    """Target line across the day = the normal-day cumulative shape scaled to end at the
    full-day target (4-week avg x (1+boost)). NOT linear."""
    if tgt is None: return []
    prof=norm_profile(hist,weekday,key,hours,exclude_date)
    return [round(p*tgt,2) for p in prof]

def drivers_for_aro(latest, aro_sofar, aro_target, aro_norm, big4_items, cars):
    """Rule-based, ranked explanation of WHY ARO sits where it does, using only data we
    already have. Returns drivers sorted by severity (biggest first); the store view fills
    its two ARO driver boxes from the top two. Each driver carries an adaptive message and
    a small chart spec the component renders client-side on expand.

    Levers considered: the lowest-attaching Big 4 item, discount+coupon load per car,
    differential attach, and today's ticket vs its own 4-week norm. Messages adapt to
    ahead/behind and degrade gracefully when a signal is missing."""
    cars=cars or 0
    out=[]
    # 1) Big 4 attach — the lowest item drags ARO, or strong attach is padding it.
    if big4_items:
        worst=min(big4_items,key=lambda it:(it["attach"]-it["target"]))
        best =max(big4_items,key=lambda it:(it["attach"]-it["target"]))
        gap=worst["target"]-worst["attach"]
        chart={"type":"bars","title":"Big 4 attach vs target",
               "data":[{"name":it["name"],"attach":it["attach"],"target":it["target"]} for it in big4_items]}
        if gap>2:
            out.append({"key":"big4","title":"Big 4 attach","score":gap+4,
                "status":"r" if gap>=worst["target"]*0.4 else "a",
                "message":(f"{worst['name']} is attaching {worst['attach']:g}% vs a {worst['target']:g}% "
                           f"target - the biggest Big 4 gap. Push-selling it is the clearest lever on $/car."),
                "chart":chart})
        else:
            out.append({"key":"big4","title":"Big 4 attach","score":2,
                "status":"g",
                "message":(f"Big 4 is well attached - {best['name']} at {best['attach']:g}% "
                           f"(target {best['target']:g}%) is padding the ticket. Keep it up."),
                "chart":chart})
    # 2) Discount + coupon load per car - a direct drag when high, a help when disciplined.
    disc=float(latest.get("discounts") or 0); coup=float(latest.get("coupons") or 0)
    per=((disc+coup)/cars) if cars else 0
    chartgb={"type":"pair","title":"$ per car",
             "data":[{"name":"Discounts","val":round(disc/cars,2) if cars else 0},
                     {"name":"Coupons","val":round(coup/cars,2) if cars else 0}]}
    if per>=4:
        out.append({"key":"givebacks","title":"Discounts & coupons","score":per,
            "status":"a" if per>=6 else "flat",
            "message":(f"Discounts + coupons are running ${per:.0f}/car (${disc+coup:,.0f} today) - "
                       f"that comes straight off ARO. Tightening approvals lifts the ticket."),"chart":chartgb})
    elif per>0:
        out.append({"key":"givebacks","title":"Discounts & coupons","score":2,"status":"g",
            "message":(f"Give-backs are light at ${per:.0f}/car - discipline here is protecting ARO."),
            "chart":chartgb})
    # 3) Differential attach - a high-margin add that moves the ticket.
    dd=differentials(latest.get("line_items")); dpct=(dd["units"]/cars*100) if cars else 0
    chartd={"type":"gauge","title":"Differential % of cars","data":{"val":round(dpct,1),"target":DIFF_TARGET}}
    if dpct<DIFF_TARGET:
        out.append({"key":"diff","title":"Differentials","score":(DIFF_TARGET-dpct)+1,"status":"a",
            "message":(f"Differentials on only {dpct:.0f}% of cars vs ~{DIFF_TARGET}% - each one is a "
                       f"high-margin add. More differential sales raise the ticket."),"chart":chartd})
    else:
        out.append({"key":"diff","title":"Differentials","score":1.5,"status":"g",
            "message":(f"Differentials on {dpct:.0f}% of cars (>= {DIFF_TARGET}% target) are lifting ARO."),
            "chart":chartd})
    # 4) Ancillary sales average.
    asa=float(latest.get("asa") or 0)
    if asa:
        out.append({"key":"asa","title":"Ancillary sales","score":abs(asa-12)/4+0.5,
            "status":"g" if asa>=12 else "a",
            "message":(f"Ancillary sales average ${asa:.0f}/car - "
                       f"{'a solid add on top of the core ticket' if asa>=12 else 'light; wiper/cabin-air/fluid upsells would lift ARO'}."),
            "chart":{"type":"pair","title":"ASA","data":[{"name":"Today","val":round(asa,2)},{"name":"~target","val":12}]}})
    # 5) Ticket vs its own 4-week norm - the summary lever.
    if aro_sofar is not None and aro_norm:
        gap=aro_norm-aro_sofar
        out.append({"key":"ticket","title":"Ticket vs normal","score":abs(gap),
            "status":"r" if gap>5 else ("a" if gap>0 else "g"),
            "message":(f"Average ticket ${aro_sofar:.0f} is ${abs(gap):.0f} "
                       f"{'below' if gap>0 else 'above'} the 4-week norm of ${aro_norm:.0f}."),
            "chart":{"type":"pair","title":"ARO vs 4-week",
                     "data":[{"name":"Today","val":round(aro_sofar,2)},{"name":"4-wk","val":round(aro_norm,2)}]}})
    out.sort(key=lambda d:d["score"],reverse=True)
    return out
