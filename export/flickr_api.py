"""Gemensamt för anrop mot Flickr REST API.

Nyckeln läses från miljövariabeln FLICKR_API_KEY eller från .env i repots rot.
Den skrivs aldrig ut, och felmeddelanden innehåller aldrig anropets URL.
Anrop med bara API-nyckel (utan inloggning) ger enbart publika foton.
"""

import os
import time
from pathlib import Path

import requests

NSID = "10817753@N03"
API = "https://api.flickr.com/services/rest/"
ROOT = Path(__file__).resolve().parent.parent
PAUSE = 1.05	# sekunder mellan anrop; håller oss under 3 600 anrop/timme
RETRIES = 3
RETRY_CODES = {105, 106}	# "Service currently unavailable", "Write operation failed"


class FlickrError(Exception):
	def __init__(self, message, code=None):
		super().__init__(message)
		self.code = code


def load_env(path=ROOT / ".env"):
	"""Läser KEY=VALUE-rader ur .env utan att skriva över befintliga variabler."""
	if not path.exists():
		return
	for line in path.read_text(encoding="utf-8").splitlines():
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _once(method, params):
	try:
		resp = requests.get(API, params=params, timeout=60)
	except requests.RequestException as exc:
		raise FlickrError(f"{method}: nätverksfel ({type(exc).__name__})", "net") from None
	finally:
		time.sleep(PAUSE)
	if resp.status_code != 200:
		raise FlickrError(f"{method}: HTTP {resp.status_code}", resp.status_code)
	try:
		data = resp.json()
	except ValueError:
		raise FlickrError(f"{method}: svaret var inte JSON", "json") from None
	if data.get("stat") != "ok":
		raise FlickrError(f"{method}: Flickr-fel {data.get('code')} – {data.get('message')}", data.get("code"))
	return data


def call(method, **params):
	"""Anropar Flickr REST. Försöker igen vid nätverksfel, 5xx och tillfälliga Flickr-fel."""
	key = os.environ.get("FLICKR_API_KEY", "")
	if not key:
		raise FlickrError("FLICKR_API_KEY saknas – lägg den i .env eller som miljövariabel.")
	params.update(method=method, api_key=key, format="json", nojsoncallback=1)
	for attempt in range(1, RETRIES + 1):
		try:
			return _once(method, params)
		except FlickrError as exc:
			transient = exc.code in ("net", "json") or exc.code in RETRY_CODES \
				or (isinstance(exc.code, int) and exc.code >= 500)
			if not transient or attempt == RETRIES:
				raise
			time.sleep(5 * attempt)
