"""
全自动数据更新 v7 · football-data.org API
覆盖: 巴甲(BSA) + 欧冠(CL) + 英超(PL) + 德甲(BL1) + 意甲(SA) + 西甲(PD) + 法甲(FL1) + 荷甲(DED) + 葡超(PPL)
Rate limit: 10 req/min → 请求间隔 7s
"""
import json, os, sys, time
import requests

# ═══════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════

API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")
BASE = "https://api.football-data.org/v4"
DATA_FILE = "data.json"
H = {"X-Auth-Token": API_KEY}

# 免费层联赛 (id, 名称, emoji, 场均进球, 主胜率, 平局率)
COMPETITIONS = [
    ("BSA", "巴甲", "🇧🇷", 2.30, 0.48, 0.26),
    ("CL",  "欧冠", "🏆", 2.80, 0.46, 0.24),
    ("PL",  "英超", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", 2.75, 0.45, 0.25),
    ("BL1", "德甲", "🇩🇪", 3.05, 0.43, 0.24),
    ("SA",  "意甲", "🇮🇹", 2.65, 0.41, 0.27),
    ("PD",  "西甲", "🇪🇸", 2.55, 0.47, 0.25),
    ("FL1", "法甲", "🇫🇷", 2.70, 0.42, 0.27),
    ("DED", "荷甲", "🇳🇱", 3.10, 0.45, 0.23),
    ("PPL", "葡超", "🇵🇹", 2.55, 0.46, 0.25),
    ("ELC", "英冠", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", 2.50, 0.43, 0.28),
]

# 比赛日查询窗口 (前后各N天)
DAY_WINDOW = 4

# Rate limit 安全间隔
REQ_GAP = 7.0  # 秒
_last_req = 0


def rate_limit():
    """确保请求间隔 ≥ REQ_GAP 秒"""
    global _last_req
    now = time.time()
    wait = REQ_GAP - (now - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()


def api(url, timeout=15, retries=2):
    """带rate-limit+超时重试的API请求, 返回JSON或None"""
    rate_limit()
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.status_code == 429:
                print(f"  ⚠️ Rate limited, sleeping 65s...")
                time.sleep(65)
                return api(url, timeout, retries)
            if r.ok:
                return r.json()
            print(f"  ❌ HTTP {r.status_code}: {url}")
            return None
        except Exception as e:
            if attempt < retries:
                print(f"  ⏳ 超时重试({attempt+1}/{retries})...")
                time.sleep(3)
            else:
                print(f"  ❌ {e}")
                return None


# ═══════════════════════════════════════════
#  数据抓取
# ═══════════════════════════════════════════

def fetch_standings(comp_id):
    """获取联赛排名 → {team_id: rank}"""
    data = api(f"{BASE}/competitions/{comp_id}/standings")
    if not data or not data.get("standings"):
        return {}
    ranks = {}
    for entry in data["standings"][0]["table"]:
        ranks[entry["team"]["id"]] = entry["position"]
    return ranks


def fetch_matches(comp_id, date_from, date_to):
    """获取指定日期范围的未开赛比赛"""
    url = f"{BASE}/competitions/{comp_id}/matches?dateFrom={date_from}&dateTo={date_to}&status=SCHEDULED"
    data = api(url)
    if not data:
        return []
    return data.get("matches", [])


def fetch_team_form(team_id, team_name):
    """获取球队近5场战绩 → (wdl_string, form_analysis)"""
    url = f"{BASE}/teams/{team_id}/matches?limit=5&status=FINISHED"
    data = api(url)
    if not data:
        return ("?", "数据缺失")

    matches = data.get("matches", [])
    if not matches:
        return ("?", "无近期数据")

    wdl = []
    home_results = []
    away_results = []
    goals_for = 0
    goals_against = 0

    for m in matches:
        is_home = m["homeTeam"]["id"] == team_id
        home_goals = m["score"]["fullTime"]["home"]
        away_goals = m["score"]["fullTime"]["away"]

        if is_home:
            gf = home_goals
            ga = away_goals
            home_results.append("W" if gf > ga else ("D" if gf == ga else "L"))
        else:
            gf = away_goals
            ga = home_goals
            away_results.append("W" if gf > ga else ("D" if gf == ga else "L"))

        goals_for += gf
        goals_against += ga

        if gf > ga:
            wdl.append("W")
        elif gf == ga:
            wdl.append("D")
        else:
            wdl.append("L")

    wdl_str = "".join(wdl)
    w = wdl.count("W")
    d = wdl.count("D")
    l = wdl.count("L")

    # 状态分析
    parts = [f"近{len(wdl)}场{w}胜{d}平{l}负"]

    # 连胜/连败检测
    streak = 1
    for i in range(1, len(wdl)):
        if wdl[i] == wdl[0]:
            streak += 1
        else:
            break
    if streak >= 3 and wdl[0] == "W":
        parts.append(f"{streak}连胜")
    elif streak >= 3 and wdl[0] == "L":
        parts.append(f"{streak}连败")
    elif streak >= 2 and wdl[0] == "D":
        parts.append(f"连续{streak}场平局")

    # 状态评级
    if w >= 4:
        parts.insert(0, "状态火爆")
    elif w >= 3:
        parts.insert(0, "状态良好")
    elif l >= 4:
        parts.insert(0, "状态低迷")
    elif w + d >= 4:
        parts.insert(0, "状态平稳")
    elif l >= 3:
        parts.insert(0, "状态下滑")

    # 主客场特征
    if home_results:
        hw = home_results.count("W")
        if hw >= 3:
            parts.append("主场强势")
    if away_results:
        al = away_results.count("L")
        if al >= 3:
            parts.append("客场疲软")
        aw = away_results.count("W")
        if aw >= 3:
            parts.append("客场强势")

    form_text = "，".join(parts)
    return (wdl_str, form_text)


# ═══════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════

def main():
    today = time.strftime("%Y-%m-%d")
    print(f"📡 {time.strftime('%Y-%m-%d %H:%M')} v7 football-data.org")

    # 日期窗口
    # 使用 time.strftime 避免跨天问题
    date_from = today
    # date_to = today + DAY_WINDOW days
    date_to = time.strftime(
        "%Y-%m-%d",
        time.localtime(time.time() + DAY_WINDOW * 86400)
    )

    # 读取已有数据 (保留history, rules, yesterday)
    existing = {"history": [], "rules": [], "yesterday": {"results": []}}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except:
            pass

    all_matches = []
    active_leagues = []

    for comp_id, lname, flag, avg_g, hw_r, dr_r in COMPETITIONS:
        # 获取排名
        ranks = fetch_standings(comp_id)
        if not ranks:
            print(f"  {flag} {lname}: 排名获取失败或休赛期")
            continue

        # 获取比赛
        raw_matches = fetch_matches(comp_id, date_from, date_to)
        if not raw_matches:
            print(f"  {flag} {lname}: 0场比赛")
            continue

        print(f"  {flag} {lname}: {len(raw_matches)}场, 排名{len(ranks)}队")

        # 收集需要查状态的球队 (去重)
        team_ids = set()
        for m in raw_matches:
            team_ids.add(m["homeTeam"]["id"])
            team_ids.add(m["awayTeam"]["id"])

        # 批量获取球队状态
        team_forms = {}
        for tid in team_ids:
            tname = next(
                (m["homeTeam"]["name"] for m in raw_matches if m["homeTeam"]["id"] == tid),
                next((m["awayTeam"]["name"] for m in raw_matches if m["awayTeam"]["id"] == tid), f"Team#{tid}")
            )
            team_forms[tid] = fetch_team_form(tid, tname)

        # 组装比赛数据
        for m in raw_matches:
            ht_id = m["homeTeam"]["id"]
            at_id = m["awayTeam"]["id"]
            ht_name = m["homeTeam"]["name"]
            at_name = m["awayTeam"]["name"]

            # 北京时间 (UTC+8)
            utc_str = m["utcDate"]
            try:
                from datetime import datetime, timezone, timedelta
                utc_dt = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
                bj_dt = utc_dt + timedelta(hours=8)
                bj_time = bj_dt.strftime("%m-%d %H:%M")
                short_time = bj_dt.strftime("%H:%M")
            except:
                # fallback: 手动解析
                bj_time = utc_str[:16].replace("T", " ") if "T" in utc_str else utc_str[:16]
                short_time = bj_time[-5:] if len(bj_time) >= 5 else bj_time

            h_rank = ranks.get(ht_id, 0)
            a_rank = ranks.get(at_id, 0)

            h_wdl, h_form = team_forms.get(ht_id, ("?", "数据缺失"))
            a_wdl, a_form = team_forms.get(at_id, ("?", "数据缺失"))

            fm_text = f"主({h_wdl}): {h_form} | 客({a_wdl}): {a_form}"

            all_matches.append({
                "id": len(all_matches) + 1,
                "lg": f"{flag} {lname}",
                "tm": short_time,
                "h": ht_name,
                "a": at_name,
                "hr": h_rank,
                "ar": a_rank,
                "odds": "待获取",
                "h2h": "数据待补充",
                "inj": "无关键伤停",
                "fm": fm_text,
                "xp": "football-data.org",
                "_source": "football-data",
                "_comp_id": comp_id,
                "_match_id": m.get("id"),
                "_date": bj_time,
            })

        active_leagues.append(f"{flag}{lname}")

    # 按时间排序
    all_matches.sort(key=lambda x: x.get("tm", "99:99"))

    # 去重(同队同时段只保留一场, 按比赛ID去重)
    seen = set()
    unique = []
    for m in all_matches:
        key = f"{m['h']}|{m['a']}|{m['tm']}"
        if key not in seen:
            seen.add(key)
            unique.append(m)
    all_matches = unique

    # 重新分配ID
    for i, m in enumerate(all_matches):
        m["id"] = i + 1

    # 构建输出
    existing["updated"] = time.strftime("%Y-%m-%d %H:%M")
    existing["today"] = {"date": today, "matches": all_matches}

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"✅ {len(all_matches)}场 [{', '.join(active_leagues) if active_leagues else '休赛期无比赛'}] → {DATA_FILE}")
    print(f"   Rate limit: {10/REQ_GAP:.1f} req/min (安全间隔{REQ_GAP}s)")


if __name__ == "__main__":
    main()
