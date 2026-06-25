// HoopsHype Claude relay Worker
// Holds ANTHROPIC_API_KEY as a secret and forwards chat requests to the
// Anthropic Messages API. Reusable by any HoopsHype browser tool that needs Claude.
//
// Talks to: https://api.anthropic.com/v1/messages
//
// Protection: origin allow-list (blocks other sites' browsers). This is NOT
// full protection against a non-browser client that knows the URL. The real
// spend backstop is the Anthropic billing cap on the key. Keep that cap on.

const ALLOWED_ORIGINS = [
  "https://jsierrahoopshype.github.io",
  // add more origins here if you host the tool elsewhere
];

export default {
  async fetch(request, env) {
    const origin = request.headers.get("Origin") || "";

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders(origin) });
    }
    if (request.method !== "POST") {
      return json({ error: "POST only" }, 405, origin);
    }
    // Origin gate
    if (!ALLOWED_ORIGINS.includes(origin)) {
      return json({ error: "Origin not allowed" }, 403, origin);
    }

    try {
      const body = await request.json();

      // Forward only the fields we expect. Defaults keep callers simple.
      const payload = {
        model: body.model || "claude-sonnet-4-6",
        max_tokens: body.max_tokens || 4000,
        system: body.system || "",
        messages: body.messages || [],
      };

      const upstream = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": env.ANTHROPIC_API_KEY,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify(payload),
      });

      const data = await upstream.json();
      return json(data, upstream.status, origin);
    } catch (err) {
      return json({ error: err.message }, 500, origin);
    }
  },
};

function corsHeaders(origin) {
  // Echo the caller's origin only if it's allowed, otherwise fall back to the
  // primary so the browser still receives a valid (if rejected) response.
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    "Access-Control-Allow-Origin": allow,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Vary": "Origin",
  };
}

function json(obj, status, origin) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
  });
}
