# DocuSign Connected Fields extension: customer name verification

A private DocuSign extension app. A sender adds a **Customer → Full Name** field to a
template; when the signer fills it in, DocuSign asks this service whether that name matches
an active customer.

```
DocuSign ──OAuth2 (authorization code)──▶ Google     (whoever connects the app signs in)
DocuSign ──POST + Google access token──▶ /api/connected-fields/{type-names,type-definitions,verify}
```

`manifest.json` follows DocuSign's manifest schema (connection, one `ConnectedFields`
extension, three actions) and was written from their Extension Apps reference. It has not been
run through DocuSign's validator yet — the console's **Validate** button is the first real test.

## Behavior

| Customer in the database | `verified` | Signer sees |
|---|---|---|
| exactly one active match | `true` | "Name verified." |
| no match | `false` | generic failure reason |
| inactive customer | `false` | same generic failure reason |
| several customers share the name | `false` | same generic failure reason |

Matching is exact and case-insensitive on `first_name + " " + last_name`; surrounding and
repeated whitespace in the entered name is ignored. The failure text is deliberately identical
for every cause so a signer can't learn which records exist. The real cause is in
`verificationResultCode` (`NOT_FOUND` / `INACTIVE` / `AMBIGUOUS`) and the matched customer's
`id`, `email` and `company` are in `passthroughResponseData`. DocuSign does not show either
to the signer; both are visible in the Developer Console's extension test results.

## Setup

1. **Railway variables.** `GOOGLE_CLIENT_ID` (already set), plus `API_ALLOWED_EMAILS` and/or
   `API_ALLOWED_EMAIL_DOMAINS` — the Google account(s) that will connect the app in DocuSign.
   With both empty, Bearer access is refused for everyone.
2. **Register the app.** At <https://devconsole.docusign.com> choose **Create App → By editing
   the manifest**. Paste `manifest.json` into the editor and replace every `REPLACE_WITH_…`
   value *in the editor* (so the client secret never lands in a file or in git):
   - `REPLACE_WITH_APP_HOST` (3 places): your Railway domain, e.g. `your-app.up.railway.app`
   - `REPLACE_WITH_GOOGLE_CLIENT_ID` / `…_SECRET`: the same Google client the service uses
   - terms / privacy / support URLs, publisher name and email
3. **Click Validate**, fix whatever it reports, then **Create App**. See DocuSign's
   "Troubleshooting manifest errors" page for the messages.
4. **Google redirect URI.** DocuSign generates the OAuth redirect URI; don't put one in the
   manifest. Copy it from the Developer Console and add it to the Google OAuth client's
   **Authorized redirect URIs** (keep the existing `/auth/google/callback` entries).
5. **Test.** On the app's test pages, run the connection test (sign in as an allowlisted
   Google account), then the extension tests for Get Type Names, Get Type Definitions and
   Verify. Then end to end: eSignature → Templates → Add Fields → Custom Fields → App Fields →
   *Customer* → drag **Full Name** onto the document, send yourself an envelope, and type a
   real customer name.

## Open question to check during testing

DocuSign's docs say the connection's access token is sent with every request, but the pages I
read don't name the header. This service accepts it as `Authorization: Bearer <token>`. If the
connection test passes but the extension tests return 401, the header is the first thing to
check (the console shows the failing request).

## Things to know

- **Bearer access isn't limited to these routes.** An allowlisted Google token can call all of
  `/api/*`, including customer create/update/delete. Keep the allowlist tight.
- **Distribution.** The manifest is `PRIVATE`. Using it in production accounts needs DocuSign's
  approval and each account admin's approval (up to 20 accounts); your developer account gets
  it automatically for testing.
- **Retries.** DocuSign retries a failed call up to three times with the same
  `idempotencyKey` and times out at 15 seconds. Verify is a pure read, so retries are safe and
  the key needs no storage.
- Each Bearer request makes one call to Google's tokeninfo endpoint; if Google is unreachable
  the service answers 503.
