'use strict';

const crypto = require('crypto');

const FRESHNESS_WINDOW_SECONDS = 30;

function hmacHex(key, message) {
    return crypto.createHmac('sha256', key).update(message).digest('hex');
}

function timingSafeEqualHex(a, b) {
    const bufA = Buffer.from(a, 'hex');
    const bufB = Buffer.from(b, 'hex');
    if (bufA.length !== bufB.length) return false;
    return crypto.timingSafeEqual(bufA, bufB);
}

// Vercel's body parser sets req.body = {} for GET/DELETE even with no payload sent;
// treat an empty object the same as no body so client/server agree on the hash input.
function bodyStringOf(req) {
    const body = req.body;
    if (body === undefined || body === null) return null;
    if (typeof body === 'string') {
        if (body === '' || body === '{}') return null;
        return body;
    }
    if (typeof body === 'object') {
        if (Object.keys(body).length === 0) return null;
        return JSON.stringify(body);
    }
    return null;
}

async function verifySignedRequest(req, supabase) {
    const token = req.headers['x-request-token'];
    const ts = req.headers['x-request-ts'];
    const keyIdHeader = req.headers['x-key-id'];
    const authHeader = req.headers['authorization'];

    if (!token || !ts) {
        return { valid: false, reason: 'missing_headers' };
    }

    const bearerToken = authHeader && authHeader.startsWith('Bearer ')
        ? authHeader.slice('Bearer '.length)
        : null;
    const sessionToken = bearerToken || keyIdHeader;
    if (!sessionToken) {
        return { valid: false, reason: 'missing_key_id' };
    }

    const tsNum = Number(ts);
    if (!Number.isFinite(tsNum)) {
        return { valid: false, reason: 'invalid_timestamp' };
    }
    const nowSeconds = Math.floor(Date.now() / 1000);
    if (Math.abs(nowSeconds - tsNum) > FRESHNESS_WINDOW_SECONDS) {
        return { valid: false, reason: 'stale_timestamp' };
    }

    const { data: keyRow, error: keyErr } = await supabase
        .from('uwu_signing_keys')
        .select('signing_key, expires_at, session_token')
        .eq('session_token', sessionToken)
        .maybeSingle();

    if (keyErr || !keyRow) {
        return { valid: false, reason: 'unknown_key' };
    }
    if (new Date(keyRow.expires_at).getTime() < Date.now()) {
        return { valid: false, reason: 'expired_key' };
    }

    const method = req.method.toUpperCase();
    const path = (req.url || '').split('?')[0];
    const bodyStr = bodyStringOf(req);
    const bodyHash = bodyStr === null ? 'empty' : hmacHex(keyRow.signing_key, bodyStr);

    const message = `${tsNum}:${method}:${path}:${bodyHash}`;
    const expectedToken = hmacHex(keyRow.signing_key, message);

    let signatureOk;
    try {
        signatureOk = timingSafeEqualHex(token, expectedToken);
    } catch (_) {
        signatureOk = false;
    }
    if (!signatureOk) {
        return { valid: false, reason: 'bad_signature' };
    }

    const { data: usedRow } = await supabase
        .from('uwu_used_request_tokens')
        .select('token')
        .eq('token', token)
        .maybeSingle();
    if (usedRow) {
        return { valid: false, reason: 'replayed' };
    }

    const { error: insertErr } = await supabase
        .from('uwu_used_request_tokens')
        .insert({ token, session_token: sessionToken, used_at: new Date().toISOString() });
    if (insertErr) {
        // unique violation on token means a concurrent request already claimed it — treat as replay
        return { valid: false, reason: 'replayed' };
    }

    return { valid: true, reason: 'ok' };
}

module.exports = { verifySignedRequest };
