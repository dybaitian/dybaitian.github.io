"""全自动数据抓取 v5 · Fotmob深度 + 赔率 + 状态 + H2H"""
import json, os, time, re
import requests

DATA = "data.json"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
LEAGUES = [
    ("76",  "K1",   "🇰🇷", 2.45, 0.43, 0.27),
    ("325", "巴甲", "🇧🇷", 2.30, 0.48, 0.26),
    ("42",  "欧冠", "🏆", 2.80, 0.46, 0.24),
    ("47",  "瑞超", "🇸🇪", 2.65, 0.42, 0.26),
    ("49",  "芬超", "🇫🇮", 2.60, 0.40, 0.28),
]

def req(url, timeout=20):
    try:
        r = requests.get(url, headers=H, timeout=timeout)
        ct = r.headers.get("content-type", "")
        return r.json() if "application/json" in ct else r.text
    except:
        return None

def get_team_form(team_id):
    """获取球队近5场W/D/L"""
    d = req(f"https://www.fotmob.com/api/teams?id={team_id}")
    if not d:
        return "?", "?"
    form = []
    form_detail = []
    matches = sorted(
        d.get("matches", {}).get("allMatches", []),
        key=lambda x: x.get("status", {}).get("utcTime", ""),
        reverse=True
    )
    for m in matches[:8]:
        st = m.get("status", {})
        if not st.get("finished"):
            continue
        hs, as_ = st.get("homeScore", 0), st.get("awayScore", 0)
        is_home = m.get("home", {}).get("id") == team_id
        opp = m.get("away" if is_home else "home", {}).get("name", "?")
        if is_home:
            if hs > as_:
                form.append("W"); form_detail.append(f"{hs}-{as_}vs{opp}")
            elif hs < as_:
                form.append("L"); form_detail.append(f"{hs}-{as_}vs{opp}")
            else:
                form.append("D"); form_detail.append(f"{hs}-{as_}vs{opp}")
        else:
            if as_ > hs:
                form.append("W"); form_detail.append(f"{as_}-{hs}at{opp}")
            elif as_ < hs:
                form.append("L"); form_detail.append(f"{as_}-{hs}at{opp}")
            else:
                form.append("D"); form_detail.append(f"{as_}-{hs}at{opp}")
        if len(form) == 5:
            break
    fs = "".join(form) if form else "?"
    fd = " | ".join(form_detail) if form_detail else "?"
    return fs, fd

def analyze_form(fs):
    """解读近5场状态，返回描述文本"""
    if not fs or fs == "?":
        return "数据不足"
    w, l, d = fs.count("W"), fs.count("L"), fs.count("D")
    parts = []
    if w >= 4: parts.append(f"状态火爆({w}胜)")
    elif w >= 3: parts.append("状态良好")
    elif w == 0: parts.append("一胜难求")
    if l >= 4: parts.append(f"状态低迷({l}负)")
    elif l >= 3: parts.append("状态下滑")
    if d >= 3: parts.append(f"平局率高({d*20}%)")
    if "WWW" in fs: parts.append("3连胜中")
    elif "WW" in fs: parts.append("2连胜中")
    if "LLL" in fs: parts.append("3连败中")
    elif "LL" in fs: parts.append("2连败中")
    if "DDD" in fs: parts.append("连续平局")
    return "; ".join(parts) if parts else "表现一般"

def get_h2h(home_id, away_id, home_name, away_name):
    """获取H2H交锋记录"""
    d = req(f"https://www.fotmob.com/api/matches?teamId={home_id}&teamId2={away_id}")
    if not d:
        return f"{home_name}与{away_name}近期无交手", 0, 0
    ms = d if isinstance(d, list) else d.get("matches", []) or []
    h_w, h_d, a_w = 0, 0, 0
    for m in ms[:12]:
        st = m.get("status", {})
        if not st.get("finished"):
            continue
        hs, as_ = st.get("homeScore", 0), st.get("awayScore", 0)
        h = m.get("home", {}).get("name", "")
        if h == home_name:
            if hs > as_: h_w += 1
            elif hs < as_: a_w += 1
            else: h_d += 1
        else:
            if as_ > hs: h_w += 1
            elif as_ < hs: a_w += 1
            else: h_d += 1
    total = h_w + h_d + a_w
    if total == 0:
        return f"{home_name}与{away_name}无交手记录", 0, 0
    if h_w >= 7:
        return f"血脉压制! {home_name}近{total}次{h_w}胜{h_d}平{a_w}负", h_w, a_w
    if a_w >= 7:
        return f"血脉压制! {away_name}近{total}次{a_w}胜{h_d}平{h_w}负", h_w, a_w
    if h_w >= 5:
        return f"{home_name}占优({h_w}胜{h_d}平{a_w}负)", h_w, a_w
    if a_w >= 5:
        return f"{away_name}占优({a_w}胜{h_d}平{h_w}负)", h_w, a_w
    if h_w == 0 and total >= 4:
        return f"⚠️ {home_name}近{total}次0胜! 极端劣势", h_w, a_w
    if a_w == 0 and total >= 4:
        return f"⚠️ {away_name}近{total}次0胜! 极端劣势", h_w, a_w
    return f"接近({h_w}胜{h_d}平{a_w}负)", h_w, a_w

