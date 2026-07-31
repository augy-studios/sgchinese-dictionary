'use strict';

// ── Constants

const PAGE_SIZE = 30;

const AVAILABLE_LETTERS = [
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k',
    'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z'
];

const TONE_MAP = {
    'ā': 'a', 'á': 'a', 'ǎ': 'a', 'à': 'a',
    'ē': 'e', 'é': 'e', 'ě': 'e', 'è': 'e',
    'ī': 'i', 'í': 'i', 'ǐ': 'i', 'ì': 'i',
    'ō': 'o', 'ó': 'o', 'ǒ': 'o', 'ò': 'o',
    'ū': 'u', 'ú': 'u', 'ǔ': 'u', 'ù': 'u',
    'ǖ': 'v', 'ǘ': 'v', 'ǚ': 'v', 'ǜ': 'v', 'ü': 'v',
    'Ā': 'A', 'Á': 'A', 'Ǎ': 'A', 'À': 'A',
    'Ē': 'E', 'É': 'E', 'Ě': 'E', 'È': 'E',
    'Ī': 'I', 'Í': 'I', 'Ǐ': 'I', 'Ì': 'I',
    'Ō': 'O', 'Ó': 'O', 'Ǒ': 'O', 'Ò': 'O',
    'Ū': 'U', 'Ú': 'U', 'Ǔ': 'U', 'Ù': 'U',
};

function normalisePinyin(str) {
    return str.replace(/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜüÀÁĀǍÈÉĒĚÌÍĪǏÒÓŌǑÙÚŪǓ]/g,
        ch => TONE_MAP[ch] || ch
    ).toLowerCase();
}

function detectQueryType(q) {
    if (/[一-鿿㐀-䶿＀-￯]/.test(q)) return 'chinese';
    const normalised = normalisePinyin(q);
    const looksLikePinyin = /^[a-z\s0-9]+$/i.test(normalised) && /[aeiouv]/i.test(normalised);
    if (/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]/i.test(q)) return 'pinyin';
    return looksLikePinyin ? 'ambiguous' : 'english';
}

// ── State

const state = {
    query: '',
    sort: 'hypy_asc',
    page: 1,
    total: 0,
    loading: false,
    debounceTimer: null,
};

// ── DOM Refs

const searchInput    = document.getElementById('searchInput');
const clearBtn       = document.getElementById('clearBtn');
const sortSelect     = document.getElementById('sortSelect');
const resultsGrid    = document.getElementById('resultsGrid');
const statusBar      = document.getElementById('statusBar');
const paginationWrap = document.getElementById('paginationWrap');
const prevBtn        = document.getElementById('prevBtn');
const nextBtn        = document.getElementById('nextBtn');
const pageIndicator  = document.getElementById('pageIndicator');
const emptyState     = document.getElementById('emptyState');
const emptySubText   = document.getElementById('emptySubText');
const loaderWrap     = document.getElementById('loaderWrap');

// Theme lives in js/theme.js and boots itself.

// ── Search

searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    clearBtn.hidden = q.length === 0;
    clearTimeout(state.debounceTimer);
    state.debounceTimer = setTimeout(() => {
        state.query = q;
        state.page = 1;
        fetchResults();
    }, 350);
});

clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.hidden = true;
    state.query = '';
    state.page = 1;
    fetchResults();
    searchInput.focus();
});

sortSelect.addEventListener('change', () => {
    state.sort = sortSelect.value;
    state.page = 1;
    fetchResults();
});

prevBtn.addEventListener('click', () => {
    if (state.page > 1) {
        state.page--;
        fetchResults();
        resultsGrid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
});

nextBtn.addEventListener('click', () => {
    const totalPages = Math.ceil(state.total / PAGE_SIZE);
    if (state.page < totalPages) {
        state.page++;
        fetchResults();
        resultsGrid.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
});

resultsGrid.addEventListener('click', e => {
    const btn = e.target.closest('.btn-copy');
    if (!btn) return;
    const text = [btn.dataset.chinese, btn.dataset.pinyin, btn.dataset.translation]
        .filter(Boolean).join('\n');
    navigator.clipboard.writeText(text).then(() => {
        btn.classList.add('copied');
        btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true">
          <polyline points="20 6 9 17 4 12" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>`;
        setTimeout(() => {
            btn.classList.remove('copied');
            btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true">
              <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2"/>
            </svg>`;
        }, 1500);
    });
});

// ── Fetch

