---
name: secrets-exposure
description: Hardcoded credentials, secrets in config and history — detection and remediation
version: 1.0.0
family: vuln-classes
tools_allowed: [trufflehog, semgrep]
---

# Secrets Exposure — CWE-798, CWE-312

## Attacker mindset
Attacker clones the repo (public or via leaked credentials), runs trufflehog or grep,
and extracts API keys in minutes. Keys in git history survive even after the file is edited.

## What to look for
- Strings matching provider key patterns in source files (sk-ant-, sk-proj-, ghp_, AIza...)
- Keys assigned to variables named: api_key, secret, token, password, credentials
- .env files committed to git
- Keys in CI/CD YAML files (GitHub Actions secrets misconfiguration)
- Keys in test fixtures or mock data

## Remediation steps (in order)
1. **Rotate the secret immediately** — assume it is compromised
2. Remove from the current file
3. Remove from git history: `git filter-repo --path <file> --invert-paths`
   or BFG Repo Cleaner for large repos
4. Move to environment variable or secrets manager (Vault, AWS SSM, GitHub Secrets)
5. Add the pattern to pre-commit hooks (detect-secrets, gitleaks)

## Platform handling
Argus stores only a fingerprint (SHA-256) and location — never the raw secret value.
The raw value is redacted before any log, database write, or LLM prompt.

## Fix validation
After rotation: confirm the old key returns 401/403 from the provider.
After history rewrite: `git log -S "old-key-value"` returns no results.
