"""
全自动数据更新 v8 · 双源融合
  football-data.org: 排名/赛程/状态 (10大免费联赛)
  sporttery.cn:      赔率/中文名/竞彩编号 (需中国IP)
自动降级: GitHub Actions无sporttery → 纯football-data模式
"""
import json, os, sys, time, re
from datetime import datetime, timezone, timedelta
import requests

# ═══════════════════════════════════════════
#  配置
# ═══════════════════════════════════════════

API_KEY = os.environ.get("FOOTBALL_DATA_API_KEY", "")
BASE = "https://api.football-data.org/v4"
DATA_FILE = "data.json"
H = {"X-Auth-Token": API_KEY}
REQ_GAP = 7.0  # football-data.org rate limit

# 免费层联赛 (id, 中文名, emoji)
COMPETITIONS = [
    ("BSA", "巴甲", "🇧🇷"),
    ("CL",  "欧冠", "🏆"),
    ("PL",  "英超", "🏴"),
    ("BL1", "德甲", "🇩🇪"),
    ("SA",  "意甲", "🇮🇹"),
    ("PD",  "西甲", "🇪🇸"),
    ("FL1", "法甲", "🇫🇷"),
    ("DED", "荷甲", "🇳🇱"),
    ("PPL", "葡超", "🇵🇹"),
    ("ELC", "英冠", "🏴"),
]

# ── 球队中文名映射 (football-data英文 → 中文) ──
TEAM_CN = {
    # 巴甲
    "SE Palmeiras": "帕尔梅拉斯",
    "CR Flamengo": "弗拉门戈",
    "Fluminense FC": "弗鲁米嫩塞",
    "RB Bragantino": "布拉甘蒂诺红牛",
    "CA Paranaense": "巴拉纳竞技",
    "EC Bahia": "巴伊亚",
    "Coritiba FBC": "科里蒂巴",
    "São Paulo FC": "圣保罗",
    "Botafogo FR": "博塔弗戈",
    "CA Mineiro": "米内罗竞技",
    "EC Vitória": "维多利亚",
    "SC Corinthians Paulista": "科林蒂安",
    "Cruzeiro EC": "克鲁塞罗",
    "SC Internacional": "巴西国际",
    "Santos FC": "桑托斯",
    "Grêmio FBPA": "格雷米奥",
    "CR Vasco da Gama": "瓦斯科达伽马",
    "Mirassol FC": "米拉索尔",
    "Clube do Remo": "里莫",
    "Chapecoense AF": "沙佩科恩斯",
    # MLS
    "Inter Miami CF": "迈阿密国际",
    "Chicago Fire FC": "芝加哥火焰",
    "Los Angeles FC": "洛杉矶FC",
    "Real Salt Lake": "皇家盐湖城",
    "LA Galaxy": "洛杉矶银河",
    "New York City FC": "纽约城",
    "New York Red Bulls": "纽约红牛",
    "Atlanta United FC": "亚特兰大联",
    "Seattle Sounders FC": "西雅图海湾人",
    "Columbus Crew": "哥伦布机员",
    "FC Cincinnati": "辛辛那提",
    "New England Revolution": "新英格兰革命",
    "Orlando City SC": "奥兰多城",
    "Toronto FC": "多伦多FC",
    "Philadelphia Union": "费城联合",
    "Nashville SC": "纳什维尔",
    "Charlotte FC": "夏洛特",
    "Colorado Rapids": "科罗拉多急流",
    "FC Dallas": "达拉斯",
    "Houston Dynamo FC": "休斯顿迪纳摩",
    "Minnesota United FC": "明尼苏达联",
    "Portland Timbers": "波特兰伐木者",
    "San Jose Earthquakes": "圣何塞地震",
    "Sporting Kansas City": "堪萨斯城竞技",
    "St. Louis City SC": "圣路易斯城",
    "Austin FC": "奥斯汀",
    "Vancouver Whitecaps FC": "温哥华白帽",
    "CF Montréal": "蒙特利尔",
    "D.C. United": "华盛顿联",
}

# sporttery简称→标准中文名
CN_SHORT = {
    "巴竞技": "巴拉纳竞技",
    "迈阿密": "迈阿密国际",
    "芝加哥": "芝加哥火焰",
    "盐湖城": "皇家盐湖城",
}

# ── Rate Limit ──
_last_req = 0
def rate_limit():
    global _last_req
    now = time.time()
    wait = REQ_GAP - (now - _last_req)
    if wait > 0: time.sleep(wait)
    _last_req = time.time()

