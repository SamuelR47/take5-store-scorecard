"""Take 5 Scorecard - central config: brand, stores, hours, forecast params, palette.
No Streamlit imports here so this module is trivially testable and importable anywhere."""
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
BRAND = "VantEdge Auto"
SUBBRAND = "Store Scorecard"

# All 15 sites. Display name + grey code in the UI. (Names repeat across sites; the
# store id disambiguates.)
CITY = {
    "1503": "Springfield",   "1504": "Joplin",        "1505": "Springfield",
    "1506": "Derby",         "1507": "Cedar Rapids",  "1508": "Wichita",
    "1509": "Ozark",         "1511": "Des Moines",    "1512": "Jefferson City",
    "1513": "Papillion",     "1515": "Columbia",      "1516": "Cedar Rapids",
    "1517": "Springfield",   "1521": "Columbia",      "1522": "Wichita",
}
STORE_CODES = list(CITY.keys())

# store login password == store code (per the site password sheet); admin via secret.
def store_password(code):        # kept as a function so the rule lives in one place
    return code
ADMIN_FALLBACK = "12345"         # used only if st.secrets has no ADMIN_PASSWORD

# Store open hours in Central by Python weekday (Mon=0..Sun=6): (open, close)
HOURS = {0: (7, 20), 1: (7, 20), 2: (7, 20), 3: (7, 20), 4: (7, 20), 5: (7, 18), 6: (9, 17)}
DOW = {0: "Mon", 1: "Tues", 2: "Wed", 3: "Thurs", 4: "Fri", 5: "Sat", 6: "Sun"}
STALE_HOURS = 2
# Wide window on purpose: the section-9 norm already selects the most RECENT 4
# same-weekday occurrences, so a wide fetch simply lets seeded/older history be
# used until live pulls accumulate and naturally take over (newest-first). No
# hard 6-week gate that hides valid history.
HIST_DAYS = 400

# Forecast (spec section 9)
RECENCY_W = [0.40, 0.30, 0.20, 0.10]
MAD_K = 3.0
PACE_CLAMP = (0.7, 1.5)

# ***Target = the normal curve inflated to create a stretch goal.***
# Projections and pace are ALWAYS measured against the true norm, never the target.
TARGET_MULT = 1.10

# Metric registry. money=formats as $, dp=decimal places, rate=not differenced per hour.
METRICS = {
    "cars":         {"label": "Cars",             "money": False, "dp": 0, "rate": False},
    "aro":          {"label": "ARO",              "money": True,  "dp": 2, "rate": True},
    "net_sales":    {"label": "Net revenue",      "money": True,  "dp": 0, "rate": False},
    "big4_total_units": {"label": "Big 4",        "money": False, "dp": 0, "rate": False},
    "labor_hours":  {"label": "Labor hours",      "money": False, "dp": 1, "rate": False},
    "lhpc":         {"label": "Labor hrs/car",    "money": False, "dp": 2, "rate": True},
}
RATE_KEYS = ("aro", "lhpc")
# Section order on the store page (confirmed): Cars, ARO, Net, Big 4, Labor.
SECTION_ORDER = ["cars", "aro", "net_sales", "big4_total_units", "labor_hours"]

# ---- VantEdge / Take 5 palette ----
NAVY  = "#14273F"; RED = "#E4002B"; BLUE = "#2E6FB7"; GREEN = "#1E8E4E"
STEEL = "#9FB4CC"; INK = "#1F2A37"; MUTE = "#5B6B7F"; LINE = "#E3E8EF"
LIGHT = "#F6F8FC"; GREYF = "#DDE4EE"; CODE = "#8DA2BD"; AMBER = "#E6A200"
# dial identity (distinct from the bars): sand expected, indigo actual, green ahead, red behind
EXP = "#CAD5E0"; EXPLN = "#93A2B4"; DIAL_ACT = "#0E86A3"   # slate expected, blue-teal actual
HEAT_SCALE = [[0.0,"#F7FBFF"],[0.25,"#CFE1F2"],[0.5,"#94C4DF"],[0.75,"#4A98C9"],[1.0,"#1F6FB2"]]
