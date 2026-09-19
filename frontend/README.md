# DueClaim frontend

Vite + React + TypeScript + Tailwind v4, Cognito auth via `@aws-amplify/ui-react`.

```sh
cp .env.example .env   # fill from the backend stack outputs (see below)
npm install
npm run dev
npm test               # vitest: money formatter + invoice validation
npm run build          # tsc + vite build -> dist/
```

## Environment variables

| Variable | Stack output |
|---|---|
| `VITE_API_URL` | `ApiUrl` |
| `VITE_USER_POOL_ID` | `UserPoolId` |
| `VITE_USER_POOL_CLIENT_ID` | `UserPoolClientId` |

Vite bakes these in at build time, so on Amplify Hosting set all three under
**App settings → Environment variables** and redeploy.

Amplify Hosting also needs an SPA rewrite so `/invoices/:id` resolves on refresh:
source `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json)$)([^.]+$)/>`
→ target `/index.html`, type `200 (Rewrite)`.