def api_fd(url, timeout=15, retries=2):
    """football-data.org API"""
    rate_limit()
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=H, timeout=timeout)
            if r.status_code == 429:
                print(f"  ⚠️ Rate limited, sleeping 65s...")
                time.sleep(65)
                return api_fd(url, timeout, retries)
            if r.ok: return r.json()
            if r.status_code == 403: return None
            print(f"  ❌ HTTP {r.status_code}")
            return None
        except Exception as e:
            if attempt < retries:
                print(f"  ⏳ 重试({attempt+1}/{retries})...")
                time.sleep(3)
            else:
                print(f"  ❌ {e}")
                return None

def api_st(url, timeout=12):
    """sporttery.cn API (仅中国IP可访问)"""
    h = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://www.sporttery.cn/",
    }
    try:
        r = requests.get(url, headers=h, timeout=timeout)
        if r.status_code == 200 and "application/json" in r.headers.get("content-type", ""):
            return r.json()
        return None
    except:
        return None

# ═══════════════════════════════════════════
#  football-data.org
# ═══════════════════════════════════════════

def fetch_standings(comp_id):
    data = api_fd(f"{BASE}/competitions/{comp_id}/standings")
    if not data or not data.get("standings"): return {}
    ranks = {}
    for entry in data["standings"][0]["table"]:
        t = entry["team"]
        ranks[t["id"]] = {
            "rank": entry["position"],
            "pts": entry["playedGames"],
            "name": t["name"],
            "crest": t.get("crest", ""),
        }
    return ranks

def fetch_matches(comp_id, date_from, date_to):
    url = f"{BASE}/competitions/{comp_id}/matches?dateFrom={date_from}&dateTo={date_to}&status=SCHEDULED"
    data = api_fd(url)
    return data.get("matches", []) if data else []

def fetch_team_data(team_id, team_name):
    """获取球队近30场战绩 → (wdl, form_text, recent_matches)"""
    url = f"{BASE}/teams/{team_id}/matches?limit=30&status=FINISHED"
    data = api_fd(url)
    if not data: return ("?", "数据缺失", [])

    all_matches = data.get("matches", [])
    recent5 = all_matches[:5]

    wdl = []
    home_r, away_r = [], []
    for m in recent5:
        is_home = m["homeTeam"]["id"] == team_id
        hs = m["score"]["fullTime"]["home"]
        aw = m["score"]["fullTime"]["away"]
        gf, ga = (hs, aw) if is_home else (aw, hs)
        if gf > ga: wdl.append("W")
        elif gf == ga: wdl.append("D")
        else: wdl.append("L")
        (home_r if is_home else away_r).append(wdl[-1])

    wdl_s = "".join(wdl)
    w, d, l2 = wdl.count("W"), wdl.count("D"), wdl.count("L")
    parts = [f"近{len(wdl)}场{w}胜{d}平{l2}负"]

    if w >= 4: parts.insert(0, "状态火爆")
    elif w >= 3: parts.insert(0, "状态良好")
    elif l2 >= 4: parts.insert(0, "状态低迷")
    elif w + d >= 4: parts.insert(0, "状态平稳")
    elif l2 >= 3: parts.insert(0, "状态下滑")

    if home_r.count("W") >= 3: parts.append("主场强势")
    if away_r.count("L") >= 3: parts.append("客场疲软")
    if away_r.count("W") >= 3: parts.append("客场强势")

    return (wdl_s, "，".join(parts), all_matches)


def build_h2h(home_matches, away_matches, home_en, away_en, home_cn, away_cn):
    """从两队近期比赛提取H2H记录"""
    h2h_records = []
    # 从主队近期比赛找对方
    for m in home_matches:
        ht_id = m["homeTeam"]["id"]
        at_id = m["awayTeam"]["id"]
        hs = m["score"]["fullTime"]["home"]
        aw = m["score"]["fullTime"]["away"]
        # 检查客场队是否参与 (用名字关键词匹配)
        if not _team_in_match(away_cn, m["homeTeam"]["name"], m["awayTeam"]["name"]):
            continue
        # 主队(en)在这场H2H中是否主场?
        h_is_home = _team_is_target(home_cn, m["homeTeam"]["name"])
        if h_is_home:
            gf, ga = hs, aw
        else:
            gf, ga = aw, hs
        h2h_records.append({
            "date": m["utcDate"][:10],
            "gf": gf, "ga": ga,
            "h_is_home": h_is_home,
        })

    if not h2h_records:
        return "近期无交手记录"

    h_w, h_d, a_w = 0, 0, 0
    for r in h2h_records:
        if r["gf"] > r["ga"]: h_w += 1
        elif r["gf"] < r["ga"]: a_w += 1
        else: h_d += 1

    total = h_w + h_d + a_w
    recent = h2h_records[0]
    loc = "主" if recent["h_is_home"] else "客"
    base = f"近{total}次{home_cn}{h_w}胜{h_d}平{a_w}负"
    if total >= 4:
        if h_w == 0: base += f" ⚠️0胜魔咒!"
        elif a_w == 0: base += " 不败"
        elif h_w >= total * 0.7: base += " 🔥血脉压制!"
        elif a_w >= total * 0.7: base += f" 🔥被{away_cn}压制!"
    base += f" | 最近{recent['date']} {loc}场 {recent['gf']}-{recent['ga']}"
    return base


