# DocuSign Connected Fields extension: customer name verification

A private DocuSign extension app. A sender adds a **Customer → Full Name** field to a
template; when the signer fills it in, DocuSign asks this service whether that name matches
an active customer.

```
DocuSign ──OAuth2 (authorization code)──▶ Google     (whoever connects the app signs in)
DocuSign ──POST + Google access token──▶ /api/connected-fields/{type-names,type-definitions,
                                                                 search-records,verify}
```

`manifest.json` follows DocuSign's manifest schema and declares **two extensions** sharing one
Google connection:

| Extension | Template | Actions |
|---|---|---|
| Customer Data | `DataIO.Version6.DataInputOutput` | `get-type-names`, `get-type-definitions`, `search-records` |
| Customer Name Verification | `ConnectedFields.Version1.ConnectedFields` | `verify` |

Why two: DocuSign's contract says Get Type Names and Get Type Definitions are *Data IO*
actions, and a read-only Data IO extension must implement Search Records as well. An earlier
version put the first two under the Connected Fields extension with no Search Records, and the
console's extension tests failed with a DocuSign-side 500. Whether that was the cause is not
confirmed. The docs don't say how the two extension types combine for a Connected Fields app.

**Search Records is deliberately narrow.** It answers only `full_name EQUALS <value>` (anything
else is a 400), returns at most one record, only when verify would pass, and returns just
`{"full_name": …}`: no email, company or id. A search with no filter would otherwise let a
caller list every customer.

The manifest has been checked for internal consistency but not yet run through DocuSign's
validator; the console's **Validate** button is the first real test.

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
   - `REPLACE_WITH_APP_HOST` (4 places): your Railway domain, e.g. `your-app.up.railway.app`
   - If an app with the same `name` already exists, change `name` (max 30 characters) or
     delete the old app first. App names must be unique.
   - `REPLACE_WITH_GOOGLE_CLIENT_ID` / `…_SECRET`: the same Google client the service uses
   - terms / privacy / support URLs, publisher name and email
3. **Click Validate**, fix whatever it reports, then **Create App**. See DocuSign's
   "Troubleshooting manifest errors" page for the messages.
4. **Google redirect URI.** DocuSign generates the OAuth redirect URI; don't put one in the
   manifest. Copy it from the Developer Console and add it to the Google OAuth client's
   **Authorized redirect URIs** (keep the existing `/auth/google/callback` entries).
5. **Test.** On the app's **App Testing** page, run the connection test (sign in as an
   allowlisted Google account), then the extension tests. You supply each request body
   yourself:
   - Get Type Names: `{}`
   - Get Type Definitions: `{"typeNames": ["customer"]}`
   - Search Records: a query with a `full_name` `EQUALS` filter (see the contract page)
   - Verify: `{"typeName": "customer", "idempotencyKey": "t1", "data": {"full_name": "<a real customer>"}}`

   Then end to end: eSignature → Templates → Add Fields → Custom Fields → App Fields →
   *Customer* → drag **Full Name** onto the document, send yourself an envelope, and type a
   real customer name.

## Notes from testing

- **Token header.** DocuSign sends the connection's access token as `Authorization: Bearer
  <token>`. DocuSign's own reference app reads it that way, and our logs show it arriving.
- **`authorizationMethod`.** The manifest uses `header` (HTTP Basic client authentication at
  Google's token endpoint), which matches DocuSign's reference app and the default. An earlier
  version used `body` and its connection test passed. If the connection test starts failing
  with "error exchanging the authorization code", set it back to `body`.
- **Where to look when a test fails.** The console's one-line error is not informative. The
  service logs the reason for every refused request (Railway → Deploy Logs), and the browser's
  Network tab shows DocuSign's own response. A DocuSign `500 "Unknown error"` from a
  `/publisher-api/…/tests` URL means the failure is inside DocuSign, before our service is called.

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
