"""Export av Ulf Bodins publika Flickr-foton för flickr-archive.

	python export/flickr_export.py              foton + album (första gången ~5 min, sedan ~1 min)
	python export/flickr_export.py --exif 500   … och EXIF för upp till 500 bilder som saknas i cachen
	python export/flickr_export.py --exif all   … och EXIF för alla som saknas (~2 h första gången)
	python export/flickr_export.py --probe      sondera API:t

Skriver:
	data/photos.json        alla publika foton, kompakt radformat (se "fields")
	data/albums.json        publika album med foto-id:n i albumets ordning
	data/details/NN.json    beskrivning och EXIF-detaljer, uppdelat på id:ts två sista siffror
	data/cache/albums.json  albumens innehåll – hämtas om bara när albumet ändrats
	data/cache/exif.json    EXIF per foto – hämtas bara en gång per foto
	config/albums.json      vitlista över album som visas ("show") + katalog över övriga ("available")
	config/tags.json        teman (vitlista), uteslutna taggar och katalog över övriga taggar

EXIF-hämtningen kan avbrytas med Ctrl+C – det som hunnit hämtas sparas.
"""

import argparse
import collections
import gzip
import json
import re
import sys
import time
from datetime import datetime, timezone

from flickr_api import NSID, ROOT, FlickrError, call, load_env

DATA = ROOT / "data"
CONFIG = ROOT / "config"
SEARCH_CAP = 3000	# flickr.photos.search ger högst ~4 000 träffar per fråga – dela intervallet före dess

EXTRAS = ",".join([
	"description", "license", "date_upload", "date_taken", "last_update", "geo", "tags",
	"o_dims", "views", "count_faves", "count_comments", "url_c", "url_l", "url_k",
])

FIELDS = [
	"id", "server", "secret", "title", "taken", "granularity", "uploaded",
	"lat", "lon", "license", "views", "faves", "comments",
	"tags", "albums", "w", "h", "big", "camera", "lens", "themes",
]

ALBUM_HELP = (
	"Vitlista: bara album i 'show' visas på sidan, i den ordningen. Flytta in album från "
	"'available' genom att lägga till {\"id\": …, \"type\": …}. type: 'place' (plats) eller 'theme' (tema). "
	"Titeln uppdateras automatiskt från Flickr. Virtuellt album som slår ihop flera: "
	"{\"id\": \"eget-id\", \"title\": …, \"type\": …, \"match\": \"reguljärt uttryck för titlarna\"} "
	"eller \"merge\": [id, …]. Sammanslagna album försvinner ur 'available'."
)
TAG_HELP = (
	"Teman: vitlista i visningsordning. Varje tema har en engelsk rubrik ('label') och de taggar som räknas dit "
	"('tags', t.ex. både svenska och engelska). 'exclude' = reguljära uttryck för taggar som tas bort helt "
	"(utrustning finns i EXIF). 'available' = vanligaste taggarna som inte ingår i något tema – skrivs om varje körning."
)
DEFAULT_EXCLUDE = [
	r"^(canon|sigma|samsung|olympus|panasonic|nikon|sony|fuji|iphone|eos|foveon|dp\d|lightroom|photoshop)",
	r"(usm|stm)$",
	r"\d+mm",
	r"^(f\d+|mm|usm|ef|efm|rf)$",
]

LENS_TAGS = ["LensModel", "Lens", "LensID", "LensType", "LensInfo"]


def log(text=""):
	print(text, flush=True)


# ---------------------------------------------------------------- filer

def read_json(path, default):
	try:
		return json.loads(path.read_text(encoding="utf-8"))
	except FileNotFoundError:
		return default


def write_json(path, data, pretty=False):
	"""Skriver atomärt. Kompakt för data, tabbindraget med CRLF för filer som redigeras för hand."""
	path.parent.mkdir(parents=True, exist_ok=True)
	if pretty:
		text = json.dumps(data, ensure_ascii=False, indent="\t") + "\n"
	else:
		text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
	tmp = path.with_suffix(path.suffix + ".tmp")
	tmp.write_text(text, encoding="utf-8", newline="\r\n")
	tmp.replace(path)
	return len(text.encode("utf-8"))


