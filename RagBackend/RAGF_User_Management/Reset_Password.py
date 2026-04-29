"""
Password reset module.

Supports two legacy verification flows:
- email code reset
- sms code reset

Also provides a simplified direct email reset endpoint for frontend use.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import smtplib
import string
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Tuple

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from RAGF_User_Management.db_config import db_cursor

logger = logging.getLogger(__name__)
router = APIRouter()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)

# target -> (code, expire_ts, retry_count)
_CODE_STORE: Dict[str, Tuple[str, float, int]] = {}
CODE_TTL = 5 * 60
MAX_RETRY = 5
CODE_RESEND_INTERVAL = 60


def _gen_code(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _store_code(target: str, code: str) -> None:
    _CODE_STORE[target] = (code, time.time() + CODE_TTL, 0)


def _verify_code(target: str, code: str) -> bool:
    entry = _CODE_STORE.get(target)
    if not entry:
        return False

    stored_code, expire_ts, retry_count = entry
    if time.time() > expire_ts:
        _CODE_STORE.pop(target, None)
        return False
    if retry_count >= MAX_RETRY:
        _CODE_STORE.pop(target, None)
        return False
    if stored_code != code:
        _CODE_STORE[target] = (stored_code, expire_ts, retry_count + 1)
        return False

    _CODE_STORE.pop(target, None)
    return True


def _can_resend(target: str) -> bool:
    entry = _CODE_STORE.get(target)
    if not entry:
        return True

    _, expire_ts, _ = entry
    remaining = expire_ts - time.time()
    return remaining < (CODE_TTL - CODE_RESEND_INTERVAL)


def _send_email(to_addr: str, code: str) -> bool:
    if not SMTP_USER or not SMTP_PASSWORD:
        logger.warning("[DEV] SMTP not configured, print code to console: %s -> %s", to_addr, code)
        print("\n" + "=" * 50)
        print(f"[Email Code] To: {to_addr}")
        print(f"Code: {code} (valid for 5 minutes)")
        print("=" * 50 + "\n")
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "【RAG-F】密码重置验证码"
        msg["From"] = SMTP_FROM
        msg["To"] = to_addr

        html_body = f"""
        <html>
          <body style="font-family:Arial,sans-serif;background:#f5f5f5;padding:20px;">
            <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:12px;padding:32px;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
              <h2 style="color:#0ea5e9;margin-bottom:8px;">RAG-F 密码重置</h2>
              <p style="color:#555;margin-bottom:24px;">您的验证码如下：</p>
              <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:20px;text-align:center;">
                <span style="font-size:36px;font-weight:bold;letter-spacing:8px;color:#0284c7;">{code}</span>
              </div>
              <p style="color:#888;margin-top:20px;font-size:13px;">验证码 5 分钟内有效，请勿泄露给他人。</p>
            </div>
          </body>
        </html>
        """
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, [to_addr], msg.as_string())

        logger.info("Verification email sent to %s", to_addr)
        return True
    except Exception as e:
        logger.error("Send email failed: %s", e)
        return False


def _send_sms(phone: str, code: str) -> bool:
    # Development fallback.
    if not os.getenv("SMS_ACCESS_KEY_ID", ""):
        logger.warning("[DEV] SMS not configured, print code to console: %s -> %s", phone, code)
        print("\n" + "=" * 50)
        print(f"[SMS Code] To: {phone}")
        print(f"Code: {code} (valid for 5 minutes)")
        print("=" * 50 + "\n")
        return True

    # If a real SMS provider is configured, integrate SDK here.
    logger.error("SMS provider configured but implementation is missing")
    return False


def _email_exists(email: str) -> bool:
    try:
        with db_cursor() as cur:
            cur.execute("SELECT id FROM user WHERE email = %s", (email,))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("_email_exists error: %s", e)
        return False


def _phone_exists(phone: str) -> bool:
    try:
        with db_cursor() as cur:
            cur.execute("DESCRIBE user")
            cols = [r[0] for r in cur.fetchall()]
            if "phone" not in cols:
                return False
            cur.execute("SELECT id FROM user WHERE phone = %s", (phone,))
            return cur.fetchone() is not None
    except Exception as e:
        logger.error("_phone_exists error: %s", e)
        return False


def _reset_password_by_email(email: str, new_password: str) -> bool:
    try:
        hashed = hashlib.sha256(new_password.encode()).hexdigest()
        with db_cursor() as cur:
            cur.execute("UPDATE user SET password = %s WHERE email = %s", (hashed, email))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("_reset_password_by_email error: %s", e)
        return False


def _reset_password_by_phone(phone: str, new_password: str) -> bool:
    try:
        hashed = hashlib.sha256(new_password.encode()).hexdigest()
        with db_cursor() as cur:
            cur.execute("UPDATE user SET password = %s WHERE phone = %s", (hashed, phone))
            return cur.rowcount > 0
    except Exception as e:
        logger.error("_reset_password_by_phone error: %s", e)
        return False


class SendEmailCodeRequest(BaseModel):
    email: str


class SendSmsCodeRequest(BaseModel):
    phone: str


class ResetPasswordRequest(BaseModel):
    method: str  # "email" or "phone"
    target: str
    code: str
    new_password: str
    confirm_password: str


class DirectEmailResetRequest(BaseModel):
    email: str
    new_password: str
    confirm_password: str


@router.post("/api/reset/send-email-code", response_model=dict, tags=["密码重置"])
async def send_email_code(req: SendEmailCodeRequest):
    email = req.email.strip().lower()

    if not _email_exists(email):
        raise HTTPException(status_code=404, detail="该邮箱未注册")
    if not _can_resend(email):
        raise HTTPException(status_code=429, detail="发送过于频繁，请 60 秒后重试")

    code = _gen_code()
    _store_code(email, code)

    if not _send_email(email, code):
        _CODE_STORE.pop(email, None)
        raise HTTPException(status_code=500, detail="验证码发送失败，请稍后重试")

    return {"status": "success", "message": "验证码已发送到邮箱，5 分钟内有效"}


@router.post("/api/reset/send-sms-code", response_model=dict, tags=["密码重置"])
async def send_sms_code(req: SendSmsCodeRequest):
    phone = req.phone.strip()

    if not _phone_exists(phone):
        raise HTTPException(status_code=404, detail="该手机号未绑定账号")
    if not _can_resend(phone):
        raise HTTPException(status_code=429, detail="发送过于频繁，请 60 秒后重试")

    code = _gen_code()
    _store_code(phone, code)

    if not _send_sms(phone, code):
        _CODE_STORE.pop(phone, None)
        raise HTTPException(status_code=500, detail="短信发送失败，请稍后重试")

    return {"status": "success", "message": "验证码已发送到手机，5 分钟内有效"}


@router.post("/api/reset/password", response_model=dict, tags=["密码重置"])
async def reset_password(req: ResetPasswordRequest):
    if req.method not in ("email", "phone"):
        raise HTTPException(status_code=400, detail="method 必须是 'email' 或 'phone'")

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于 6 位")

    target = req.target.strip().lower() if req.method == "email" else req.target.strip()

    if not _verify_code(target, req.code.strip()):
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    success = (
        _reset_password_by_email(target, req.new_password)
        if req.method == "email"
        else _reset_password_by_phone(target, req.new_password)
    )
    if not success:
        raise HTTPException(status_code=500, detail="密码重置失败，请稍后重试")

    return {"status": "success", "message": "密码已重置，请重新登录"}


@router.post("/api/reset/password/email-direct", response_model=dict, tags=["密码重置"])
async def reset_password_email_direct(req: DirectEmailResetRequest):
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="邮箱不能为空")
    if not _email_exists(email):
        raise HTTPException(status_code=404, detail="该邮箱未注册")

    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于 6 位")

    if not _reset_password_by_email(email, req.new_password):
        raise HTTPException(status_code=500, detail="密码重置失败，请稍后重试")

    return {"status": "success", "message": "密码已重置，请使用新密码登录"}


@router.get("/api/reset/check-email", response_model=dict, tags=["密码重置"])
async def check_email_registered(email: str):
    exists = _email_exists(email.strip().lower())
    return {"exists": exists}
