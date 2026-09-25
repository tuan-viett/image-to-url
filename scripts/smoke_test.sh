#!/usr/bin/env bash
# End-to-end smoke test for ImageURL. Hits the public host (localhost through nginx).
set -euo pipefail

BASE="${BASE_URL:-http://localhost}"
EMAIL="smoke+$(date +%s)@example.com"
PASSWORD="Smoke12345"

say() { echo -e "\033[1;34m[smoke]\033[0m $*"; }
ok()  { echo -e "\033[1;32m  ✓\033[0m $*"; }
fail(){ echo -e "\033[1;31m  ✗\033[0m $*"; exit 1; }

say "1. healthz"
H=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/healthz" || true)
[ "$H" = "200" ] && ok "healthz=200" || fail "healthz=$H"

# Build a tiny PNG (1x1 red) on the fly
TMP_PNG=$(mktemp -t smoke.XXXXXX.png)
python3 - <<'PY' > "$TMP_PNG"
import struct, zlib, sys
sig = b"\x89PNG\r\n\x1a\n"
ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
ihdr_chunk = b"IHDR" + ihdr
def chunk(t, d):
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t+d) & 0xffffffff)
data = b"\x00\xff\x00\x00"
idat = zlib.compress(data)
png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
sys.stdout.buffer.write(png)
PY

say "2. anonymous upload"
ANON=$(curl -s -F "file=@$TMP_PNG" "$BASE/api/v1/anonymous/images")
ANON_URL=$(echo "$ANON" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['url'])")
[ -n "$ANON_URL" ] && ok "anon url=$ANON_URL" || fail "anon failed: $ANON"
PATH_=$(echo "$ANON_URL" | sed "s|^$BASE||")
HEAD=$(curl -sI "$BASE$PATH_" | head -1)
echo "$HEAD" | grep -q "200" && ok "fetch $PATH_ -> 200" || fail "fetch anon: $HEAD"

say "3. register"
REG=$(curl -s -X POST "$BASE/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\",\"name\":\"Smoke\"}")
TOKEN=$(echo "$REG" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['access_token'])")
[ -n "$TOKEN" ] && ok "registered $EMAIL" || fail "register failed: $REG"