def get_injuries(team_id):
    """尝试从Fotmob获取伤停信息"""
    d = req(f"https://www.fotmob.com/api/teams?id={team_id}")
    if not d:
        return "无伤停数据"
    players = d.get("squad", []) or d.get("players", []) or []
    injured = []
    for p in players[:35]:
        name = p.get("name", "") or f"{p.get('firstName','')} {p.get('lastName','')}".strip()
        status = (p.get("injuryStatus", "") or p.get("status", "") or "").lower()
        if any(k in status for k in ["injured", "suspended", "unavailable", "out"]):
            injured.append(name)
    if injured:
        return f"缺阵: {', '.join(injured[:5])}"
    return "无关键伤停"

def get_match_odds(match_id):
    """从Fotmob比赛详情获取赔率"""
    d = req(f"https://www.fotmob.com/api/matchDetails?matchId={match_id}")
    if not d:
        return ""
    # 尝试从content.odds获取
    content = d.get("content", {}) or {}
    odds_data = content.get("odds", {}) or d.get("odds", {})
    if not odds_data:
        return ""
    # Fotmob odds结构: odds.{bookmaker}.matchOdds.{1,x,2}
    # 尝试取Bet365或平均
    for bk in ["bet365", "Bet365", "pinnacle", "Pinnacle", "william hill", "betfair"]:
        bk_odds = odds_data.get(bk, {}) or {}
        mo = bk_odds.get("matchOdds", {}) or bk_odds.get("match", {})
        if mo:
            w = mo.get("1", mo.get("home", 0))
            d_raw = mo.get("x", mo.get("X", mo.get("draw", 0)))
            l = mo.get("2", mo.get("away", 0))
            if w and d_raw and l:
                return f"{float(w):.2f}/{float(d_raw):.2f}/{float(l):.2f}"
    # 取第一个有数据的bookmaker
    for bk_name, bk_data in odds_data.items():
        if isinstance(bk_data, dict):
            mo = bk_data.get("matchOdds", {}) or bk_data.get("match", {})
            w = mo.get("1", mo.get("home", 0))
            d_raw = mo.get("x", mo.get("X", mo.get("draw", 0)))
            l = mo.get("2", mo.get("away", 0))
            if w and d_raw and l:
                return f"{float(w):.2f}/{float(d_raw):.2f}/{float(l):.2f}"
    return ""

def get_expert_consensus(home_name, away_name, odds_str):
    """根据赔率推导市场共识"""
    if not odds_str:
        return "赔率待获取"
    try:
        w, d_raw, l = [float(x) for x in odds_str.split("/")]
        parts = []
        if w < 1.50:
            parts.append(f"市场强烈看好{home_name}")
        elif l < 1.50:
            parts.append(f"市场强烈看好{away_name}")
        elif abs(w - l) < 0.30:
            parts.append("市场认为势均力敌")
        elif w < l:
            parts.append(f"市场倾向{home_name}不败")
        else:
            parts.append(f"市场倾向{away_name}不败")
        if w < 1.30 or l < 1.30:
            parts.append("⚠️极低赔率注意翻车")
        return " | ".join(parts)
    except:
        return "赔率解析异常"

