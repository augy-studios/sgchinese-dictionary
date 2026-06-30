'use strict';

// Shared client-side request signing for UwU Apps PWAs.
// HMAC-SHA256 signed requests via SubtleCrypto. See uwu-request-signing-server.js for the server half.

(function (global) {
    const LS_KEY = 'uwu_signing_key';
    const SS_KEY = 'uwu_signing_key';

    function readEntry(storage, key) {
        try {
            const raw = storage.getItem(key);
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (parsed.expiresAt && Date.now() > parsed.expiresAt) {
                storage.removeItem(key);
                return null;
            }
            return parsed;
        } catch (_) {
            return null;
        }
    }

    // expiresAt is an internal extra used by initGuestKey to enforce the 10-min guest TTL client-side;
    // login flows only ever pass (signingKey, keyId, persistent).
    function storeSigningKey(signingKey, keyId, persistent = false, expiresAt = null) {
        const entry = JSON.stringify({ signingKey, keyId, expiresAt });
        if (persistent) {
            localStorage.setItem(LS_KEY, entry);
            sessionStorage.removeItem(SS_KEY);
        } else {
            sessionStorage.setItem(SS_KEY, entry);
            localStorage.removeItem(LS_KEY);
        }
    }

    function getSigningKey() {
        const persisted = readEntry(localStorage, LS_KEY);
        if (persisted) return { signingKey: persisted.signingKey, keyId: persisted.keyId };
        const sessioned = readEntry(sessionStorage, SS_KEY);
        if (sessioned) return { signingKey: sessioned.signingKey, keyId: sessioned.keyId };
        return null;
    }

    function clearSigningKey() {
        localStorage.removeItem(LS_KEY);
        sessionStorage.removeItem(SS_KEY);
    }

    async function initGuestKey(appId) {
        if (getSigningKey()) return;
        const res = await fetch(`/api/auth/guest-key?app_id=${encodeURIComponent(appId)}`);
        if (!res.ok) throw new Error(`Failed to obtain guest signing key: ${res.status}`);
        const { key_id, signing_key } = await res.json();
        storeSigningKey(signing_key, key_id, false, Date.now() + 10 * 60 * 1000);
    }

    async function hmacHex(key, message) {
        const enc = new TextEncoder();
        const cryptoKey = await crypto.subtle.importKey(
            'raw', enc.encode(key), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']
        );
        const sig = await crypto.subtle.sign('HMAC', cryptoKey, enc.encode(message));
        return Array.from(new Uint8Array(sig)).map(b => b.toString(16).padStart(2, '0')).join('');
    }

    function bodyStringOf(options) {
        if (!options || options.body === undefined || options.body === null) return null;
        if (typeof options.body !== 'string') return null;
        if (options.body === '' || options.body === '{}') return null;
        return options.body;
    }

    async function signedFetch(url, options = {}) {
        const stored = getSigningKey();
        if (!stored) {
            throw new Error('signedFetch: no signing key available — call initGuestKey() or log in first');
        }
        const { signingKey, keyId } = stored;

        const method = (options.method || 'GET').toUpperCase();
        const path = new URL(url, global.location.origin).pathname;
        const bodyStr = bodyStringOf(options);
        const bodyHash = bodyStr === null ? 'empty' : await hmacHex(signingKey, bodyStr);
        const ts = Math.floor(Date.now() / 1000);

        const message = `${ts}:${method}:${path}:${bodyHash}`;
        const token = await hmacHex(signingKey, message);

        const headers = new Headers(options.headers || {});
        headers.set('X-Request-Token', token);
        headers.set('X-Request-TS', String(ts));
        headers.set('X-Key-ID', keyId);

        return fetch(url, { ...options, headers });
    }

    const UwuRequestSigning = {
        storeSigningKey,
        getSigningKey,
        clearSigningKey,
        initGuestKey,
        signedFetch,
    };

    global.UwuRequestSigning = UwuRequestSigning;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = UwuRequestSigning;
    }
})(typeof window !== 'undefined' ? window : globalThis);
