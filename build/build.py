"""Bygger den statiska sidan i dist/ från data/ och config/.

	python build/build.py             bygger dist/ (dagens urval)
	python build/build.py --date 2026-12-24   … med urvalet för ett visst datum

Hero, årsbilder, temamosaiker och albumrader väljs med ett frö per dag – sidan byggs
varje natt (GitHub Actions) och får då ett nytt urval. Själva filtreringen sker i
webbläsaren mot data/photos.json (static/archive.js).

Förhandsvisning lokalt:

	python -m http.server -d dist 8000      → http://localhost:8000/
"""

import argparse
import collections
import json
import random
import shutil
from datetime import date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config"
DIST = ROOT / "dist"

HERO_PICKED = 6		# handplockade per dag
HERO_RANDOM = 6		# därefter slumpbilder
THEMES_SHOWN = 12	# teman som syns direkt, resten bakom "Show more themes"
ALBUM_PICTURES = 20	# bilder per albumrad (bara de som får plats laddas)
YEAR_MIN = 3		# år med färre bilder hoppas över i tidslinjen
CDN = "https://live.staticflickr.com"

# Texterna som skriptet behöver ({count}, {what} … fylls i av tr() i archive.js).
SCRIPT_TEXTS = {
	"label_bm": "Showing", "label_year": "Year", "label_decade": "Decade", "label_theme": "Theme",
	"label_place": "Place", "label_album": "Album", "label_camera": "Camera", "label_lens": "Lens",
	"label_license": "Licence", "label_q": "Search",
	"bm_value": "bookmarks", "map": "Map", "remove": "Remove {what}", "decade": "{decade}s",
	"count_one": "{count} photo", "count_many": "{count} photos",
	"bm_remove": "Remove the bookmark", "bm_add": "Bookmark the photo", "bookmark": "Bookmark", "bookmarked": "Bookmarked",
	"loading": "Loading photos …", "none_bm": "No bookmarked photos yet – click the star on a photo.",
	"none": "No photos with these choices.", "failed": "Could not load the photos right now.",
	"collapse": "Collapse", "show_choices": "Show choices", "map_empty": "No photos with a map position for these choices.",
	"untitled": "Untitled", "v_themes": "Themes", "v_albums": "Albums", "v_tags": "Tags", "v_place": "Place",
	"v_camera": "Camera", "v_settings": "Settings", "v_license": "Licence", "v_stats": "On Flickr",
	"v_views": "{count} views", "v_faves": "{count} faves", "v_comments": "{count} comments", "v_comment": "1 comment",
	"v_view": "1 view", "v_fave": "1 fave",
	"v_flickr": "View the photo on Flickr ↗", "v_osm": "Open the place in OpenStreetMap ↗", "v_onmap": "Show nearby photos",
	"v_zoom": "Click to zoom", "v_rights": "All rights reserved – please ask before using the photo.",
	"v_failed": "Could not load the information.", "circa": "c. {year}",
}


def read(path, default=None):
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError:
		if default is None:
			raise SystemExit(f"Saknas: {path.relative_to(ROOT)} – kör export/flickr_export.py först.")
		return default


def of_the_day(items, day, salt):
	"""Samma slumpordning hela dagen – sidan ändras från dag till dag."""
	items = list(items)
	random.Random(f"{day.isoformat()}-{salt}").shuffle(items)
	return items


def num(n):
	return f"{n:,}"


class Photos:
	"""photos.json avkodad till ordböcker."""

	def __init__(self, raw):
		self.raw = raw
		f = {k: i for i, k in enumerate(raw["fields"])}
		self.items = []
		for r in raw["photos"]:
			taken = r[f["taken"]]
			p = {k: r[i] for k, i in f.items()}
			p["year"] = int(taken[:4]) if taken else None
			p["ratio"] = round(p["w"] / p["h"], 3) if p["w"] and p["h"] else 1.5
			self.items.append(p)
		self.by_id = {p["id"]: p for p in self.items}

	@staticmethod
	def url(p, size):
		if size == "k":
			if p["big"].startswith("k:"):
				return f"{CDN}/{p['server']}/{p['id']}_{p['big'][2:]}_k.jpg"
			size = "c" if p["big"] == "c" else "b"
		return f"{CDN}/{p['server']}/{p['id']}_{p['secret']}_{size}.jpg"

	def card(self, p, size="z"):
		return {
			"id": p["id"], "title": p["title"], "year": p["year"], "ratio": p["ratio"],
			"src": self.url(p, size), "small": self.url(p, "n"), "big": self.url(p, "k"),
		}


def top(items, n):
	return sorted(items, key=lambda p: (-p["faves"], -p["views"], p["id"]))[:n]


