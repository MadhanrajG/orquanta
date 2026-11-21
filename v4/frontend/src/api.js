/**
 * OrQuanta — Central API base URL utility
 *
 * Resolves the API base from VITE_API_BASE_URL (production env) with
 * VITE_API_URL as a fallback for backward-compat, then empty string
 * (same-origin, handled by Vite proxy in dev / FastAPI static in prod).
 */
export const API = import.meta.env.VITE_API_BASE_URL
    || import.meta.env.VITE_API_URL
    || ''

/**
 * Convenience: build an auth header object from a JWT token.
 * Usage: headers: authHeader(token)
 */
export function authHeader(token) {
    return token ? { Authorization: `Bearer ${token}` } : {}
}

/**
 * Convenience: authenticated fetch with timeout (default 10s).
 */
export async function apiFetch(path, token, options = {}, timeoutMs = 10_000) {
    const { headers = {}, ...rest } = options
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), timeoutMs)
    try {
        const res = await fetch(`${API}${path}`, {
            ...rest,
            headers: { ...authHeader(token), ...headers },
            signal: controller.signal,
        })
        return res
    } finally {
        clearTimeout(timer)
    }
}
