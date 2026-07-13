"""Take 5 Scorecard V3 - central config. No Streamlit import (testable)."""
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
BRAND = "VantEdge Auto"; SUBBRAND = "Take 5 · Time Report"

CITY = {"1503":"Springfield","1504":"Joplin","1505":"Springfield","1506":"Derby",
        "1507":"Cedar Rapids","1508":"Wichita","1509":"Ozark","1511":"Des Moines",
        "1512":"Jefferson City","1513":"Papillion","1515":"Columbia","1516":"Cedar Rapids",
        "1517":"Springfield","1521":"Columbia","1522":"Wichita"}
STORE_CODES = list(CITY.keys())

REGIONS = {"Central MO":["1512","1515","1521"], "Iowa":["1507","1511","1516"],
           "Nebraska":["1513"], "Springfield":["1503","1504","1505","1509","1517"],
           "Wichita":["1506","1508","1522"]}
# DM/AM tier: code -> (label, [stores]) - the area managers
DISTRICTS = {"1111":("DM South",["1503","1504","1505","1509","1517"]),
             "2222":("Wichita Area",["1506","1508","1522"]),
             "3333":("DM North",["1507","1511","1513","1516"]),
             "4444":("Central MO Area",["1512","1515","1521"])}
# Admin access is controlled solely by the ADMIN_PASSWORD secret (see app.py).
# No password is stored in source, so admin fails closed if the secret is unset.

HOURS = {0:(7,20),1:(7,20),2:(7,20),3:(7,20),4:(7,20),5:(7,18),6:(9,17)}
DOW = {0:"Mon",1:"Tues",2:"Wed",3:"Thurs",4:"Fri",5:"Sat",6:"Sun"}
DOW_FULL = {0:"Monday",1:"Tuesday",2:"Wednesday",3:"Thursday",4:"Friday",5:"Saturday",6:"Sunday"}
HIST_DAYS = 400                       # wide: section-9 picks the recent 4 same-weekdays.
# NOTE (V3): the seeded baseline is ~1yr old summer data, so this window MUST stay
# wide or the norms go empty. The review's "45-day cap" would delete the baseline;
# instead we harden fetch_history with desc order + an explicit row cap (below).
HIST_MAX_ROWS = 8000                  # explicit ceiling; desc order keeps NEWEST rows
                                      # if the PostgREST db-max-rows cap is lower (H1 fix)
SCORECARD_DAYS = 7                    # weekly matrix scorecard span

RECENCY_W = [0.40,0.30,0.20,0.10]      # weighted (estimated) - newest first
MAD_K = 3.0
PACE_CLAMP = (0.7,1.5)

ARO_TARGET = 125.0
LHPC_TARGET = 1.10
# Big 4 per-item attach-% targets (units/cars per item). V3: the headline Big 4 number is
# the AVERAGE of the four items' attach rates, not the sum. Averaging keeps it on a per-item
# ~0-20% scale and stops one multi-item car (or a pair-sold item like wipers) from ballooning
# the figure past 100%. Goal = average of the four item targets = 13.25%. Differentials are
# never folded in. (Mathematically this is the old summed rate / 4 vs the old 53% / 4, so
# pass/fail and grades are unchanged — only the display scale is saner.)
BIG4_TARGETS = {"Air Filter":25,"Cabin Filter":10,"Wiper Blade":10,"Coolant Exchange":8}
BIG4_GOAL = round(sum(BIG4_TARGETS.values())/len(BIG4_TARGETS), 2)   # 13.25 (avg item target)
BIG4_AMBER = 8                                 # amber floor for the average attach %
DIFF_TARGET = 3

# palette (also used by the PDF)
NAVY="#14273F"; RED="#D0342C"; BLUE="#2E6FB7"; GREEN="#158A5A"; AMBER="#B57611"
TEAL="#0E7490"; PURPLE="#6C4FB6"; INK="#0F172A"; MUTE="#5B6472"
