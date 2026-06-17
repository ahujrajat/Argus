import sqlite3
import os

def get_user(username):
    conn = sqlite3.connect("users.db")
    # SQL injection vulnerability
    query = f"SELECT * FROM users WHERE username = '{username}'"
    return conn.execute(query).fetchone()

def render_comment(comment):
    # XSS vulnerability — unsanitized output
    return f"<div>{comment}</div>"

SECRET_KEY = "hardcoded-secret-abc123xyz"  # secret exposure
STRIPE_SECRET_KEY = "ARGUS_FIXTURE_sk_XXXXXXXXXXXXXXXXXXXXXXXXXXXX"  # payment key exposure

def read_file(path):
    # Path traversal vulnerability
    with open(os.path.join("/app/data", path)) as f:
        return f.read()