def fetch_matches(lid, lname, lflag):
    """深度抓取: 赛程 + H2H + 状态 + 伤停 + 赔率 + 共识"""
    data = req(f"https://www.fotmob.com/api/leagues?id={lid}&season=2026")
    if not data:
        return [], [], []

    today = time.strftime("%Y-%m-%d")
    up, fin = [], []

    all_matches = data.get("matches", {}).get("allMatches", [])
    # 预筛选今天和昨天的比赛，避免不必要处理
    today_matches = []
    for m in all_matches:
        st = m.get("status", {})
        md = (st.get("utcTime", "") or "")[:10]
        if md == today and not st.get("finished"):
            today_matches.append(m)
        elif st.get("finished") and md == time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400)):
            fin.append({
                "date": md,
                "match": f"{m.get('home',{}).get('name','?')} vs {m.get('away',{}).get('name','?')}",
                "result": f"{st.get('homeScore',0)}-{st.get('awayScore',0)}",
                "league": lname,
                "w": None, "p": "", "note": "自动收录"
            })

    for m in today_matches:
        st = m.get("status", {})
        hm = m.get("home", {})
        am = m.get("away", {})
        hn = hm.get("name", "?")
        an = am.get("name", "?")
        hid = hm.get("id", 0)
        aid = am.get("id", 0)
        mid = m.get("id", "")

        # 状态(必须)
        h_fs, h_fd = get_team_form(hid)
        a_fs, a_fd = get_team_form(aid)
        h_fm = analyze_form(h_fs)
        a_fm = analyze_form(a_fs)

        # H2H(必须)
        h2h_desc, _, _ = get_h2h(hid, aid, hn, an)

        # 赔率(尝试从match详情获取)
        odds_str = get_match_odds(mid)

        # 伤停(轻量获取, 只对前几场)
        inj_h = get_injuries(hid) if len(up) < 8 else "无关键伤停"
        inj_a = get_injuries(aid) if len(up) < 8 else "无关键伤停"

        # 共识
        xp = get_expert_consensus(hn, an, odds_str)

        up.append({
            "id": len(up) + 1,
            "lg": f"{lflag} {lname}",
            "tm": (st.get("utcTime", "") or "")[11:16],
            "h": hn, "a": an,
            "hr": hm.get("rank", 0), "ar": am.get("rank", 0),
            "odds": odds_str if odds_str else "待更新",
            "h2h": h2h_desc,
            "fm": f"主({h_fs}): {h_fm} | 客({a_fs}): {a_fm}",
            "fd": f"主: {h_fd} | 客: {a_fd}",
            "inj": f"主: {inj_h} | 客: {inj_a}",
            "xp": xp
        })

    return up, fin


def main():
    print(f"📡 {time.strftime('%Y-%m-%d %H:%M')} v5 全自动 (Poisson-Elo模型)")
    start = time.time()

    # 读取已有数据（保留history/rules及手动数据）
    ex = {"history": [], "rules": [], "yesterday": {"results": []}}
    if os.path.exists(DATA):
        try:
            with open(DATA, "r", encoding="utf-8") as f:
                ex = json.load(f)
        except:
            pass

    # 保存旧的高质量手动数据（人工输入的赔率/H2H/伤停优先级最高）
    old_rich = {}
    for m in ex.get("today", {}).get("matches", []):
        key = f"{m.get('h', '')}|{m.get('a', '')}"
        old_rich[key] = {}
        for k in ["odds", "h2h", "inj", "xp"]:
            v = m.get(k, "")
            if v and v != "待更新" and "数据不足" not in str(v):
                old_rich[key][k] = v

    all_up, all_fin = [], []
    for lid, lname, lflag, *_ in LEAGUES:
        try:
            up, fin = fetch_matches(lid, lname, lflag)
            all_up.extend(up)
            all_fin.extend(fin)
            if up:
                print(f"  {lflag} {lname}: {len(up)}场 (含H2H+状态+赔率)")
        except Exception as e:
            print(f"  ⚠️ {lflag} {lname}: {e}")

    # 手动数据覆盖（保留人工修正的赔率等）
    for m in all_up:
        key = f"{m.get('h', '')}|{m.get('a', '')}"
        if key in old_rich:
            for k, v in old_rich[key].items():
                if v:
                    m[k] = v

    # 按时间排序
    all_up.sort(key=lambda x: x.get("tm", "99:99"))

    # 更新data.json
    ex["updated"] = time.strftime("%Y-%m-%d %H:%M")
    ex["today"] = {"date": time.strftime("%Y-%m-%d"), "matches": all_up}

    # 合并赛果
    if all_fin:
        old_results = ex.get("yesterday", {}).get("results", [])
        seen = {r.get("match", "") for r in old_results}
        for r in all_fin:
            if r["match"] not in seen:
                old_results.append(r)
                seen.add(r["match"])
        ex["yesterday"]["results"] = old_results[-30:]
        ex["yesterday"]["date"] = all_fin[-1]["date"]

    # 保持rules不变（手动维护）
    if "rules" not in ex or not ex["rules"]:
        ex["rules"] = []

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(ex, f, ensure_ascii=False, indent=2)

    elapsed = time.time() - start
    odds_ok = sum(1 for m in all_up if m.get("odds") and m["odds"] != "待更新")
    print(f"✅ {len(all_up)}场 ({odds_ok}场有赔率) | 耗时{elapsed:.0f}s → {DATA}")


if __name__ == "__main__":
    main()
