"""Bygger den statiska sidan i dist/ från data/ och config/.

	python build/build.py             bygger dist/ (dagens urval)
	python build/build.py --date 2026-12-24   … med urvalet för ett visst datum

Dessutom dist/data/last.json: den senast uppladdade bilden, för sidan ulfbodin.se/flickr-last/.

Hero, årsbilder, temamosaiker och albumrader väljs med ett frö per dag – sidan byggs
varje natt (GitHub Actions) och får då ett nytt urval. Själva filtreringen sker i
webbläsaren mot data/photos.json (static/archive.js).

Förhandsvisning lokalt:

	python -m http.server -d dist 8000      → http://localhost:8000/
"""

import argparse
import collections
import colorsys
import io
import json
import random
import re
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
ALBUMS_SHOWN = 10	# album som syns direkt, resten bakom "Show more albums"
ALBUM_PICTURES = 20	# bilder per albumrad (bara de som får plats laddas)
YEAR_MIN = 3		# år med färre bilder hoppas över i tidslinjen
CDN = "https://live.staticflickr.com"

# Texterna som skriptet behöver ({count}, {what} … fylls i av tr() i archive.js).
SCRIPT_TEXTS = {
	"label_bm": "Showing", "label_year": "Year", "label_decade": "Decade", "label_theme": "Theme",
	"label_place": "Place", "label_album": "Album", "label_camera": "Camera", "label_lens": "Lens", "label_focal": "Focal length", "equiv": "equiv.",
	"label_license": "Licence", "label_q": "Search", "explored": "Explored", "v_explored": "Picked for Flickr's Explore",
	"bm_value": "bookmarks", "map": "Map", "map_fullscreen": "Full screen", "map_fullscreen_exit": "Exit full screen", "map_opacity": "Background map", "map_map": "Map", "map_satellite": "Satellite", "remove": "Remove {what}", "decade": "{decade}s",
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


LENS_MOUNTS = [("RF", "RF"), ("EF-M", "EF-M"), ("EF-S", "EF-S"), ("EF", "EF")]
MOUNT_ORDER = ["RF", "EF", "EF-S", "EF-M", "Sigma", "Other"]
MOUNT_TITLES = {"RF": "Canon RF", "EF": "Canon EF", "EF-S": "Canon EF-S", "EF-M": "Canon EF-M", "Sigma": "Sigma", "Other": "Other lenses"}


class Gear:
	"""Kameror, objektiv och brännvidd (config/gear.json) – EXIF-namnen översatta till visningsnamn."""

	def __init__(self, cfg, raw):
		self.cfg = cfg
		self.brands = [b.lower() for b in cfg.get("brands", ["Canon", "Sigma"])]
		self.cams = cfg.get("cameras", {})
		self.buckets = cfg.get("focal", [[0, 20], [21, 30], [31, 40], [41, 60], [61, 100], [101, 160], [161, 300], [301, 5000]])
		self.raw_cameras = raw.get("cameras", [])
		self.raw_lenses = raw.get("lenses", [])

	def shown(self, camera):
		if not camera:
			return False
		name = camera.lower()
		if any(name.startswith(x.lower()) for x in self.cfg.get("exclude_cameras", [])):
			return False
		return any(name.startswith(b) for b in self.brands)

	def camera_label(self, camera):
		label = self.cams.get(camera, {}).get("label")
		if label:
			return label
		return camera.replace("SIGMA ", "Sigma ") if camera else ""

	def crop(self, camera):
		if camera in self.cams and "crop" in self.cams[camera]:
			return float(self.cams[camera]["crop"])
		name = (camera or "").lower()
		if name.startswith("sigma dp"):
			return 1.7
		if re.search(r"eos m\d*$|eos \d{2,4}d$|eos [7-9]\d*d$|eos rebel|eos kiss", name) and not re.search(r"eos [156]d", name):
			return 1.6
		return 1.0

	def lens_of(self, p):
		"""Objektivet enligt EXIF – eller kamerans fasta objektiv."""
		camera = self.raw_cameras[p["camera"]] if p.get("camera") is not None else None
		if p.get("lens") is not None:
			return self.raw_lenses[p["lens"]]
		return self.cams.get(camera, {}).get("fixed_lens")

	@staticmethod
	def mount(lens):
		if lens.lower().startswith("sigma"):
			return "Sigma"
		for prefix, mount in LENS_MOUNTS:
			if lens.startswith(prefix):
				return mount
		return "Other"

	@staticmethod
	def lens_label(lens):
		"""'RF70-200mm F2.8 L IS USM' → 'RF 70–200mm F2.8 L IS USM'."""
		label = re.sub(r"^(RF|EF-M|EF-S|EF)(?=\d)", r"\1 ", lens)
		return re.sub(r"(?<=\d)-(?=\d)", "–", label)

	def eq(self, p):
		camera = self.raw_cameras[p["camera"]] if p.get("camera") is not None else None
		if not p.get("focal"):
			return None
		return round(p["focal"] * self.crop(camera))

	def bucket(self, eq):
		for lo, hi in self.buckets:
			if eq is not None and lo <= eq <= hi:
				return f"{lo}-{hi}"
		return None

	def bucket_label(self, lo, hi):
		if lo == 0:
			return f"≤ {hi} mm"
		if hi >= 1000:
			return f"{lo}+ mm"
		return f"{lo}–{hi} mm"


def span(years):
	years = sorted(y for y in years if y)
	if not years:
		return ""
	return f"{years[0]}–{years[-1]}" if years[0] != years[-1] else str(years[0])


def muted_colour(image_bytes):
	"""The photo's most prominent colour, darkened and muted into a background (flickr-last).

	The photo is reduced to eight colours; the most common one wins, but near-black and near-white
	give way to a real colour that covers at least a tenth of the photo. The background keeps the
	hue, gets at most 35 % saturation and 17 % lightness - dark enough for the photo to stand out
	and for light text. Returns None if Pillow is missing or the image cannot be read.
	"""
	try:
		from PIL import Image
	except ImportError:
		return None
	try:
		img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
	except Exception:
		return None
	img.thumbnail((120, 120))
	quant = img.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
	palette = quant.getpalette()
	counts = sorted(quant.getcolors(), reverse=True)
	total = sum(c for c, _ in counts)
	colours = []
	for count, index in counts:
		r, g, b = (v / 255 for v in palette[index * 3:index * 3 + 3])
		h, l, sat = colorsys.rgb_to_hls(r, g, b)
		colours.append((count / total, h, l, sat))
	share, h, l, sat = colours[0]
	if l < 0.12 or l > 0.9 or sat < 0.08:
		for c in colours[1:]:
			if c[0] >= 0.1 and 0.12 <= c[2] <= 0.9 and c[3] >= 0.08:
				share, h, l, sat = c
				break

	def hexc(h, l, s):
		return "#%02x%02x%02x" % tuple(round(v * 255) for v in colorsys.hls_to_rgb(h, l, s))

	return {
		"bg": hexc(h, 0.17, min(sat, 0.35)),
		"text": hexc(h, 0.96, min(sat, 0.25)),
		"muted": hexc(h, 0.68, min(sat, 0.22)),
	}


def fetch_colour(url):
	"""Downloads the small square (_q, 150 px) and returns muted_colour() - or None offline."""
	try:
		import requests
		resp = requests.get(url, timeout=20)
		resp.raise_for_status()
	except Exception as exc:
		print(f"OBS: kunde inte hämta bilden för färgen ({type(exc).__name__}) – standardfärgen används")
		return None
	return muted_colour(resp.content)


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

	# --- Explored (config/explored.html): the photos picked for Flickr's Explore, from Scout's posters
	try:
		explored_text = (CONFIG / "explored.html").read_text(encoding="utf-8")
	except FileNotFoundError:
		explored_text = ""
	explored_ids = set(re.findall(r"photos/(?:[^/\s\"]+)/(\d+)", explored_text))
	explored_items = [p for p in items if p["id"] in explored_ids]
	missing_explored = len(explored_ids) - len(explored_items)
	if missing_explored:
		print(f"OBS: {missing_explored} Explore-bilder i config/explored.html finns inte bland de publika")
	explored = None
	if explored_items:
		ex_years = collections.Counter(p["year"] for p in explored_items if p["year"])
		explored = {
			"count": len(explored_items),
			"years": [{"year": y, "count": n} for y, n in sorted(ex_years.items(), reverse=True)],
			"span": span(p["year"] for p in explored_items),
			"pictures": [photos.card(p, "n") for p in sorted(top(explored_items, ALBUM_PICTURES), key=lambda p: p["taken"] or "", reverse=True)],
		}

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
		pictures = sorted(top(members, ALBUM_PICTURES), key=lambda p: p["taken"] or "")
		album_rows.append({
			"id": a["id"], "title": a["title"], "type": a["type"], "count": len(members), "years": span(ys),
			"pictures": [photos.card(p, "n") for p in pictures],
		})
	places = [a for a in album_rows if a["type"] == "place"]
	why = [a for a in album_rows if a["type"] != "place"]

	# --- utrustning (config/gear.json): Canon och Sigma – kameror, brännvidd, objektiv
	gear = Gear(read(CONFIG / "gear.json", {}), raw)
	for p in items:
		p["camera_name"] = raw["cameras"][p["camera"]] if p.get("camera") is not None else None
		p["lens_name"] = gear.lens_of(p)
		p["eq"] = gear.eq(p)
	shown = [p for p in items if gear.shown(p["camera_name"])]
	exif_total = sum(1 for p in items if p["camera_name"])

	by_camera = collections.defaultdict(list)
	for p in shown:
		by_camera[p["camera_name"]].append(p)
	cameras = []
	for name, members in by_camera.items():
		pic = of_the_day(top([p for p in members if p["title"]] or members, 12), day, f"camera-{name}")[0]
		cameras.append({
			"name": name, "label": gear.camera_label(name), "count": len(members),
			"years": span(p["year"] for p in members), "first": min((p["taken"] or "9999") for p in members),
			"picture": photos.card(pic, "n"),
		})
	cameras.sort(key=lambda c: c["first"])
	camera_peak = max((c["count"] for c in cameras), default=1)

	focal = []
	for lo, hi in gear.buckets:
		key = f"{lo}-{hi}"
		members = [p for p in shown if gear.bucket(p["eq"]) == key]
		if not members:
			continue
		pic = of_the_day(top(members, 12), day, f"focal-{key}")[0]
		focal.append({"key": key, "label": gear.bucket_label(lo, hi), "count": len(members), "picture": photos.card(pic, "n")})
	focal_peak = max((f["count"] for f in focal), default=1)

	# Panoramas: the same buckets, only the panoramas (the theme in gear.json) - stitched from
	# frames taken at the bucket's focal length, so the span is much wider than the lens's.
	pano_id = gear.cfg.get("panorama_theme", "panorama")
	pano_index = next((n for n, t in enumerate(raw.get("themes", [])) if t["id"] == pano_id), None)
	panoramas, pano_total = [], 0
	if pano_index is not None:
		panos = [p for p in shown if pano_index in p["themes"]]
		pano_total = len(panos)
		for lo, hi in gear.buckets:
			key = f"{lo}-{hi}"
			members = [p for p in panos if gear.bucket(p["eq"]) == key]
			if not members:
				continue
			pic = of_the_day(top(members, 12), day, f"pano-{key}")[0]
			card = photos.card(pic, "n")
			card["ratio"] = min(card["ratio"], 3)	# a 6:1 panorama would fill the strip
			panoramas.append({"key": key, "label": gear.bucket_label(lo, hi), "count": len(members), "picture": card})
	pano_peak = max((f["count"] for f in panoramas), default=1)

	by_lens = collections.defaultdict(list)
	for p in shown:
		if p["lens_name"]:
			by_lens[p["lens_name"]].append(p)
	mounts = collections.defaultdict(list)
	for name, members in by_lens.items():
		pictures = sorted(top(members, ALBUM_PICTURES), key=lambda p: p["taken"] or "")
		mounts[gear.mount(name)].append({
			"name": name, "label": gear.lens_label(name), "count": len(members),
			"years": span(p["year"] for p in members), "pictures": [photos.card(p, "n") for p in pictures],
		})
	lens_groups = [
		{"mount": m, "title": MOUNT_TITLES[m], "lenses": sorted(mounts[m], key=lambda l: -l["count"])}
		for m in MOUNT_ORDER if mounts.get(m) and m not in gear.cfg.get("hide_mounts", [])
	]
	lenses = [l for g in lens_groups for l in g["lenses"]]
	gear_total = len(shown)
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
		"explored": sorted(p["id"] for p in explored_items),
		"gear": {
			"crop": {c: gear.crop(c) for c in raw.get("cameras", [])},
			"cameras": {c: gear.camera_label(c) for c in raw.get("cameras", [])},
			"lenses": {l: gear.lens_label(l) for l in list(raw.get("lenses", [])) + [v["fixed_lens"] for v in gear.cams.values() if v.get("fixed_lens")]},
			"fixed": {c: v["fixed_lens"] for c, v in gear.cams.items() if v.get("fixed_lens")},
			"focal": [[lo, hi, gear.bucket_label(lo, hi)] for lo, hi in gear.buckets],
		},
	}

	env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
	env.filters["num"] = num
	html = env.get_template("index.html").render(
		site=site, coll=coll, hero=hero, years=years, when=when, themes=themes, themes_shown=THEMES_SHOWN, albums_shown=ALBUMS_SHOWN,
		albums=album_rows, places=places, why=why, cameras=cameras, camera_peak=camera_peak, focal=focal, focal_peak=focal_peak,
		lens_groups=lens_groups, lenses=lenses, panoramas=panoramas, pano_peak=pano_peak, explored=explored,
		pano_total=pano_total, pano_theme=pano_id, exif_total=exif_total, gear_total=gear_total,
		licenses=licenses, fx=fx, version=datetime.now().strftime("%Y%m%d%H%M"),
	)

	# --- flickr-last: the latest uploaded photo as a tiny data/last.json, read by the stand-alone
	# page ulfbodin.se/flickr-last/ (bodwigg.github.io/flickr-last/index.html).
	latest = sorted(items, key=lambda p: (-p["uploaded"], p["id"]))[0]
	last = {
		"id": latest["id"],
		"title": latest["title"],
		"taken": latest["taken"],
		"uploaded": latest["uploaded"],
		"ratio": latest["ratio"],
		"src": photos.url(latest, "k"),
		"medium": photos.url(latest, "b"),
		"small": photos.url(latest, "n"),	# 320 px – the photo on ulfbodin.se/photography.html
		"url": f"https://www.flickr.com/photos/{site.get('flickr_user', 'ulfbodin')}/{latest['id']}/",
		"colour": fetch_colour(photos.url(latest, "q")),
	}

	if DIST.exists():
		shutil.rmtree(DIST)
	shutil.copytree(ROOT / "static", DIST / "static", copy_function=shutil.copyfile)
	(DIST / "data").mkdir(parents=True)
	shutil.copyfile(DATA / "photos.json", DIST / "data" / "photos.json")
	if (DATA / "details").exists():
		shutil.copytree(DATA / "details", DIST / "data" / "details", copy_function=shutil.copyfile)
	(DIST / "index.html").write_text(html, encoding="utf-8", newline="\n")
	(DIST / "data" / "last.json").write_text(json.dumps(last, ensure_ascii=False), encoding="utf-8")
	# … och en kopia i data/ (inte i git) för förhandsvisning av flickr-last lokalt, se README.
	(DATA / "last.json").write_text(json.dumps(last, ensure_ascii=False), encoding="utf-8")
	(DIST / ".nojekyll").write_text("", encoding="utf-8")
	print(f"dist/ byggd för {day}: {len(items)} foton, {len(hero)} hero, {len(years)} år, "
		f"{len(themes)} teman, {len(album_rows)} album, {len(cameras)} kameror, {len(lenses)} objektiv, "
		f"index.html {len(html) // 1024} kB; data/last.json = {latest['id']}")


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--date", help="urvalet för ett visst datum (ÅÅÅÅ-MM-DD)")
	args = parser.parse_args()
	build(date.fromisoformat(args.date) if args.date else date.today())


if __name__ == "__main__":
	main()
