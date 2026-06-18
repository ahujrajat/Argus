---
name: python
description: Secure coding patterns, dangerous APIs, and fix patterns for Python
version: 1.0.0
family: languages
tools_allowed: [semgrep, bandit]
---

# Python Secure Coding

## Dangerous sinks
- `exec()`, `eval()`, `compile()` with user input → RCE
- `subprocess.run/Popen` with `shell=True` and user input → command injection
- `os.system()` with user input → command injection
- `open(user_input)` without path normalization → path traversal
- `pickle.loads()`, `yaml.load()` without Loader → deserialization RCE
- String-formatted SQL queries → SQL injection
- `render_template_string(user_input)` → SSTI

## Safe alternatives
- SQL: use parameterized queries `cursor.execute("SELECT ... WHERE x = ?", (val,))`
- Subprocess: `subprocess.run(["cmd", arg], shell=False)`
- File paths: `pathlib.Path(base).joinpath(user_input).resolve()` then assert starts with base
- Deserialization: `json.loads()` instead of pickle; `yaml.safe_load()` instead of `yaml.load()`
- Templates: pass data as context variables, never interpolate into template strings

## Attacker entry points in Python web apps
- Flask/Django request parameters: `request.args`, `request.form`, `request.json`
- File uploads: `request.files`
- HTTP headers: `request.headers`
- URL path segments: `<variable>` in Flask routes, `kwargs` in Django views

## Fix validation checklist
- [ ] Input validated or sanitized before reaching sink
- [ ] ORM or parameterized query used for all DB access
- [ ] Path traversal check: resolved path starts with expected base
- [ ] Subprocess uses list form, not string with shell=True
