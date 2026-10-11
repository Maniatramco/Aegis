# Home after sign-in — 2026-10-11

Successful administrator and ordinary-user sign-ins now navigate to Home and replace the prior screen hash with `#Home`. The initial screen and empty/invalid hash fallback are Home. Explicit navigation and authenticated deep-link refresh remain available.

Production Next.js Docker build and TypeScript checks passed. Four real Chromium checks against the isolated Oracle QA installation passed:

- Administrator sign-in from a previous Assistant URL opens Home.
- Authenticated root URL shows Home; explicit Assistant navigation survives refresh.
- Sign-out followed by sign-in from a Review URL opens Home.
- Ordinary-user sign-in from a Review URL opens Home.

No browser JavaScript errors were observed. Only the web image/container is updated for this change; the backend and database configuration are retained.

[Browser results](results/home-login-2026-10-11/home-login.json) · [Home screenshot](results/home-login-2026-10-11/home-login.png)
