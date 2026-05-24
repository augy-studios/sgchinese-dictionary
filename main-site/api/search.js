// api/search.js

'use strict';

const {
    createClient
} = require('@supabase/supabase-js');

// Available letter-suffixed tables
const AVAILABLE_LETTERS = [
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k',
    'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z'
];

// Pinyin tone → base letter map
const TONE_MAP = {
    'ā': 'a',
    'á': 'a',
    'ǎ': 'a',
    'à': 'a',
    'ē': 'e',
    'é': 'e',
    'ě': 'e',
    'è': 'e',
    'ī': 'i',
    'í': 'i',
    'ǐ': 'i',
    'ì': 'i',
    'ō': 'o',
    'ó': 'o',
    'ǒ': 'o',
    'ò': 'o',
    'ū': 'u',
    'ú': 'u',
    'ǔ': 'u',
    'ù': 'u',
    'ǖ': 'v',
    'ǘ': 'v',
    'ǚ': 'v',
    'ǜ': 'v',
    'ü': 'v',
};

function normalisePinyin(str) {
    return str.replace(/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]/gi,
        ch => TONE_MAP[ch.toLowerCase()] || ch
    ).toLowerCase();
}

// Expands each bare vowel into a character class that matches all tonal variants.
// e.g. "jie" → "ji[eēéěè]", "a jie" → "[aāáǎà] ji[eēéěè]"
const ACCENT_CLASS = {
    a: '[aāáǎà]',
    e: '[eēéěè]',
    i: '[iīíǐì]',
    o: '[oōóǒò]',
    u: '[uūúǔù]',
    v: '[vüǖǘǚǜ]',
};

function buildPinyinRegex(query) {
    const norm = normalisePinyin(query);
    // Escape regex metacharacters (but NOT brackets — we're about to add them)
    const escaped = norm.replace(/[.+*?^${}()|[\]\\]/g, '\\$&');
    return escaped.replace(/[aeiouv]/g, ch => ACCENT_CLASS[ch] || ch);
}

function detectQueryType(q) {
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(q)) return 'chinese';
    if (/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]/i.test(q)) return 'pinyin';
    // Pure alphabetic — could be pinyin syllable or english word
    // We treat it as ambiguous and search both
    return 'ambiguous';
}

function getSortColumns(sort) {
    // Returns [column, ascending]
    switch (sort) {
        case 'hypy_asc':
            return [{
                col: 'hanyupinyin',
                asc: true
            }];
        case 'hypy_desc':
            return [{
                col: 'hanyupinyin',
                asc: false
            }];
        case 'en_asc':
            return [{
                col: 'translation',
                asc: true
            }];
        case 'en_desc':
            return [{
                col: 'translation',
                asc: false
            }];
        default:
            return [{
                col: 'hanyupinyin',
                asc: true
            }];
    }
}

// Determine which tables to query based on query type
function getTablesToQuery(q, queryType) {
    // All searches use ilike '%query%' (substring match), so a query like "jie"
    // can match entries in any table (e.g. "ā jiě" is in sgchn_a, not sgchn_j).
    // Always query all tables.
    return AVAILABLE_LETTERS;
}

module.exports = async function handler(req, res) {
    // CORS
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    if (req.method === 'OPTIONS') {
        res.status(200).end();
        return;
    }
    if (req.method !== 'GET') {
        res.status(405).json({
            error: 'Method not allowed'
        });
        return;
    }

    const {
        q = '', sort = 'hypy_asc', offset = '0', limit = '30'
    } = req.query;

    const query = q.trim();

    const pageOffset = Math.max(0, parseInt(offset, 10) || 0);
    const pageLimit = Math.min(100, Math.max(1, parseInt(limit, 10) || 30));

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_KEY;

    if (!supabaseUrl || !supabaseKey) {
        return res.status(500).json({
            error: 'Supabase env vars not set'
        });
    }

    const supabase = createClient(supabaseUrl, supabaseKey);
    const queryType = query ? detectQueryType(query) : 'all';
    const tables = query ? getTablesToQuery(query, queryType) : AVAILABLE_LETTERS;
    const sortCols = getSortColumns(sort);

    try {
        // Collect all matching rows across relevant tables with COUNT
        // We do this with parallel queries for speed

        const normQ = normalisePinyin(query);

        const tableResults = await Promise.all(
            tables.map(letter => {
                const table = `sgchn_${letter}`;
                let qb = supabase.from(table).select('hanyupinyin, chinese, translation', {
                    count: 'exact'
                });

                if (queryType === 'chinese') {
                    qb = qb.ilike('chinese', `%${query}%`);
                } else if (queryType === 'pinyin') {
                    // imatch = case-insensitive regex; expands e→[eēéěè] etc.
                    qb = qb.filter('hanyupinyin', 'imatch', buildPinyinRegex(query));
                } else if (queryType === 'ambiguous') {
                    const pinyinPattern = buildPinyinRegex(query);
                    qb = qb.or(
                        `hanyupinyin.imatch.${pinyinPattern},translation.ilike.%${query}%`
                    );
                }
                // queryType === 'all': no filter — fetch everything

                // Apply sort (no limit/offset here — we aggregate first)
                return qb;
            })
        );

        // Merge and de-duplicate
        const allRows = [];
        const seen = new Set();

        for (const {
                data,
                error
            } of tableResults) {
            if (error) {
                console.error('Supabase error:', error.message);
                continue;
            }
            if (!data) continue;
            for (const row of data) {
                const key = `${row.chinese}__${row.hanyupinyin}`;
                if (!seen.has(key)) {
                    seen.add(key);
                    allRows.push(row);
                }
            }
        }

        // Total before pagination
        const total = allRows.length;

        // Sort merged results
        const {
            col,
            asc
        } = sortCols[0];
        allRows.sort((a, b) => {
            const av = (a[col] || '').toLowerCase();
            const bv = (b[col] || '').toLowerCase();
            // For pinyin sort, normalise
            const an = col === 'hanyupinyin' ? normalisePinyin(av) : av;
            const bn = col === 'hanyupinyin' ? normalisePinyin(bv) : bv;
            if (an < bn) return asc ? -1 : 1;
            if (an > bn) return asc ? 1 : -1;
            return 0;
        });

        // Paginate
        const pageRows = allRows.slice(pageOffset, pageOffset + pageLimit);

        return res.status(200).json({
            results: pageRows,
            total,
            queryType,
        });

    } catch (err) {
        console.error('Search error:', err);
        return res.status(500).json({
            error: 'Internal server error'
        });
    }
};