# ---------------------------------------------------------------- foton

def slim(p):
	"""Behåller det som behövs ur ett sökresultat."""
	def num(key, cast=int):
		value = p.get(key)
		return cast(value) if value not in (None, "") else 0

	big = ""
	if p.get("url_k"):
		# _k har en egen secret: …/{server}/{id}_{secret}_k.jpg
		big = "k:" + p["url_k"].rsplit("/", 1)[1].split("_")[1]
	elif p.get("url_l"):
		big = "b"
	elif p.get("url_c"):
		big = "c"
	w = num("o_width") or num("width_k") or num("width_l") or num("width_c")
	h = num("o_height") or num("height_k") or num("height_l") or num("height_c")
	lat, lon = num("latitude", float), num("longitude", float)
	return {
		"id": p["id"],
		"server": p["server"],
		"secret": p["secret"],
		"title": (p.get("title") or "").strip(),
		"taken": None if str(p.get("datetakenunknown", "0")) == "1" else p.get("datetaken"),
		"granularity": num("datetakengranularity"),
		"uploaded": num("dateupload"),
		"updated": num("lastupdate"),
		"lat": round(lat, 5) if lat or lon else None,
		"lon": round(lon, 5) if lat or lon else None,
		"license": num("license"),
		"views": num("views"),
		"faves": num("count_faves"),
		"comments": num("count_comments"),
		# Flickrs normaliserade taggar; maskintaggar (ns:pred=värde) utesluts
		"tags": [t for t in (p.get("tags") or "").split() if ":" not in t and "=" not in t],
		"description": ((p.get("description") or {}).get("_content") or "").strip(),
		"w": w,
		"h": h,
		"big": big,
	}


def search_page(lo, hi, page):
	return call(
		"flickr.photos.search", user_id=NSID, media="photos", min_upload_date=lo, max_upload_date=hi,
		sort="date-posted-asc", per_page=500, page=page, extras=EXTRAS,
	)["photos"]


def fetch_range(lo, hi, photos):
	"""Hämtar alla sidor för ett uppladdningsintervall; delar intervallet om det har för många träffar."""
	first = search_page(lo, hi, 1)
	total = int(first["total"])
	if total > SEARCH_CAP and hi - lo > 3600:
		mid = (lo + hi) // 2
		fetch_range(lo, mid, photos)
		fetch_range(mid + 1, hi, photos)
		return
	got = 0
	for page in range(1, int(first["pages"]) + 1):
		result = first if page == 1 else search_page(lo, hi, page)
		for p in result["photo"]:
			photos[p["id"]] = slim(p)
			got += 1
	label = datetime.fromtimestamp(lo, timezone.utc).strftime("%Y-%m-%d")
	log(f"  {label}  {got:>5} foton" + ("" if got == total else f"  (Flickr angav {total})"))


def fetch_photos():
	info = call("flickr.people.getInfo", user_id=NSID)["person"]
	first = int(info["photos"]["firstdate"]["_content"])
	expected = int(call("flickr.photos.search", user_id=NSID, media="photos", per_page=1)["photos"]["total"])
	log(f"Foton: Flickr anger {expected} publika foton. Hämtar per uppladdningsår …")
	photos = {}
	for year in range(datetime.fromtimestamp(first, timezone.utc).year, datetime.now(timezone.utc).year + 1):
		lo = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp())
		hi = int(datetime(year + 1, 1, 1, tzinfo=timezone.utc).timestamp()) - 1
		fetch_range(lo, hi, photos)
	if len(photos) != expected:
		log(f"  OBS: hämtade {len(photos)} men Flickr angav {expected}.")
	return photos


