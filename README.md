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
Webhook events merge the paid order into `afdian/users/<user_id>.json`
immediately. Scheduled runs only scan recent `query-order` pages and stop after
reaching an order recorded in `afdian/order_checkpoint.json`. Manual workflow
runs use the same incremental mode by default; set `full_sync=true` to rebuild
the full snapshot and ranking files.

GitHub's own `schedule` trigger can be delayed or skipped. For reliable
five-minute polling, run `tools/oauth_sync_dispatch.sh` from an external
cron-capable host every five minutes. It sends these repository dispatch events
and only advances the hourly full-sync state after GitHub accepts the dispatch:

- `afdian_incremental`: run recent Afdian order sync.
- `afdian_full`: run full Afdian order and sponsor snapshot sync once per hour.
- `bili_followers`: run Bilibili follower snapshot sync.
- `bili_followers_full`: run full Bilibili follower snapshot sync once per
  six-hour UTC slot.

The external host only needs `GITHUB_DISPATCH_TOKEN` in its environment. The
token must be able to call repository dispatch on `lunaleevip/sgscq_oauth`.

Bilibili follower sync also runs in incremental mode by default. It reads the
existing `bilibili/followers.compact.txt`, crawls the newest follower pages, and
prepends new mids without dropping old mids that no longer fit in Bilibili's
latest-page API window. Scheduled and external cron runs force a full Bilibili
sync once every six hours. Manual `Fast follower snapshot` runs can set
`full_sync=true` to rebuild from the Bilibili API limit.

Douyin follower sync is not scheduled through GitHub Actions. The web follower
endpoint requires a fresh browser-style `a_bogus` signature for every page, so
the scheduled job runs on the VPS instead. The VPS job signs each page locally,
commits `douyin/followers.json` and `douyin/followers.compact.txt`, and mirrors
the result to Gitee. The GitHub workflow remains available only for manual or
repository-dispatch fallback runs.

Configure these GitHub Actions secrets in `lunaleevip/sgscq_oauth`:

- `AFDIAN_USER_ID`: Afdian OpenAPI user id.
- `AFDIAN_TOKEN`: Afdian OpenAPI token.
- `DOUYIN_COOKIE`: Douyin logged-in web Cookie for manual fallback runs.
- `DOUYIN_TARGET_ID`: target Douyin account id used by the followers endpoint,
  usually the account `sec_user_id`.
- `DOUYIN_FOLLOWERS_URL_TEMPLATE`: optional override for the Douyin followers
  endpoint. The template can use `{target_id}`, `{cursor}`, and `{count}`.
- `DOUYIN_REFERER_URL`: optional Douyin page URL used as the request `Referer`;
  defaults to `https://www.douyin.com/jingxuan`.
- `DOUYIN_EXTRA_HEADERS`: optional JSON object for extra Douyin request
  headers, for example `{"sec-ch-ua-platform":"\"Windows\""}`. Do not put the
  Cookie here; use `DOUYIN_COOKIE` instead.
- `DOUYIN_ENABLED`: set to `true` only after the Cookie and endpoint template
  have been verified. Other values make the workflow skip successfully.

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
python tests\test_afdian_orders_incremental.py
```
