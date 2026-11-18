# DocuSign Data Verification extension (draft)

`manifest.json` wires DocuSign to this service:

```
DocuSign ──OAuth2 auth-code──▶ Google          (user signs in, DocuSign holds the token)
DocuSign ──POST /api/verify, Authorization: Bearer <google access token>──▶ this service
```

## Status: DRAFT — validate before uploading

The **service side is built and tested** (`app/google_token.py`, `app/routers/api_verify.py`).
The **manifest is not verified against DocuSign's schema.** It was written without access to
DocuSign's Extension Apps documentation, so the structure and key names above (`connections`,
`actions`, `request`/`response` mapping, `{{fullName}}` templating) are a best-effort sketch
of the intent, not confirmed field names. Before using it:

1. Compare against DocuSign's current Extension Apps manifest reference and the Data
   Verification extension type, and rename/restructure keys to match. Run it through the
   Developer Console's manifest validation.
2. Confirm how DocuSign passes the signer's name into the call and how it expects the
   found/not-found result shaped. If it needs a different request/response contract than
   `POST /api/verify` `{"full_name"}` → `{"found","verified","id","email","company"}`, adapt
   the endpoint (or add an adapter route) rather than the matching logic.

## Setup checklist

1. **Google OAuth client.** Create a "Web application" client (a *separate* one from the staff
   sign-in client is cleaner; the service accepts only tokens issued to `GOOGLE_CLIENT_ID`, so
   use whichever client you set there). Add **DocuSign's OAuth callback URL** — shown in the
   DocuSign Developer Console for your app — to its authorized redirect URIs.
2. **Service config** (Railway variables):
   - `GOOGLE_CLIENT_ID` — the client above (the token audience that is enforced)
   - `API_ALLOWED_EMAIL_DOMAINS` and/or `API_ALLOWED_EMAILS` — who may call the API. With both
     empty, Bearer access is refused for everyone.
3. **Manifest.** Replace `REPLACE_WITH_GOOGLE_CLIENT_ID` and `REPLACE_WITH_APP_HOST`. The
   **client secret does not go in the manifest** — enter it in DocuSign's connection settings.
4. **Scopes.** `openid email` is the minimum: the service needs the verified email to apply the
   allowlist. A token without the `email` scope is rejected.

## Things to know

- **Who can call.** The allowlist is checked against the Google account that authorized the
  connection (whoever connects the app in DocuSign), not against each signer.
- **Bearer access is not limited to `/api/verify`.** An allowlisted token can call all of
  `/api/customers` too, including create/update/delete. Keep the allowlist tight.
- **Latency.** Each Bearer request makes one call to Google's tokeninfo endpoint. If Google is
  unreachable the service answers `503` (fails closed).