def fetch_licenses():
	return {
		int(l["id"]): [l["name"], l.get("url") or ""]
		for l in call("flickr.photos.licenses.getInfo")["licenses"]["license"]
	}


# ---------------------------------------------------------------- album

def fetch_album_photos(sid):
	ids, page = [], 1
	while True:
		result = call(
			"flickr.photosets.getPhotos", photoset_id=sid, user_id=NSID, privacy_filter=1,
			media="photos", per_page=500, page=page,
		)["photoset"]
		ids += [p["id"] for p in result["photo"]]
		if page >= int(result.get("pages", 1)):
			return ids
		page += 1


def fetch_albums(cache):
	sets, page = [], 1
	while True:
		result = call("flickr.photosets.getList", user_id=NSID, per_page=500, page=page)["photosets"]
		sets += result["photoset"]
		if page >= int(result.get("pages", 1)):
			break
		page += 1
	log(f"Album: {len(sets)} publika. Hämtar innehållet i nya och ändrade album …")
	albums, fetched = {}, 0
	for s in sets:
		sid = s["id"]
		stamp = f"{s.get('date_update')}:{s.get('photos')}"
		old = cache.get(sid)
		if old and old.get("stamp") == stamp:
			ids = old["photos"]
		else:
			ids = fetch_album_photos(sid)
			fetched += 1
		albums[sid] = {
			"stamp": stamp,
			"title": (s.get("title", {}).get("_content") or "").strip(),
			"description": (s.get("description", {}).get("_content") or "").strip(),
			"primary": s.get("primary"),
			"created": int(s.get("date_create") or 0),
			"updated": int(s.get("date_update") or 0),
			"photos": ids,
		}
	log(f"  {fetched} album hämtade, {len(sets) - fetched} oförändrade från cachen")
	return albums	# dict i Flickrs albumordning


def virtual_album(entry, albums, photos):
	"""Slår ihop flera Flickr-album till ett. "match" = reguljärt uttryck för titlarna, "merge" = lista med id:n."""
	pattern = re.compile(entry["match"]) if entry.get("match") else None
	merge = set(entry.get("merge", []))
	members = [
		sid for sid, a in albums.items()
		if sid in merge or (pattern and pattern.fullmatch(a["title"]))
	]
	if not members:
		return None, []
	ids = list(dict.fromkeys(i for sid in members for i in albums[sid]["photos"]))
	ids.sort(key=lambda i: (photos[i]["taken"] or "9999") if i in photos else "9999")
	largest = max(members, key=lambda sid: len(albums[sid]["photos"]))
	return {
		"title": entry.get("title") or entry["id"],
		"description": entry.get("description", ""),
		"primary": entry.get("primary") or albums[largest]["primary"],
		"created": min(albums[sid]["created"] for sid in members),
		"updated": max(albums[sid]["updated"] for sid in members),
		"photos": ids,
	}, members


def update_album_config(albums, photos):
	"""Läser vitlistan i config/albums.json och skriver om katalogen över alla publika album.

	Bara album i "show" kommer med på sidan, i listans ordning. Ett album i "show" med
	"match" eller "merge" är virtuellt: det slår ihop flera Flickr-album (se virtual_album).
	Katalogen "available" skrivs om varje körning så att nya album syns där och kan flyttas in.
	Lägger in de virtuella albumen i albums.
	"""
	path = CONFIG / "albums.json"
	config = read_json(path, {})
	show, merged = [], set()
	for entry in config.get("show", []):
		sid = entry.get("id")
		kind = entry.get("type", "theme")
		if entry.get("match") or entry.get("merge"):
			album, members = virtual_album(entry, albums, photos)
			if album is None:
				log(f"  OBS: det virtuella albumet {sid} matchar inga album – hoppas över")
				continue
			albums[sid] = album
			merged.update(members)
			out = {"id": sid, "title": album["title"], "type": kind}
			for key in ("match", "merge", "description", "primary"):
				if entry.get(key):
					out[key] = entry[key]
			out["albums"] = [albums[m]["title"] for m in members]
			show.append(out)
			log(f"  Virtuellt album {album['title']}: {len(members)} album, {len(album['photos'])} foton")
			continue
		if sid not in albums:
			log(f"  OBS: albumet {sid} ({entry.get('title')}) i show finns inte längre bland de publika – hoppas över")
			continue
		show.append({"id": sid, "title": albums[sid]["title"], "type": kind})
	shown = {e["id"] for e in show} | merged
	available = {
		sid: f"{a['title']} ({sum(1 for i in a['photos'] if i in photos)})"
		for sid, a in sorted(albums.items(), key=lambda x: -len(x[1]["photos"]))
		if sid not in shown
	}
	write_json(path, {"help": ALBUM_HELP, "show": show, "available": available}, pretty=True)
	log(f"  {len(show)} album visas (config/albums.json), {len(available)} övriga i katalogen")
	return show


