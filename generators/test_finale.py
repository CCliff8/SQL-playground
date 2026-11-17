"""Generates datasets/test_finale.sql (PostgreSQL). Deterministic. Run: python3 generators/test_finale.py

Tables: customers, subscriptions, invoices, events (same schema as saas_extended, without hubspot_customers).
Data is consistent (FKs enforced, no overlapping subscriptions, invoices/events only while a subscription is active) and
shaped for these exercises (kept here as design notes):
 1. Per size_band: issued invoices and average amount in Q3 2026 (Jul-Sep), bands without invoices shown as 0.
    -> the 1000+ band is fully churned before July 2026, so it has no Q3 invoices.
 2. Customers with an active subscription (ended_at IS NULL) that never issued an invoice.
    -> 2 recent customers have no invoices at all, 2 have only draft/cancelled ones (trap for status filters).
 3. Customers "active" in a month = events on >= 3 distinct days, per month of 2026.
 4. events.properties JSON (source, doc_type): share of WhatsApp events per month of 2026 and doc_type breakdown.
    -> login/export/report events carry no "source", so the denominator matters.
 5. Cohort retention by month of first ISSUED invoice, months 0..3 (recent cohorts have not reached month 3 yet).
Today in this dataset is 2026-11-17 (the current month is partial).
"""
import random, math, json, datetime as dt, os, calendar
random.seed(2026)
TODAY = dt.date(2026, 11, 17)
BASE = (2024, 10)           # month index 0
LAST = 25                   # 2026-11
def ym(i): y, m = divmod(BASE[1] - 1 + i, 12); return BASE[0] + y, m + 1
def mstart(i): y, m = ym(i); return dt.date(y, m, 1)
def mend(i): y, m = ym(i); return dt.date(y, m, calendar.monthrange(y, m)[1])
def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return repr(v) if isinstance(v, float) else str(v)
    return "'" + str(v).replace("'", "''") + "'"
def ins(table, cols, rows, chunk=400):
    out = []
    for i in range(0, len(rows), chunk):
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n" + ",\n".join("  (" + ", ".join(q(x) for x in r) + ")" for r in rows[i:i+chunk]) + ";")
    return "\n".join(out)

PLANS = ["Starter", "Pro", "Business", "Enterprise"]; PRICE = {"Starter": 49, "Pro": 199, "Business": 499, "Enterprise": 1500}
BANDS = ["1-10"] * 20 + ["11-50"] * 18 + ["51-200"] * 12 + ["201-1000"] * 8 + ["1000+"] * 2
PLAN_W = {"1-10": [7,3,0,0], "11-50": [3,5,2,0], "51-200": [0,3,6,1], "201-1000": [0,0,5,5], "1000+": [0,0,0,1]}
LAM = {"1-10": 1.5, "11-50": 3, "51-200": 6, "201-1000": 10, "1000+": 18}
BASEAMT = {"1-10": 450, "11-50": 900, "51-200": 1800, "201-1000": 3500, "1000+": 7000}
NUSERS = {"1-10": 2, "11-50": 3, "51-200": 6, "201-1000": 12, "1000+": 30}
SECTORS = {"Logistics": ["Trasporti", "Logistica"], "Construction": ["Costruzioni", "Edilizia"], "Food & Beverage": ["Alimentari", "Forneria"],
           "Retail": ["Market", "Commerciale"], "Manufacturing": ["Meccanica", "Industrie"], "Healthcare": ["Farmacia", "Clinica"], "Professional Services": ["Studio", "Consulting"]}
REGIONS = [("Italy", "S.r.l.", .55), ("Italy", "S.p.A.", .1), ("DACH", "GmbH", .12), ("Iberia", "S.L.", .08), ("France", "SAS", .08), ("Benelux", "BV", .07)]
SURN = ["Rossi","Bianchi","Ferrari","Esposito","Romano","Colombo","Ricci","Marino","Greco","Bruno","Gallo","Conti","DeLuca","Costa","Giordano","Mancini","Rizzo","Lombardi","Moretti","Barbieri","Fontana","Santoro","Mariani","Rinaldi","Caruso","Ferrara","Galli","Martini","Leone","Longo","Gentile","Martinelli","Vitale","Lombardo","Serra","Coppola","DeSantis","D'Angelo","Marchetti","Parisi","Villa","Conte","Ferretti","Sala","DeRosa","Pellegrino","Palumbo","Fabbri","Bernardi","Basile","Neri","Orlando","Sanna","Valentini","Piras","Monti","Cattaneo","Silvestri","Testa","Guerra"]
random.shuffle(SURN)

