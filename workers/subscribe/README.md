# pn-subscribe

Email capture for the alerts on parkingnetherlands.com. A standalone Worker, on
purpose: the site itself is served by Cloudflare static assets with no request
handler, and putting one in front of it to catch a single POST would make that
handler responsible for all 1,459 pages.

## Deploy

    cd workers/subscribe
    npx wrangler login
    npx wrangler kv namespace create SUBS      # paste the id into wrangler.toml
    npx wrangler deploy

Wrangler prints the URL, something like `https://pn-subscribe.<you>.workers.dev`.
Put that in `ENDPOINT` at the top of `/subscribe.js` in the site repo, commit,
and the form is live.

For a tidier address, add a DNS record for `alerts.parkingnetherlands.com`,
uncomment the `[[routes]]` block, redeploy, and set `ENDPOINT` to
`https://alerts.parkingnetherlands.com`.

## Read what has come in

    npx wrangler kv key list --binding SUBS --prefix sub:
    npx wrangler kv key get --binding SUBS "sub:someone@example.com"

## What a record looks like

    {
      "email": "someone@example.com",
      "created": "2026-10-05T21:30:00.000Z",
      "topics": ["tariffs", "chargers"],
      "source": "/alerts",
      "consent_version": "2026-10-05",
      "consent_at": "2026-10-05T21:30:00.000Z",
      "country": "NL",
      "confirmed": false,
      "token": "..."
    }

`confirmed` is false for everyone until the sending side exists. When it does,
mail the confirmation link first and only treat `confirmed: true` as a list.
The token is already stored, so no migration is needed, and the same token
drives `/unsubscribe?e=<email>&t=<token>`, which works today.