# ---------------------------------------------------------------- taggar och teman

def update_tag_config(photos):
	"""Läser config/tags.json, tar bort uteslutna taggar ur fotona och skriver om katalogen "available"."""
	path = CONFIG / "tags.json"
	config = read_json(path, {})
	exclude_list = config.get("exclude", DEFAULT_EXCLUDE)
	exclude = re.compile("|".join(f"(?:{x})" for x in exclude_list)) if exclude_list else None
	themes = config.get("themes", [])
	removed = 0
	for p in photos.values():
		if exclude:
			kept = [t for t in p["tags"] if not exclude.search(t)]
			removed += len(p["tags"]) - len(kept)
			p["tags"] = kept
	count = collections.Counter(t for p in photos.values() for t in p["tags"])
	covered = {t for theme in themes for t in theme.get("tags", [])}
	for theme in themes:
		members = set(theme.get("tags", []))
		theme["photos"] = sum(1 for p in photos.values() if members.intersection(p["tags"]))
		missing = [t for t in theme.get("tags", []) if t not in count]
		if missing:
			log(f"  OBS: temat {theme.get('label')} har taggar som inte finns: {', '.join(missing)}")
	available = {t: c for t, c in count.most_common() if t not in covered and c >= 20}
	write_json(path, {
		"help": TAG_HELP,
		"exclude": exclude_list,
		"themes": [{k: th[k] for k in ("id", "label", "tags", "photos") if k in th} for th in themes],
		"available": available,
	}, pretty=True)
	log(f"Taggar: {removed} uteslutna förekomster, {len(count)} olika kvar, {len(themes)} teman (config/tags.json)")
	return themes


# ---------------------------------------------------------------- EXIF

def parse_exif(e):
	tags = {}
	for t in e.get("exif", []):
		tags.setdefault(t.get("tag"), (t.get("clean") or t.get("raw") or {}).get("_content"))

	def clean(value):
		value = (value or "").strip()
		return None if value in ("", "0", "----", "Unknown") or set(value) <= {"-", " ", "0", "."} else value

	camera = clean(e.get("camera")) or clean(" ".join(filter(None, (tags.get("Make"), tags.get("Model")))))
	lens = next((clean(tags.get(t)) for t in LENS_TAGS if clean(tags.get(t))), None)
	record = {
		"camera": camera,
		"lens": lens,
		"focal": clean(tags.get("FocalLength")),
		"aperture": clean(tags.get("FNumber")),
		"exposure": clean(tags.get("ExposureTime")),
		"iso": clean(tags.get("ISO")),
	}
	return {k: v for k, v in record.items() if v}