async function fetchResults() {
    if (state.loading) return;
    state.loading = true;

    setLoading(true);
    resultsGrid.innerHTML = '';
    emptyState.hidden = true;
    paginationWrap.hidden = true;
    statusBar.textContent = '';

    const offset = (state.page - 1) * PAGE_SIZE;
    const params = new URLSearchParams({
        q: state.query,
        sort: state.sort,
        offset,
        limit: PAGE_SIZE,
    });

    try {
        const res = await UwuRequestSigning.signedFetch(`/api/search?${params}`);
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        const { results, total, queryType } = await res.json();

        state.total = total;

        renderResults(results, queryType);
        updateStatusBar(total, queryType);
        updatePagination();
    } catch (err) {
        try {
            const { results, total, queryType } = await searchOffline(state.query, state.sort, offset, PAGE_SIZE);
            state.total = total;
            renderResults(results, queryType);
            updateStatusBar(total, queryType);
            updatePagination();
            const base = statusBar.textContent;
            statusBar.textContent = base ? `${base} · offline` : 'offline';
        } catch (offlineErr) {
            console.error(err);
            statusBar.textContent = 'Something went wrong. Please try again.';
        }
    } finally {
        state.loading = false;
        setLoading(false);
    }
}

// ── Render

function renderResults(results, queryType) {
    if (results.length === 0) {
        emptyState.hidden = false;
        emptySubText.textContent = state.query
            ? `No matches found for "${state.query}". Try a different spelling or term.`
            : 'No entries found in the dictionary.';
        return;
    }

    const q = state.query;

    results.forEach((entry, i) => {
        const card = document.createElement('div');
        card.className = 'entry-card glass';
        card.setAttribute('role', 'listitem');
        card.style.animationDelay = `${i * 25}ms`;

        card.innerHTML = `
      <button class="btn-copy" aria-label="Copy entry"
        data-chinese="${escapeHtml(entry.chinese || '')}"
        data-pinyin="${escapeHtml(entry.hanyupinyin || '')}"
        data-translation="${escapeHtml(entry.translation || '')}">
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" width="16" height="16" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2"/>
        </svg>
      </button>
      <div class="entry-chinese">${highlightMatch(entry.chinese || '', q, 'chinese')}</div>
      <div class="entry-pinyin">${highlightMatch(entry.hanyupinyin || '', q, 'pinyin')}</div>
      <div class="entry-translation">${highlightMatch(entry.translation || '', q, 'english')}</div>
    `;

        resultsGrid.appendChild(card);
    });
}

function highlightMatch(text, query, field) {
    if (!query || !text) return escapeHtml(text);

    try {
        if (field === 'pinyin') {
            const normText = normalisePinyin(text);
            const normQ = normalisePinyin(query);
            const idx = normText.indexOf(normQ);
            if (idx >= 0) {
                return escapeHtml(text.substring(0, idx)) +
                    '<mark>' + escapeHtml(text.substring(idx, idx + query.length)) + '</mark>' +
                    escapeHtml(text.substring(idx + query.length));
            }
        } else {
            const lower = text.toLowerCase();
            const lowerQ = query.toLowerCase();
            const idx = lower.indexOf(lowerQ);
            if (idx >= 0) {
                return escapeHtml(text.substring(0, idx)) +
                    '<mark>' + escapeHtml(text.substring(idx, idx + query.length)) + '</mark>' +
                    escapeHtml(text.substring(idx + query.length));
            }
        }
    } catch (_) {}

    return escapeHtml(text);
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function updateStatusBar(total, queryType) {
    if (!state.query) {
        statusBar.textContent = total === 0 ? '' : `${total.toLocaleString()} entr${total !== 1 ? 'ies' : 'y'} in dictionary`;
        return;
    }
    const typeLabel = {
        chinese: 'Chinese characters',
        pinyin: 'Hanyu Pinyin',
        english: 'English',
        ambiguous: 'Pinyin / English',
    }[queryType] || '';
    statusBar.textContent = total === 0
        ? `No results found`
        : `${total.toLocaleString()} result${total !== 1 ? 's' : ''} found${typeLabel ? ` · searched by ${typeLabel}` : ''}`;
}

function updatePagination() {
    const totalPages = Math.ceil(state.total / PAGE_SIZE);
    if (totalPages <= 1) {
        paginationWrap.hidden = true;
        return;
    }
    paginationWrap.hidden = false;
    pageIndicator.textContent = `Page ${state.page} of ${totalPages}`;
    prevBtn.disabled = state.page <= 1;
    nextBtn.disabled = state.page >= totalPages;
}

// ── UI States

function setLoading(on) {
    loaderWrap.hidden = !on;
}

// ── Offline Cache (IndexedDB)

const IDB_NAME = 'sgchn-dict-offline';
const IDB_VERSION = 1;
const IDB_STORE = 'entries';
const PREFETCH_BATCH = 100;
const PREFETCH_TTL_MS = 60 * 60 * 1000; // re-prefetch if data is older than 1 hour

let _idbPromise = null;

function openIDB() {
    if (_idbPromise) return _idbPromise;
    _idbPromise = new Promise((resolve, reject) => {
        const req = indexedDB.open(IDB_NAME, IDB_VERSION);
        req.onupgradeneeded = e => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(IDB_STORE)) {
                db.createObjectStore(IDB_STORE, { keyPath: '_key' });
            }
        };
        req.onsuccess = e => resolve(e.target.result);
        req.onerror = e => { _idbPromise = null; reject(e.target.error); };
    });
    return _idbPromise;
}