def simulate(band):
    """returns list over month idx -> (plan, mrr) or None"""
    disc = random.choice([1, 1, 1, 0.9, 0.85, 1.1])
    price = lambda p: round(PRICE[p] * disc, 2)
    start = random.choice(range(3, 25)) if random.random() > .06 else LAST
    plan = random.choices(PLANS, PLAN_W[band])[0]; state = (plan, price(plan)); out = [None] * (LAST + 1); last_plan = plan
    for t in range(start, LAST + 1):
        if state: out[t] = state
        if t == LAST: break
        r = random.random()
        if state:
            p, m = state
            if r < .020 and band != "1000+": last_plan, state = p, None                                  # churn
            elif r < .050:                                                                                # plan change
                i = PLANS.index(p); j = i + 1 if (random.random() < .65 and i < 3) or i == 0 else i - 1
                if band == "1-10": j = min(j, 1)
                state = (PLANS[j], price(PLANS[j]))
            elif r < .075: state = (p, round(m * random.choice([1.1, 1.15, 1.25]), 2))                    # seat expansion
            elif r < .085: state = (p, round(m * .9, 2))                                                  # contraction
        elif r < .07 and band != "1000+": state = (last_plan, price(last_plan))                           # returns
    return out

custs = []
for band in BANDS:
    life = simulate(band)
    if band == "1000+":
        life = [None] * (LAST + 1)
        s, e = (4, 19) if not any(c["band"] == "1000+" for c in custs) else (8, 18)
        for t in range(s, e + 1): life[t] = ("Enterprise", 1500.0 if s == 4 else 1275.0)   # both churned, no return
    custs.append({"band": band, "life": life})
# force a few "cancel and come back" customers
cands = [c for c in custs if c["band"] != "1000+" and c["life"][8] and c["life"][14] and c["life"][21]]
for c, (g, n) in zip(cands, [(10, 3), (14, 2), (17, 4)]):
    for t in range(g, g + n): c["life"][t] = None
for c in custs:
    c["start"] = next(t for t, v in enumerate(c["life"]) if v)
custs.sort(key=lambda c: (c["start"], random.random()))
quiet = set(random.sample([i for i, c in enumerate(custs) if c["band"] in ("1-10", "11-50") and c["start"] < 20], 2))   # never used the product

