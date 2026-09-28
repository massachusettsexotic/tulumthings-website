#!/usr/bin/env python3
"""Build the cruise-port pages on tulumthings.com from the Things apps' own bundled data.

    python3 tools/build_port_pages.py            # rebuild every port page, hub, sitemap, robots
    python3 tools/build_port_pages.py --check    # also print a per-page summary

Reads (READ-ONLY) each app's Swift sources, exactly what ships inside the app:
    ~/<App>/<App>/Curated*.swift          hand-curated venues (name, description, coordinates)
    ~/<App>/<App>/PortInfo.swift          pier names, pier coordinates, logistics note, typical hours
    ~/<App>/<App>/DayTripsViews.swift     the ready-made days (ids + stops)
    ~/<App>/<App>/Localization.swift      English titles/summaries of those days, the "tricks"
    ~/<App>/<App>/Models.swift            area and category display names
    ~/<App>/<App>/BundledPhotosData.swift the human-reviewed Wikimedia Commons photos + credits
    ~/<App>/<App>/TravelerGuides2Views.swift  which trick keys the app shows

Writes (inside this repo only):
    <app>/ports/<port-slug>/index.html    one page per cruise port
    <app>/ports/index.html                one hub per app
    <app>/index.html                      ONLY the block between <!-- ports:start --> / <!-- ports:end -->
    sitemap.xml, robots.txt, ports.css

App Store links come from /app-store.json (one file for the whole site): set an app's value to its
numeric App Store ID when Apple approves it, then re-run this script and push. The pages also read that
file at load time, so even before a rebuild the "Coming soon" badge turns into the App Store link.

Walking minutes use the app's own formula (PortInfo.walkingMinutes): straight-line metres x 1.3,
at 75 m a minute (4.5 km/h); over 60 minutes the app says "shuttle or taxi" instead, and so do we.
"""
import html, json, math, os, re, sys, unicodedata
from datetime import date

HOME = os.path.expanduser("~")
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://tulumthings.com"

# --------------------------------------------------------------------------------------------- config
# One entry per app. `pages` maps a PortInfo pierName (or several) to a page. Apps with one port per
# Area (Norway, Alaska) derive their pages from PortInfo automatically (`auto`).
APPS = [
    dict(app="NassauThings", region="The Bahamas", pages=[
        dict(slug="nassau", port="Nassau", place="Nassau, The Bahamas", piers=["Nassau Cruise Port (Prince George Wharf)"])]),
    dict(app="StThomasThings", region="US Virgin Islands", pages=[
        dict(slug="havensight", port="Havensight", place="St. Thomas, US Virgin Islands", piers=["Havensight cruise dock (WICO)"]),
        dict(slug="crown-bay", port="Crown Bay", place="St. Thomas, US Virgin Islands", piers=["Crown Bay cruise dock"]),
        # Ships don't dock at St. John: a day there is the Red Hook ferry from St. Thomas. Anchor = the ferry dock.
        dict(slug="st-john", port="St. John", place="US Virgin Islands, by ferry from St. Thomas", piers=[],
             anchor_venue="Cruz Bay Ferry Dock", areas=["cruzBay", "stJohnNorth", "coralBay"],
             h1="St. John cruise day guide", dock_keys=["arrival.ferry.body", "trick.ferry.body"])]),
    dict(app="StMaartenThings", region="St. Maarten / St. Martin", pages=[
        dict(slug="philipsburg", port="Philipsburg", place="St. Maarten", piers=["Dr. A.C. Wathey Cruise Facility, Philipsburg"])]),
    dict(app="CozumelThings", region="Cozumel, Mexico", pages=[
        dict(slug="punta-langosta", port="Punta Langosta", place="Cozumel, Mexico", piers=["Punta Langosta pier, downtown San Miguel"]),
        dict(slug="international-pier", port="International Pier", place="Cozumel, Mexico", piers=["International Pier (SSA México)"]),
        dict(slug="puerta-maya", port="Puerta Maya", place="Cozumel, Mexico", piers=["Puerta Maya pier"])]),
    dict(app="RoatanThings", region="Roatán, Honduras", pages=[
        dict(slug="mahogany-bay", port="Mahogany Bay", place="Roatán, Honduras", piers=["Mahogany Bay cruise pier"]),
        dict(slug="coxen-hole", port="Coxen Hole (Town Center)", place="Roatán, Honduras", piers=["Town Center pier, Coxen Hole"])]),
    dict(app="JamaicaThings", region="Jamaica", pages=[
        dict(slug="montego-bay", port="Montego Bay", place="Jamaica", piers=["Montego Bay Cruise Port (Freeport)"]),
        dict(slug="falmouth", port="Falmouth", place="Jamaica", piers=["Historic Falmouth Cruise Port"]),
        dict(slug="ocho-rios", port="Ocho Rios", place="Jamaica", piers=["Ocho Rios Cruise Ship Pier", "Reynolds Pier, Ocho Rios"])]),
    dict(app="BermudaThings", region="Bermuda", pages=[
        dict(slug="royal-naval-dockyard", port="Royal Naval Dockyard", place="Bermuda", piers=["Heritage Wharf, Royal Naval Dockyard"]),
        dict(slug="hamilton", port="Hamilton", place="Bermuda", piers=["Front Street cruise berth, Hamilton"]),
        dict(slug="st-georges", port="St. George's", place="Bermuda", piers=["Ordnance Island cruise berth, St. George's"])]),
    dict(app="CaboThings", region="Los Cabos, Mexico", pages=[
        dict(slug="cabo-san-lucas", port="Cabo San Lucas", place="Baja California Sur, Mexico", piers=["Cabo San Lucas tender pier (marina)"])]),
    dict(app="TurksCaicosThings", region="Turks & Caicos", pages=[
        dict(slug="grand-turk", port="Grand Turk", place="Turks & Caicos Islands", piers=["Grand Turk Cruise Center pier"])]),
    dict(app="MaltaThings", region="Malta", pages=[
        dict(slug="valletta", port="Valletta", place="Malta", piers=["Valletta Cruise Port (Grand Harbour waterfront)"])]),
    dict(app="NorwayThings", region="Norway", auto=True, place="Norway"),
    dict(app="AlaskaThings", region="Alaska", auto=True, place="Alaska", place_overrides={"victoria": "British Columbia, Canada"}),
]
# TulumThings is left out on purpose: it has no pier data (no PortInfo.swift); Cozumel is CozumelThings' job.

