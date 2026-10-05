/* Email capture for parkingnetherlands.com alerts.
 *
 * Stores an address, what it asked to hear about, and the consent that was
 * given. It does not send anything: the sending side is deliberately a later
 * job, and this is written so that turning it on needs no migration. Every
 * record already carries a confirmation token and a confirmed flag, so double
 * opt-in is a switch rather than a rewrite.
 *
 * Nothing here is shared with anyone. The data sits in one KV namespace in the
 * site owner's own Cloudflare account.
 */

const MAX_EMAIL = 254;
const TOPICS = new Set(["tariffs", "chargers", "fines", "research"]);
const CONSENT_VERSION = "2026-10-05";

function cors(origin, allowed) {
  // Echo the origin only when it is the one we expect, so the endpoint cannot
  // be driven from someone else's page.
  const ok = origin === allowed;
  return {
    "Access-Control-Allow-Origin": ok ? origin : allowed,
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function json(body, status, headers) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...headers },
  });
}

/* Deliberately permissive. The job of this check is to catch a typo and a bot,
 * not to adjudicate RFC 5322; anything that survives it still has to answer a
 * confirmation mail before it is worth anything. */
function validEmail(s) {
  if (typeof s !== "string") return false;
  const e = s.trim();
  if (e.length < 6 || e.length > MAX_EMAIL) return false;
  if (/\s/.test(e)) return false;
  const at = e.indexOf("@");
  if (at < 1 || at !== e.lastIndexOf("@")) return false;
  const dom = e.slice(at + 1);
  return dom.includes(".") && !dom.startsWith(".") && !dom.endsWith(".")
         && !dom.includes("..");
}

async function token() {
  const b = crypto.getRandomValues(new Uint8Array(16));
  return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

export default {
  async fetch(request, env) {
    const allowed = env.ALLOWED_ORIGIN || "https://parkingnetherlands.com";
    const origin = request.headers.get("Origin") || "";
    const head = cors(origin, allowed);
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: head });
    }

    if (url.pathname === "/unsubscribe") {
      const e = (url.searchParams.get("e") || "").toLowerCase().trim();
      const t = url.searchParams.get("t") || "";
      const raw = e && await env.SUBS.get("sub:" + e);
      if (!raw) return new Response("Not found.", { status: 404 });
      const rec = JSON.parse(raw);
      if (!t || t !== rec.token) return new Response("Bad link.", { status: 403 });
      rec.unsubscribed = new Date().toISOString();
      await env.SUBS.put("sub:" + e, JSON.stringify(rec));
      return new Response(
        "You are unsubscribed. Nothing further will be sent to this address.",
        { status: 200, headers: { "Content-Type": "text/plain; charset=utf-8" } });
    }

    if (request.method !== "POST" || url.pathname !== "/subscribe") {
      return json({ ok: false, error: "not_found" }, 404, head);
    }
    if (origin && origin !== allowed) {
      return json({ ok: false, error: "bad_origin" }, 403, head);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "bad_json" }, 400, head);
    }

    // A field no human sees and no human fills. Answer 200 so a bot learns
    // nothing from the difference.
    if (body.website) return json({ ok: true }, 200, head);

    const email = String(body.email || "").trim().toLowerCase();
    if (!validEmail(email)) {
      return json({ ok: false, error: "bad_email" }, 400, head);
    }
    if (body.consent !== true) {
      return json({ ok: false, error: "no_consent" }, 400, head);
    }

    const ip = request.headers.get("CF-Connecting-IP") || "";
    if (ip) {
      const k = "rl:" + ip;
      const n = parseInt((await env.SUBS.get(k)) || "0", 10);
      if (n >= 5) return json({ ok: false, error: "rate_limited" }, 429, head);
      await env.SUBS.put(k, String(n + 1), { expirationTtl: 3600 });
    }

    const topics = Array.isArray(body.topics)
      ? body.topics.filter((t) => TOPICS.has(t)) : [];

    const key = "sub:" + email;
    const existing = await env.SUBS.get(key);
    const now = new Date().toISOString();
    let rec;
    if (existing) {
      // Re-subscribing is how someone undoes an unsubscribe, so clear it.
      rec = JSON.parse(existing);
      rec.topics = topics.length ? topics : rec.topics;
      rec.updated = now;
      delete rec.unsubscribed;
    } else {
      rec = {
        email,
        created: now,
        topics,
        source: String(body.source || "").slice(0, 64),
        consent_version: CONSENT_VERSION,
        consent_at: now,
        country: request.cf && request.cf.country ? request.cf.country : null,
        confirmed: false,
        token: await token(),
      };
    }
    await env.SUBS.put(key, JSON.stringify(rec));
    return json({ ok: true, already: Boolean(existing) }, 200, head);
  },
};