say "4. login"
LOG=$(curl -s -X POST "$BASE/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
LOG_TOKEN=$(echo "$LOG" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['access_token'])")
[ -n "$LOG_TOKEN" ] && ok "login OK" || fail "login failed: $LOG"

say "5. /me"
ME=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/auth/me")
echo "$ME" | grep -q "\"email\":\"$EMAIL\"" && ok "/me returns user" || fail "/me: $ME"

say "6. authenticated upload"
UP=$(curl -s -H "Authorization: Bearer $TOKEN" -F "file=@$TMP_PNG" "$BASE/api/v1/images")
IMG_URL=$(echo "$UP" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['url'])")
[ -n "$IMG_URL" ] && ok "auth upload url=$IMG_URL" || fail "auth upload: $UP"

say "7. list images"
LIST=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/images?page=1&page_size=10")
TOTAL=$(echo "$LIST" | python3 -c "import json,sys;print(json.load(sys.stdin)['pagination']['total'])")
[ "$TOTAL" -ge 1 ] && ok "list total=$TOTAL" || fail "list: $LIST"

say "8. plans (anonymous)"
PLANS=$(curl -s "$BASE/api/v1/plans")
N=$(echo "$PLANS" | python3 -c "import json,sys;print(len(json.load(sys.stdin)['data']))")
[ "$N" -ge 3 ] && ok "plans=$N" || fail "plans: $PLANS"

say "9. create API key"
KEY=$(curl -s -X POST "$BASE/api/v1/api-keys" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"smoke","environment":1}')
SECRET=$(echo "$KEY" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['secret'])")
[ -n "$SECRET" ] && ok "api key created" || fail "create key: $KEY"

say "10. upload with API key"
KEY_UP=$(curl -s -H "Authorization: Bearer $SECRET" -F "file=@$TMP_PNG" "$BASE/api/v1/images")
echo "$KEY_UP" | grep -q "\"url\"" && ok "upload via API key" || fail "key upload: $KEY_UP"

say "11. usage"
USE=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/usage")
echo "$USE" | grep -q "\"event_type\"" && ok "usage returned" || fail "usage: $USE"

say "12. base64 upload via JSON body"
B64=$(python3 -c "
import base64
b = open('$TMP_PNG','rb').read()
print('data:image/png;base64,' + base64.b64encode(b).decode())
")
B64_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -X POST "$BASE/api/v1/images" \
  -d "{\"image\":\"$B64\",\"filename\":\"json-b64.png\"}")
B64_URL=$(echo "$B64_RESP" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['url'])" 2>/dev/null || echo "")
[ -n "$B64_URL" ] && ok "json b64 url=$B64_URL" || fail "json b64: $B64_RESP"

# ============ SePay flow ============
say "13. SePay: get public config"
SEPAY_CFG=$(curl -s "$BASE/api/v1/payments/sepay-config")
SEPAY_ACC=$(echo "$SEPAY_CFG" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['account_number'])")
[ -n "$SEPAY_ACC" ] && ok "sepay account=$SEPAY_ACC" || fail "sepay-config: $SEPAY_CFG"

say "14. SePay: create upgrade order (plan=3 Pro)"
ORD=$(curl -s -X POST "$BASE/api/v1/payments/upgrade" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"plan_id":3}')
PID=$(echo "$ORD" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['payment']['id'])")
QR=$(echo "$ORD" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['qr_image_url'])")
[ -n "$PID" ] && ok "order id=$PID qr=${QR:0:60}…" || fail "create order: $ORD"

say "15. SePay: webhook with wrong signature (should reject 401)"
TS=$(date +%s)
DUMMY="{\"id\":1,\"transferType\":\"in\"}"
WRONG=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "X-SePay-Signature: sha256=deadbeef" \
  -H "X-SePay-Timestamp: $TS" \
  -d "$DUMMY")
[ "$WRONG" = "401" ] && ok "bad signature → 401" || fail "expected 401 got $WRONG"

say "16. SePay: signed webhook completes payment + upgrades plan"
CODE=$(echo "$ORD" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['description'])")
AMOUNT_VND=$(echo "$ORD" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['amount_vnd'])")
SECRET="${SEPAY_WEBHOOK_SECRET:-test_webhook_secret_for_local_dev_only}"
PAYLOAD=$(printf '{"id":99999999,"gateway":"MBBank","accountNumber":"%s","code":"%s","content":"%s thanh toan","transferType":"in","transferAmount":%s,"referenceCode":"SMOKE"}' \
  "$SEPAY_ACC" "$CODE" "$CODE" "$AMOUNT_VND")
TS=$(date +%s)
SIG="sha256=$(printf '%s.%s' "$TS" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" -binary | xxd -p -c 256)"
WEBHOOK=$(curl -s -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "X-SePay-Signature: $SIG" \
  -H "X-SePay-Timestamp: $TS" \
  -d "$PAYLOAD")
echo "$WEBHOOK" | grep -q '"success":true' && ok "webhook accepted" || fail "webhook: $WEBHOOK"

say "17. SePay: poll status returns is_paid=true"
STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/payments/$PID/status")
PAID=$(echo "$STATUS" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['is_paid'])")
[ "$PAID" = "True" ] && ok "payment marked paid" || fail "status: $STATUS"

say "18. SePay: webhook replay is idempotent"
TS=$(date +%s)
SIG="sha256=$(printf '%s.%s' "$TS" "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" -binary | xxd -p -c 256)"
REPLAY=$(curl -s -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "X-SePay-Signature: $SIG" -H "X-SePay-Timestamp: $TS" \
  -d "$PAYLOAD")
