"""Sondering av Flickr API:t – rapporterar vad som faktiskt levereras.

	python export/flickr_export.py --probe
"""

import collections
import json
from datetime import datetime, timezone

from flickr_api import NSID, ROOT, FlickrError, call

EXTRAS = [
	"description", "license", "date_upload", "date_taken", "last_update",
	"geo", "tags", "machine_tags", "o_dims", "views", "media", "path_alias",
	"url_q", "url_n", "url_w", "url_c", "url_l", "url_k",	# url_l = suffix _b, 1024 px
]
# Odokumenterade extras som provas i sonderingen.
TRIAL_EXTRAS = ["count_faves", "count_comments"]


def pct(part, whole):
	return f"{part:>5} av {whole:<5} ({100 * part / whole:5.1f} %)" if whole else f"{part} av 0"


def has(photo, field):
	value = photo.get(field)
	if isinstance(value, dict):
		value = value.get("_content")
	return value not in (None, "", "0", 0)


def probe():
	report = {"nsid": NSID, "tid": datetime.now(timezone.utc).isoformat(timespec="seconds")}
	out = []

	def say(text=""):
		print(text)
		out.append(text)

	say(f"Sondering av Flickr-kontot {NSID}")
	say("=" * 60)

	# 1. Konto
	info = call("flickr.people.getInfo", user_id=NSID)["person"]
	report["konto"] = {
		"användarnamn": info.get("username", {}).get("_content"),
		"pro": info.get("ispro"),
		"foton_enligt_getInfo": info.get("photos", {}).get("count", {}).get("_content"),
		"första_uppladdning": info.get("photos", {}).get("firstdate", {}).get("_content"),
	}
	say(f"Konto: {report['konto']}")

	# 2. Antal publika foton (anrop utan inloggning ger bara publika)
	public = int(call("flickr.people.getPublicPhotos", user_id=NSID, per_page=1)["photos"]["total"])
	search_all = int(call("flickr.photos.search", user_id=NSID, per_page=1)["photos"]["total"])
	search_photos = int(call("flickr.photos.search", user_id=NSID, per_page=1, media="photos")["photos"]["total"])
	report["antal"] = {"getPublicPhotos": public, "search_alla": search_all, "search_foton": search_photos}
	say(f"Publika objekt (getPublicPhotos): {public}")
	say(f"Publika objekt (search):          {search_all}")
	say(f"Publika foton (search, media=photos): {search_photos}   (briefen: 6 751 publika objekt)")

	# 3. Två sidor à 500 foton – nyaste och äldsta – med alla extras
	extras = ",".join(EXTRAS + TRIAL_EXTRAS)
	newest = call("flickr.photos.search", user_id=NSID, media="photos", per_page=500, page=1,
		sort="date-posted-desc", extras=extras)["photos"]
	oldest = call("flickr.photos.search", user_id=NSID, media="photos", per_page=500, page=1,
		sort="date-posted-asc", extras=extras)["photos"]
	seen = {}
	for photo in newest["photo"] + oldest["photo"]:
		seen[photo["id"]] = photo
	sample = list(seen.values())
	n = len(sample)
	say()
	say(f"Stickprov: {n} foton (500 nyaste + 500 äldsta uppladdade)")
	say("-" * 60)

	checks = [
		("count_faves (odokumenterad)", lambda p: "count_faves" in p),
		("count_comments (odokumenterad)", lambda p: "count_comments" in p),
		("views", lambda p: "views" in p),
		("url_k (2048 px)", lambda p: has(p, "url_k")),
		("url_l (1024 px)", lambda p: has(p, "url_l")),
		("url_c (800 px)", lambda p: has(p, "url_c")),
		("o_dims (originalets mått)", lambda p: has(p, "o_width")),
		("geotaggade", lambda p: has(p, "latitude") or has(p, "longitude")),
		("taggar", lambda p: has(p, "tags")),
		("maskintaggar", lambda p: has(p, "machine_tags")),
		("beskrivning", lambda p: has(p, "description")),
		("tagningsdatum känt", lambda p: str(p.get("datetakenunknown", "0")) == "0"),
	]
	report["stickprov"] = {"antal": n, "fält": {}}
	for label, test in checks:
		hits = sum(1 for p in sample if test(p))
		report["stickprov"]["fält"][label] = hits
		say(f"{label:32} {pct(hits, n)}")

	faves = [int(p["count_faves"]) for p in sample if "count_faves" in p]
	views = [int(p["views"]) for p in sample if "views" in p]
	if faves:
		say(f"Favoriter i stickprovet: max {max(faves)}, summa {sum(faves)}")
	if views:
		say(f"Visningar i stickprovet: max {max(views)}, median {sorted(views)[len(views) // 2]}")

	# 4. Licenser
	names = {str(l["id"]): l["name"] for l in call("flickr.photos.licenses.getInfo")["licenses"]["license"]}
	lic = collections.Counter(names.get(str(p.get("license")), f"okänd ({p.get('license')})") for p in sample)
	report["licenser_stickprov"] = dict(lic.most_common())
	say()
	say("Licenser i stickprovet:")
	for name, count in lic.most_common():
		say(f"  {count:>5}  {name}")

	# 5. Album
	sets = call("flickr.photosets.getList", user_id=NSID, per_page=500)["photosets"]
	albums = sets.get("photoset", [])
	in_albums = sum(int(a.get("photos", 0)) for a in albums)
	report["album"] = {"antal": int(sets.get("total", len(albums))), "fotoplatser_summa": in_albums}
	say()
	say(f"Publika album: {report['album']['antal']}  (summa foton i album, med dubbletter: {in_albums})")
	for a in sorted(albums, key=lambda a: -int(a.get("photos", 0)))[:5]:
		say(f"  {int(a.get('photos', 0)):>5}  {a['title']['_content']}")

	# 6. EXIF på 10 bilder spridda över stickprovet
	step = max(1, n // 10)
	exif_rows = []
	for photo in sample[::step][:10]:
		try:
			exif = call("flickr.photos.getExif", photo_id=photo["id"])["photo"]
		except FlickrError as exc:
			exif_rows.append({"id": photo["id"], "fel": str(exc)})
			continue
		tags = {t.get("tag"): t.get("raw", {}).get("_content") for t in exif.get("exif", [])}
		exif_rows.append({
			"id": photo["id"],
			"kamera": exif.get("camera") or None,
			"objektiv": tags.get("LensModel") or tags.get("Lens") or tags.get("LensInfo"),
		})
	report["exif"] = exif_rows
	with_camera = sum(1 for r in exif_rows if r.get("kamera"))
	with_lens = sum(1 for r in exif_rows if r.get("objektiv"))
	say()
	say(f"EXIF (10 bilder): kamera {with_camera}/10, objektiv {with_lens}/10")
	for r in exif_rows:
		say(f"  {r['id']}: {r.get('kamera') or '–'} | {r.get('objektiv') or '–'}" + (f"  [{r['fel']}]" if "fel" in r else ""))

	path = ROOT / "data" / "probe.json"
	path.parent.mkdir(exist_ok=True)
	path.write_text(json.dumps(report, ensure_ascii=False, indent="\t"), encoding="utf-8", newline="\r\n")
	say()
	say(f"Rapporten sparad i {path.relative_to(ROOT)} (innehåller ingen nyckel).")
