# flickr-archive

**Ulf Bodin – Photography**: a static, exhibition-style archive of my public Flickr photos, published at [ulfbodin.se/flickr-archive/](https://ulfbodin.se/flickr-archive/).

Photos are loaded from Flickr and every image links back to its Flickr page.

## Kom igång

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      (fyll i FLICKR_API_KEY)
```

## Export

```
python export/flickr_export.py              foton + album (första gången ~5 min, sedan ~1 min)
python export/flickr_export.py --exif 500   … och EXIF för upp till 500 bilder som saknas
python export/flickr_export.py --exif all   … och EXIF för alla som saknas (~2 h första gången)
python export/flickr_export.py --probe      sondera API:t
```

EXIF-hämtningen kan avbrytas med Ctrl+C – det som hunnit hämtas sparas och nästa körning fortsätter där.

| Fil | Innehåll |
|---|---|
| `data/photos.json` | Alla publika foton i radformat; kolumnerna står i `fields`. Taggar, album, kameror och objektiv är index i listorna med samma namn; licens är Flickrs licens-id (namn och länk i `licenses`). `big` = `k:<secret>` (2048 px), `b` (1024 px) eller `c` (800 px). |
| `data/albums.json` | Publika album i Flickrs ordning, med typ och foto-id:n |
| `data/details/NN.json` | Beskrivning och EXIF-detaljer per foto, uppdelat på id:ts två sista siffror |
| `data/cache/` | Albuminnehåll och EXIF – gör att bara nytt hämtas |
| `config/albums.json` | **Redigeras för hand.** Vitlista (`show`) över album som visas, i ordning, med typ `place` (Var) eller `theme` (Varför). Virtuella album slår ihop flera med `match` (reguljärt uttryck) eller `merge` (id:n). Övriga album listas under `available`. |
| `config/tags.json` | **Redigeras för hand.** Teman (vitlista med engelsk rubrik och taggar på båda språken) och uteslutna taggar (`exclude`). Övriga vanliga taggar listas under `available`. |

Nyckeln läses från `.env` och skrivs aldrig ut.

## Bygge och förhandsvisning

```
python build/build.py                    bygger dist/ med dagens urval
python -m http.server -d dist 8000       → http://localhost:8000/
```

| Fil | Innehåll |
|---|---|
| `config/site.json` | Sidans texter: titel, presentation, länkar |
| `config/gear.json` | Delen Gear: märken som visas (Canon, Sigma), visningsnamn, cropfaktor per kamera (för fullformatsekvivalent brännvidd), fasta objektiv och brännviddsfacken |
| `config/explored.json` | **Redigeras för hand.** Bilderna som valts till Flickrs Explore (delen Explored, filtret `?explored=1`). En rad per bild: `{"id": "…"}`, id:t är numret i bildens Flickr-adress (hela adressen går också bra). Titeln är bara för läsbarhet. |
| `config/hero.json` | Handplockade hero-bilder (portfolion) + slumpurvalets storlek |
| `data/last.json` (byggs) | Den senast uppladdade bilden – läses av den fristående sidan ulfbodin.se/flickr-last/ (repot bodwigg.github.io) |
| `templates/index.html` | Sidan (Jinja2) – upplägget från Radius "månadens" |
| `static/archive.css`, `static/archive.js` | Stil och skript; filtreringen sker i webbläsaren mot `data/photos.json` |
| `static/vendor/` | Leaflet 1.9.4, Leaflet.markercluster 1.5.3, OpenSeadragon 4.1.1 |

flickr-last (`ulfbodin.se/flickr-last/`, i repot bodwigg.github.io) läser `/flickr-archive/data/last.json`. Lokalt: bygg här, starta sedan servern i mappen ovanför båda repona och öppna sidan:

```
python build/build.py
cd ..
python -m http.server 8000               → http://localhost:8000/bodwigg.github.io/flickr-last/
```

Hero, årsbilder, temamosaiker och albumrader väljs med ett frö per dag; bygget körs varje natt och sidan får då ett nytt urval.
