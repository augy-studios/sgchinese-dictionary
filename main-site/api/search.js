'use strict';

const {
    createClient
} = require('@supabase/supabase-js');
const { verifySignedRequest } = require('../lib/uwu-request-signing-server');

const AVAILABLE_LETTERS = [
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k',
    'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z'
];

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

// maps each bare vowel to a char class matching all tonal variants
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
    const escaped = norm.replace(/[.+*?^${}()|[\]\\]/g, '\\$&');
    return escaped.replace(/[aeiouv]/g, ch => ACCENT_CLASS[ch] || ch);
}

function detectQueryType(q) {
    if (/[\u4e00-\u9fff\u3400-\u4dbf]/.test(q)) return 'chinese';
    if (/[āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü]/i.test(q)) return 'pinyin';
    return 'ambiguous';
}

function getSortColumns(sort) {
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

function getTablesToQuery(q, queryType) {
    // substring match can span tables (e.g. "jie" matches "ā jiě" in sgchn_a)
    return AVAILABLE_LETTERS;
}

module.exports = async function handler(req, res) {
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

    const verification = await verifySignedRequest(req, supabase);
    if (!verification.valid) {
        return res.status(403).json({
            error: 'Invalid request signature',
            reason: verification.reason
        });
    }

    const queryType = query ? detectQueryType(query) : 'all';
    const tables = query ? getTablesToQuery(query, queryType) : AVAILABLE_LETTERS;
    const sortCols = getSortColumns(sort);

    try {
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
                    // imatch: case-insensitive regex, expands e→[eēéěè] etc.
                    qb = qb.filter('hanyupinyin', 'imatch', buildPinyinRegex(query));
                } else if (queryType === 'ambiguous') {
                    const pinyinPattern = buildPinyinRegex(query);
                    qb = qb.or(
                        `hanyupinyin.imatch.${pinyinPattern},translation.ilike.%${query}%`
                    );
                }
                // 'all': no filter, fetch everything; no limit here, sort after aggregation
                return qb;
            })
        );

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

        const total = allRows.length;

        const {
            col,
            asc
        } = sortCols[0];
        allRows.sort((a, b) => {
            const av = (a[col] || '').toLowerCase();
            const bv = (b[col] || '').toLowerCase();
            const an = col === 'hanyupinyin' ? normalisePinyin(av) : av;
            const bn = col === 'hanyupinyin' ? normalisePinyin(bv) : bv;
            if (an < bn) return asc ? -1 : 1;
            if (an > bn) return asc ? 1 : -1;
            return 0;
        });

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