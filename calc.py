"""V2 pure math: section-9 forecast + all payload builders. No Streamlit/network."""
import datetime as dt, statistics
from config import (HOURS, DOW, DOW_FULL, RECENCY_W, MAD_K, PACE_CLAMP, ARO_TARGET,
                    LHPC_TARGET, BIG4_TARGETS, DIFF_TARGET, BIG45_TARGET)

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
def st_big45(pct):
    if pct is None: return "flat"
    return "g" if pct>=BIG45_TARGET else ("a" if pct>=BIG45_TARGET*0.6 else "r")
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
    bcum=cum_by_hour(today_rows,"big4_total_units"); ccum=cum_by_hour(today_rows,"cars")
    run=[]; lb=0.0; lc=0.0
    for h in hours:
        if h in bcum: lb=bcum[h]
        if h in ccum: lc=ccum[h]
        run.append(round(lb/lc*100,1) if (lc and h<=now_hour) else None)
    ba=big4_attach(latest)
    items=[{"name":n,"attach":round(ba["breakdown"][n],1),"target":BIG4_TARGETS[n]} for n in BIG4_TARGETS]
    return {"run":run,"sofar":round(ba["pct"],1) if ba["pct"] is not None else None,
            "target":BIG45_TARGET,"units":ba["units"],"items":items}

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
    lab=labor_block(latest)
    ops=[["Differentials",str(diff["units"]),f"${diff['amount']:,.0f} · {(diff['units']/dcars*100 if dcars else 0):.0f}% of cars"],
         ["Materials %",f"{latest.get('materials_pct') or 0:.0f}%","of net sales"],
         ["ASA",f"${latest.get('asa') or 0:,.2f}","ancillary avg"],
         ["Coupons",f"${latest.get('coupons') or 0:,.0f}","redeemed"],
         ["Discounts",f"${latest.get('discounts') or 0:,.0f}","applied"],
         ["New / Repeat",f"{latest.get('new_customers') or 0} / {latest.get('repeat_customers') or 0}","customer split"],
         ["Gross sales",f"${latest.get('gross_sales') or 0:,.0f}","before discounts"],
         ["Labor hours",f"{lab.get('hours') or 0:,.1f}","clocked today"]]
    status={"cars":st_pace(cars["pace_pct"]),"aro":st_aro(aro["sofar"]),
            "net":st_pace(net["pace_pct"]),"big4":st_big45(big4["sofar"]),"lhpc":st_lhpc(lhpc["day"])}
    return {"id":store,"name":city,"region":region,"hours":[hour_label(h) for h in hours],
            "now":hour_label(now_hour),"date":f"{DOW_FULL[weekday]}, {now:%b %-d %Y}",
            "asof":now.strftime("%-I:%M %p"),"open":latest.get("report_timestamp") or "—",
            "cars":cars,"net":net,"aro":aro,"big4":big4,"lhpc":lhpc,"diff":diff,"ops":ops,"status":status}

def build_admin_row(store, city, today_rows, hist, now):
    weekday=now.weekday(); o,c=HOURS[weekday]; hours=list(range(o,c+1)); now_hour=min(max(now.hour,o),c)
    if not today_rows:
        return {"id":store,"name":city,"open":"—","cars":None,"net":None,"aro":None,"lhpc":None,
                "b45":None,"diff":0,"pace":None,"heat":[None]*len(hours),"breakdown":{}}
    latest=today_rows[-1]; td=row_date(latest)
    cm=count_metric(today_rows,hist,hours,weekday,now_hour,"cars",td)
    cars=latest.get("cars") or 0; net=latest.get("net_sales") or 0
    ba=big4_attach(latest); dd=differentials(latest.get("line_items"))
    dpct=(dd["units"]/cars*100) if cars else 0
    lh=lhpc_series(today_rows,hours,now_hour)
    cpp=to_per_period(cum_by_hour(today_rows,"cars"))
    heat=[cpp.get(h) for h in hours]
    lat=None
    try:
        rt=latest.get("report_timestamp") or ""
        lat=rt
    except Exception: pass
    return {"id":store,"name":city,"open":latest.get("report_timestamp") or "—",
            "cars":cars,"net":round(net),"aro":round(net/cars,2) if cars else None,
            "lhpc":lh["day"],"b45":round((ba["pct"] or 0)+dpct,1),"diff":dd["units"],
            "pace":cm["pace_pct"],"heat":[round(v,1) if v is not None else None for v in heat],
            "breakdown":{n:round(ba["breakdown"][n],1) for n in ba["breakdown"]}}
