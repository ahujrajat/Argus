---
name: javascript-typescript
description: Secure coding patterns for JavaScript and TypeScript (Node.js and browser)
version: 1.0.0
family: languages
tools_allowed: [semgrep, eslint-security]
---

# JavaScript / TypeScript Secure Coding

## Dangerous sinks
- `innerHTML`, `outerHTML`, `document.write()` with user input → XSS
- `eval()`, `new Function(userInput)` → RCE / code injection
- `child_process.exec(userInput)` → command injection
- Template literals in SQL: `` `SELECT * WHERE id = ${id}` `` → SQL injection
- `require(userInput)`, `import(userInput)` → arbitrary code load
- `res.redirect(req.query.url)` without allowlist → open redirect

## Safe alternatives
- DOM: `element.textContent = userInput` (never innerHTML with user data)
- SQL: use parameterized queries or ORM methods
- Shell: `child_process.execFile('cmd', [arg])` — array form, no shell
- Redirects: validate against an allowlist of allowed domains

## Prototype pollution signals
- `obj[userKey] = userValue` where key comes from user input
- `JSON.parse` result assigned to object properties without sanitization
- lodash `merge`, `set`, `zipObjectDeep` with user-controlled keys

## Fix validation checklist
- [ ] No innerHTML with user-controlled content
- [ ] All SQL uses parameterized queries or ORM
- [ ] eval() / new Function() replaced with safe alternative
- [ ] open redirect validates against allowlist
