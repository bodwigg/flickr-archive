/*
 * static/archive.js
 * ------------------
 * Ulf Bodin – Photography (templates/index.html). A port of Radius's
 * static/featured.js ("månadens") to a static page: instead of /api/images,
 * /api/facets, /api/geo and /api/image the script loads data/photos.json once
 * and filters, counts and sorts in the browser. The descriptions and EXIF
 * details are loaded per photo from data/details/NN.json (the id's last two digits).
 *   - the large picture changes slowly between a few pictures;
 *   - the archive: a wall of photos, page by page as one scrolls, filtered by
 *     year, decade, theme, album, place, camera, lens, licence and free text;
 *     the filters are kept in the address;
 *   - the panels' counts follow the other panels' choices (cross-faceting);
 *   - the picture viewer: a large photo with its facts, arrows/keys to move,
 *     deep zoom (OpenSeadragon) and the link to the photo on Flickr;
 *   - bookmarks: a star on every photo, stored in the browser (IndexedDB).
 */
(function () {
	'use strict';

	const FX = window.FX || {};
	const CDN = 'https://live.staticflickr.com';
	const wall = document.querySelector('[data-wall]');
	const statusEl = document.querySelector('[data-wall-status]');
	const countEl = document.querySelector('[data-wall-count]');
	const activeEl = document.querySelector('[data-wall-active]');
	const sentinel = document.querySelector('[data-wall-sentinel]');
	const searchForm = document.querySelector('[data-wall-search]');
	const archive = document.getElementById('archive');

	const T = FX.t || {};
	function tr(key, values) {
		return String(T[key] || key).replace(/\{(\w+)\}/g, function (m, k) { return values && values[k] != null ? values[k] : m; });
	}
	const LABELS = { geo: '', bm: tr('label_bm'), year: tr('label_year'), decade: tr('label_decade'), theme: tr('label_theme'), place: tr('label_place'), album: tr('label_album'), camera: tr('label_camera'), lens: tr('label_lens'), focal: tr('label_focal'), license: tr('label_license'), q: tr('label_q') };
	const KEYS = ['geo', 'bm', 'year', 'decade', 'theme', 'place', 'album', 'camera', 'lens', 'focal', 'license', 'q'];
	const SMALL_SCREEN = window.matchMedia('(max-width: 760px)');
	// Which panel shows which filters - and which filters a panel's counts leave out (cross-faceting).
	const PANEL_OF = { decade: 'when', year: 'when', place: 'where', geo: 'where', theme: 'what', album: 'why', camera: 'how', lens: 'how', focal: 'how' };
	const GROUPS = { when: ['year', 'decade'], where: ['place', 'geo'], what: ['theme'], why: ['album'], how: ['camera', 'lens', 'focal'] };

	function el(tag, cls, text) {
		const node = document.createElement(tag);
		if (cls) node.className = cls;
		if (text != null) node.textContent = text;
		return node;
	}
	function fmt(n) { return new Intl.NumberFormat('en-GB').format(n); }

	// --- the data: data/photos.json, decoded once ---------------------------------------------
	const DATA = { photos: [], byId: {}, ready: false, themeIds: [], albumIds: [] };
	function urlOf(p, size) {
		if (size === 'k') {
			if (p.big.indexOf('k:') === 0) return CDN + '/' + p.server + '/' + p.id + '_' + p.big.slice(2) + '_k.jpg';
			size = p.big === 'c' ? 'c' : 'b';
		}
		return CDN + '/' + p.server + '/' + p.id + '_' + p.secret + '_' + size + '.jpg';
	}
	function decode(raw) {
		const f = {};
		raw.fields.forEach(function (k, i) { f[k] = i; });
		DATA.albumIds = raw.albums || [];
		DATA.themeIds = (raw.themes || []).map(function (t) { return t.id; });
		DATA.cameras = raw.cameras || [];
		DATA.lenses = raw.lenses || [];
		DATA.tags = raw.tags || [];
		const albumTitle = DATA.albumIds.map(function (id) { return ((FX.albums || {})[id] || {}).title || ''; });
		const themeLabel = DATA.themeIds.map(function (id) { return (FX.themes || {})[id] || ''; });
		raw.photos.forEach(function (r) {
			const taken = r[f.taken];
			const p = {
				id: r[f.id], server: r[f.server], secret: r[f.secret], title: r[f.title] || '',
				taken: taken, year: taken ? parseInt(taken.slice(0, 4), 10) : null, granularity: r[f.granularity],
				lat: r[f.lat], lon: r[f.lon], license: String(r[f.license]),
				views: r[f.views], faves: r[f.faves], comments: r[f.comments],
				tags: r[f.tags].map(function (i) { return DATA.tags[i]; }),
				albums: r[f.albums].map(function (i) { return DATA.albumIds[i]; }),
				themes: (r[f.themes] || []).map(function (i) { return DATA.themeIds[i]; }),
				w: r[f.w], h: r[f.h], big: r[f.big] || '',
				camera: r[f.camera] == null ? null : DATA.cameras[r[f.camera]],
				lens: r[f.lens] == null ? null : DATA.lenses[r[f.lens]],
			};
			// Gear (config/gear.json): the fixed lens of a camera without lens EXIF, and the focal
			// length as full-frame equivalent (the crop factor per camera) in its bucket.
			if (!p.lens && p.camera && GEAR.fixed[p.camera]) p.lens = GEAR.fixed[p.camera];
			p.focal = f.focal != null ? r[f.focal] : null;
			p.eq = p.focal ? Math.round(p.focal * (GEAR.crop[p.camera] || 1)) : null;
			p.focalKey = focalKey(p.eq);
			p.ratio = p.w && p.h ? Math.round(p.w / p.h * 1000) / 1000 : 1.5;
			p.src = urlOf(p, 'z');
			p.small = urlOf(p, 'n');
			p.search = [p.title, p.tags.join(' '),
				r[f.albums].map(function (i) { return albumTitle[i]; }).join(' '),
				(r[f.themes] || []).map(function (i) { return themeLabel[i]; }).join(' '),
				GEAR.cameras[p.camera] || '', GEAR.lenses[p.lens] || p.lens || ''].join(' ').toLowerCase();
			DATA.photos.push(p);
			DATA.byId[p.id] = p;
		});
		DATA.ready = true;
	}

	const GEAR = Object.assign({ crop: {}, cameras: {}, lenses: {}, fixed: {}, focal: [] }, FX.gear || {});
	function focalKey(eq) {
		if (eq == null) return null;
		for (let i = 0; i < GEAR.focal.length; i++) {
			if (eq >= GEAR.focal[i][0] && eq <= GEAR.focal[i][1]) return GEAR.focal[i][0] + '-' + GEAR.focal[i][1];
		}
		return null;
	}
	function focalLabel(key) {
		const b = GEAR.focal.filter(function (x) { return x[0] + '-' + x[1] === key; })[0];
		return b ? b[2] : key;
	}

	// The same shuffled order all day (the build's date) - "Shuffled" changes from day to day.
	function dayHash(id) {
		let h = 2166136261;
		const s = (FX.day || '') + id;
		for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
		return h >>> 0;
	}

	// --- the large picture ------------------------------------------------------------------------
	const frames = Array.prototype.slice.call(document.querySelectorAll('.fx-hero__frame'));
	const caption = document.querySelector('.fx-hero__caption');
	function loadFrame(i) {
		const img = frames[i] && frames[i].querySelector('img[data-src]');
		if (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); }
	}
	if (frames.length > 1 && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
		let current = 0;
		setTimeout(function () { loadFrame(1); }, 4000);
		setInterval(function () {
			frames[current].classList.remove('is-active');
			current = (current + 1) % frames.length;
			loadFrame(current);
			frames[current].classList.add('is-active');
			// A square or upright picture is shown whole beside the text (.is-whole).
			frames[current].closest('.fx-hero').classList.toggle('is-whole', frames[current].classList.contains('fx-hero__frame--whole'));
			loadFrame((current + 1) % frames.length);
			const img = frames[current].querySelector('img');
			if (caption) {
				caption.dataset.open = frames[current].dataset.id;
				caption.querySelector('.fx-hero__caption-title').textContent = img.alt;
				const year = frames[current].dataset.year || '';
				// The year only when the title does not already say it ("Uppsala, July 6, 2019").
				caption.querySelector('.fx-hero__caption-year').textContent = img.alt.indexOf(year) >= 0 ? '' : year;
			}
		}, 9000);
	}

	// --- the album rows: up to 20 pictures each (data-src); only those that fit are loaded ---------
	const albumRows = document.querySelectorAll('.fx-job__pictures');
	function fillAlbumRows() {
		albumRows.forEach(function (row) {
			const right = row.getBoundingClientRect().right;
			row.querySelectorAll('img[data-src]').forEach(function (img) {
				if (img.parentElement.getBoundingClientRect().left < right) {
					img.src = img.dataset.src;
					img.removeAttribute('data-src');
				}
			});
		});
	}
	if (albumRows.length) {
		fillAlbumRows();
		let rowTimer = null;
		window.addEventListener('resize', function () { clearTimeout(rowTimer); rowTimer = setTimeout(fillAlbumRows, 200); });
	}

	// --- the year strip: large arrows to scroll it -----------------------------------------------
	const strip = document.querySelector('[data-strip]');
	if (strip) {
		const prev = document.querySelector('[data-strip-prev]');
		const next = document.querySelector('[data-strip-next]');
		const syncArrows = function () {
			prev.hidden = strip.scrollLeft < 8;
			next.hidden = strip.scrollLeft + strip.clientWidth > strip.scrollWidth - 8;
		};
		prev.addEventListener('click', function () { strip.scrollBy({ left: -strip.clientWidth * 0.8, behavior: 'smooth' }); });
		next.addEventListener('click', function () { strip.scrollBy({ left: strip.clientWidth * 0.8, behavior: 'smooth' }); });
		strip.addEventListener('scroll', syncArrows, { passive: true });
		window.addEventListener('resize', syncArrows);
		syncArrows();
	}

	// --- state -------------------------------------------------------------------------------------
	const state = { filters: {}, labels: {}, order: 'time_desc', next: 0, done: false, items: [], list: [], auto: 0, pin: null };
	// The wall fills itself as it is scrolled - AUTO_PAGES pages at a time, then a button:
	// otherwise the footer (About) could never be reached.
	const PAGE = 60;
	const AUTO_PAGES = 4;
	const moreWrap = document.querySelector('[data-wall-more-wrap]');
	(function fromUrl() {
		const params = new URLSearchParams(window.location.search);
		KEYS.forEach(function (k) { if (params.get(k)) state.filters[k] = params.get(k); });
		// Newest first unless the address says otherwise (order=time: oldest first, order=random).
		if (['time', 'random', 'time_desc'].indexOf(params.get('order')) >= 0) state.order = params.get('order');
	})();

	function toUrl() {
		const url = new URL(window.location.href);
		KEYS.forEach(function (k) { url.searchParams.delete(k); });
		url.searchParams.delete('order');
		Object.keys(state.filters).forEach(function (k) { url.searchParams.set(k, state.filters[k]); });
		if (state.order !== 'time_desc') url.searchParams.set('order', state.order);
		history.replaceState(null, '', url);
	}

	function label(key, value) {
		if (state.labels[key + ':' + value]) return state.labels[key + ':' + value];
		if (key === 'decade') return tr('decade', { decade: value });
		if (key === 'theme') return (FX.themes || {})[value] || value;
		if (key === 'place' || key === 'album') return ((FX.albums || {})[value] || {}).title || value;
		if (key === 'license') return ((FX.licenses || {})[value] || [value])[0];
		if (key === 'camera') return GEAR.cameras[value] || value;
		if (key === 'lens') return GEAR.lenses[value] || value;
		if (key === 'focal') return focalLabel(value);
		if (key === 'bm') return tr('bm_value');
		if (key === 'geo') return tr('map');
		return value;
	}

	function syncControls() {
		document.querySelectorAll('[data-panel-chip]').forEach(function (b) {
			b.setAttribute('aria-pressed', state.filters[b.dataset.filter] === b.dataset.value ? 'true' : 'false');
		});
		const summary = { when: [], where: [], what: [], why: [], how: [] };
		Object.keys(state.filters).forEach(function (k) {
			if (PANEL_OF[k]) summary[PANEL_OF[k]].push(label(k, state.filters[k]));
		});
		document.querySelectorAll('[data-summary]').forEach(function (span) {
			const values = summary[span.dataset.summary] || [];
			span.textContent = values.length ? values.join(', ') : '';
			span.closest('.fx-facet').classList.toggle('is-active', values.length > 0);
		});
		document.querySelectorAll('[data-order]').forEach(function (b) {
			const on = b.dataset.order === 'time' ? state.order !== 'random' : b.dataset.order === state.order;
			b.setAttribute('aria-pressed', on ? 'true' : 'false');
			const dir = b.querySelector('[data-order-dir]');
			if (dir) {
				const desc = state.order === 'time_desc';
				dir.textContent = desc ? '↓' : '↑';
				b.title = desc ? b.dataset.desc : b.dataset.asc;
			}
		});
		if (searchForm && document.activeElement !== searchForm.q) searchForm.q.value = state.filters.q || '';
		activeEl.innerHTML = '';
		const keys = Object.keys(state.filters).filter(function (k) { return k !== 'q'; });
		keys.forEach(function (k) {
			const chip = el('button', 'fx-active__chip');
			chip.type = 'button';
			chip.appendChild(el('span', null, LABELS[k]));
			chip.appendChild(document.createTextNode(label(k, state.filters[k])));
			chip.appendChild(document.createTextNode(' ✕'));
			chip.setAttribute('aria-label', tr('remove', { what: (LABELS[k] + ' ' + label(k, state.filters[k])).trim() }));
			chip.addEventListener('click', function () { delete state.filters[k]; reload(false); });
			activeEl.appendChild(chip);
		});
		activeEl.hidden = keys.length === 0;
		const clear = document.querySelector('[data-clear]');
		if (clear) clear.hidden = Object.keys(state.filters).length === 0;
		syncStars();
	}

	function setFilter(key, value, labelText, scroll, toggle) {
		if (key === 'year') delete state.filters.decade;
		if (key === 'decade') delete state.filters.year;
		if (toggle && state.filters[key] === value) delete state.filters[key];
		else state.filters[key] = value;
		if (labelText) state.labels[key + ':' + value] = labelText;
		reload(scroll !== false);
	}

	// --- filtering ---------------------------------------------------------------------------------
	function matcher(filters, leaveOut) {
		const f = {};
		Object.keys(filters).forEach(function (k) { if (!leaveOut || leaveOut.indexOf(k) < 0) f[k] = filters[k]; });
		const terms = f.q ? f.q.toLowerCase().split(/\s+/).filter(Boolean) : [];
		const year = f.year ? parseInt(f.year, 10) : null;
		const decade = f.decade ? parseInt(f.decade, 10) : null;
		return function (p) {
			if (f.geo && p.lat == null) return false;
			if (f.bm && !BM.has(p.id)) return false;
			if (year != null && p.year !== year) return false;
			if (decade != null && (p.year == null || p.year < decade || p.year > decade + 9)) return false;
			if (f.theme && p.themes.indexOf(f.theme) < 0) return false;
			if (f.place && p.albums.indexOf(f.place) < 0) return false;
			if (f.album && p.albums.indexOf(f.album) < 0) return false;
			if (f.camera && p.camera !== f.camera) return false;
			if (f.lens && p.lens !== f.lens) return false;
			if (f.focal && p.focalKey !== f.focal) return false;
			if (f.license && p.license !== f.license) return false;
			for (let i = 0; i < terms.length; i++) if (p.search.indexOf(terms[i]) < 0) return false;
			return true;
		};
	}

	function sorted(list) {
		if (state.order === 'random') {
			return list.map(function (p) { return [dayHash(p.id), p]; }).sort(function (a, b) { return a[0] - b[0]; }).map(function (x) { return x[1]; });
		}
		const desc = state.order === 'time_desc';
		return list.slice().sort(function (a, b) {
			// Photos without a date last, either way.
			if (!a.taken !== !b.taken) return a.taken ? -1 : 1;
			const c = (a.taken || '').localeCompare(b.taken || '') || a.id.localeCompare(b.id);
			return desc ? -c : c;
		});
	}

	function reload(scroll) {
		state.next = 0;
		state.done = false;
		state.auto = 0;
		state.items = [];
		wall.innerHTML = '';
		toUrl();
		syncControls();
		if (DATA.ready) {
			state.list = sorted(DATA.photos.filter(matcher(state.filters)));
			if (state.pin && DATA.byId[state.pin]) {
				// The clicked picture (a year's or a theme's) first in the wall, framed.
				const pinned = DATA.byId[state.pin];
				state.list = [pinned].concat(state.list.filter(function (p) { return p.id !== pinned.id; }));
				state.pinned = pinned.id;
			} else {
				state.pinned = null;
			}
			state.pin = null;
			showMap(!!state.filters.geo);
			load();
			loadFacets();
		}
		if (scroll) archive.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	// --- cross-faceting: the panels' counts follow the other panels' choices -------------------------
	function setCount(chip, n) {
		const span = chip.querySelector('span');
		if (span) span.textContent = fmt(n);
		else chip.title = tr(n === 1 ? 'count_one' : 'count_many', { count: fmt(n) });
		chip.hidden = n === 0 && chip.getAttribute('aria-pressed') !== 'true';
	}
	function panelEmpty(name) {
		const panel = document.querySelector('[data-panel-body="' + name + '"]');
		if (!panel) return;
		const empty = panel.querySelector('[data-panel-empty]');
		if (empty) empty.hidden = !!panel.querySelector('[data-panel-chip]:not([hidden])');
	}
	function countBy(group, key) {
		const counts = {};
		const test = matcher(state.filters, Array.isArray(group) ? group : GROUPS[group]);
		DATA.photos.forEach(function (p) {
			if (!test(p)) return;
			key(p).forEach(function (v) { if (v != null) counts[v] = (counts[v] || 0) + 1; });
		});
		return counts;
	}
	function loadFacets() {
		if (!DATA.ready) return;
		const years = countBy('when', function (p) { return p.year == null ? [] : [p.year]; });
		const decades = {};
		Object.keys(years).forEach(function (y) { const d = Math.floor(y / 10) * 10; decades[d] = (decades[d] || 0) + years[y]; });
		document.querySelectorAll('[data-panel-body="when"] .fx-panel__row').forEach(function (row) {
			row.querySelectorAll('[data-filter="year"]').forEach(function (b) { setCount(b, years[b.dataset.value] || 0); });
			const decade = row.querySelector('[data-filter="decade"]');
			if (decade) setCount(decade, decades[decade.dataset.value] || 0);
			row.hidden = !row.querySelector('[data-panel-chip]:not([hidden])');
		});
		const where = countBy('where', function (p) { return p.albums.concat(p.lat != null ? ['__geo'] : []); });
		document.querySelectorAll('[data-panel-body="where"] [data-filter="place"]').forEach(function (b) { setCount(b, where[b.dataset.value] || 0); });
		// The map: every other choice counts - the photos with a position among them.
		const geoChip = document.querySelector('[data-panel-body="where"] [data-filter="geo"]');
		if (geoChip) {
			const test = matcher(state.filters, ['geo']);
			setCount(geoChip, DATA.photos.filter(function (p) { return p.lat != null && test(p); }).length);
		}
		document.querySelectorAll('[data-panel-body="where"] .fx-panel__group').forEach(function (group) {
			group.hidden = !group.querySelector('[data-panel-chip]:not([hidden])');
		});
		const what = countBy('what', function (p) { return p.themes; });
		document.querySelectorAll('[data-panel-body="what"] [data-filter="theme"]').forEach(function (b) { setCount(b, what[b.dataset.value] || 0); });
		const why = countBy('why', function (p) { return p.albums; });
		document.querySelectorAll('[data-panel-body="why"] [data-filter="album"]').forEach(function (b) { setCount(b, why[b.dataset.value] || 0); });
		// How: camera, lens and focal length narrow each other - each leaves out only its own choice.
		const cams = countBy(['camera'], function (p) { return [p.camera]; });
		const lensCounts = countBy(['lens'], function (p) { return [p.lens]; });
		const focals = countBy(['focal'], function (p) { return [p.focalKey]; });
		document.querySelectorAll('[data-panel-body="how"] [data-filter="camera"]').forEach(function (b) { setCount(b, cams[b.dataset.value] || 0); });
		document.querySelectorAll('[data-panel-body="how"] [data-filter="lens"]').forEach(function (b) { setCount(b, lensCounts[b.dataset.value] || 0); });
		document.querySelectorAll('[data-panel-body="how"] [data-filter="focal"]').forEach(function (b) { setCount(b, focals[b.dataset.value] || 0); });
		document.querySelectorAll('[data-panel-body="how"] .fx-panel__group').forEach(function (group) {
			group.hidden = !group.querySelector('[data-panel-chip]:not([hidden])');
		});
		['when', 'where', 'what', 'why', 'how'].forEach(panelEmpty);
	}

	// --- the wall ---------------------------------------------------------------------------------
	function tile(item, index) {
		const wrap = el('div', 'fx-tile');
		wrap.style.setProperty('--r', item.ratio || 1);
		const a = el('button', 'fx-tile__open');
		a.type = 'button';
		a.dataset.index = index;
		a.setAttribute('aria-label', item.title || tr('untitled'));
		wrap.appendChild(a);
		if (BM.available) wrap.appendChild(starButton(item, 'fx-tile__star'));
		const img = el('img');
		img.src = item.src;
		img.alt = item.title || '';
		img.loading = 'lazy';
		img.decoding = 'async';
		a.appendChild(img);
		const cap = el('span', 'fx-tile__caption');
		const title = el('span', 'fx-tile__title');
		if (item.year) title.appendChild(el('b', null, item.year + ' '));
		title.appendChild(document.createTextNode(item.title || ''));
		cap.appendChild(title);
		// EXIF on hover: camera, lens and focal length at once (photos.json); aperture, time and
		// ISO from the details file the first time the photo is pointed at.
		const gear = gearLine(item);
		if (gear.length) {
			const exif = el('span', 'fx-tile__exif', gear.join(' · '));
			cap.appendChild(exif);
			wrap.addEventListener('mouseenter', function () {
				if (exif.dataset.done) return;
				exif.dataset.done = '1';
				detailsOf(item.id).then(function (d) {
					const more = settingsOf(d.exif || {});
					if (more.length) exif.textContent = gear.concat(more).join(' · ');
				});
			});
		}
		a.appendChild(cap);
		a.addEventListener('click', function () { openViewer(index); });
		return wrap;
	}

	// The short EXIF line: "EOS R5 · RF 85mm F1.2 L USM · 85 mm" (+ the equivalent for a smaller sensor).
	function gearLine(p) {
		const parts = [];
		if (p.camera) parts.push((GEAR.cameras[p.camera] || p.camera).replace(/^Canon /, ''));
		if (p.lens) parts.push(GEAR.lenses[p.lens] || p.lens);
		if (p.focal) {
			const crop = GEAR.crop[p.camera] || 1;
			parts.push(p.focal + ' mm' + (crop !== 1 && p.eq ? ' (' + p.eq + ' ' + tr('equiv') + ')' : ''));
		}
		return parts;
	}
	function settingsOf(e) {
		// Flickr's exposure: "0.001 sec (1/800)" - the fraction is enough.
		const time = e.exposure ? (e.exposure.match(/\(([^)]+)\)/) || [null, e.exposure.replace(/\s*sec$/, '')])[1] + ' s' : null;
		return [e.aperture, time, e.iso ? 'ISO ' + e.iso : null].filter(Boolean);
	}

	function load() {
		if (!DATA.ready || state.done) return;
		const page = state.list.slice(state.next, state.next + PAGE);
		const frag = document.createDocumentFragment();
		page.forEach(function (item) {
			state.items.push(item);
			const t = tile(item, state.items.length - 1);
			if (item.id === state.pinned && state.items.length === 1) t.classList.add('is-pinned');
			frag.appendChild(t);
		});
		wall.appendChild(frag);
		const total = state.list.length;
		countEl.textContent = tr(total === 1 ? 'count_one' : 'count_many', { count: fmt(total) });
		state.next += page.length;
		state.done = state.next >= total;
		if (moreWrap) moreWrap.hidden = state.done || state.auto < AUTO_PAGES;
		statusEl.textContent = total === 0 ? (state.filters.bm ? tr('none_bm') : tr('none')) : '';
	}

	if (sentinel && 'IntersectionObserver' in window) {
		new IntersectionObserver(function (entries) {
			if (!entries.some(function (e) { return e.isIntersecting; })) return;
			if (state.auto >= AUTO_PAGES || state.done || !DATA.ready || !state.items.length) return;
			state.auto += 1;
			load();
		}, { rootMargin: '400px 0px' }).observe(sentinel);
	}
	if (moreWrap) {
		moreWrap.querySelector('button').addEventListener('click', function () {
			state.auto = 0;
			moreWrap.hidden = true;
			load();
		});
	}
	// About: the wall stops filling itself, so the footer stays where it is.
	document.querySelectorAll('a[href="#about"]').forEach(function (a) {
		a.addEventListener('click', function () {
			state.auto = AUTO_PAGES;
			if (moreWrap && !state.done && state.items.length) moreWrap.hidden = false;
		});
	});

	// --- bookmarks (IndexedDB, this page's own store) ---------------------------------------------
	const BM = (function () {
		const api = { available: 'indexedDB' in window, keys: new Set() };
		let dbPromise = null;
		function open() {
			if (dbPromise) return dbPromise;
			dbPromise = new Promise(function (resolve, reject) {
				let request;
				try { request = indexedDB.open('ulfbodin-photography', 1); } catch (e) { reject(e); return; }
				request.onupgradeneeded = function () {
					const db = request.result;
					if (!db.objectStoreNames.contains('bookmarks')) db.createObjectStore('bookmarks', { keyPath: 'id' });
				};
				request.onsuccess = function () { resolve(request.result); };
				request.onerror = function () { reject(request.error); };
			});
			return dbPromise;
		}
		function run(mode, fn) {
			return open().then(function (db) {
				return new Promise(function (resolve, reject) {
					const tx = db.transaction('bookmarks', mode);
					const req = fn(tx.objectStore('bookmarks'));
					let result;
					if (req) req.onsuccess = function () { result = req.result; };
					tx.oncomplete = function () { resolve(result); };
					tx.onerror = function () { reject(tx.error); };
				});
			});
		}
		api.load = function () {
			return run('readonly', function (s) { return s.getAll(); }).then(function (all) {
				api.keys = new Set((all || []).map(function (r) { return r.id; }));
			});
		};
		api.count = function () {
			let n = 0;
			api.keys.forEach(function (k) { if (!DATA.ready || DATA.byId[k]) n += 1; });
			return n;
		};
		api.has = function (id) { return api.keys.has(id); };
		api.toggle = function (item) {
			if (api.keys.has(item.id)) {
				return run('readwrite', function (s) { return s.delete(item.id); }).then(function () { api.keys.delete(item.id); return false; });
			}
			const record = { id: item.id, title: item.title || '', created: new Date().toISOString() };
			return run('readwrite', function (s) { return s.put(record); }).then(function () { api.keys.add(item.id); return true; });
		};
		return api;
	})();

	function starButton(item, cls) {
		const b = el('button', cls, '★');
		b.type = 'button';
		b.dataset.star = item.id;
		showStar(b);
		b.addEventListener('click', function (event) {
			event.stopPropagation();
			BM.toggle(item).then(function () {
				syncStars();
				if (state.filters.bm) reload(false);
			}).catch(function () {});
		});
		return b;
	}

	function showStar(b) {
		const on = BM.has(b.dataset.star);
		b.classList.toggle('is-active', on);
		b.setAttribute('aria-pressed', on ? 'true' : 'false');
		const text = on ? tr('bm_remove') : tr('bm_add');
		b.title = text;
		b.setAttribute('aria-label', text);
		const starLabel = b.querySelector('.fx-v-star__label');
		if (starLabel) starLabel.textContent = on ? tr('bookmarked') : tr('bookmark');
	}

	const bmToggle = document.querySelector('[data-bookmarks-toggle]');
	const bmCount = document.querySelector('[data-bookmarks-count]');
	function syncStars() {
		document.querySelectorAll('[data-star]').forEach(showStar);
		if (bmToggle) {
			bmToggle.hidden = !BM.available;
			const n = BM.count();
			bmCount.textContent = n ? String(n) : '';
			bmToggle.setAttribute('aria-pressed', state.filters.bm ? 'true' : 'false');
			bmToggle.classList.toggle('is-active', !!state.filters.bm);
		}
	}
	if (bmToggle) {
		bmToggle.addEventListener('click', function () {
			if (state.filters.bm) delete state.filters.bm;
			else state.filters.bm = '1';
			reload(false);
		});
	}

	// --- clicks: every filter on the page leads to the wall ------------------------------------------
	document.addEventListener('click', function (event) {
		const f = event.target.closest('[data-filter]');
		if (f) {
			event.preventDefault();
			closeViewer();
			const panel = f.closest('[data-panel-body]');
			// A year, a theme or an album above the archive starts a new selection.
			if (f.closest('#years, #themes, #albums, #gear')) {
				state.filters = {};
				if (searchForm) searchForm.q.value = '';
			}
			const pinEl = event.target.closest('[data-pin]') || (f.classList.contains('fx-year') ? f.querySelector('[data-pin]') : null);
			state.pin = pinEl ? pinEl.dataset.pin : null;
			const deselect = !!panel && state.filters[f.dataset.filter] === f.dataset.value;
			const closeAfter = !!panel && !deselect && SMALL_SCREEN.matches;
			if (f.dataset.filter === 'q') {
				state.filters = {};
				state.filters.q = f.dataset.value;
				reload(true);
				return;
			}
			// data-also: further choices made together with this one ("theme:panorama" - the panoramas strip).
			if (f.dataset.also) f.dataset.also.split(';').forEach(function (pair) {
				const i = pair.indexOf(':');
				if (i > 0) state.filters[pair.slice(0, i)] = pair.slice(i + 1);
			});
			setFilter(f.dataset.filter, f.dataset.value, f.dataset.label, !panel || closeAfter, !!panel);
			if (closeAfter && !panel.hidden) togglePanel(panel.dataset.panelBody);
			return;
		}
		const panelButton = event.target.closest('[data-panel]');
		if (panelButton) { togglePanel(panelButton.dataset.panel); return; }
		const o = event.target.closest('[data-order]');
		if (o) {
			// Chronological: a click on the pressed button turns it (newest ↔ oldest first); from Shuffled back to newest first.
			if (o.dataset.order === 'time') state.order = state.order === 'time_desc' ? 'time' : 'time_desc';
			else state.order = o.dataset.order;
			reload(false);
			return;
		}
		const open = event.target.closest('[data-open]');
		if (open) openSingle(open.dataset.open);
	});

	const clearButton = document.querySelector('[data-clear]');
	if (clearButton) {
		clearButton.addEventListener('click', function () {
			state.filters = {};
			if (searchForm) searchForm.q.value = '';
			document.querySelectorAll('[data-panel-body]').forEach(function (panel) {
				if (!panel.hidden) togglePanel(panel.dataset.panelBody);
			});
			reload(false);
			if (searchForm) searchForm.q.focus({ preventScroll: true });
		});
	}

	// One panel open at a time.
	function togglePanel(name) {
		const opening = !!document.querySelector('[data-panel-body="' + name + '"][hidden]');
		if (opening && archive.getBoundingClientRect().top < -40) archive.scrollIntoView({ behavior: 'smooth', block: 'start' });
		document.querySelectorAll('[data-panel-body]').forEach(function (panel) {
			const open = panel.dataset.panelBody === name && panel.hidden;
			panel.hidden = !open;
			const button = document.querySelector('[data-panel="' + panel.dataset.panelBody + '"]');
			if (button) {
				button.setAttribute('aria-expanded', open ? 'true' : 'false');
				button.title = open ? tr('collapse') : tr('show_choices');
			}
		});
	}
	document.querySelectorAll('[data-panel-close]').forEach(function (b) {
		b.addEventListener('click', function () {
			const panel = b.closest('[data-panel-body]');
			togglePanel(panel.dataset.panelBody);
			const button = document.querySelector('[data-panel="' + panel.dataset.panelBody + '"]');
			if (button) button.focus({ preventScroll: true });
		});
	});

	// "Show more themes": the hidden theme tiles (their pictures load when shown).
	// "Show more albums": the albums after the first ten (their rows fill when shown).
	const moreAlbums = document.querySelector('[data-albums-more]');
	if (moreAlbums) {
		const moreText = moreAlbums.textContent;
		moreAlbums.addEventListener('click', function () {
			const extra = document.querySelectorAll('[data-album-more]');
			const show = extra.length && extra[0].hidden;
			extra.forEach(function (row) { row.hidden = !show; });
			moreAlbums.textContent = show ? moreAlbums.dataset.less : moreText;
			if (show) fillAlbumRows();
			else document.getElementById('albums').scrollIntoView({ behavior: 'smooth', block: 'start' });
		});
	}

	const moreThemes = document.querySelector('[data-themes-more]');
	if (moreThemes) {
		const moreText = moreThemes.textContent;
		moreThemes.addEventListener('click', function () {
			const extra = document.querySelectorAll('[data-theme-more]');
			const show = extra.length && extra[0].hidden;
			extra.forEach(function (t) {
				t.hidden = !show;
				t.querySelectorAll('img[data-src]').forEach(function (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); });
			});
			moreThemes.textContent = show ? moreThemes.dataset.less : moreText;
			if (!show) document.getElementById('themes').scrollIntoView({ behavior: 'smooth', block: 'start' });
		});
	}

	if (searchForm) {
		let timer = null;
		searchForm.addEventListener('submit', function (event) { event.preventDefault(); });
		searchForm.q.addEventListener('input', function () {
			clearTimeout(timer);
			timer = setTimeout(function () {
				const q = searchForm.q.value.trim();
				const next = q.length >= 2 ? q : '';
				if (next === (state.filters.q || '')) return;
				if (next) state.filters.q = next;
				else delete state.filters.q;
				reload(false);
			}, 300);
		});
	}

	// --- the map (the choice "Show on map" under Where) ----------------------------------------------
	const mapEl = document.querySelector('[data-map]');
	let map = null;
	let mapGroup = null;
	let mapKey = null;
	let mapEmpty = null;
	function showMap(show) {
		if (!mapEl) return;
		mapEl.hidden = !show;
		if (!show || !window.L) return;
		if (!map) {
			map = L.map(mapEl, { scrollWheelZoom: false });
			const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
				maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
			});
			// Satellite: Esri World Imagery, as on ulfbodin.se/gotland.html.
			const satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
				maxZoom: 19, attribution: 'Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
			});
			mapBase(map, { osm: osm, satellite: satellite });
			mapFullscreen(map);
			mapOpacity(map, [osm, satellite]);
			mapEmpty = el('p', 'fx-map__empty', tr('map_empty'));
			mapEmpty.hidden = true;
			mapEl.appendChild(mapEmpty);
		} else {
			map.invalidateSize();
		}
		const key = JSON.stringify(state.filters);
		if (key === mapKey) return;
		mapKey = key;
		if (mapGroup) map.removeLayer(mapGroup);
		mapGroup = L.markerClusterGroup ? L.markerClusterGroup({ maxClusterRadius: 40, showCoverageOnHover: false }) : L.featureGroup();
		const points = state.list.filter(function (p) { return p.lat != null; });
		points.forEach(function (p) {
			const icon = L.divIcon({ className: 'fx-map__dot', iconSize: [14, 14] });
			const marker = L.marker([p.lat, p.lon], { icon: icon, title: p.title || '', alt: p.title || '' });
			marker.bindTooltip(function () {
				return '<img src="' + p.small + '" alt="" width="120"><span>' + (p.year ? p.year + ' ' : '') + String(p.title || '').replace(/[<>&"]/g, function (c) { return { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]; }) + '</span>';
			}, { direction: 'top', offset: [0, -8], className: 'fx-map__tip' });
			marker.on('click', function () { openSingle(p.id); });
			mapGroup.addLayer(marker);
		});
		mapGroup.addTo(map);
		mapEmpty.hidden = points.length > 0;
		const bounds = mapGroup.getBounds();
		if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
		else if (!map._loaded) map.setView([60, 15], 4);
	}

	// Full screen (from Radius's static/map-fullscreen.js): a button below the zoom buttons lays the
	// map over the whole window (position: fixed, not the browser's Fullscreen API - the picture
	// viewer still opens above it and Escape works). Scroll-wheel zoom only in full screen.
	const ICON_FS_OPEN = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/></svg>';
	const ICON_FS_CLOSE = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/></svg>';
	let mapIsFull = false;
	let setMapFull = function () {};
	function mapFullscreen(m) {
		const container = m.getContainer();
		let button = null;
		setMapFull = function (on) {
			if (on === mapIsFull) return;
			mapIsFull = on;
			const center = m.getCenter();
			container.classList.toggle('map--fullscreen', on);
			document.documentElement.classList.toggle('has-map-fullscreen', on);
			if (on) m.scrollWheelZoom.enable(); else m.scrollWheelZoom.disable();
			const text = on ? tr('map_fullscreen_exit') : tr('map_fullscreen');
			// The icon is swapped after the click - otherwise Leaflet takes the click for the map's.
			setTimeout(function () { button.innerHTML = on ? ICON_FS_CLOSE : ICON_FS_OPEN; }, 0);
			button.title = text;
			button.setAttribute('aria-label', text);
			button.setAttribute('aria-pressed', on ? 'true' : 'false');
			requestAnimationFrame(function () {
				m.invalidateSize();
				m.setView(center, m.getZoom(), { animate: false });
			});
		};
		const Control = L.Control.extend({
			options: { position: 'topleft' },
			onAdd: function () {
				const bar = L.DomUtil.create('div', 'leaflet-bar map-fullscreen');
				button = L.DomUtil.create('a', 'map-fullscreen__button', bar);
				button.href = '#';
				button.setAttribute('role', 'button');
				button.innerHTML = ICON_FS_OPEN;
				button.title = tr('map_fullscreen');
				button.setAttribute('aria-label', button.title);
				button.setAttribute('aria-pressed', 'false');
				L.DomEvent.disableClickPropagation(bar);
				button.addEventListener('click', function (event) { event.preventDefault(); setMapFull(!mapIsFull); });
				return bar;
			},
		});
		new Control().addTo(m);
	}

	// The background map's visibility (from Radius's static/map-opacity.js): a button at the top right
	// unfolds a slider; the dots stay as they are, so they stand out when the background is dimmed.
	// The value is remembered in the browser.
	const OPACITY_KEY = 'ulfbodin:map-opacity';
	function storedOpacity() {
		try {
			const v = parseFloat(localStorage.getItem(OPACITY_KEY));
			return Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 1;
		} catch (err) { return 1; }
	}
	function mapOpacity(m, layers) {
		const text = tr('map_opacity');
		const tiles = { setOpacity: function (v) { layers.forEach(function (l) { l.setOpacity(v); }); } };
		tiles.setOpacity(storedOpacity());
		const Control = L.Control.extend({
			options: { position: 'topright' },
			onAdd: function () {
				const box = L.DomUtil.create('div', 'leaflet-bar map-opacity');
				const button = L.DomUtil.create('a', 'map-opacity__button', box);
				button.href = '#';
				button.title = text;
				button.setAttribute('role', 'button');
				button.setAttribute('aria-label', text);
				button.setAttribute('aria-expanded', 'false');
				button.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M11.99 18.54l-7.37-5.73L3 14.07l9 7 9-7-1.63-1.27-7.38 5.74zM12 16l7.36-5.73L21 9l-9-7-9 7 1.63 1.27L12 16z"/></svg>';
				const panel = L.DomUtil.create('div', 'map-opacity__panel', box);
				panel.hidden = true;
				L.DomUtil.create('span', 'map-opacity__label', panel).textContent = text;
				const input = L.DomUtil.create('input', 'map-opacity__range', panel);
				input.type = 'range'; input.min = '0'; input.max = '100'; input.step = '5';
				input.value = String(Math.round(storedOpacity() * 100));
				input.setAttribute('aria-label', text);
				const value = L.DomUtil.create('span', 'map-opacity__value', panel);
				function showValue(v) {
					value.textContent = Math.round(v * 100) + '%';
					box.classList.toggle('map-opacity--dimmed', v < 1);
				}
				showValue(storedOpacity());
				function setOpen(open) {
					panel.hidden = !open;
					button.setAttribute('aria-expanded', open ? 'true' : 'false');
					box.classList.toggle('map-opacity--open', open);
					if (open) input.focus();
				}
				L.DomEvent.disableClickPropagation(box);
				L.DomEvent.disableScrollPropagation(box);
				button.addEventListener('click', function (event) { event.preventDefault(); setOpen(panel.hidden); });
				document.addEventListener('click', function (event) { if (!panel.hidden && !box.contains(event.target)) setOpen(false); });
				box.addEventListener('keydown', function (event) {
					if (event.key === 'Escape' && !panel.hidden) { event.stopPropagation(); setOpen(false); button.focus(); }
				});
				input.addEventListener('input', function () {
					const v = Number(input.value) / 100;
					tiles.setOpacity(v);
					showValue(v);
					try { localStorage.setItem(OPACITY_KEY, String(v)); } catch (err) { /* no storage */ }
				});
				return box;
			},
		});
		new Control().addTo(m);
	}
	// Map | Satellite (from ulfbodin.se/gotland.html): a two-part switch at the top right; the choice
	// is remembered in the browser. The visibility slider applies to both.
	const BASE_KEY = 'ulfbodin:map-base';
	function mapBase(m, layers) {
		let current = 'osm';
		try { if (layers[localStorage.getItem(BASE_KEY)]) current = localStorage.getItem(BASE_KEY); } catch (err) { /* no storage */ }
		layers[current].addTo(m);
		const Control = L.Control.extend({
			options: { position: 'topright' },
			onAdd: function () {
				const bar = L.DomUtil.create('div', 'leaflet-bar map-base');
				bar.setAttribute('role', 'group');
				const buttons = {};
				[['osm', tr('map_map')], ['satellite', tr('map_satellite')]].forEach(function (pair) {
					const b = L.DomUtil.create('a', 'map-base__button', bar);
					b.href = '#';
					b.setAttribute('role', 'button');
					b.textContent = pair[1];
					b.setAttribute('aria-pressed', pair[0] === current ? 'true' : 'false');
					b.addEventListener('click', function (event) {
						event.preventDefault();
						if (pair[0] === current) return;
						m.removeLayer(layers[current]);
						current = pair[0];
						layers[current].addTo(m);
						layers[current].bringToBack();
						Object.keys(buttons).forEach(function (k) { buttons[k].setAttribute('aria-pressed', k === current ? 'true' : 'false'); });
						try { localStorage.setItem(BASE_KEY, current); } catch (err) { /* no storage */ }
					});
					buttons[pair[0]] = b;
				});
				L.DomEvent.disableClickPropagation(bar);
				return bar;
			},
		});
		new Control().addTo(m);
	}

	// Escape leaves the map's full screen - unless the picture viewer is open above it.
	document.addEventListener('keydown', function (event) {
		if (event.key === 'Escape' && mapIsFull && viewer.hidden) setMapFull(false);
	});

	// --- the picture viewer ------------------------------------------------------------------------
	const viewer = document.querySelector('[data-viewer]');
	const vImg = viewer.querySelector('[data-viewer-img]');
	const vZoom = viewer.querySelector('[data-viewer-zoom]');
	const vDeep = viewer.querySelector('[data-viewer-deep]');
	const vZoombar = viewer.querySelector('[data-viewer-zoombar]');
	const vInfo = viewer.querySelector('[data-viewer-info]');
	let osdLoading = null;
	let osd = null;
	let zooming = false;
	let vIndex = -1;
	let vList = null;
	let lastFocus = null;

	// Deep zoom: OpenSeadragon with the largest size (2048 px, _k) as a simple image source.
	function loadOsd() {
		if (window.OpenSeadragon) return Promise.resolve();
		if (!osdLoading) {
			osdLoading = new Promise(function (resolve, reject) {
				const script = document.createElement('script');
				script.src = 'static/vendor/openseadragon/openseadragon.min.js';
				script.onload = resolve;
				script.onerror = reject;
				document.head.appendChild(script);
			});
		}
		return osdLoading;
	}
	function enterZoom() {
		const p = vList && vList[vIndex];
		if (!p || !vDeep) return;
		loadOsd().then(function () {
			if (vList[vIndex] !== p) return;
			vDeep.hidden = false;
			vZoombar.hidden = false;
			vZoom.hidden = true;
			zooming = true;
			if (!osd) {
				osd = window.OpenSeadragon({
					element: vDeep.querySelector('[data-viewer-osd]'),
					showNavigationControl: false,
					visibilityRatio: 1,
					minZoomImageRatio: 0.9,
					maxZoomPixelRatio: 2,
					gestureSettingsMouse: { clickToZoom: true, scrollToZoom: true },
					crossOriginPolicy: false,
				});
				osd.addHandler('open-failed', exitZoom);
			}
			osd.open({ type: 'image', url: urlOf(p, 'k') });
		}).catch(function () { /* the photo stays as it is */ });
	}
	function exitZoom() {
		if (!zooming) return;
		zooming = false;
		if (osd) osd.close();
		vDeep.hidden = true;
		vZoombar.hidden = true;
		vZoom.hidden = false;
	}
	vZoom.addEventListener('click', function (event) { event.preventDefault(); enterZoom(); });
	vZoombar.addEventListener('click', function (event) {
		const b = event.target.closest('[data-zoom]');
		if (!b || !osd) return;
		if (b.dataset.zoom === 'in') osd.viewport.zoomBy(1.6);
		else if (b.dataset.zoom === 'out') osd.viewport.zoomBy(1 / 1.6);
		else if (b.dataset.zoom === 'home') osd.viewport.goHome();
		else if (b.dataset.zoom === 'back') exitZoom();
		if (osd && b.dataset.zoom !== 'back') osd.viewport.applyConstraints();
	});

	// The details (description, EXIF) - data/details/NN.json, NN = the id's last two digits.
	const detailFiles = {};
	function detailsOf(id) {
		const key = ('0' + id).slice(-2);
		if (!detailFiles[key]) {
			detailFiles[key] = fetch('data/details/' + key + '.json')
				.then(function (r) { return r.ok ? r.json() : {}; })
				.catch(function () { return {}; });
		}
		return detailFiles[key].then(function (all) { return all[id] || {}; });
	}

	// Flickr's descriptions are HTML: only links and simple formatting are kept.
	function safeHtml(html) {
		const doc = new DOMParser().parseFromString('<div>' + html.replace(/\n/g, '<br>') + '</div>', 'text/html');
		const out = el('div', 'fx-v-desc');
		(function copy(from, to) {
			from.childNodes.forEach(function (n) {
				if (n.nodeType === 3) { to.appendChild(document.createTextNode(n.textContent)); return; }
				if (n.nodeType !== 1) return;
				const tag = n.tagName.toLowerCase();
				let node;
				if (tag === 'a' && /^https?:/i.test(n.getAttribute('href') || '')) {
					node = el('a');
					node.href = n.getAttribute('href');
					node.target = '_blank';
					node.rel = 'noopener nofollow';
				} else if (tag === 'br') {
					to.appendChild(el('br'));
					return;
				} else if (['b', 'strong', 'i', 'em'].indexOf(tag) >= 0) {
					node = el(tag);
				} else {
					node = document.createDocumentFragment();
				}
				copy(n, node);
				to.appendChild(node);
			});
		})(doc.body.firstChild, out);
		return out;
	}

	const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
	function dateOf(p) {
		if (!p.taken) return '';
		const y = p.taken.slice(0, 4);
		const m = parseInt(p.taken.slice(5, 7), 10);
		const d = parseInt(p.taken.slice(8, 10), 10);
		// Flickr's granularity: 0 = the exact time, 4 = the month, 6 = the year, 8 = circa.
		if (p.granularity === 8) return tr('circa', { year: y });
		if (p.granularity === 6) return y;
		if (p.granularity === 4) return MONTHS[m - 1] + ' ' + y;
		return MONTHS[m - 1] + ' ' + d + ', ' + y;
	}

	function row(dl, term, node) {
		if (!node) return;
		dl.appendChild(el('dt', null, term));
		const dd = el('dd');
		if (typeof node === 'string') dd.textContent = node; else dd.appendChild(node);
		dl.appendChild(dd);
	}
	function filterButton(key, value, text, cls) {
		const b = el('button', cls || null, text);
		b.type = 'button';
		b.dataset.filter = key;
		b.dataset.value = value;
		return b;
	}

	function showDetail(p) {
		vInfo.innerHTML = '';
		if (p.taken) vInfo.appendChild(el('p', 'fx-v-year', dateOf(p)));
		vInfo.appendChild(el('h2', null, p.title || tr('untitled')));
		if (BM.available) {
			const star = starButton(p, 'fx-v-star');
			star.textContent = '';
			star.appendChild(el('span', 'fx-v-star__icon', '★'));
			star.appendChild(el('span', 'fx-v-star__label', ''));
			showStar(star);
			vInfo.appendChild(star);
		}
		const descSlot = el('div');
		vInfo.appendChild(descSlot);
		const dl = el('dl');
		if (p.themes.length || p.albums.length) {
			const box = el('div', 'fx-v-tags');
			p.themes.forEach(function (t) { box.appendChild(filterButton('theme', t, (FX.themes || {})[t] || t, 'is-theme')); });
			row(dl, tr('v_themes'), p.themes.length ? box : null);
			if (p.albums.length) {
				const ab = el('div', 'fx-v-tags');
				p.albums.forEach(function (a) {
					const meta = (FX.albums || {})[a] || {};
					ab.appendChild(filterButton(meta.type === 'place' ? 'place' : 'album', a, meta.title || a));
				});
				row(dl, tr('v_albums'), ab);
			}
		}
		if (p.tags.length) {
			const tags = el('div', 'fx-v-tags');
			p.tags.slice(0, 30).forEach(function (t) { tags.appendChild(filterButton('q', t, t)); });
			row(dl, tr('v_tags'), tags);
		}
		if (p.lat != null) {
			const links = el('div', 'fx-v-links');
			const near = el('button', null, tr('v_onmap'));
			near.type = 'button';
			near.addEventListener('click', function () {
				closeViewer();
				state.filters = { geo: '1' };
				state.pin = p.id;
				reload(true);
				setTimeout(function () { if (map) map.setView([p.lat, p.lon], 14); }, 400);
			});
			links.appendChild(near);
			const osm = el('a', null, tr('v_osm'));
			osm.href = 'https://www.openstreetmap.org/?mlat=' + p.lat + '&mlon=' + p.lon + '#map=15/' + p.lat + '/' + p.lon;
			osm.target = '_blank';
			osm.rel = 'noopener';
			links.appendChild(osm);
			row(dl, tr('v_place'), links);
		}
		const camSlot = el('div');
		if (p.camera || p.lens) {
			const box = el('div', 'fx-v-tags');
			if (p.camera) box.appendChild(filterButton('camera', p.camera, GEAR.cameras[p.camera] || p.camera));
			if (p.lens) box.appendChild(filterButton('lens', p.lens, GEAR.lenses[p.lens] || p.lens));
			row(dl, tr('v_camera'), box);
		}
		dl.appendChild(camSlot);
		const lic = (FX.licenses || {})[p.license] || [p.license, ''];
		const licNode = el('div');
		const licName = lic[1] ? el('a', null, lic[0]) : el('span', null, lic[0]);
		if (lic[1]) { licName.href = lic[1]; licName.target = '_blank'; licName.rel = 'noopener license'; }
		licNode.appendChild(licName);
		if (p.license === '0') {
			licName.textContent = '© ' + lic[0];
			licName.classList.add('is-rights');
			licNode.appendChild(el('p', 'fx-v-rights', tr('v_rights')));
		}
		row(dl, tr('v_license'), licNode);
		const stats = [p.views === 1 ? tr('v_view') : tr('v_views', { count: fmt(p.views) }), p.faves === 1 ? tr('v_fave') : tr('v_faves', { count: fmt(p.faves) })];
		if (p.comments) stats.push(p.comments === 1 ? tr('v_comment') : tr('v_comments', { count: fmt(p.comments) }));
		row(dl, tr('v_stats'), stats.join(' · '));
		vInfo.appendChild(dl);
		const flickr = el('a', 'fx-v-link fx-v-flickr', tr('v_flickr'));
		flickr.href = 'https://www.flickr.com/photos/' + (FX.user || 'ulfbodin') + '/' + p.id + '/';
		flickr.target = '_blank';
		flickr.rel = 'noopener';
		vInfo.appendChild(flickr);

		detailsOf(p.id).then(function (d) {
			if (!vList || vList[vIndex] !== p) return;
			if (d.description) descSlot.appendChild(safeHtml(d.description));
			const e = d.exif || {};
			// The focal length - with the full-frame equivalent for a smaller sensor.
			const crop = GEAR.crop[p.camera] || 1;
			const focalText = e.focal ? e.focal + (crop !== 1 && p.eq ? ' (' + p.eq + ' mm ' + tr('equiv') + ')' : '') : null;
			const settings = [focalText, e.aperture, e.exposure ? (/s/.test(e.exposure) ? e.exposure : e.exposure + ' s') : null, e.iso ? 'ISO ' + e.iso : null].filter(Boolean);
			if (settings.length) {
				camSlot.appendChild(el('dt', null, tr('v_settings')));
				camSlot.appendChild(el('dd', null, settings.join(' · ')));
				camSlot.style.display = 'contents';
			}
		});
	}

	function openViewer(index) {
		vList = state.items;
		vIndex = index;
		show();
	}
	function openSingle(id) {
		const p = DATA.byId[id];
		if (!p) return;
		vList = [p];
		vIndex = 0;
		show();
	}

	function show() {
		const item = vList[vIndex];
		if (!item) return;
		if (viewer.hidden) {
			lastFocus = document.activeElement;
			viewer.hidden = false;
			document.documentElement.style.overflow = 'hidden';
			viewer.querySelector('[data-viewer-close]').focus();
		}
		exitZoom();
		vImg.src = urlOf(item, 'b');
		vImg.alt = item.title || '';
		viewer.querySelector('[data-viewer-prev]').hidden = vIndex <= 0;
		viewer.querySelector('[data-viewer-next]').hidden = vList.length < 2 || (vIndex >= vList.length - 1 && (vList !== state.items || state.done));
		showDetail(item);
		// Near the end of what is shown: the next page of the wall.
		if (vList === state.items && vIndex > state.items.length - 6) load();
	}

	function step(delta) {
		if (!vList) return;
		const next = vIndex + delta;
		if (next < 0 || next >= vList.length) return;
		vIndex = next;
		show();
	}

	function closeViewer() {
		if (viewer.hidden) return;
		exitZoom();
		viewer.hidden = true;
		vImg.removeAttribute('src');
		document.documentElement.style.overflow = '';
		if (lastFocus) lastFocus.focus({ preventScroll: true });
	}

	viewer.querySelector('[data-viewer-close]').addEventListener('click', closeViewer);
	viewer.querySelector('[data-viewer-prev]').addEventListener('click', function () { step(-1); });
	viewer.querySelector('[data-viewer-next]').addEventListener('click', function () { step(1); });
	viewer.addEventListener('click', function (event) { if (event.target === viewer || event.target.classList.contains('fx-viewer__figure')) closeViewer(); });
	document.addEventListener('keydown', function (event) {
		if (viewer.hidden) return;
		if (event.key === 'Escape') { if (zooming) exitZoom(); else closeViewer(); }
		else if (zooming) return;
		else if (event.key === 'ArrowRight') step(1);
		else if (event.key === 'ArrowLeft') step(-1);
	});

	// --- start: the labels, the bookmarks, the data -----------------------------------------------
	document.querySelectorAll('[data-filter][data-label]').forEach(function (b) {
		state.labels[b.dataset.filter + ':' + b.dataset.value] = b.dataset.label;
	});
	syncControls();
	statusEl.textContent = tr('loading');
	const bmReady = BM.available ? BM.load().catch(function () { BM.available = false; }) : Promise.resolve();
	const dataReady = fetch('data/photos.json').then(function (r) {
		if (!r.ok) throw new Error(r.status);
		return r.json();
	}).then(decode);
	Promise.all([dataReady, bmReady]).then(function () {
		statusEl.textContent = '';
		// Opened with choices in the address (a link to the map, a year, an album …): straight to the archive.
		const linked = Object.keys(state.filters).length > 0 || window.location.hash === '#archive';
		reload(false);
		if (linked) archive.scrollIntoView({ block: 'start' });
		if (state.filters.geo) window.addEventListener('load', function () { showMap(true); });
	}).catch(function (err) {
		if (window.console) console.error('archive: photos.json', err);
		statusEl.textContent = tr('failed');
	});
})();