# Categories that aren't "places to go" on a port day.
SKIP_CATS = {"transport", "help", "atm", "pharmacy", "hospital", "fuel", "groceries", "hotel", "events", "lodging", "practical"}
FOOD_CATS = {"restaurant", "cafe", "nightlife", "food"}
# sights only: OSM "snorkel"/"adventure" entries are mostly dive shops and tour sellers
OSM_CATS = {"landmark", "museum", "park", "beach", "culture", "familyFun", "market", "wildlife", "glacier"}
SHARE_M = 1500
NEAR_KM = 5.0          # also consider any curated venue within this straight line of the pier
MAX_PLACES, MAX_FOOD, MAX_TRIPS = 15, 4, 6
PRICE_RE = re.compile(r"(US\$|\$\s?\d|€\s?\d|\d\s?€|£\s?\d|\bUSD\b|\bEUR\b|\bNOK\b|\bBZD\b|\bL\s?\d|\d\s?(kr|NOK|pesos|lempiras|euros?|dollars?)\b|\bkr\s?\d)", re.I)
ABBREV = {"St", "Dr", "Mt", "Ft", "No", "Rd", "Ave", "Mr", "Mrs", "Ms", "Sr", "Jr", "vs", "approx", "e.g", "i.e", "U.S", "Ltd", "Co"}

# --------------------------------------------------------------------------------------------- helpers
def rd(p):
    with open(p, encoding="utf-8") as f: return f.read()
