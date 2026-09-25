"""SePay QR + webhook helpers.

Docs: https://developer.sepay.vn/vi/sepay-webhooks/xac-thuc

Two responsibilities:

1. ``build_qr_url`` — render URL ảnh QR SePay cho frontend:
       https://qr.sepay.vn/img?bank=...&acc=...&amount=...&description=...&template=...

2. Webhook verification — 3 phương thức SePay hỗ trợ:
   - ``verify_webhook``     HMAC-SHA256 — khuyến nghị (chống tamper + replay)
   - ``verify_api_key``     Authorization: Apikey <key> — đơn giản, chỉ verify nguồn
   - ``verify_oauth_bearer`` Authorization: Bearer <token> — OAuth2 client_credentials

Toàn bộ tham số SePay (bank, account, secret, api_key, ttl, template) đọc
từ bảng ``configs`` (single source of truth). Seed chạy idempotent tạo sẵn
placeholder rows ở ``app/seed.py``. Đổi giá trị runtime bằng SQL:
    UPDATE configs SET config_value='...' WHERE config_key='sepay.webhook_secret';
KHÔNG cần rebuild container, KHÔNG đọc env.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.config import Config


# Replay window (seconds) — same as PHP reference impl.
REPLAY_WINDOW_SECONDS = 300

# Map keyword → ngân hàng cho SePay QR (theo docs).
DEFAULT_BANK_CODE = "MBBank"   # Dùng khi row configs chưa có hoặc rỗng
DEFAULT_TEMPLATE = "compact"   # compact | print | qr_only
DEFAULT_QR_TTL_MINUTES = 15


@dataclass(frozen=True)
class SepayAccount:
    bank_code: str
    account_number: str
    account_name: str
    template: str  # compact | print | qr_only
    qr_ttl_minutes: int


def _read_cfg(db: Session, key: str, default: str = "") -> str:
    """Đọc 1 key từ bảng ``configs``. Trả về ``default`` nếu row thiếu / rỗng.

    Caller nên xử lý default một cách hợp lý — ví dụ tài khoản ngân hàng
    trống thì webhook/QR không dùng được, không nên âm thầm fallback về
    placeholder dev.
    """
    row = db.scalar(select(Config).where(Config.config_key == key))
    if row and row.config_value and row.config_value.strip():
        return row.config_value.strip()
    return default


def load_sepay_account(db: Session) -> SepayAccount:
    """Đọc thông tin TK nhận từ bảng ``configs`` (single source of truth).

    Nếu ``sepay.account_number`` rỗng → trả về ``account_number=""``.
    Caller (router payments) sẽ từ chối tạo payment nếu tài khoản rỗng.
    """
    bank = _read_cfg(db, Config.KEY_SEPAY_BANK, DEFAULT_BANK_CODE)
    account = _read_cfg(db, Config.KEY_SEPAY_ACCOUNT, "")
    name = _read_cfg(db, Config.KEY_SEPAY_ACCOUNT_NAME, "")
    template = _read_cfg(db, Config.KEY_SEPAY_TEMPLATE, DEFAULT_TEMPLATE)
    ttl_raw = _read_cfg(db, Config.KEY_SEPAY_QR_TTL_MINUTES, str(DEFAULT_QR_TTL_MINUTES))

    try:
        ttl = int(ttl_raw) if ttl_raw else DEFAULT_QR_TTL_MINUTES
    except ValueError:
        ttl = DEFAULT_QR_TTL_MINUTES
    ttl = max(1, min(ttl, 60))

    return SepayAccount(
        bank_code=bank,
        account_number=account,
        account_name=name or "",
        template=template or DEFAULT_TEMPLATE,
        qr_ttl_minutes=ttl,
    )


def load_vietqr_store(db: Session) -> str:
    """Tên cửa hàng hiển thị trên VietQR (query param ``store``).

    Optional. Nếu row ``sepay.store_name`` rỗng → trả về ``""`` và
    ``build_qr_url`` sẽ bỏ qua param ``store``.
    """
    return _read_cfg(db, Config.KEY_SEPAY_STORE, "")


def resolve_webhook_secret(db: Session) -> str:
    """Webhook HMAC secret. Đọc thẳng bảng ``configs``.

    Trả về chuỗi rỗng nếu row ``sepay.webhook_secret`` rỗng — caller
    sẽ từ chối mọi request và log cảnh báo. KHÔNG đọc env.
    """
    return _read_cfg(db, Config.KEY_SEPAY_WEBHOOK_SECRET, "")


def resolve_webhook_api_key(db: Session) -> str:
    """API Key cho header ``Authorization: Apikey <key>``. Đọc thẳng bảng ``configs``.

    Trả về rỗng nếu chưa cấu hình. KHÔNG đọc env.
    """
    return _read_cfg(db, Config.KEY_SEPAY_WEBHOOK_API_KEY, "")


def build_qr_url(
    *,
    bank_code: str,
    account_number: str,
    amount_vnd: int,
    description: str,
    account_name: str = "",
    template: str = "compact",
    store_name: str = "",
) -> str:
    """Render URL ảnh QR VietQR (https://vietqr.app).

    Format query theo docs VietQR:
        ?bank=<BIN/BIC>&acc=<STK>&template=<...>&des=<nội dung>&amount=<...>
        &showinfo=true|false&holder=<chủ TK>&store=<tên cửa hàng>

    Lưu ý:
    - ``des`` là tên field của VietQR (khác với SePay dùng ``description``).
    - Webhook vẫn do SePay xử lý — VietQR chỉ là QR image renderer, không có
      payment gateway riêng. SePay match theo substring của nội dung CK
      (đã được set trong ``des``) → đẩy về ``/api/v1/webhooks/sepay``.
    """
    base = "https://vietqr.app/img"
    params = [
        f"bank={quote(bank_code)}",
        f"acc={quote(account_number)}",
        f"template={quote(template)}",
        f"des={quote(description)}",          # ← field là ``des`` (không phải description)
    ]
    if amount_vnd > 0:
        # VietQR optional — bỏ qua nếu amount=0 để cho user tự nhập.
        params.append(f"amount={int(amount_vnd)}")
    params.append("showinfo=true")
    if account_name:
        params.append(f"holder={quote(account_name)}")
    if store_name:
        params.append(f"store={quote(store_name)}")
    return f"{base}?{'&'.join(params)}"


def build_payment_description(
    *, code: str, prefix: str = "IMGU", short_code: Optional[str] = None,
) -> str:
    """Tạo nội dung CK mà user phải ghi khi CK.

    Format dính liền: ``<prefix><code>`` (vd: ``IMGUAB12CD`` — 10 ký tự).
    KHÔNG dấu cách giữa prefix và code để VietQR QR render đúng và SePay match
    substring chính xác hơn.
    """
    body = short_code or code
    return f"{prefix}{body}".strip()


def verify_webhook(
    *,
    raw_body: bytes,
    signature_header: Optional[str],
    timestamp_header: Optional[str],
    secret: str,
    now_ts: Optional[int] = None,
) -> tuple[bool, str]:
    """Xác thực webhook SePay bằng HMAC-SHA256.

    Returns (ok, reason). Ký số không hợp lệ / hết hạn → (False, reason).
    Caller KHÔNG được parse body cho đến khi ``ok == True``.

    Header format: ``X-SePay-Signature: sha256=<hexdigest>``
    """
    if not secret:
        return False, "webhook secret not configured"
    if not signature_header or not timestamp_header:
        return False, "missing signature or timestamp header"

    # Replay protection
    try:
        ts = int(timestamp_header)
    except ValueError:
        return False, "invalid timestamp header"
    now = int(now_ts if now_ts is not None else time.time())
    if abs(now - ts) > REPLAY_WINDOW_SECONDS:
        return False, "request expired (replay window > 5min)"

    # HMAC-SHA256("{timestamp}.{raw_body}", secret) compared via constant-time
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        f"{ts}.".encode("utf-8") + raw_body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        return False, "invalid signature"
    return True, "ok"


def verify_api_key(
    *,
    auth_header: Optional[str],
    expected_key: str,
) -> tuple[bool, str]:
    """Xác thực webhook SePay bằng API Key (đơn giản hơn HMAC).

    Header format: ``Authorization: Apikey YOUR_API_KEY`` (theo docs SePay).
    So sánh constant-time để chống timing attack.

    Lưu ý bảo mật: API Key chỉ xác minh request đến từ SePay, không chống
    tamper/replay. Nếu cần bảo mật cao hơn → dùng HMAC.
    """
    if not expected_key:
        return False, "API key not configured"
    if not auth_header:
        return False, "missing Authorization header"
    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "apikey":
        return False, "wrong auth scheme (expected: Apikey <key>)"
    presented = parts[1].strip()
    if not presented:
        return False, "empty API key"
    if not hmac.compare_digest(presented, expected_key):
        return False, "invalid API key"
    return True, "ok"


def verify_oauth_bearer(
    *,
    auth_header: Optional[str],
    expected_token: str,
) -> tuple[bool, str]:
    """Xác thực webhook SePay bằng OAuth 2.0 Bearer token.

    Header format: ``Authorization: Bearer <access_token>`` (theo docs SePay).
    Token do SePay cấp qua flow client_credentials; SePay tự refresh khi hết hạn.

    Trong MVP mình chỉ verify constant-time so với token đã lưu; production nên
    gọi SePay OAuth introspection endpoint để kiểm tra expiry/revoke.
    """
    if not expected_token:
        return False, "OAuth token not configured"
    if not auth_header:
        return False, "missing Authorization header"
    parts = auth_header.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False, "wrong auth scheme (expected: Bearer <token>)"
    presented = parts[1].strip()
    if not presented:
        return False, "empty bearer token"
    if not hmac.compare_digest(presented, expected_token):
        return False, "invalid bearer token"
    return True, "ok"


def slug_code() -> str:
    """Sinh mã nội dung CK 8 ký tự A-Z0-9, dễ đọc trên app ngân hàng."""
    import secrets
    import string
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))