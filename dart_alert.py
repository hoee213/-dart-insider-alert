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
            "pblntf_detail_ty": "D002",  # 임원·주요주주특정증권등소유상황보고서
            "page_count": 100,
        },
        timeout=10,
    )
    data = resp.json()
    if data.get("status") == "000":
        return data.get("list", [])
    return []


def is_jangnaemaesu(rcept_no):
    """공시 원문 XML에서 '장내매수' 텍스트 확인"""
    try:
        resp = requests.get(
            "https://opendart.fss.or.kr/api/document.json",
            params={"crtfc_key": DART_KEY, "rcept_no": rcept_no},
            timeout=20,
        )
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        for fname in zf.namelist():
            if fname.lower().endswith(".xml"):
                content = zf.read(fname).decode("utf-8", errors="ignore")
                if "장내매수" in content:
                    return True
        return False
    except Exception:
        return False


def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
        timeout=10,
    )


def main():
    today = date.today().strftime("%Y%m%d")
    items = fetch_disclosures(today)

    seen = load_seen()
    new_items = [i for i in items if i["rcept_no"] not in seen]

    for item in new_items:
        rcept_no = item["rcept_no"]
        seen.add(rcept_no)  # 매수/매도 무관하게 중복 방지

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
