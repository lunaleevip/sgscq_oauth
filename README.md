# SGSCQ OAuth Redirect

Static OAuth callback relay for SGSCQ.

Use this with static hosting such as Gitee Pages. The page receives an HTTPS
OAuth callback and redirects the browser back into the Android app.

## Routes

- `/index.html?target=afdian&code=...&state=...`
- `/afdian/oauth.html?code=...&state=...`
- `/afdian/webhook`
- `/bilibili/oauth.html?code=...&state=...`

## App Schemes

- Afdian: `sgscq://afdian/oauth`
- Bilibili: `sgscq://bilibili/oauth`

## Afdian Redirect URI Example

```text
https://<your-gitee-pages-domain>/<project>/afdian/oauth.html
```

Use the exact same redirect URI in the OAuth authorization request and token
exchange request.

## Afdian Webhook Auto Sync

The static Afdian snapshot is refreshed by `.github/workflows/afdian-sponsors.yml`.
Manual runs and scheduled runs perform a full Afdian sync. The Afdian webhook
uses `repository_dispatch` with type `afdian_order` and only merges the paid
order into `afdian/users/<user_id>.json`; ranking files are left for scheduled
full syncs.

Configure these GitHub Actions secrets in `lunaleevip/sgscq_oauth`:

- `AFDIAN_USER_ID`: Afdian OpenAPI user id.
- `AFDIAN_TOKEN`: Afdian OpenAPI token.

Deploy `tools/afdian_webhook_dispatch_worker.mjs` to EdgeOne Pages Functions,
Cloudflare Workers, or another Worker-compatible runtime. Configure these
Worker environment variables:

- `AFDIAN_WEBHOOK_SECRET`: optional random webhook secret. If it is configured,
  the webhook URL must pass the same value through `?secret=` or the
  `x-webhook-secret` header. Leave it unset when the webhook provider cannot
  append a secret.
- `GITHUB_DISPATCH_TOKEN`: GitHub PAT that can call repository dispatch on
  `lunaleevip/sgscq_oauth`.
- `GITHUB_REPO`: optional, defaults to `lunaleevip/sgscq_oauth`.

Set the Afdian webhook URL to:

```text
https://<worker-domain>/afdian/webhook
```

If `AFDIAN_WEBHOOK_SECRET` is configured and the provider supports query
parameters, use:

```text
https://<worker-domain>/afdian/webhook?secret=<AFDIAN_WEBHOOK_SECRET>
```

The Worker accepts only paid order payloads (`ec=200`, `data.type=order`,
`order.status=2`) and dispatches the GitHub Action. Other order statuses return
`202 ignored`.

Local verification:

```powershell
node --test tests\afdian_webhook_dispatch_worker.test.mjs
python tests\test_afdian_webhook_merge.py
```
