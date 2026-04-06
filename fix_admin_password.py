"""Fix admin password in all orquanta SQLite databases."""
import sqlite3, os, sys

try:
    import bcrypt
    new_hash = bcrypt.hashpw(b"OrQ-Admin-2026!", bcrypt.gensalt(12)).decode()
    method = "bcrypt-12"
except ImportError:
    import hashlib
    new_hash = "pbkdf2:" + hashlib.pbkdf2_hmac("sha256", b"OrQ-Admin-2026!", b"orquanta", 260000).hex()
    method = "pbkdf2"

candidates = [
    "orquanta_local.db",
    "orquanta.db",
    "v4/orquanta.db",
    "orquanta_demo.db",
]

for db_path in candidates:
    if not os.path.exists(db_path):
        continue
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cur.fetchall()]
    print(f"[{db_path}] Tables: {tables}")
    if "users" in tables:
        cur.execute("SELECT id, email, role FROM users")
        users = cur.fetchall()
        print(f"  Users: {users}")
        # Get actual column names
        cur.execute(f"PRAGMA table_info(users)")
        cols = [c[1] for c in cur.fetchall()]
        # Find the password column name name
        pw_col = "hashed_password" if "hashed_password" in cols else "hashed_pw"
        print(f"  Password column: {pw_col}")
        # Update existing admin
        cur.execute(
            f"UPDATE users SET {pw_col}=?, role='admin' WHERE email='admin@orquanta.com'",
            (new_hash,)
        )
        affected = cur.rowcount
        if affected == 0:
            # Insert if not exists
            import uuid
            cur.execute(f"""
                INSERT OR REPLACE INTO users (id, email, {pw_col}, name, role)
                VALUES (?, 'admin@orquanta.com', ?, 'OrQuanta Admin', 'admin')
            """, (str(uuid.uuid4()), new_hash))
        conn.commit()
        # Verify
        cur.execute("SELECT email, role FROM users WHERE email='admin@orquanta.com'")
        result = cur.fetchone()
        print(f"  Admin updated ({method}): {result}")
    conn.close()

print("\nDone. Use: admin@orquanta.com / OrQ-Admin-2026!")