echo "$REPLAY" | grep -q '"already processed"' && ok "replay ignored" || fail "replay: $REPLAY"

# ====== SePay API Key auth path ======
APIKEY="${SEPAY_API_KEY:-test_apikey_for_local_dev_only}"
say "19. SePay: webhook with wrong API Key (should reject 401)"
WRONG_API=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Apikey wrong_key_xxxxxxxxxxxxxxxx" \
  -d "$DUMMY")
[ "$WRONG_API" = "401" ] && ok "bad api key → 401" || fail "expected 401 got $WRONG_API"

say "20. SePay: webhook with wrong scheme (should reject 401)"
WRONG_SCH=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $APIKEY" \
  -d "$DUMMY")
[ "$WRONG_SCH" = "401" ] && ok "Bearer scheme → 401 (must use Apikey)" || fail "expected 401 got $WRONG_SCH"

say "21. SePay: API Key auth completes payment (new order)"
ORD2=$(curl -s -X POST "$BASE/api/v1/payments/upgrade" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"plan_id":3}')
PID2=$(echo "$ORD2" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['payment']['id'])")
CODE2=$(echo "$ORD2" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['description'])")
AMOUNT2=$(echo "$ORD2" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['amount_vnd'])")
PAYLOAD2=$(printf '{"id":88888888,"gateway":"MBBank","accountNumber":"%s","code":"%s","content":"%s","transferType":"in","transferAmount":%s}' \
  "$SEPAY_ACC" "$CODE2" "$CODE2" "$AMOUNT2")
ACK=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Apikey $APIKEY" \
  -d "$PAYLOAD2")
[ "$ACK" = "200" ] && ok "api key → 200 (payment $PID2 paid)" || fail "api key webhook got $ACK"

say "22. SePay: API Key replay is idempotent"
REPLAY2=$(curl -s -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Apikey $APIKEY" \
  -d "$PAYLOAD2")
echo "$REPLAY2" | grep -q '"already processed"' && ok "api key replay ignored" || fail "replay: $REPLAY2"

# ====== Renewal: user đã ở Pro, mua Pro lần nữa → vẫn cộng credit ======
say "23. SePay: renewal (same plan) still grants credits"
# Lấy credits hiện tại
CREDITS_BEFORE=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/auth/me" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['upload_credits'])")
# Tạo order mới cho cùng plan 3 (user đã ở Pro từ test 16)
ORD3=$(curl -s -X POST "$BASE/api/v1/payments/upgrade" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"plan_id":3}')
PID3=$(echo "$ORD3" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['payment']['id'])")
CODE3=$(echo "$ORD3" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['description'])")
AMOUNT3=$(echo "$ORD3" | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['amount_vnd'])")
PAYLOAD3=$(printf '{"id":77777777,"gateway":"MBBank","accountNumber":"%s","code":"%s","content":"%s","transferType":"in","transferAmount":%s}' \
  "$SEPAY_ACC" "$CODE3" "$CODE3" "$AMOUNT3")
curl -s -o /dev/null -X POST "$BASE/api/v1/webhooks/sepay" \
  -H "Content-Type: application/json" \
  -H "Authorization: Apikey $APIKEY" \
  -d "$PAYLOAD3"
# Lấy credits sau
CREDITS_AFTER=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/auth/me" \
  | python3 -c "import json,sys;print(json.load(sys.stdin)['data']['upload_credits'])")
DELTA=$((CREDITS_AFTER - CREDITS_BEFORE))
[ "$DELTA" -gt 0 ] && ok "renewal granted +$DELTA credits ($CREDITS_BEFORE → $CREDITS_AFTER)" \
                  || fail "renewal did NOT grant credits ($CREDITS_BEFORE → $CREDITS_AFTER)"

echo -e "\n\033[1;32mAll smoke checks passed.\033[0m"