customers, subs, invoices, events = [], [], [], []
sid = 1; used_names = set()
for i, c in enumerate(custs):
    cid = i + 1; c["id"] = cid
    sector = random.choice(list(SECTORS)); region, suf, _ = random.choices(REGIONS, [r[2] for r in REGIONS])[0]
    while True:
        name = f"{SURN[i % len(SURN)]} {random.choice(SECTORS[sector])} {suf}"
        if name not in used_names: used_names.add(name); break
    created = mstart(c["start"]) - dt.timedelta(days=random.randint(0, 25))
    customers.append([cid, name, c["band"], region, sector, created.isoformat()])
    # subscriptions: group consecutive identical months
    life = c["life"]; t = 0
    while t <= LAST:
        if life[t]:
            u = t
            while u + 1 <= LAST and life[u + 1] == life[t]: u += 1
            subs.append([sid, cid, life[t][0], life[t][1], mstart(t).isoformat(), None if u == LAST else mend(u).isoformat()]); sid += 1
            t = u + 1
        else: t += 1
    # invoices
    for t in range(LAST + 1):
        if not life[t] or random.random() < .12: continue
        lam = LAM[c["band"]] * (1 + .03 * t)
        for _ in range(max(0, round(random.gauss(lam, lam ** .5)))):
            last_day = mend(t) if mend(t) <= TODAY else TODAY
            d = mstart(t) + dt.timedelta(days=random.randint(0, (last_day - mstart(t)).days))
            age = (TODAY - d).days; r = random.random()
            status = ("issued" if r < .70 else "draft" if r < .90 else "cancelled") if age <= 45 else ("issued" if r < .88 else "cancelled" if r < .99 else "draft")
            invoices.append([d, cid, round(BASEAMT[c["band"]] * random.lognormvariate(0, .7), 2), "active" if random.random() < .6 else "passive", status])
    # events
    if i in quiet: continue
    mu = random.choice([2, 2, 5, 5, 10]); users = [cid * 1000 + u for u in range(1, NUSERS[c["band"]] + 1)]
    for t in range(LAST + 1):
        if not life[t]: continue
        last_day = mend(t) if mend(t) <= TODAY else TODAY
        days = [mstart(t) + dt.timedelta(days=k) for k in range((last_day - mstart(t)).days + 1)]
        k = min(len(days), max(0, round(random.gauss(mu, 2))))
        days.sort(key=lambda d: -math.log(random.random()) / (1 if d.weekday() < 5 else .15))
        pw = .08 + .012 * t
        for d in days[:k]:
            for _ in range(random.randint(1, 3)):
                ts = dt.datetime(d.year, d.month, d.day, random.randint(7, 19), random.randint(0, 59), random.randint(0, 59))
                name = random.choices(["document_uploaded", "document_processed", "user_login", "invoice_exported", "report_viewed"], [35, 30, 15, 12, 8])[0]
                if name in ("document_uploaded", "document_processed"):
                    src = random.choices(["whatsapp", "email", "web", "api"], [pw, (1 - pw) * .4, (1 - pw) * .4, (1 - pw) * .2])[0]
                    props = {"source": src, "doc_type": random.choices(["delivery_note", "invoice", "receipt", "purchase_order"], [30, 35, 20, 15])[0]}
                    if name == "document_processed": props["pages"] = random.randint(1, 8)
                elif name == "user_login": props = {"device": random.choice(["desktop", "desktop", "mobile"])}
                elif name == "invoice_exported": props = {"format": random.choice(["csv", "xml", "pdf"])}
                else: props = {"report": random.choice(["monthly", "vat", "aging"])}
                events.append([ts, cid, random.choice(users), name, json.dumps(props)])

recent = [c for c in custs if c["life"][LAST] and c["start"] >= 20] or [c for c in custs if c["life"][LAST] and c["start"] >= 15]
no_inv, only_open = recent[:2], recent[2:4]
for c in no_inv: invoices = [r for r in invoices if r[1] != c["id"]]
for c in only_open:
    for r in invoices:
        if r[1] == c["id"]: r[4] = random.choice(["draft", "cancelled"])
invoices.sort(key=lambda r: (r[0], r[1])); invoices = [[n + 1, r[1], r[0].isoformat(), r[2], r[3], r[4]] for n, r in enumerate(invoices)]
events.sort(key=lambda r: (r[0], r[1])); events = [[n + 1, r[1], r[2], r[3], r[0].strftime("%Y-%m-%d %H:%M:%S+00"), r[4]] for n, r in enumerate(events)]

SCHEMA = """
CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY, company_name TEXT NOT NULL, size_band TEXT, region TEXT, sector TEXT, created_at DATE NOT NULL);
CREATE TABLE subscriptions (
  subscription_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers, plan TEXT NOT NULL,
  mrr_eur NUMERIC(10,2) NOT NULL, started_at DATE NOT NULL, ended_at DATE);
CREATE TABLE invoices (
  invoice_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers, created_at DATE NOT NULL, amount_eur NUMERIC(12,2) NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('active','passive')), status TEXT NOT NULL CHECK (status IN ('draft','issued','cancelled')));
CREATE TABLE events (
  event_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers, user_id INTEGER, event_name TEXT NOT NULL,
  event_ts TIMESTAMPTZ NOT NULL, properties JSONB);
"""
sql = "-- AUTO-GENERATED by generators/test_finale.py (PostgreSQL)\n" + SCHEMA + "\n"
sql += ins("customers", ["customer_id","company_name","size_band","region","sector","created_at"], customers) + "\n\n"
sql += ins("subscriptions", ["subscription_id","customer_id","plan","mrr_eur","started_at","ended_at"], subs) + "\n\n"
sql += ins("invoices", ["invoice_id","customer_id","created_at","amount_eur","type","status"], invoices) + "\n\n"
sql += ins("events", ["event_id","customer_id","user_id","event_name","event_ts","properties"], events, 500) + "\n\n"
open(os.path.join(os.path.dirname(__file__), "..", "datasets", "test_finale.sql"), "w").write(sql)
print({"customers": len(customers), "subscriptions": len(subs), "invoices": len(invoices), "events": len(events)})
