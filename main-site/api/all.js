'use strict';

const { createClient } = require('@supabase/supabase-js');

const AVAILABLE_LETTERS = [
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'j', 'k',
    'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'w', 'x', 'y', 'z'
];

module.exports = async function handler(req, res) {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    if (req.method === 'OPTIONS') { res.status(200).end(); return; }
    if (req.method !== 'GET') { res.status(405).json({ error: 'Method not allowed' }); return; }

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_KEY;
    if (!supabaseUrl || !supabaseKey) {
        return res.status(500).json({ error: 'Supabase env vars not set' });
    }

    const supabase = createClient(supabaseUrl, supabaseKey);

    try {
        const tableResults = await Promise.all(
            AVAILABLE_LETTERS.map(letter =>
                supabase
                    .from(`sgchn_${letter}`)
                    .select('hanyupinyin, chinese, translation')
            )
        );

        const entries = [];
        const seen = new Set();

        for (const { data, error } of tableResults) {
            if (error) { console.error('Supabase error:', error.message); continue; }
            if (!data) continue;
            for (const row of data) {
                const key = `${row.chinese}__${row.hanyupinyin}`;
                if (!seen.has(key)) {
                    seen.add(key);
                    entries.push(row);
                }
            }
        }

        return res.status(200).json({ entries, total: entries.length });
    } catch (err) {
        console.error('All-entries error:', err);
        return res.status(500).json({ error: 'Internal server error' });
    }
};
