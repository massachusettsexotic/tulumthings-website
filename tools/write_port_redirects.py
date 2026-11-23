#!/usr/bin/env python3
"""tulumthings.com side of the port-page move (23 Nov 2026): the 53 cruise-port pages and 12 hubs now live on
portthings.com/guide/<id>/ports/. This writes, inside this repo only:

    <app>/ports/**/index.html   redirect stubs (canonical + meta refresh + JS), kept forever so old links work
    <app>/index.html            a "Now part of Port Things" box + canonical to the Port Things guide page,
                                and the old "Cruise port guides" block now pointing at portthings.com
    sitemap.xml, robots.txt     moved URLs dropped (only the root and the app pages stay)

The old-path -> new-URL map is written by the portthings.com generator:
    ~/portthings-website/tools/port-moves.json   (run python3 tools/build_site.py there first)

    python3 tools/write_port_redirects.py
"""
import html, json, os, re
from datetime import date

HOME = os.path.expanduser("~")
SITE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://tulumthings.com"
PT = "https://portthings.com"
MOVES = os.path.join(HOME, "portthings-website", "tools", "port-moves.json")
CATALOG = os.path.join(HOME, "ThingsHub", "ThingsHub", "Catalog", "catalog.json")
E = lambda s: html.escape(str(s), quote=True)


def wr(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f: f.write(s)


def stub(new, what):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(what)} has moved to Port Things</title>
<link rel="canonical" href="{E(new)}">
<meta http-equiv="refresh" content="0; url={E(new)}">
<script>location.replace({json.dumps(new)});</script>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<main>
  <p>This page has moved to <a href="{E(new)}">{E(new)}</a>.</p>
</main>
</body>
</html>
"""


def main():
    moves = json.load(open(MOVES))
    guides = {g["app"].lower(): g for g in json.load(open(CATALOG))["guides"]}
    n = 0
    for old, new in sorted(moves.items()):
        wr(os.path.join(SITE, old, "index.html"), stub(new, "This cruise port guide")); n += 1
    # any old port page the map doesn't know about would be a dead end: fail loudly instead
    for root, _, files in os.walk(SITE):
        rel = os.path.relpath(root, SITE).replace(os.sep, "/") + "/"
        if "/ports/" in "/" + rel and "index.html" in files and rel not in moves:
            raise SystemExit(f"no new URL for {rel} -- rerun the portthings generator")
    # app pages: point at Port Things
    patched = 0
    for d in sorted(os.listdir(SITE)):
        p = os.path.join(SITE, d, "index.html")
        g = guides.get(d)
        if not g or not os.path.exists(p): continue
        guide_url = f"{PT}/guide/{g['id']}/"
        s = open(p, encoding="utf-8").read()
        box = (f'<!-- portthings:start (tools/write_port_redirects.py) -->\n'
               f'  <div class="moved"><p><b>Now part of Port Things.</b> The {E(g["name"])} guide lives on inside '
               f'<a href="{PT}/">Port Things</a>, one offline app for cruise ports and trips.</p>\n'
               f'  <p><a href="{guide_url}">See the {E(g["name"])} guide on portthings.com</a></p></div>\n'
               f'  <!-- portthings:end -->')
        s = re.sub(r"\s*<!-- portthings:start.*?<!-- portthings:end -->", "", s, flags=re.S)
        s = re.sub(r'(<p class="tagline">.*?</p>)', lambda m: m.group(1) + "\n\n  " + box, s, count=1, flags=re.S)
        s = s.replace('<p><span class="badge">Coming soon to the App Store</span></p>',
                      f'<p><a class="store" href="{guide_url}">Get it in Port Things</a></p>')
        if '<link rel="canonical"' not in s:
            s = s.replace('<link rel="stylesheet" href="/style.css">', f'<link rel="canonical" href="{guide_url}">\n<link rel="stylesheet" href="/style.css">', 1)
        hub = moves.get(f"{d}/ports/")
        if hub:
            blk = (f'<!-- ports:start (now on portthings.com; tools/write_port_redirects.py) -->\n'
                   f'  <h2>Cruise port guides</h2>\n  <p>The port pages moved to Port Things: '
                   f'<a href="{hub}">{E(g["name"])} port pages on portthings.com</a></p>\n  <!-- ports:end -->')
            s = re.sub(r"<!-- ports:start.*?<!-- ports:end -->", lambda m: blk, s, flags=re.S)
        open(p, "w", encoding="utf-8").write(s); patched += 1
    # sitemap without the moved URLs
    today = date.today().isoformat()
    urls = [BASE + "/"] + [f"{BASE}/{d}/" for d in sorted(os.listdir(SITE))
                           if os.path.exists(os.path.join(SITE, d, "index.html")) and not d.startswith(".")]
    body = "".join(f"  <url><loc>{E(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
    wr(os.path.join(SITE, "sitemap.xml"), f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{body}</urlset>\n')
    wr(os.path.join(SITE, "robots.txt"), f"User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n")
    print(f"{n} redirect stubs, {patched} app pages pointed at Port Things, sitemap {len(urls)} URLs")


if __name__ == "__main__":
    main()