def fetch_exif(photos, cache, limit):
	path = DATA / "cache" / "exif.json"
	todo = [pid for pid in sorted(photos, key=lambda i: -photos[i]["uploaded"]) if pid not in cache]
	if limit is not None:
		todo = todo[:limit]
	if not todo:
		log("EXIF: inget att hämta.")
		return
	log(f"EXIF: hämtar {len(todo)} av {sum(1 for i in photos if i not in cache)} som saknas "
		f"(~{len(todo) * 1.1 / 60:.0f} min). Ctrl+C avbryter och sparar.")
	done = 0
	try:
		for pid in todo:
			try:
				cache[pid] = parse_exif(call("flickr.photos.getExif", photo_id=pid)["photo"])
			except FlickrError as exc:
				if exc.code in (1, 2):	# fotot finns inte / EXIF är dold
					cache[pid] = {}
				else:
					log(f"  {pid}: {exc} – försöker igen nästa körning")
			done += 1
			if done % 50 == 0:
				write_json(path, cache)
				log(f"  {done}/{len(todo)}")
	except KeyboardInterrupt:
		log(f"\n  Avbrutet efter {done} bilder.")
	write_json(path, cache)


# ---------------------------------------------------------------- utdata

def write_outputs(photos, albums, show, themes, licenses, exif):
	album_types = {e["id"]: e["type"] for e in show}
	visible = [e["id"] for e in show if any(i in photos for i in albums[e["id"]]["photos"])]
	album_index = {sid: n for n, sid in enumerate(visible)}
	photo_albums = collections.defaultdict(list)
	for sid in visible:
		for pid in albums[sid]["photos"]:
			if pid in photos:
				photo_albums[pid].append(album_index[sid])

	tag_count = collections.Counter(t for p in photos.values() for t in p["tags"])
	tag_list = [t for t, _ in sorted(tag_count.items(), key=lambda x: (-x[1], x[0]))]
	tag_index = {t: n for n, t in enumerate(tag_list)}

	def indexed(key):
		count = collections.Counter(exif.get(pid, {}).get(key) for pid in photos)
		count.pop(None, None)
		values = [v for v, _ in sorted(count.items(), key=lambda x: (-x[1], x[0]))]
		return values, {v: n for n, v in enumerate(values)}

	theme_sets = [set(t.get("tags", [])) for t in themes]

	cameras, camera_index = indexed("camera")
	lenses, lens_index = indexed("lens")

	order = sorted(photos.values(), key=lambda p: (p["taken"] or "9999", p["id"]))
	rows = []
	for p in order:
		e = exif.get(p["id"], {})
		rows.append([
			p["id"], p["server"], p["secret"], p["title"], p["taken"], p["granularity"], p["uploaded"],
			p["lat"], p["lon"], p["license"], p["views"], p["faves"], p["comments"],
			[tag_index[t] for t in p["tags"]], photo_albums.get(p["id"], []),
			p["w"], p["h"], p["big"],
			camera_index.get(e.get("camera")), lens_index.get(e.get("lens")),
			[n for n, members in enumerate(theme_sets) if members.intersection(p["tags"])],
		])
	used = sorted({p["license"] for p in photos.values()})
	sizes = {}
	sizes["photos.json"] = write_json(DATA / "photos.json", {
		"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
		"nsid": NSID,
		"count": len(rows),
		"fields": FIELDS,
		"licenses": {str(i): licenses.get(i, [f"licens {i}", ""]) for i in used},
		"tags": tag_list,
		"themes": [{"id": t.get("id"), "label": t.get("label"), "count": t.get("photos", 0)} for t in themes],
		"albums": visible,
		"cameras": cameras,
		"lenses": lenses,
		"photos": rows,
	})

	album_out = []
	for sid in visible:
		a = albums[sid]
		ids = [i for i in a["photos"] if i in photos]
		album_out.append({
			"id": sid,
			"title": a["title"],
			"description": a["description"],
			"type": album_types.get(sid, "theme"),
			"count": len(ids),
			"primary": a["primary"] if a["primary"] in photos else ids[0],
			"created": a["created"],
			"updated": a["updated"],
			"photos": ids,
		})
	sizes["albums.json"] = write_json(DATA / "albums.json", {"albums": album_out})

	details = collections.defaultdict(dict)
	for p in photos.values():
		entry = {}
		if p["description"]:
			entry["description"] = p["description"]
		e = {k: v for k, v in exif.get(p["id"], {}).items() if k not in ("camera", "lens")}
		if e:
			entry["exif"] = e
		if entry:
			details[p["id"][-2:].zfill(2)][p["id"]] = entry
	folder = DATA / "details"
	folder.mkdir(parents=True, exist_ok=True)
	for old in folder.glob("*.json"):
		if old.stem not in details:
			old.unlink()
	sizes["details/"] = sum(write_json(folder / f"{k}.json", v) for k, v in details.items())
	return sizes, album_out, tag_list, cameras, lenses