def wr(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: f.write(s)
E = lambda s: html.escape(str(s), quote=True)
SSTR = r'"((?:[^"\\]|\\.)*)"'

def unswift(s):
    s = re.sub(r"\\u\{([0-9a-fA-F]+)\}", lambda m: chr(int(m.group(1), 16)), s)
    return s.replace('\\"', '"').replace("\\n", " ").replace("\\t", " ").replace("\\'", "'").replace("\\\\", "\\")

def slugify(s):
    s = s.replace("ø", "o").replace("Ø", "O").replace("æ", "ae").replace("Æ", "AE").replace("'", "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def metres(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))

def walk(pier, v):
    """Mirror of PortInfo.walkingMeters / walkingMinutes / pierLabel in the apps."""
    m = metres(pier, (v["lat"], v["lon"])) * 1.3
    mins = max(1, int(round(m / 75.0)))
    return m, mins

def walk_label(m, mins, what="the pier"):
    if mins <= 60: return f"{mins} min walk"
    km = m / 1000
    return f"{km / 1.609:.0f} mi / {km:.0f} km from {what} — taxi or shuttle"

def sentences(text):
    parts, cur = [], ""
    for tok in re.split(r"(?<=[.!?])\s+", text.strip()):
        cur = (cur + " " + tok).strip() if cur else tok
        last = cur.rstrip(".!?").split(" ")[-1] if cur else ""
        if last in ABBREV or re.fullmatch(r"[A-Z]", last or "x"): continue
        parts.append(cur); cur = ""
    if cur: parts.append(cur)
    return parts

def brief(desc, limit=240):
    """First sentence(s) of the app's own description, skipping any sentence that states a price."""
    out = ""
    for s in sentences(desc):
        if PRICE_RE.search(s): continue
        if out and len(out) + len(s) + 1 > limit: break
        out = (out + " " + s).strip()
        if len(out) >= 70: break
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0].rstrip(",;:—–- ") + "…"
    return out

# --------------------------------------------------------------------------------------------- read an app
def app_src(app):
    for d in (os.path.join(HOME, app, app), os.path.join(HOME, app, app, app)):
        if os.path.exists(os.path.join(d, "PortInfo.swift")): return d
    sys.exit(f"{app}: no PortInfo.swift under ~/{app}")

def read_app(app):
    src = app_src(app)
    A = dict(app=app, src=src)
    # areas + categories
    models = rd(os.path.join(src, "Models.swift"))
    def enum_cases(name):
        m = re.search(r"enum %s\b[^{]*\{(.*?)\n\}" % name, models, re.S)
        return dict(re.findall(r"case (\w+) = " + SSTR, m.group(1))) if m else {}
    A["areas"] = {k: unswift(v) for k, v in enum_cases("Area").items()}
    A["cats"] = {k: unswift(v) for k, v in enum_cases("Category").items()}
    # venues
    venues = []
    osm = []
    for f in sorted(os.listdir(src)):
        if re.search(r"OSMData\d*\.swift$", f):
            for blk in rd(os.path.join(src, f)).split("Venue(")[1:]:
                m = re.search(r"name:\s*" + SSTR + r".*?category:\s*\.(\w+),\s*area:\s*\.(\w+),\s*latitude:\s*(-?[\d.]+),\s*longitude:\s*(-?[\d.]+)", blk, re.S)
                if m: osm.append(dict(name=unswift(m.group(1)), cat=m.group(2), area=m.group(3), lat=float(m.group(4)), lon=float(m.group(5))))
    A["osm"] = osm
    for f in sorted(os.listdir(src)):
        if not (f.startswith("Curated") and f.endswith(".swift")): continue
        for blk in rd(os.path.join(src, f)).split("Venue(")[1:]:
            g = lambda pat: (re.search(pat, blk, re.S) or [None, None])[1]
            name, desc = g(r"name:\s*" + SSTR), g(r"description:\s*" + SSTR)
            lat, lon = g(r"latitude:\s*(-?[\d.]+)"), g(r"longitude:\s*(-?[\d.]+)")
            if not (name and lat and lon): continue
            venues.append(dict(name=unswift(name), desc=unswift(desc or ""), cat=g(r"category:\s*\.(\w+)"), area=g(r"area:\s*\.(\w+)"),
                               lat=float(lat), lon=float(lon), file=f))
    seen, A["venues"] = set(), []
    for v in venues:                                   # same name+area dedup the app does
        k = (v["name"], v["area"])
        if k in seen: continue
        seen.add(k); A["venues"].append(v)
    A["by_name"] = {}
    for v in A["venues"]: A["by_name"].setdefault(v["name"], v)
    # ports
    pi = rd(os.path.join(src, "PortInfo.swift"))
    A["ports"] = []
    for m in re.finditer(r"\.(\w+):\s*PortInfo\(area:\s*\.\w+,\s*pierName:\s*" + SSTR + r",\s*pier:\s*CLLocationCoordinate2D\(latitude:\s*(-?[\d.]+),\s*longitude:\s*(-?[\d.]+)\),\s*note:\s*" + SSTR + r",\s*typicalHours:\s*" + SSTR, pi, re.S):
        A["ports"].append(dict(area=m.group(1), pier=unswift(m.group(2)), lat=float(m.group(3)), lon=float(m.group(4)),
                               note=unswift(m.group(5)), hours=unswift(m.group(6))))
    # English strings
    loc = rd(os.path.join(src, "Localization.swift"))
    A["en"] = {k: unswift(v) for k, v in re.findall(r'"([\w.]+)":\s*\[\s*"en"\s*:\s*' + SSTR, loc)}
    # day trips
    dt = rd(os.path.join(src, "DayTripsViews.swift"))
    A["trips"] = []
    for blk in dt.split("DayTrip(id:")[1:]:
        tid = re.match(r'\s*"([^"]+)"', blk).group(1)
        stops = [unswift(s) for s in re.findall(r"venueName:\s*" + SSTR, blk)]
        A["trips"].append(dict(id=tid, title=A["en"].get(f"trip.{tid}.title", ""), sub=A["en"].get(f"trip.{tid}.sub", ""), stops=stops))
    # tricks the app actually shows
    g2 = os.path.join(src, "TravelerGuides2Views.swift")
    m = re.search(r'ForEach\(\[([^\]]*)\], id: \\\.self\) \{ key in\s*\n[^\n]*\n\s*Text\(Strings\.t\("trick', rd(g2)) if os.path.exists(g2) else None
    A["tricks"] = re.findall(r'"(\w+)"', m.group(1)) if m else []
    # bundled photos
    A["photos"] = {}
    bp = os.path.join(src, "BundledPhotosData.swift")
    if os.path.exists(bp):
        for key, url, credit, page in re.findall(SSTR + r":\s*Entry\(url:\s*" + SSTR + r",\s*credit:\s*" + SSTR + r",\s*page:\s*" + SSTR, rd(bp)):
            A["photos"][unswift(key)] = dict(url=unswift(url), credit=unswift(credit), page=unswift(page))
    return A

def photo_for(A, v):
    p = A["photos"].get(f'{v["name"]}|{v["lat"]:.5f}|{v["lon"]:.5f}')
    if not p: return None
    u = p["url"].split("?")[0]
    if "/thumb/" not in u or not re.search(r"/\d+px-[^/]+$", u): return None   # only light thumbnails, never originals
    return dict(url=re.sub(r"/\d+px-([^/]+)$", r"/330px-\1", u), credit=p["credit"], page=p["page"])

# --------------------------------------------------------------------------------------------- page model
def resolve_pages(cfg, A):
    if cfg.get("auto"):
        pages = []
        for p in A["ports"]:
            full = A["areas"].get(p["area"], p["area"])
            port = full.split(" & ")[0]
            pages.append(dict(slug=slugify(port), port=port, full=full, place=cfg.get("place_overrides", {}).get(p["area"], cfg["place"]),
                              piers=[p["pier"]], areas=[p["area"]]))
        return pages
    pages = []
    for pg in cfg["pages"]:
        pg = dict(pg)
        if "areas" not in pg: pg["areas"] = sorted({p["area"] for p in A["ports"] if p["pier"] in pg["piers"]})
        pages.append(pg)
    return pages

def page_anchor(pg, A):
    if pg.get("anchor_venue"):
        v = A["by_name"][pg["anchor_venue"]]
        return (v["lat"], v["lon"])
    p = next(p for p in A["ports"] if p["pier"] == pg["piers"][0])
    return (p["lat"], p["lon"])

def build_model(cfg, A):
    pages = resolve_pages(cfg, A)
    pier_names = {p["pier"] for p in A["ports"]}
    for pg in pages:
        for pier in pg["piers"]:
            assert pier in pier_names, f'{A["app"]}: pier "{pier}" not in PortInfo.swift ({sorted(pier_names)})'
        pg["anchor"] = page_anchor(pg, A)
    anchors = [(pg, pg["anchor"]) for pg in pages]
    def nearest_page(pt):
        return min(anchors, key=lambda a: metres(a[1], pt))[0]
    pier_venue_names = set()
    for pg in pages:
        pa = pg["anchor"]
        # the pier itself is a curated venue in most apps: keep it out of "places"
        for v in A["venues"]:
            if metres(pa, (v["lat"], v["lon"])) < 250 and v["cat"] in ("transport",): pier_venue_names.add(v["name"])
    for pg in pages:
        pa = pg["anchor"]
        cand = [v for v in A["venues"] if v["cat"] not in SKIP_CATS and v["name"] not in pier_venue_names and v["desc"]
                and (v["area"] in pg["areas"] or metres(pa, (v["lat"], v["lon"])) <= NEAR_KM * 1000)]
        # a venue sitting nearer another page's pier belongs to that page, unless it's in this page's own areas
        # (piers within ~1.5 km of each other share their surroundings, e.g. Cozumel's two southern piers)
        def mine(v):
            pt = (v["lat"], v["lon"])
            return v["area"] in pg["areas"] or metres(pa, pt) <= metres(nearest_page(pt)["anchor"], pt) + SHARE_M
        cand = [v for v in cand if mine(v)]
        cand.sort(key=lambda v: metres(pa, (v["lat"], v["lon"])))
        places, food = [], 0
        for v in cand:
            if v["cat"] in FOOD_CATS:
                if food >= MAX_FOOD: continue
                food += 1
            m, mins = walk(pa, v)
            text = brief(v["desc"])
            if not text: continue
            places.append(dict(v=v, m=m, mins=mins, text=text, photo=photo_for(A, v)))
            if len(places) >= MAX_PLACES: break
        pg["places"] = places
        # thin page? add the app's bundled OpenStreetMap sights within walking distance: name, type, minutes only
        extra = []
        if len(places) < 10:
            have = {re.sub(r"[^a-z0-9]", "", n.lower()) for n in [p["v"]["name"] for p in places] + list(pier_venue_names)}
            taken = [(p["v"]["lat"], p["v"]["lon"]) for p in places]
            for v in sorted(A["osm"], key=lambda v: metres(pa, (v["lat"], v["lon"]))):
                key = re.sub(r"[^a-z0-9]", "", v["name"].lower())
                if v["cat"] not in OSM_CATS or key in have or not mine(v): continue
                if any(metres((v["lat"], v["lon"]), q) < 120 for q in taken): continue   # same place, other spelling

                m, mins = walk(pa, v)
                if mins > 30: break
                have.add(key); taken.append((v["lat"], v["lon"])); extra.append(dict(v=v, m=m, mins=mins))
                if len(extra) >= 12: break
        pg["extra"] = extra
        pg["walkable"] = sum(1 for p in places if p["mins"] <= 60)
        # trips: first stop nearest this page, or most stops nearest this page
        trips = []
        for t in A["trips"]:
            pts = [(A["by_name"][s]["lat"], A["by_name"][s]["lon"]) for s in t["stops"] if s in A["by_name"]]
            if not pts or not t["title"]: continue
            first = t["stops"][0] in A["by_name"] and nearest_page((A["by_name"][t["stops"][0]]["lat"], A["by_name"][t["stops"][0]]["lon"])) is pg
            votes = sum(1 for p in pts if nearest_page(p) is pg)
            if first or votes * 2 > len(pts): trips.append(t)
        pg["trips"] = trips[:MAX_TRIPS]
        pg["trip_total"] = len(trips)
        # where ships dock + logistics, straight from PortInfo
        docks = []
        for pier in pg["piers"]:
            p = next(p for p in A["ports"] if p["pier"] == pier and p["area"] in pg["areas"]) if any(p["pier"] == pier and p["area"] in pg["areas"] for p in A["ports"]) else next(p for p in A["ports"] if p["pier"] == pier)
            docks.append(p)
        pg["docks"] = docks
        pg["dock_notes"] = [A["en"][k] for k in pg.get("dock_keys", []) if k in A["en"]]
    tricks = []
    for k in A["tricks"]:
        t, b = A["en"].get(f"trick.{k}.title"), A["en"].get(f"trick.{k}.body")
        if t and b and not PRICE_RE.search(b): tricks.append((t, b))
    return pages, tricks

# --------------------------------------------------------------------------------------------- render
def store_cfg():
    p = os.path.join(SITE, "app-store.json")
    return json.load(open(p)) if os.path.exists(p) else {}

def cta(app, store, has_page):
    sid = str(store.get(app) or "").strip()
    icon = f'<img src="/{app.lower()}/icon.png" alt="{E(app)} icon" width="64" height="64">' if os.path.exists(os.path.join(SITE, app.lower(), "icon.png")) else ""
    more = f'<a href="/{app.lower()}/">About {E(app)}</a>' if has_page else f'<a href="/{app.lower()}/ports/">All {E(app)} port guides</a>'
    if sid:
        badge = f'<a class="store" href="https://apps.apple.com/app/id{E(sid)}">Get {E(app)} on the App Store</a>'
    else:
        badge = f'<span class="badge" data-app="{E(app)}">Coming soon to the App Store</span>'
    return f'''<section class="cta">
    {icon}
    <div>
      <h2>Get {E(app)} for iPhone</h2>
      <p>Every place, description and opening time is stored on the phone, so the guide works at sea and ashore with no signal. Only the map background needs one. $4.99 once, no subscription, no ads, no tracking.</p>
      <p>{badge} · {more}</p>
    </div>
  </section>'''

LIVE_JS = """<script>
fetch('/app-store.json').then(function(r){return r.json()}).then(function(j){
  document.querySelectorAll('[data-app]').forEach(function(e){var id=j[e.getAttribute('data-app')];
    if(id){var a=document.createElement('a');a.className='store';a.href='https://apps.apple.com/app/id'+id;
      a.textContent='Get '+e.getAttribute('data-app')+' on the App Store';e.replaceWith(a);}});
}).catch(function(){});
</script>"""

def head(title, desc, url, image, jsonld):
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(url)}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Things travel guides">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(url)}">
<meta property="og:image" content="{E(image)}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="/tulumthings/icon.png">
<link rel="stylesheet" href="/style.css">
<link rel="stylesheet" href="/ports.css">
<script type="application/ld+json">
{json.dumps(jsonld, ensure_ascii=False, indent=1)}
</script>
</head>'''

def render_port(cfg, A, pg, tricks, store, pages):
    app, low = A["app"], A["app"].lower()
    url = f"{BASE}/{low}/ports/{pg['slug']}/"
    has_page = os.path.exists(os.path.join(SITE, low, "index.html"))
    icon_url = f"{BASE}/{low}/icon.png" if os.path.exists(os.path.join(SITE, low, "icon.png")) else f"{BASE}/tulumthings/icon.png"
    h1 = pg.get("h1") or f"{pg['port']} cruise port guide"
    is_ferry = not pg["piers"]
    what = "the Cruz Bay ferry dock" if is_ferry else "the pier"
    pier_list = ", ".join(d["pier"] for d in pg["docks"])
    title = f"{h1} — {'ferry dock' if is_ferry else 'where ships dock'}, what's near the pier | {app}"
    if len(title) > 70: title = f"{h1} | {app}"
    n_trips = len(pg["trips"])
    n_near = pg["walkable"] + len(pg["extra"])
    pl = lambda n, w: f"{n} {w}" + ("" if n == 1 else "s")
    if is_ferry:
        desc = (f"A St. John day from a St. Thomas cruise ship: the Red Hook ferry, {len(pg['places'])} places with minutes from the Cruz Bay ferry dock"
                f"{', and ' + pl(n_trips, 'ready-made day') if n_trips else ''} from {app}, the offline iPhone guide.")
    else:
        near = f"{pl(n_near, 'place')} within walking distance of the pier, with minutes on foot" if n_near else "what's near the pier, with distances"
        desc = (f"{pg['port']} cruise port: ships dock at {pier_list}. {near}"
                f"{', plus ' + pl(n_trips, 'ready-made port day') if n_trips else ''}, from {app}, the offline iPhone guide.")
    if len(desc) > 300: desc = desc[:297].rsplit(" ", 1)[0] + "…"
    attractions = [{"@type": "TouristAttraction", "name": p["v"]["name"], "description": p["text"],
                    "geo": {"@type": "GeoCoordinates", "latitude": round(p["v"]["lat"], 5), "longitude": round(p["v"]["lon"], 5)}}
                   for p in pg["places"]]
    jsonld = {"@context": "https://schema.org", "@graph": [
        {"@type": "TouristDestination", "@id": url + "#destination", "name": f"{pg['port']}, {pg['place']}", "url": url,
         "description": desc,
         "geo": {"@type": "GeoCoordinates", "latitude": round(pg["anchor"][0], 5), "longitude": round(pg["anchor"][1], 5)},
         "includesAttraction": attractions},
        {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Things apps", "item": BASE + "/"},
            {"@type": "ListItem", "position": 2, "name": app, "item": f"{BASE}/{low}/" if has_page else f"{BASE}/{low}/ports/"},
            {"@type": "ListItem", "position": 3, "name": "Port guides", "item": f"{BASE}/{low}/ports/"},
            {"@type": "ListItem", "position": 4, "name": pg["port"], "item": url}]}]}
    out = [head(title, desc, url, icon_url, jsonld), "<body>\n<main class=\"port\">"]
    crumbs = ['<a href="/">Things apps</a>']
    if has_page: crumbs.append(f'<a href="/{low}/">{E(app)}</a>')
    crumbs.append(f'<a href="/{low}/ports/">Port guides</a>')
    out.append(f'  <nav class="backlink crumbs" aria-label="Breadcrumb">{" › ".join(crumbs)}</nav>')
    out.append(f"  <h1>{E(h1)}</h1>")
    out.append(f'  <p class="tagline">{E(pg["place"])} · from {E(app)}, the offline iPhone guide</p>')
    # where ships dock
    if is_ferry:
        out.append("  <h2>Getting there from the ship</h2>")
        for n in pg["dock_notes"]: out.append(f"  <p>{E(n)}</p>")
    else:
        out.append("  <h2>Where ships dock</h2>")
        for d in pg["docks"]:
            out.append(f'  <div class="dock"><h3>{E(d["pier"])}</h3><p>{E(d["note"])}</p><p class="hours">{E(d["hours"])}</p></div>')
        out.append('  <p class="small">All-aboard is in ship time. Check the daily programme and be back at the gangway 30 minutes early.</p>')
    # places
    out.append(f'  <h2>Top places near {E(what)}</h2>')
    out.append(f'  <p class="small">Walking times come from the app: straight-line distance plus 30% for streets, at an easy 4.5 km/h. Places further than an hour on foot show the distance instead.</p>')
    out.append('  <ol class="places">')
    for p in pg["places"]:
        v = p["v"]
        cat = A["cats"].get(v["cat"], "")
        img = ""
        if p["photo"]:
            ph = p["photo"]
            img = (f'<figure><img src="{E(ph["url"])}" alt="{E(v["name"])}" loading="lazy" decoding="async" width="88" height="88">'
                   f'<figcaption><a href="{E(ph["page"])}" rel="nofollow">{E(ph["credit"])}</a></figcaption></figure>')
        label = walk_label(p["m"], p["mins"], what)
        out.append(f'    <li>{img}<div><h3>{E(v["name"])}</h3><p class="meta"><span class="walk">{E(label)}</span>'
                   f'{" · " + E(cat) if cat else ""}</p><p>{E(p["text"])}</p></div></li>')
    out.append("  </ol>")
    if pg["extra"]:
        out.append(f'  <h3 class="more">More places within walking distance</h3>')
        out.append(f'  <p class="small">Also in {E(app)}, from its OpenStreetMap listings.</p>')
        out.append('  <ul class="extra">')
        for p in pg["extra"]:
            cat = A["cats"].get(p["v"]["cat"], "")
            out.append(f'    <li>{E(p["v"]["name"])} <span class="meta">· {E(cat) + " · " if cat else ""}<span class="walk">{p["mins"]} min walk</span></span></li>')
        out.append("  </ul>")
    # trips
    if pg["trips"]:
        more = f" ({pg['trip_total']} in all for this port)" if pg["trip_total"] > len(pg["trips"]) else ""
        out.append(f"  <h2>Ready-made port days in {E(app)}</h2>")
        out.append(f'  <p class="small">Each is a timed plan in the app, starting and ending at the ship{E(more)}.</p>')
        out.append('  <ul class="trips">')
        for t in pg["trips"]:
            out.append(f'    <li><b>{E(t["title"])}</b>{("<br>" + E(t["sub"])) if t["sub"] else ""}</li>')
        out.append("  </ul>")
    # getting around
    if tricks:
        out.append("  <h2>Getting around: what the app tells you</h2>")
        out.append('  <dl class="tricks">')
        for t, b in tricks: out.append(f"    <dt>{E(t)}</dt><dd>{E(b)}</dd>")
        out.append("  </dl>")
    out.append("  " + cta(app, store, has_page))
    others = [o for o in pages if o is not pg]
    if others:
        out.append(f"  <h2>Other {E(app)} ports</h2>")
        out.append('  <p class="others">' + " · ".join(f'<a href="/{low}/ports/{o["slug"]}/">{E(o["port"])}</a>' for o in others) + "</p>")
    out.append(f'  <footer>© 2026 Things apps · Places, walking times and day plans come from the data bundled in the {E(app)} app. '
               f'Photos: Wikimedia Commons, credited under each image. · <a href="/{low}/privacy.html">Privacy</a></footer>')
    out.append("</main>\n" + LIVE_JS + "\n</body>\n</html>\n")
    return "\n".join(out)

def render_hub(cfg, A, pages, store):
    app, low = A["app"], A["app"].lower()
    url = f"{BASE}/{low}/ports/"
    has_page = os.path.exists(os.path.join(SITE, low, "index.html"))
    icon_url = f"{BASE}/{low}/icon.png" if os.path.exists(os.path.join(SITE, low, "icon.png")) else f"{BASE}/tulumthings/icon.png"
    title = f"{cfg['region']} cruise port guides | {app}"
    names = ", ".join(p["port"] for p in pages)
    desc = f"Cruise port guides for {names}: where ships dock, what's within walking distance of the pier, and ready-made port days from {app}."
    if len(desc) > 300: desc = f"{len(pages)} {cfg['region']} cruise port guides: where ships dock, what's within walking distance of the pier, and ready-made port days from {app}."
    jsonld = {"@context": "https://schema.org", "@type": "ItemList", "name": title, "url": url,
              "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": p["port"], "url": f"{url}{p['slug']}/"} for i, p in enumerate(pages)]}
    out = [head(title, desc, url, icon_url, jsonld), "<body>\n<main class=\"port\">"]
    crumbs = ['<a href="/">Things apps</a>'] + ([f'<a href="/{low}/">{E(app)}</a>'] if has_page else [])
    out.append(f'  <nav class="backlink crumbs" aria-label="Breadcrumb">{" › ".join(crumbs)}</nav>')
    out.append(f"  <h1>{E(cfg['region'])} cruise port guides</h1>")
    out.append(f'  <p class="tagline">Where the ship docks and what\'s near the pier, from {E(app)}.</p>')
    out.append('  <ul class="hub">')
    for p in pages:
        piers = ", ".join(d["pier"] for d in p["docks"]) or "By ferry from St. Thomas"
        out.append(f'    <li><a href="/{low}/ports/{p["slug"]}/"><h3>{E(p.get("h1") or p["port"] + " cruise port guide")}</h3>'
                   f'<span>{E(piers)} · {len(p["places"]) + len(p["extra"])} places · {len(p["trips"])} port day{"" if len(p["trips"]) == 1 else "s"}</span></a></li>')
    out.append("  </ul>")
    out.append("  " + cta(app, store, has_page))
    out.append(f'  <footer>© 2026 Things apps · <a href="/{low}/privacy.html">Privacy</a></footer>')
    out.append("</main>\n" + LIVE_JS + "\n</body>\n</html>\n")
    return "\n".join(out)

def link_block(app, pages):
    low = app.lower()
    items = "".join(f'\n    <li><a href="/{low}/ports/{p["slug"]}/">{E(p.get("h1") or p["port"] + " cruise port guide")}</a></li>' for p in pages)
    return (f'<!-- ports:start (generated by tools/build_port_pages.py) -->\n  <h2>Cruise port guides</h2>\n'
            f'  <ul>{items}\n  </ul>\n  <p><a href="/{low}/ports/">All {E(app)} port guides</a></p>\n  <!-- ports:end -->')

def patch_app_page(app, pages):
    p = os.path.join(SITE, app.lower(), "index.html")
    if not os.path.exists(p): return False
    s = rd(p); blk = link_block(app, pages)
    if "<!-- ports:start" in s:
        s2 = re.sub(r"<!-- ports:start.*?<!-- ports:end -->", lambda m: blk, s, flags=re.S)
    else:
        anchor = '  <p><span class="badge">Coming soon to the App Store</span></p>'
        i = s.find(anchor)
        if i < 0: i = s.find("  <footer>")
        s2 = s[:i] + "  " + blk + "\n\n" + s[i:]
    if s2 != s: wr(p, s2)
    return True

def sitemap(urls):
    today = date.today().isoformat()
    body = "".join(f"  <url><loc>{E(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n'

def main():
    check = "--check" in sys.argv
    store = store_cfg()
    port_urls, count = [], 0
    for cfg in APPS:
        A = read_app(cfg["app"])
        pages, tricks = build_model(cfg, A)
        low = A["app"].lower()
        slugs = [p["slug"] for p in pages]
        assert len(set(slugs)) == len(slugs), f"duplicate slugs in {A['app']}: {slugs}"
        for pg in pages:
            wr(os.path.join(SITE, low, "ports", pg["slug"], "index.html"), render_port(cfg, A, pg, tricks, store, pages))
            port_urls.append(f"{BASE}/{low}/ports/{pg['slug']}/"); count += 1
            if check:
                print(f'  {A["app"]:18} {pg["slug"]:22} places={len(pg["places"]):2} walk={pg["walkable"]:2} trips={len(pg["trips"])}/{pg["trip_total"]} '
                      f'photos={sum(1 for p in pg["places"] if p["photo"])} osm={len(pg["extra"])}')
        wr(os.path.join(SITE, low, "ports", "index.html"), render_hub(cfg, A, pages, store))
        port_urls.append(f"{BASE}/{low}/ports/")
        patched = patch_app_page(A["app"], pages)
        print(f'{A["app"]}: {len(pages)} port pages, {len(tricks)} tricks{"" if patched else " (no app page to link from)"}')
    # sitemap: root + every app page + every port page/hub (privacy mirrors are excluded: canonical lives on incmpltellc.com)
    urls = [BASE + "/"]
    for d in sorted(os.listdir(SITE)):
        if os.path.exists(os.path.join(SITE, d, "index.html")) and not d.startswith("."): urls.append(f"{BASE}/{d}/")
    urls += sorted(port_urls)
    wr(os.path.join(SITE, "sitemap.xml"), sitemap(urls))
    wr(os.path.join(SITE, "robots.txt"), f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    print(f"{count} port pages, {len(urls)} URLs in sitemap.xml")

if __name__ == "__main__":
    main()