def _team_is_target(cn_name, en_name):
    """中文名是否匹配英文名"""
    for en, cn in TEAM_CN.items():
        if cn == cn_name:
            pa = set(en.lower().replace("fc","").replace("sc","").replace("ec","").split())
            pb = set(en_name.lower().replace("fc","").replace("sc","").replace("ec","").split())
            return len(pa & pb) >= 1
    return False


def _team_in_match(cn_name, home_name, away_name):
    """检查中文队名是否参与这场比赛"""
    for en, cn in TEAM_CN.items():
        if cn == cn_name:
            en_parts = set(en.lower().replace("fc","").replace("sc","").replace("ec","").split())
            h_parts = set(home_name.lower().replace("fc","").replace("sc","").replace("ec","").split())
            a_parts = set(away_name.lower().replace("fc","").replace("sc","").replace("ec","").split())
            if en_parts & h_parts or en_parts & a_parts:
                return True
    return False

# ═══════════════════════════════════════════
#  sporttery.cn
# ═══════════════════════════════════════════

def fetch_sporttery():
    """获取今日竞彩赛程+赔率+中文名。不可用时返回空dict。"""
    url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=hhad,had&channel=c"
    data = api_st(url)
    if not data: return {}

    lottery = {}
    for mi in data.get("value", {}).get("matchInfoList", []):
        for sm in mi.get("subMatchList", []):
            num = sm.get("matchNum", "")
            home_cn = sm.get("homeTeamAllName", "")
            away_cn = sm.get("awayTeamAbbName", "")
            league_cn = sm.get("leagueAbbName", "")
            home_cn = CN_SHORT.get(home_cn, home_cn)
            away_cn = CN_SHORT.get(away_cn, away_cn)

            odds_had = ""
            odds_hhad = ""
            handicap = ""
            for o in sm.get("oddsList", []):
                if o.get("poolCode") == "HAD":
                    odds_had = f"{o.get('h','?')}/{o.get('d','?')}/{o.get('a','?')}"
                if o.get("poolCode") == "HHAD":
                    odds_hhad = f"{o.get('h','?')}/{o.get('d','?')}/{o.get('a','?')}"
                    gl = o.get("goalLine", "")
                    handicap = gl if gl else ""

            lottery[num] = {
                "num": num, "hCn": home_cn, "aCn": away_cn,
                "lgCn": league_cn, "odds": odds_had,
                "odds_hhad": odds_hhad, "handicap": handicap,
            }

    print(f"  🎫 竞彩: {len(lottery)}场")
    return lottery


def match_lottery(fd_matches, lottery):
    """将竞彩数据匹配到football-data比赛"""
    for m in fd_matches:
        h_en = m.get("h", "")
        a_en = m.get("a", "")
        for num, lt in lottery.items():
            if _match_team(lt["hCn"], h_en) and _match_team(lt["aCn"], a_en):
                m["matchNum"] = num
                m["isLottery"] = True
                m["hCn"] = lt["hCn"]
                m["aCn"] = lt["aCn"]
                m["odds"] = lt["odds"] or "待获取"
                m["odds_hhad"] = lt.get("odds_hhad", "")
                m["handicap"] = lt.get("handicap", "")
                m["lgCn"] = lt.get("lgCn", "")
                break
    return fd_matches


def _match_team(cn_name, en_name):
    """中文名匹配英文名"""
    if not cn_name or not en_name: return False
    # 反查: 中文→英文→检查重叠
    for en, cn in TEAM_CN.items():
        if cn == cn_name:
            pa = set(en.lower().replace("fc","").replace("sc","").replace("ec","").split())
            pb = set(en_name.lower().replace("fc","").replace("sc","").replace("ec","").split())
            return len(pa & pb) >= 1
    return False


def _cn_name(en_name):
    return TEAM_CN.get(en_name, en_name)


# ═══════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════

