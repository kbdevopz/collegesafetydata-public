# Security Policy

## Reporting a vulnerability

Please report security issues privately by email to
**contact@collegesafetydata.org**, with "Security" in the subject line.
Do not open a public issue for a security problem.

Include what you found, where (file, page or URL), and how to reproduce it.

I maintain this project alone. I will acknowledge your report within 7 days
and keep you updated until it is fixed. Fixes go to `main`, which redeploys
collegesafetydata.org and collegesafetydata.com. With your permission, I will
credit you when the fix is released.

## Scope

In scope:
- Code in this repository (`etl/`, `frontend/`)
- The deployed sites collegesafetydata.org and collegesafetydata.com

Out of scope:
- U.S. Department of Education and NCES systems the data comes from
- Cloudflare and Vercel themselves (report to them directly)
- Errors in the source data itself. Please open a normal issue for those.

Please do not run load tests or automated scans that could disrupt the sites.

## Supported versions

Only the current `main` branch, which is what the live sites serve, receives
security fixes.
