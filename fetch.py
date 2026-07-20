"""GitHub Action 数据抓取脚本 · 每3小时自动运行"""
import json, os, sys, time
import requests

DATA_FILE = "data.json"
LEAGUES = [
    ("47", "瑞超", "🇸🇪"),
    ("49", "芬超", "🇫🇮"),
    ("76", "K1", "🇰🇷"),
]

def fetch_fotmob(lid, lname, lflag):
    """抓一个联赛的数据"""
    try:
        r = requests.get(
            f"https://www.fotmob.com/api/leagues?id={lid}&season=2026",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20
        )
        data = r.json()
    except Exception as e:
        print(f"  ⚠️ {lname}: {e}")
        return [],[]

    today = time.strftime("%Y-%m-%d")
    upcoming, finished = [], []

    for m in data.get("matches",{}).get("allMatches",[]):
        st = m.get("status",{})
        md = (st.get("utcTime","") or "")[:10]
        home = m.get("home",{}).get("name","?")
        away = m.get("away",{}).get("name","?")

        if md == today and not st.get("finished"):
            upcoming.append({
                "lg": f"{lflag} {lname}",
                "tm": (st.get("utcTime","") or "")[11:16],
                "h": home, "a": away,
                "hr": m.get("home",{}).get("rank",0),
                "ar": m.get("away",{}).get("rank",0)
            })
        elif st.get("finished"):
            finished.append({
                "date": md,
                "match": f"{home} vs {away}",
                "result": f"{st.get('homeScore',0)}-{st.get('awayScore',0)}",
                "league": lname
            })

    return upcoming, finished

def main():
    print(f"📡 {time.strftime('%Y-%m-%d %H:%M')} 开始抓取...")

    # 读取现有数据（保留历史/规则）
    existing = {"history":[], "rules":[], "yesterday":{"results":[]}}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE,"r",encoding="utf-8") as f:
                existing = json.load(f)
        except:
            pass

    all_up, all_done = [], []
    for lid, lname, lflag in LEAGUES:
        up, done = fetch_fotmob(lid, lname, lflag)
        all_up.extend(up); all_done.extend(done)
        if up: print(f"  {lflag} {lname}: {len(up)}场")

    # 合并结果
    existing["updated"] = time.strftime("%Y-%m-%d %H:%M")
    existing["today"] = {
        "date": time.strftime("%Y-%m-%d"),
        "matches": all_up
    }
    # 追加新赛果
    if all_done:
        old_results = existing.get("yesterday",{}).get("results",[])
        old_matches = {r.get("match","") for r in old_results}
        for r in all_done:
            if r["match"] not in old_matches:
                old_results.append({**r, "w": None, "p": "", "note": "自动收录"})
        existing["yesterday"]["results"] = old_results[-20:]  # 只保留最近20条
        existing["yesterday"]["date"] = all_done[-1]["date"]

    with open(DATA_FILE,"w",encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"✅ 共 {len(all_up)} 场今日, {len(all_done)} 条新赛果 → {DATA_FILE}")

if __name__ == "__main__":
    main()