def main():
    # ── 比赛日 = 北京时间今天11:00 ~ 明天10:59 ──
    now = time.time()
    bt = time.localtime(now)
    if bt.tm_hour < 11:
        # 还没到11点，当前比赛日从昨天11点开始
        match_day_start = now - 86400
    else:
        match_day_start = now
    match_day_date = time.strftime("%Y-%m-%d", time.localtime(match_day_start))
    print(f"📡 {time.strftime('%Y-%m-%d %H:%M')} v8 双源融合 · 比赛日 {match_day_date}")

    date_from = time.strftime("%Y-%m-%d", time.localtime(match_day_start - 86400))
    date_to = time.strftime("%Y-%m-%d", time.localtime(match_day_start + 5 * 86400))

    # 读已有数据
    existing = {"history": [], "rules": [], "yesterday": {"results": []}}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except: pass

    # ── 1. sporttery.cn ──
    lottery = fetch_sporttery()

    # ── 2. football-data.org ──
    all_matches = []
    active = []

    for comp_id, cn_name, flag in COMPETITIONS:
        ranks = fetch_standings(comp_id)
        if not ranks:
            continue

        raw = fetch_matches(comp_id, date_from, date_to)
        if not raw:
            print(f"  {flag}{cn_name}: 0场")
            continue

        team_ids = set()
        for m in raw:
            team_ids.add(m["homeTeam"]["id"])
            team_ids.add(m["awayTeam"]["id"])

        forms = {}
        for tid in team_ids:
            tname = next((m["homeTeam"]["name"] for m in raw if m["homeTeam"]["id"] == tid),
                         next((m["awayTeam"]["name"] for m in raw if m["awayTeam"]["id"] == tid), f"#{tid}"))
            forms[tid] = fetch_team_data(tid, tname)

        for m in raw:
            ht_id = m["homeTeam"]["id"]
            at_id = m["awayTeam"]["id"]
            h_en = m["homeTeam"]["name"]
            a_en = m["awayTeam"]["name"]

            hr_info = ranks.get(ht_id, {})
            ar_info = ranks.get(at_id, {})
            h_rank = hr_info.get("rank", 0)
            a_rank = ar_info.get("rank", 0)

            h_cn = _cn_name(h_en)
            a_cn = _cn_name(a_en)

            try:
                utc_dt = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                bj_dt = utc_dt + timedelta(hours=8)
                short_time = bj_dt.strftime("%H:%M")
                # 比赛日: 11点后属于当天, 11点前属于前一天
                if bj_dt.hour >= 11:
                    match_day = bj_dt.strftime("%Y-%m-%d")
                else:
                    match_day = (bj_dt - timedelta(days=1)).strftime("%Y-%m-%d")
            except:
                short_time = m["utcDate"][11:16] if "T" in m["utcDate"] else m["utcDate"][:5]
                match_day = m["utcDate"][:10]

            h_wdl, h_form, h_matches = forms.get(ht_id, ("?", "数据缺失", []))
            a_wdl, a_form, a_matches = forms.get(at_id, ("?", "数据缺失", []))
            fm_text = f"主({h_wdl}): {h_form} | 客({a_wdl}): {a_form}"
            h2h_text = build_h2h(h_matches, a_matches, h_en, a_en, h_cn, a_cn)

            # 只保留当前比赛日及之后的比赛
            if match_day < match_day_date:
                continue

            all_matches.append({
                "id": len(all_matches) + 1,
                "lg": f"{flag} {cn_name}",
                "matchDay": match_day,
                "tm": short_time,
                "h": h_en, "a": a_en,
                "hCn": h_cn, "aCn": a_cn,
                "hr": h_rank, "ar": a_rank,
                "odds": "待获取",
                "matchNum": "",
                "isLottery": False,
                "handicap": "",
                "odds_hhad": "",
                "h2h": h2h_text,
                "inj": "无关键伤停",
                "fm": fm_text,
                "xp": "football-data.org",
                "hCrest": hr_info.get("crest", ""),
                "aCrest": ar_info.get("crest", ""),
            })

        print(f"  {flag}{cn_name}: {len(raw)}场, 排名{len(ranks)}队")
        active.append(f"{flag}{cn_name}")

    # ── 3. 融合 ──
    if lottery:
        all_matches = match_lottery(all_matches, lottery)

    # 排序: 竞彩优先 → 编号 → 时间
    all_matches.sort(key=lambda x: (
        0 if x.get("isLottery") else 1,
        x.get("matchNum", "9999"),
        x.get("tm", "99:99"),
    ))

    # 去重
    seen, unique = set(), []
    for m in all_matches:
        key = f"{m['h']}|{m['a']}|{m['tm']}"
        if key not in seen:
            seen.add(key); unique.append(m)
    for i, m in enumerate(unique): m["id"] = i + 1

    lc = sum(1 for m in unique if m.get("isLottery"))
    tc = len(unique)

    existing["updated"] = time.strftime("%Y-%m-%d %H:%M")
    existing["today"] = {"date": match_day_date, "matches": unique}
    existing["_lottery_count"] = lc
    existing["_total_count"] = tc

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"✅ 竞彩{lc}场 + 其他{tc-lc}场 = {tc}场 [{', '.join(active)}] → {DATA_FILE}")


if __name__ == "__main__":
    main()