def build(day):
	raw = read(DATA / "photos.json")
	photos = Photos(raw)
	albums = read(DATA / "albums.json")["albums"]
	site = read(CONFIG / "site.json")
	hero_cfg = read(CONFIG / "hero.json", {"groups": [], "fill": {"pool": 300}})
	items = photos.items

	# --- hero: handplockade (i dagens ordning) och sedan slump bland de mest favoritmarkerade
	picked_ids = [i for g in hero_cfg.get("groups", []) for i in g.get("photos", []) if i in photos.by_id]
	missing = [i for g in hero_cfg.get("groups", []) for i in g.get("photos", []) if i not in photos.by_id]
	if missing:
		print(f"OBS: hero-bilder som inte är publika/finns: {', '.join(missing)}")
	picked = of_the_day(picked_ids, day, "hero")[:HERO_PICKED]
	pool = [p["id"] for p in top(items, hero_cfg.get("fill", {}).get("pool", 300)) if p["id"] not in picked]
	hero = [photos.card(photos.by_id[i], "k") for i in picked + of_the_day(pool, day, "hero-fill")[:HERO_RANDOM]]

	# --- år
	year_count = collections.Counter(p["year"] for p in items if p["year"])
	strip = sorted(y for y, n in year_count.items() if n >= YEAR_MIN)
	peak = max((year_count[y] for y in strip), default=1)
	years = []
	for y in strip:
		candidates = top([p for p in items if p["year"] == y and p["title"]], 12)
		pic = of_the_day(candidates, day, f"year-{y}")[0]
		years.append({"year": y, "count": year_count[y], "picture": photos.card(pic, "n")})
	decades = collections.defaultdict(list)
	for y in sorted(year_count):
		decades[y // 10 * 10].append({"year": y, "count": year_count[y]})
	when = [{"decade": d, "count": sum(x["count"] for x in ys), "years": ys} for d, ys in sorted(decades.items())]

	# --- teman
	themes = []
	for n, t in enumerate(raw.get("themes", [])):
		members = [p for p in items if n in p["themes"]]
		if not members:
			continue
		mosaic = of_the_day(top(members, 24), day, f"theme-{t['id']}")[:4]
		themes.append({"id": t["id"], "label": t["label"], "count": len(members), "pictures": [photos.card(p, "n") for p in mosaic]})

	# --- album
	album_rows = []
	for a in albums:
		members = [photos.by_id[i] for i in a["photos"] if i in photos.by_id]
		if not members:
			continue
		ys = sorted(p["year"] for p in members if p["year"])
		span = (f"{ys[0]}–{ys[-1]}" if ys[0] != ys[-1] else str(ys[0])) if ys else ""
		pictures = sorted(top(members, ALBUM_PICTURES), key=lambda p: p["taken"] or "")
		album_rows.append({
			"id": a["id"], "title": a["title"], "type": a["type"], "count": len(members), "years": span,
			"pictures": [photos.card(p, "n") for p in pictures],
		})
	places = [a for a in album_rows if a["type"] == "place"]
	why = [a for a in album_rows if a["type"] != "place"]

	# --- utrustning (EXIF) och licenser
	cam_count = collections.Counter(p["camera"] for p in items if p["camera"] is not None)
	lens_count = collections.Counter(p["lens"] for p in items if p["lens"] is not None)
	cameras = [{"name": raw["cameras"][i], "count": n} for i, n in cam_count.most_common()]
	lenses = [{"name": raw["lenses"][i], "count": n} for i, n in lens_count.most_common()]
	exif_total = sum(1 for p in items if p["camera"] is not None)
	lic_count = collections.Counter(p["license"] for p in items)
	licenses = [
		{"id": str(i), "name": raw["licenses"][str(i)][0], "url": raw["licenses"][str(i)][1], "count": n, "rights": i == 0}
		for i, n in lic_count.most_common()
	]
	geo_count = sum(1 for p in items if p["lat"] is not None)

	coll = {
		"total": len(items),
		"first_year": strip[0] if strip else None,
		"last_year": strip[-1] if strip else None,
		"peak": peak,
		"geo": geo_count,
		"albums": len(album_rows),
		"themes": len(themes),
		"updated": raw.get("generated", "")[:10],
	}
	fx = {
		"user": site.get("flickr_user", ""),
		"t": SCRIPT_TEXTS,
		"albums": {a["id"]: {"title": a["title"], "type": a["type"]} for a in album_rows},
		"themes": {t["id"]: t["label"] for t in themes},
		"licenses": {l["id"]: [l["name"], l["url"]] for l in licenses},
		"day": day.isoformat(),
	}

	env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
	env.filters["num"] = num
	html = env.get_template("index.html").render(
		site=site, coll=coll, hero=hero, years=years, when=when, themes=themes, themes_shown=THEMES_SHOWN,
		albums=album_rows, places=places, why=why, cameras=cameras, lenses=lenses, exif_total=exif_total,
		licenses=licenses, fx=fx, version=datetime.now().strftime("%Y%m%d%H%M"),
	)

	if DIST.exists():
		shutil.rmtree(DIST)
	shutil.copytree(ROOT / "static", DIST / "static", copy_function=shutil.copyfile)
	(DIST / "data").mkdir(parents=True)
	shutil.copyfile(DATA / "photos.json", DIST / "data" / "photos.json")
	if (DATA / "details").exists():
		shutil.copytree(DATA / "details", DIST / "data" / "details", copy_function=shutil.copyfile)
	(DIST / "index.html").write_text(html, encoding="utf-8", newline="\n")
	(DIST / ".nojekyll").write_text("", encoding="utf-8")
	print(f"dist/ byggd för {day}: {len(items)} foton, {len(hero)} hero, {len(years)} år, "
		f"{len(themes)} teman, {len(album_rows)} album, index.html {len(html) // 1024} kB")


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--date", help="urvalet för ett visst datum (ÅÅÅÅ-MM-DD)")
	args = parser.parse_args()
	build(date.fromisoformat(args.date) if args.date else date.today())


if __name__ == "__main__":
	main()
