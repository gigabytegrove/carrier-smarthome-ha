# Security and privacy rules

- Research and control only devices and accounts you own or administer.
- All discovery tools default to read-only. The explicit subnet scanner is opt-in and restricted to RFC1918 /24 or smaller.
- No automatic writes, thermostat pairing changes, firmware modification, certificate pinning bypass, MITM proxy, or credentials scraping.
- Use HTTPS with certificate validation for cloud tests; refuse redirects.
- Redact API tokens, cookies, passwords, serials, MAC, public IP, account data, addresses and full raw responses before issue/commit submission.
- Cloud calls should use owner-approved rate limits and stop on authentication errors; no repeated login attempts.
- Build HA credentials/config entries securely after authentication is verified, with token renewal and graceful failures.
