# Optional owner session trace without knowing any API address

This is only needed if APK/static public portal inspection cannot prove live routing. It is not required for the initial offline research.

1. Open the official Carrier SmartHome web portal and sign in to **your** thermostat account using the normal interface.
2. In Chrome/Edge open developer tools (`F12`) → **Network** → select **Fetch/XHR**, then reload and view your thermostat. No need to change any setting.
3. Export a HAR **to your own computer**. A HAR may contain session cookies, Bearer tokens, serial numbers, account details and passwords. **Do not upload it to this chat, GitHub, or third parties.**
4. Process locally with `python tools/analyze_har.py path-to-private.har --output private-safe-summary.json`.
5. Review the sanitized summary before sharing; it contains only endpoint host/path *patterns*, HTTP method, GraphQL operation name, parameter *keys*, and authentication mechanism. It strips values, response bodies and query strings.
6. Delete the raw HAR securely when no longer needed.

This may reveal the web portal's active GraphQL host, but not necessarily the app's mobile endpoint, nor OAuth grant details. The sanitizer intentionally cannot recover credentials or give a complete login implementation. Never disable certificate checking or attempt to bypass pinning as a prerequisite to initial work.
