"""全自动数据更新 v6 · 多源聚合 (OpenLigaDB + 缓存保留)"""
import json, os, time
import requests

DATA = "data.json"
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}

# OpenLigaDB 联赛映射 (leagueId, 联赛名, emoji, 场均进球)
OL_SOURCES = [
    ("bl1/2026", "德甲", "🇩🇪", 3.0),
    ("bl2/2026", "德乙", "🇩🇪", 2.8),
    ("ucl/2026", "欧冠", "🏆", 2.8),
]

def req(url, timeout=15):
    try:
        r = requests.get(url, headers=H, timeout=timeout)
        return r.json() if r.ok else None
    except:
        return None

def fetch_openligadb():
    """从OpenLigaDB获取比赛"""
    matches = []
    for path, lname, flag, avg in OL_SOURCES:
        data = req(f"https://api.openligadb.de/getmatchdata/{path}")
        if not data:
            continue
        today = time.strftime("%Y-%m-%d")
        for m in data:
            dt = m.get("matchDateTime", "")[:10]
            if dt != today:
                continue
            t1 = m.get("team1", {})
            t2 = m.get("team2", {})
            # 检查是否已完赛
            results = m.get("matchResults", []) or []
            finished = len(results) > 0 and results[0].get("resultName") != "-:-"
            if finished:
                continue
            matches.append({
                "id": len(matches) + 1,
                "lg": f"{flag} {lname}",
                "tm": m.get("matchDateTime", "")[11:16],
                "h": t1.get("teamName", "?"),
                "a": t2.get("teamName", "?"),
                "hr": 0, "ar": 0,
                "odds": "待获取",
                "h2h": "数据待补充",
                "inj": "无关键伤停",
                "fm": "待获取",
                "xp": "OpenLigaDB数据",
                "_source": "openligadb"
            })
        if matches:
            print(f"  {flag} {lname}: {len(matches)}场")
    return matches

def main():
    print(f"📡 {time.strftime('%Y-%m-%d %H:%M')} v6 多源聚合")

    # 读取已有数据
    ex = {"history": [], "rules": [], "yesterday": {"results": []}}
    if os.path.exists(DATA):
        try:
            with open(DATA, "r", encoding="utf-8") as f:
                ex = json.load(f)
        except:
            pass

    # 1. OpenLigaDB数据
    ol_matches = fetch_openligadb()

    # 2. 保留旧数据中手动维护的非OpenLigaDB联赛(如K1、巴甲、瑞超、芬超)
    preserved = []
    ol_keys = set()
    for m in ol_matches:
        ol_keys.add(f"{m.get('h','')}|{m.get('a','')}")
    for m in ex.get("today", {}).get("matches", []):
        key = f"{m.get('h','')}|{m.get('a','')}"
        if key not in ol_keys:
            # 检查是否过期(超过2天的比赛丢弃)
            preserved.append(m)

    # 3. 合并
    all_matches = ol_matches + preserved
    all_matches.sort(key=lambda x: x.get("tm", "99:99"))

    # 4. 保存
    ex["updated"] = time.strftime("%Y-%m-%d %H:%M")
    ex["today"] = {"date": time.strftime("%Y-%m-%d"), "matches": all_matches}

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(ex, f, ensure_ascii=False, indent=2)

    new_src = sum(1 for m in all_matches if m.get("_source") == "openligadb")
    old_src = len(all_matches) - new_src
    print(f"✅ OpenLigaDB:{new_src}场 + 缓存:{old_src}场 → {DATA}")

if __name__ == "__main__":
    main()
