'use strict';

const crypto = require('crypto');
const { createClient } = require('@supabase/supabase-js');

const GUEST_TTL_MS = 10 * 60 * 1000;

function isAllowedOrigin(origin) {
    if (!origin) return true; // same-origin requests often arrive with no Origin header, so allow
    const allowed = (process.env.ALLOWED_ORIGINS || '').split(',').map(o => o.trim()).filter(Boolean);
    return allowed.includes(origin);
}

module.exports = async function handler(req, res) {
    const origin = req.headers.origin;
    res.setHeader('Access-Control-Allow-Origin', origin || '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
    if (req.method === 'OPTIONS') { res.status(200).end(); return; }
    if (req.method !== 'GET') { res.status(405).json({ error: 'Method not allowed' }); return; }

    if (!isAllowedOrigin(origin)) {
        return res.status(403).json({ error: 'Origin not allowed' });
    }

    const supabaseUrl = process.env.SUPABASE_URL;
    const supabaseKey = process.env.SUPABASE_SERVICE_KEY;
    if (!supabaseUrl || !supabaseKey) {
        return res.status(500).json({ error: 'Supabase env vars not set' });
    }

    const appId = (req.query.app_id || 'unknown').toString();
    const signingKey = crypto.randomBytes(32).toString('hex');
    const sessionToken = crypto.randomUUID();
    const expiresAt = new Date(Date.now() + GUEST_TTL_MS).toISOString();

    const supabase = createClient(supabaseUrl, supabaseKey);

    try {
        const { error } = await supabase.from('uwu_signing_keys').insert({
            session_token: sessionToken,
            signing_key: signingKey,
            is_guest: true,
            app_id: appId,
            expires_at: expiresAt,
        });
        if (error) {
            console.error('guest-key insert error:', error.message);
            return res.status(500).json({ error: 'Internal server error' });
        }

        return res.status(200).json({ key_id: sessionToken, signing_key: signingKey });
    } catch (err) {
        console.error('guest-key error:', err);
        return res.status(500).json({ error: 'Internal server error' });
    }
};