def summary(photos, album_out, tags, cameras, lenses, licenses, exif, sizes):
	n = len(photos)
	log()
	log("Sammanfattning")
	log("=" * 60)
	geo = sum(1 for p in photos.values() if p["lat"] is not None)
	k = sum(1 for p in photos.values() if p["big"].startswith("k:"))
	log(f"Foton {n}  |  geotaggade {geo} ({100 * geo / n:.1f} %)  |  2048 px {k} ({100 * k / n:.1f} %)")
	years = collections.Counter(p["taken"][:4] if p["taken"] else "okänt" for p in photos.values())
	log("Tagningsår: " + ", ".join(f"{y} {c}" for y, c in sorted(years.items())))
	log(f"Taggar: {len(tags)} olika. Vanligast: {', '.join(tags[:15])}")
	types = collections.Counter(a["type"] for a in album_out)
	log(f"Album: {len(album_out)} ({dict(types)}). Foton utan album: "
		f"{n - len({i for a in album_out for i in a['photos']})}")
	lic = collections.Counter(p["license"] for p in photos.values())
	log("Licenser: " + ", ".join(f"{licenses.get(i, [str(i)])[0]} {c}" for i, c in lic.most_common()))
	have = sum(1 for i in photos if i in exif)
	log(f"EXIF: {have} av {n} hämtade, {len(cameras)} kameror, {len(lenses)} objektiv")
	raw = (DATA / "photos.json").read_bytes()
	log("Filer: " + ", ".join(f"{name} {size / 1024:.0f} kB" for name, size in sizes.items())
		+ f"  (photos.json gzip {len(gzip.compress(raw)) / 1024:.0f} kB)")


def export(exif_limit):
	start = time.time()
	licenses = fetch_licenses()
	photos = fetch_photos()
	albums = fetch_albums(read_json(DATA / "cache" / "albums.json", {}))
	write_json(DATA / "cache" / "albums.json", albums)
	show = update_album_config(albums, photos)
	themes = update_tag_config(photos)
	exif = read_json(DATA / "cache" / "exif.json", {})
	if exif_limit != 0:
		fetch_exif(photos, exif, exif_limit)
	sizes, album_out, tags, cameras, lenses = write_outputs(photos, albums, show, themes, licenses, exif)
	summary(photos, album_out, tags, cameras, lenses, licenses, exif, sizes)
	log(f"Klart på {(time.time() - start) / 60:.1f} min.")


def main():
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument("--probe", action="store_true", help="sondera API:t och rapportera vad som finns")
	parser.add_argument("--exif", metavar="N", help="hämta EXIF för upp till N bilder som saknas ('all' = alla)")
	args = parser.parse_args()
	if args.exif is None:
		exif_limit = 0
	elif args.exif == "all":
		exif_limit = None
	elif args.exif.isdigit():
		exif_limit = int(args.exif)
	else:
		parser.error("--exif tar ett antal eller 'all'")
	load_env()
	if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
		sys.stdout.reconfigure(encoding="utf-8")
	try:
		if args.probe:
			from probe import probe
			probe()
		else:
			export(exif_limit)
	except FlickrError as exc:
		print(f"Fel: {exc}", file=sys.stderr)
		sys.exit(1)


if __name__ == "__main__":
	main()
