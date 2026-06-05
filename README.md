# SGSCQ OAuth Redirect

Static OAuth callback relay for SGSCQ.

Use this with static hosting such as Gitee Pages. The page receives an HTTPS
OAuth callback and redirects the browser back into the Android app.

## Routes

- `/index.html?target=afdian&code=...&state=...`
- `/afdian/oauth.html?code=...&state=...`
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
