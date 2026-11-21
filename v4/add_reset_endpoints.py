#!/usr/bin/env python3
"""
Inject forgot-password / reset-password endpoints into main.py
and add ForgotPasswordPage route to App.jsx
"""
import re

# ─── 1. PATCH main.py ────────────────────────────────────────────────────────
main_path = r'c:\ai-gpu-cloud\v4\api\main.py'
content = open(main_path, encoding='utf-8').read()

NEW_ENDPOINTS = r'''

# --- Forgot / Reset password (unauthenticated) --------------------------------

class _ForgotPasswordRequest(_BaseModel):
    email: str

class _ResetPasswordRequest(_BaseModel):
    token: str
    new_password: str

@app.post("/auth/forgot-password", tags=["Auth"], summary="Request password reset link")
async def forgot_password(req: _ForgotPasswordRequest):
    """Accept an email, generate a time-limited reset token (1 h JWT), log it, optionally send SMTP."""
    from .middleware.auth import _get_db, _USE_PG, _ph, JWT_SECRET, JWT_ALGORITHM
    import secrets as _sec

    ph = _ph()
    conn = _get_db()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(f"SELECT id FROM users WHERE email = {ph}", (req.email.lower(),))
            row = cur.fetchone()
            cur.close()
        else:
            row = conn.execute(f"SELECT id FROM users WHERE email = {ph}", (req.email.lower(),)).fetchone()
    finally:
        conn.close()

    if row:
        payload = {
            "sub": req.email.lower(),
            "type": "reset",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "jti": _sec.token_hex(16),
        }
        reset_token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        frontend_url = os.getenv("FRONTEND_URL", "https://orquanta.com")
        reset_url = f"{frontend_url}/forgot-password?token={reset_token}"
        logger.info(f"[PASSWORD RESET] Email={req.email}  URL={reset_url}")

        smtp_host = os.getenv("SMTP_HOST", "")
        if smtp_host:
            try:
                import smtplib, email.mime.text as _mt, email.mime.multipart as _mm
                smtp_port = int(os.getenv("SMTP_PORT", "587"))
                smtp_user = os.getenv("SMTP_USER", "")
                smtp_pass = os.getenv("SMTP_PASS", "")
                smtp_from = os.getenv("SMTP_FROM", smtp_user)
                msg = _mm.MIMEMultipart("alternative")
                msg["Subject"] = "Reset your OrQuanta password"
                msg["From"] = smtp_from
                msg["To"] = req.email
                html_body = (
                    "<html><body style='font-family:sans-serif;padding:32px;'>"
                    "<h2 style='color:#7B2FFF;'>OrQuanta Password Reset</h2>"
                    "<p>Click below to reset your password. Expires in <strong>1 hour</strong>.</p>"
                    f"<a href='{reset_url}' style='display:inline-block;padding:12px 24px;"
                    "background:linear-gradient(135deg,#7B2FFF,#0091FF);color:#fff;"
                    "text-decoration:none;border-radius:8px;font-weight:700;'>Reset Password</a>"
                    "<p style='margin-top:24px;color:#94A3B8;font-size:12px;'>"
                    "If you did not request this, ignore this email.</p></body></html>"
                )
                msg.attach(_mt.MIMEText(html_body, "html"))
                with smtplib.SMTP(smtp_host, smtp_port) as s:
                    s.ehlo(); s.starttls(); s.login(smtp_user, smtp_pass)
                    s.sendmail(smtp_from, [req.email], msg.as_string())
                logger.info(f"[PASSWORD RESET] Email delivered to {req.email}")
            except Exception as smtp_err:
                logger.warning(f"[PASSWORD RESET] SMTP failed: {smtp_err}")

    # Always 200 — prevents email enumeration
    return {"success": True, "message": "If that email is registered, a reset link has been sent."}


@app.post("/auth/reset-password", tags=["Auth"], summary="Complete password reset with token")
async def reset_password_endpoint(req: _ResetPasswordRequest):
    """Verify the reset JWT and update the user password."""
    from .middleware.auth import _get_db, _USE_PG, _ph, JWT_SECRET, JWT_ALGORITHM, hash_password
    import secrets as _sec

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    try:
        payload = jwt.decode(req.token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=400, detail="Invalid reset token.")

    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Invalid token type.")

    email = payload.get("sub", "")
    if not email:
        raise HTTPException(status_code=400, detail="Malformed token.")

    ph = _ph()
    new_salt = _sec.token_hex(8)
    new_hash = hash_password(req.new_password, new_salt)
    conn = _get_db()
    try:
        if _USE_PG:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE users SET hashed_pw = {ph}, salt = {ph} WHERE email = {ph}",
                (new_hash, new_salt, email.lower()),
            )
            conn.commit()
            affected = cur.rowcount
            cur.close()
        else:
            conn.execute(
                f"UPDATE users SET hashed_pw = {ph}, salt = {ph} WHERE email = {ph}",
                (new_hash, new_salt, email.lower()),
            )
            conn.commit()
            affected = conn.total_changes
    finally:
        conn.close()

    if affected == 0:
        raise HTTPException(status_code=404, detail="Account not found.")

    logger.info(f"[PASSWORD RESET] Password reset complete for: {email}")
    return {"success": True, "message": "Password updated successfully. You can now sign in."}

'''

ANCHOR = '    return {"success": True, "full_name": req.full_name}'

if ANCHOR in content:
    new_content = content.replace(ANCHOR, ANCHOR + NEW_ENDPOINTS, 1)
    open(main_path, 'w', encoding='utf-8').write(new_content)
    print("SUCCESS: Password reset endpoints added to main.py")
else:
    print(f"ERROR: anchor not found in main.py")
    idx = content.find('"full_name"')
    print(repr(content[idx-100:idx+200]))

# ─── 2. PATCH App.jsx — add import + route ───────────────────────────────────
app_path = r'c:\ai-gpu-cloud\v4\frontend\src\App.jsx'
app = open(app_path, encoding='utf-8').read()

IMPORT_ANCHOR = "import HelpPage from './pages/HelpPage.jsx'"
IMPORT_NEW = "import HelpPage from './pages/HelpPage.jsx'\nimport ForgotPasswordPage from './pages/ForgotPasswordPage.jsx'"

ROUTE_ANCHOR = "                        <Route path=\"/help\" element={<HelpPage />} />"
ROUTE_NEW = "                        <Route path=\"/help\" element={<HelpPage />} />\n                        <Route path=\"/forgot-password\" element={<ForgotPasswordPage />} />"

if IMPORT_ANCHOR in app and ROUTE_ANCHOR in app:
    app = app.replace(IMPORT_ANCHOR, IMPORT_NEW, 1)
    app = app.replace(ROUTE_ANCHOR, ROUTE_NEW, 1)
    open(app_path, 'w', encoding='utf-8').write(app)
    print("SUCCESS: ForgotPasswordPage added to App.jsx")
else:
    if IMPORT_ANCHOR not in app:
        print("ERROR: import anchor not found in App.jsx")
    if ROUTE_ANCHOR not in app:
        print("ERROR: route anchor not found in App.jsx")

print("Done.")
