import json
import os
import re
from datetime import date

import requests

DART_KEY = os.environ["DART_API_KEY"]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = "seen.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f)


def fetch_all_d002(today):
    """DART API로 오늘 D002 공시 목록 조회 (회사명 등 메타 포함)"""
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
    items = data.get("list", []) if data.get("status") == "000" else []
    return {i["rcept_no"]: i for i in items if "소유상황" in i.get("report_nm", "")}


def fetch_jangnaemaesu_rcepts(today):
    """DART 통합검색으로 '장내매수' 텍스트가 포함된 D002 공시의 rcpNo 목록 반환"""
    resp = requests.post(
        "https://dart.fss.or.kr/dsab001/search.ax",
        headers={**HEADERS, "X-Requested-With": "XMLHttpRequest"},
        data={
            "selectKey": "text",
            "textCrpNm": "",
            "startDate": today,
            "endDate": today,
            "publicType": "D002",
            "keyWord": "장내매수",
            "currentPage": "1",
            "maxResults": "100",
        },
        timeout=20,
    )
    text = resp.content.decode("utf-8", errors="replace")
    return set(re.findall(r"rcpNo[='](\d{14})", text))


def send_telegram(msg):
    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "HTML"},
        timeout=10,
    )


def main():
    today = date.today().strftime("%Y%m%d")

    all_d002 = fetch_all_d002(today)
    buy_rcepts = fetch_jangnaemaesu_rcepts(today)

    seen = load_seen()
    new_buys = [rcept_no for rcept_no in buy_rcepts
                if rcept_no not in seen and rcept_no in all_d002]

    # 오늘 D002 전체를 seen에 기록 (매도 포함 중복 방지)
    seen.update(all_d002.keys())

    print(f"D002 전체={len(all_d002)} 장내매수={len(buy_rcepts)} 신규알림={len(new_buys)}")

    for rcept_no in new_buys:
        item = all_d002[rcept_no]
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
