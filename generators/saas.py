"""Generates datasets/saas.sql. Deterministic (fixed seed). Run: python3 generators/saas.py"""
import random, datetime as dt, os
random.seed(42)
D = dt.date
def q(v):
    if v is None: return "NULL"
    if isinstance(v, (int, float)): return str(v)
    return "'" + str(v).replace("'", "''") + "'"
def ins(table, cols, rows):
    out = [f"INSERT INTO {table} ({', '.join(cols)}) VALUES"]
    out.append(",\n".join("  (" + ", ".join(q(x) for x in r) + ")" for r in rows) + ";")
    return "\n".join(out)

SCHEMA = """
-- No foreign keys on purpose, so orphan rows can exist.
CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, company_name TEXT, size_band TEXT, region TEXT, created_at DATE);
CREATE TABLE subscriptions (subscription_id INTEGER PRIMARY KEY, customer_id INTEGER, plan TEXT, mrr_eur NUMERIC(10,2), started_at DATE, ended_at DATE);
CREATE TABLE invoices (invoice_id INTEGER PRIMARY KEY, customer_id INTEGER, created_at DATE, amount_eur NUMERIC);
CREATE TABLE events (event_id INTEGER PRIMARY KEY, customer_id INTEGER, user_id INTEGER, event_name TEXT, event_ts TIMESTAMPTZ);
"""
names = ["Acme","Globex","Initech","Umbrella","Hooli","Stark","Wayne","Wonka","Soylent","Vandelay","Cyberdyne","Tyrell","Aperture","Oscorp","Pied Piper","Dunder","Massive Dynamic","Gringotts","Nakatomi","Bluth","Prestige","Monarch","Sterling","Vehement","Rekall","Duff","Krusty","Gekko","Spacely","Cogswell","Bubba","Lexcorp","Zorg","Veidt","Ollivander","Weyland","Genco","Hanso","Kwik","Dharma","Tessier","Halcyon","Brightwater","Northwind","Contoso","Fabrikam","Litware","Tailspin","Adatum","Proseware","Lucerne","Margrave","Quanta","Ironclad","Foxglove","Parallax","Redwood","Skyline","Tundra","Zenith"]
suffix = ["GmbH","Ltd","SAS","BV","SpA","AB","Inc","S.L.","AG","Oy"]
region_of = {"GmbH":"DACH","AG":"DACH","Ltd":"UK","SAS":"FR","BV":"Benelux","SpA":"IT","AB":"Nordics","Oy":"Nordics","Inc":"US","S.L.":"ES"}

customers = []
cid = 1
for i in range(60):
    suf = random.choice(suffix)
    created = D(2023,1,1) + dt.timedelta(days=random.randint(0,650))
    customers.append([cid, f"{names[i]} {suf}", random.choice(["1-10","11-50","51-200","201-1000"]), region_of[suf], created.isoformat()])
    cid += 1
# --- inconsistencies in customers
customers[3][2] = None                       # NULL size_band
customers[7][2] = "unknown"                  # sentinel instead of NULL
customers[11][3] = None                      # NULL region
customers[15][3] = "dach"                    # case variant
customers[19][3] = "Germany"                 # different granularity
customers[22][3] = ""                        # empty string region
customers[25][1] = customers[25][1].upper()  # casing
customers[33][4] = "2027-03-01"              # future created_at
customers[36][1] = None                      # NULL company_name
# duplicate companies (same company entered twice, different formatting, different id)
customers.append([cid, customers[0][1].lower() + " ", customers[0][2], customers[0][3], "2024-06-15"]); cid += 1
customers.append([cid, customers[1][1].replace("Ltd","Limited").replace("GmbH","Gmbh"), customers[1][2], customers[1][3], "2024-09-02"]); cid += 1
customers.append([cid, "  " + customers[5][1], customers[5][2], customers[5][3], "2025-01-20"]); cid += 1
NC = len(customers)

# subscriptions
plans = {"Starter":49, "Pro":199, "Business":499, "Enterprise":1500}
subs = []
sid = 1
for c in customers[:56]:
    if c[0] in (5, 9, 14, 21): continue         # customers with NO subscription
    try: start = D.fromisoformat(c[4].replace("/", "-"))
    except: start = D(2024,1,1)
    start += dt.timedelta(days=random.randint(0,30))
    plan = random.choices(list(plans), [4,4,2,1])[0]
    n = random.choice([1,2,2,3,3])
    for k in range(n):
        end = None
        if k < n-1 or random.random() < 0.35:
            end = start + dt.timedelta(days=random.randint(60,400))
            if end > D(2026,11,1): end = None
        subs.append([sid, c[0], plan, round(plans[plan] * random.choice([1,1,1,0.9,1.1]), 2), start.isoformat(), end.isoformat() if end else None]); sid += 1
        if end is None: break
        start = end + dt.timedelta(days=random.choice([0,1,1,30,90]))   # gaps / back-to-back
        plan = random.choice(list(plans))
