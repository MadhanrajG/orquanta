/**
 * Cloudflare Worker — orquanta.com proxy
 * Intercepts all requests and proxies to Render (orquanta-sg.onrender.com)
 * Rewrites Host header so Render serves the page without a custom domain registration.
 */

const RENDER_ORIGIN = "https://orquanta-sg.onrender.com";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // Build upstream URL — same path/query, different host
    const upstream = new URL(url.pathname + url.search, RENDER_ORIGIN);

    // Clone headers, rewrite Host to Render's hostname
    const headers = new Headers(request.headers);
    headers.set("Host", "orquanta-sg.onrender.com");
    // Forward real client IP so FastAPI logs are meaningful
    headers.set("X-Forwarded-Host", url.hostname);
    headers.set("X-Forwarded-Proto", url.protocol.replace(":", ""));

    const upstreamReq = new Request(upstream.toString(), {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? null : request.body,
      redirect: "manual",
    });

    let response;
    try {
      response = await fetch(upstreamReq);
    } catch (err) {
      return new Response("OrQuanta gateway error: " + err.message, { status: 502 });
    }

    // Pass through redirects (Render may redirect /login → /login/)
    if (response.status >= 300 && response.status < 400) {
      const location = response.headers.get("Location") || "";
      // Rewrite Location headers that point to the Render hostname back to orquanta.com
      const rewritten = location.replace(
        /https?:\/\/orquanta-sg\.onrender\.com/g,
        url.origin
      );
      const newHeaders = new Headers(response.headers);
      if (rewritten !== location) newHeaders.set("Location", rewritten);
      return new Response(response.body, {
        status: response.status,
        headers: newHeaders,
      });
    }

    // Stream response back, preserving all headers
    return new Response(response.body, {
      status: response.status,
      headers: response.headers,
    });
  },
};
