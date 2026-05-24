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

// Determine which tables to query based on query type and first letter(s)
function getTablesToQuery(q, queryType) {
    if (queryType === 'chinese') {
        // Chinese search can be in any table — query all
        return AVAILABLE_LETTERS;
    }

    if (queryType === 'pinyin' || queryType === 'ambiguous') {
        // Try to narrow by first letter of pinyin
        const normalised = normalisePinyin(q);
        const firstChar = normalised[0];
        if (AVAILABLE_LETTERS.includes(firstChar)) {
            return [firstChar];
        }
        // fallback: all
        return AVAILABLE_LETTERS;
    }

    // English — query all tables
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
    if (!query) {
        return res.status(200).json({
            results: [],
            total: 0,
            queryType: 'none'
        });
    }

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
    const queryType = detectQueryType(query);
    const tables = getTablesToQuery(query, queryType);
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
                    // Exact or partial Chinese character match
                    qb = qb.ilike('chinese', `%${query}%`);
                } else if (queryType === 'pinyin') {
                    // Match with and without tone marks
                    // We store both original and check normalised via ilike
                    qb = qb.or(`hanyupinyin.ilike.%${query}%,hanyupinyin.ilike.%${normQ}%`);
                } else {
                    // Ambiguous: search pinyin OR translation
                    qb = qb.or(
                        `hanyupinyin.ilike.%${normQ}%,translation.ilike.%${query}%`
                    );
                }

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