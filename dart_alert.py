import io
import json
import os
import zipfile
from datetime import date

import requests

DART_KEY = os.environ["DART_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = "seen.json"


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f)


def fetch_disclosures(today):
    resp = requests.get(
        "https://opendart.fss.or.kr/api/list.json",
        params={
            "crtfc_key": DART_KEY,
            "bgn_de": today,
            "end_de": today,
            "pblntf_ty": "D",
            "page_count": 100,
        },
        timeout=10,
    )
    data = resp.json()
    print(f"[DART API] status={data.get('status')}, total={data.get('total_count', 0)}")
    items = data.get("list", []) if data.get("status") == "000" else []
    filtered = [i for i in items if "소유상황" in i.get("report_nm", "")]
    print(f"[DART] 소유상황 공시 {len(filtered)}건: {[i.get('corp_name') for i in filtered]}")
    return filtered


def read_zip_text(content_bytes, debug=False):
    texts = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(content_bytes))
        if debug:
            print(f"[ZIP] 파일목록: {zf.namelist()}")
        for fname in zf.namelist():
            raw = zf.read(fname)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    text = raw.decode(enc)
                    if debug:
                        print(f"[ZIP] {fname} ({enc}) 앞200자: {text[:200]}")
                    texts.append(text)
                    break
                except Exception:
                    continue
    except Exception as e:
        if debug:
            print(f"[ZIP] zip 오류: {e}")
    return "\n".join(texts)


DEBUG_RCEPT = "20260629000133"  # 삼성중공업


def is_jangnaemaesu(rcept_no):
    debug = (rcept_no == DEBUG_RCEPT)
    try:
        resp = requests.get(
            "https://opendart.fss.or.kr/api/document.json",
            params={"crtfc_key": DART_KEY, "rcept_no": rcept_no},
            timeout=20,
        )
        if debug:
            print(f"[DOC] HTTP={resp.status_code} size={len(resp.content)} type={resp.headers.get('content-type','')}")
        text = read_zip_text(resp.content, debug=debug)
        found = "장내매수" in text
        if debug or found:
            print(f"[DOC] {rcept_no} 장내매수={found}")
        return found
    except Exception as e:
        print(f"[DOC] {rcept_no} 오류: {e}")
        return False


def send_telegram(msg):
    resp = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
        timeout=10,
    )
    print(f"[TG] status={resp.status_code} body={resp.text[:200]}")


def main():
    # 삼성중공업 공시 고정 디버그
    print("[FIXED DEBUG] 삼성중공업 20260629000133 직접 검사")
    is_jangnaemaesu("20260629000133")

    today = date.today().strftime("%Y%m%d")
    items = fetch_disclosures(today)

    seen = load_seen()
    new_items = [i for i in items if i["rcept_no"] not in seen]
    print(f"[SEEN] 신규 공시 {len(new_items)}건")

    for item in new_items:
        rcept_no = item["rcept_no"]
        seen.add(rcept_no)

        if not is_jangnaemaesu(rcept_no):
            continue

        corp = item.get("corp_name", "")
        filer = item.get("flr_nm", "")
        link = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

        msg = (
            f"🟢 <b>임원·주요주주 장내매수</b>\n"
            f"종목: <b>{corp}</b>\n"
            f"보고자: {filer}\n"
            f'<a href="{link}">공시 원문 →</a>'
        )
        send_telegram(msg)

    save_seen(seen)


if __name__ == "__main__":
    main()