async function idbPutAll(entries) {
    const db = await openIDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(IDB_STORE, 'readwrite');
        const store = tx.objectStore(IDB_STORE);
        entries.forEach(e => store.put(e));
        tx.oncomplete = resolve;
        tx.onerror = e => reject(e.target.error);
    });
}

async function idbGetAll() {
    const db = await openIDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(IDB_STORE, 'readonly');
        const req = tx.objectStore(IDB_STORE).getAll();
        req.onsuccess = () => resolve(req.result);
        req.onerror = e => reject(e.target.error);
    });
}

async function idbCount() {
    const db = await openIDB();
    return new Promise((resolve, reject) => {
        const tx = db.transaction(IDB_STORE, 'readonly');
        const req = tx.objectStore(IDB_STORE).count();
        req.onsuccess = () => resolve(req.result);
        req.onerror = e => reject(e.target.error);
    });
}

async function prefetchAllEntries() {
    try {
        const lastTs = parseInt(localStorage.getItem('sgchn_prefetch_ts') || '0', 10);
        const cached = await idbCount();
        // Skip if recently prefetched and data exists; always run on online event (caller clears ts)
        if (cached > 0 && Date.now() - lastTs < PREFETCH_TTL_MS) return;

        const res = await UwuRequestSigning.signedFetch('/api/all');
        if (!res.ok) return;
        const { entries } = await res.json();
        if (!entries || !entries.length) return;

        const keyed = entries.map(e => ({ ...e, _key: `${e.chinese}__${e.hanyupinyin}` }));
        for (let i = 0; i < keyed.length; i += PREFETCH_BATCH) {
            await idbPutAll(keyed.slice(i, i + PREFETCH_BATCH));
        }
        localStorage.setItem('sgchn_prefetch_ts', String(Date.now()));
    } catch (_) {}
}

async function searchOffline(query, sort, offset, limit) {
    const all = await idbGetAll();
    const queryType = detectQueryType(query);
    const q = query.trim();

    let filtered;
    if (!q) {
        filtered = all;
    } else if (queryType === 'chinese') {
        filtered = all.filter(e => e.chinese && e.chinese.includes(q));
    } else if (queryType === 'pinyin') {
        const normQ = normalisePinyin(q);
        filtered = all.filter(e => e.hanyupinyin && normalisePinyin(e.hanyupinyin).includes(normQ));
    } else if (queryType === 'ambiguous') {
        const normQ = normalisePinyin(q);
        const lowerQ = q.toLowerCase();
        filtered = all.filter(e =>
            (e.hanyupinyin && normalisePinyin(e.hanyupinyin).includes(normQ)) ||
            (e.translation && e.translation.toLowerCase().includes(lowerQ))
        );
    } else {
        const lowerQ = q.toLowerCase();
        filtered = all.filter(e => e.translation && e.translation.toLowerCase().includes(lowerQ));
    }

    const dirMap = { hypy_asc: ['hanyupinyin', 1], hypy_desc: ['hanyupinyin', -1], en_asc: ['translation', 1], en_desc: ['translation', -1] };
    const [field, dir] = dirMap[sort] || dirMap.hypy_asc;
    filtered.sort((a, b) => {
        const va = (a[field] || '').toLowerCase();
        const vb = (b[field] || '').toLowerCase();
        return va < vb ? -dir : va > vb ? dir : 0;
    });

    return { results: filtered.slice(offset, offset + limit), total: filtered.length, queryType };
}

// ── PWA Service Worker

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').catch(err => {
            console.warn('SW registration failed:', err);
        });
        if (navigator.onLine) guestKeyReady.then(prefetchAllEntries);
    });
}

window.addEventListener('online', () => {
    // Clear the TTL so prefetch always runs when coming back online
    localStorage.removeItem('sgchn_prefetch_ts');
    guestKeyReady.then(prefetchAllEntries);
});

// ── Init

// No login on this site, every visitor is anonymous, so a guest signing key
// is required before any signedFetch() call can succeed.
const guestKeyReady = UwuRequestSigning.initGuestKey('sg-chinese-dictionary')
    .catch(err => console.warn('Guest key init failed:', err));

guestKeyReady.then(fetchResults);