# --- inconsistencies in subscriptions
subs[2][2] = subs[2][2].lower()       # 'pro' vs 'Pro'
subs[5][2] = subs[5][2].upper()
subs[8][3] = None                      # NULL mrr
subs[11][3] = 0                        # free / trial
subs[14][3] = -199.0                   # negative (credit)
subs[17][5] = "2023-01-01"; subs[17][4] = "2024-02-01"     # ended before started
subs.append([sid, 9999, "Pro", 199.0, "2025-03-01", None]); sid += 1                # orphan customer
subs.append([sid, subs[0][1], "Enterprise", 1500.0, subs[0][4], None]); sid += 1    # overlaps with existing sub
subs.append([sid, 2, "Pro", 199.0, "2025-05-01", "2025-05-01"]); sid += 1          # zero-length
subs.append([sid, 4, "Business", 499.0, "2025-11-01", "2026-10-31"]); sid += 1
subs.append([sid, 6, "Starter", 49.0, "2026-12-01", None]); sid += 1                # starts in the future
subs.append([sid, 8, "Pro ", 199.0, "2025-07-01", None]); sid += 1                  # trailing space in plan
subs.append([sid, 10, "Team", 299.0, "2025-02-01", "2025-12-31"]); sid += 1         # legacy plan, not in list
subs = subs[:100]

# invoices
inv = []
iid = 1
for s in subs:
    if s[1] > NC or s[4] > "2026-11-15": continue
    d = D.fromisoformat(s[4])
    end = D.fromisoformat(s[5]) if s[5] else D(2026,10,1)
    m = 0
    while d <= end and m < 3 and s[3]:
        inv.append([iid, s[1], d.isoformat(), round(abs(s[3]) * random.choice([1,1,1,1,3,12]) , 2)]); iid += 1
        d += dt.timedelta(days=random.choice([30,31,90,365])); m += 1
random.shuffle(inv)
inv = inv[:92]
for i, r in enumerate(inv, 1): r[0] = i
iid = len(inv) + 1
# --- inconsistencies in invoices
inv[3][3] = None                                              # NULL amount
inv[6][3] = -abs(inv[6][3])                                   # refund / credit note
inv[9][3] = 0                                                 # zero invoice
inv.append([iid, inv[12][1], inv[12][2], inv[12][3]]); iid += 1       # exact duplicate (diff id)
inv.append([iid, inv[20][1], inv[20][2], inv[20][3]]); iid += 1       # another duplicate
inv.append([iid, 9999, "2025-04-01", 199.0]); iid += 1                # orphan customer
inv.append([iid, 5, "2025-06-01", 49.0]); iid += 1                    # customer without subscription
inv.append([iid, 30, "2022-01-01", 120.0]); iid += 1                  # before customer existed
inv.append([iid, 12, "2026-11-30", 499.0]); iid += 1                  # future invoice
inv.append([iid, 7, "2025-09-15", 99999.99]); iid += 1                # outlier
inv.append([iid, 8, "2025-09-15", 199.005]); iid += 1                 # sub-cent precision

# events
events = []
eid = 1
names_ev = ["login","create_report","export_csv","invite_user","dashboard_view","api_call"]
for i in range(88):
    c = random.choice(customers[:45])[0]
    ts = dt.datetime(2025,1,1) + dt.timedelta(minutes=random.randint(0, 60*24*320))
    events.append([eid, c, c*100 + random.randint(1,6), random.choice(names_ev), ts.strftime("%Y-%m-%d %H:%M:%S")]); eid += 1
events[4][2] = None                                           # NULL user
events[9][3] = events[9][3].upper()                           # LOGIN
events[14][3] = "Login "                                      # whitespace / case
events[19][3] = None                                          # NULL event_name
events[24][4] = events[24][4].replace(" ", "T") + "Z"         # ISO-T with Z
events[29][4] = events[29][4].replace(" ", "T") + "+02:00"    # tz offset
events.append([eid, 9999, 999901, "login", "2025-06-01 09:00:00"]); eid += 1              # orphan customer
events.append([eid, events[0][1], events[0][2], events[0][3], events[0][4]]); eid += 1     # exact duplicate event
events.append([eid, events[1][1], events[1][2], events[1][3], events[1][4]]); eid += 1
events.append([eid, 3, 300, "login", "2030-01-01 00:00:00"]); eid += 1                    # future event
events.append([eid, 5, 500, "login", "2025-08-01 10:00:00"]); eid += 1                    # customer without subscription
events.append([eid, 4, 400, "export_csv", "1970-01-01 00:00:00"]); eid += 1               # epoch-0 default
events.append([eid, 4, 400, "login", "2025-08-01"]); eid += 1                             # date-only
events.append([eid, 1, 100, "login", "2025-08-01 10:00:00"]); eid += 1
events.append([eid, 1, 100, "login", "2025-08-01 10:00:00"]); eid += 1                    # dup w/ different id again
events.append([eid, 2, 200, "api_call", "2025-12-31 23:59:59"]); eid += 1                 # boundary
events.append([eid, 2, 200, "api_call", "2026-01-01 00:00:00"]); eid += 1                 # boundary

sql = "-- AUTO-GENERATED by generators/saas.py (PostgreSQL)\n" + SCHEMA + "\n"
sql += ins("customers", ["customer_id","company_name","size_band","region","created_at"], customers) + "\n\n"
sql += ins("subscriptions", ["subscription_id","customer_id","plan","mrr_eur","started_at","ended_at"], subs) + "\n\n"
sql += ins("invoices", ["invoice_id","customer_id","created_at","amount_eur"], inv) + "\n\n"
sql += ins("events", ["event_id","customer_id","user_id","event_name","event_ts"], events) + "\n"
out = os.path.join(os.path.dirname(__file__), "..", "datasets", "saas.sql")
open(out, "w").write(sql)
print(len(customers), len(subs), len(inv), len(events))
