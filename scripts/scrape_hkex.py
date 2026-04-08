#!/usr/bin/env python3
"""
港股打新 — 每日全自动更新脚本
GitHub Actions cron: 0 2 * * 1-5  (HKT 10:00 每个工作日)

Claude 调用方式（按优先级，在环境变量中配置其中一个）:
  1. CLAUDE_CODE_OAUTH_TOKEN  →  用你的 Claude Pro/Max 订阅，最推荐
  2. GEMINI_API_KEY           →  Google Gemini 2.5 Flash，完全免费备选
  3. ANTHROPIC_API_KEY        →  Anthropic 直接 API（需单独 API 账号）
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ─── 路径常量 ──────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).parent.parent
DATA_DIR    = ROOT / "data"
PITCHES_DIR = DATA_DIR / "pitches"
SIDEBAR_JSON = DATA_DIR / "sidebar.json"

HKT       = timezone(timedelta(hours=8))
TODAY     = datetime.now(HKT).strftime("%Y-%m-%d")
CUTOFF_DT = datetime.now(HKT) + timedelta(days=92)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}

# ─── 检测可用的 AI 后端 ────────────────────────────────────────────────────────

def detect_ai_backend() -> str:
    """
    返回当前可用的 AI 后端名称。
    优先级: claude-oauth > gemini > anthropic-api
    """
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        return "claude-oauth"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic-api"
    return "none"


# ─── 1. IPO 数据抓取（多源，无需登录）────────────────────────────────────────
#
#  ❌ 富途 OpenAPI — 需要 FutuOpenD 网关程序，无法在 GitHub Actions 直接调用
#  ✅ etnet.com.hk  — IPO 日历数据嵌在页面 JS 里，免登录，直接解析
#  ✅ AKShare       — Python 库封装港股 IPO 接口，pip install akshare
#  ✅ HKEX News     — 官方新股公告，免登录静态 HTML
# ─────────────────────────────────────────────────────────────────────────────

def fetch_ipo_data() -> list[dict]:
    """
    依次尝试各数据源，返回标准化 IPO 条目列表。
    优先级: etnet → AKShare → HKEX News
    """
    entries = fetch_etnet_ipo()
    if entries:
        return entries

    entries = fetch_akshare_ipo()
    if entries:
        return entries

    print("[WARN] 所有数据源均失败，返回空列表")
    return []


# ── 数据源 A: etnet.com.hk ────────────────────────────────────────────────────

def fetch_etnet_ipo() -> list[dict]:
    """
    抓取 etnet IPO 日历。
    数据以 JSON 形式嵌在页面 JS 变量 full_yearmonth_array 中，无需登录。
    字段: 股票代码、公司名（中英）、上市日期、招股状态标签
    """
    url = "https://www.etnet.com.hk/www/tc/stocks/ipo-calendar.php"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        # 提取页面内嵌的 JSON 数据
        match = re.search(r'full_yearmonth_array\s*=\s*(\{.+?\});', resp.text, re.DOTALL)
        if not match:
            print("[WARN] etnet: 未找到 full_yearmonth_array")
            return []

        raw_data = json.loads(match.group(1))
        entries = []
        for year_month, stocks in raw_data.items():
            if not isinstance(stocks, list):
                continue
            for stock in stocks:
                entry = _normalize_etnet(stock, year_month)
                if entry and _within_3months(entry.get("listingDate", "")):
                    entries.append(entry)

        print(f"[OK] etnet: {len(entries)} 条（3个月窗口内）")
        return entries

    except Exception as e:
        print(f"[WARN] etnet 抓取失败: {e}")
        return []


def _normalize_etnet(stock: dict, year_month: str) -> dict | None:
    """标准化 etnet 单条 IPO 记录。"""
    code = str(stock.get("Code", "")).zfill(5)
    name = stock.get("Name", "") or stock.get("Name_en", "")
    if not name:
        return None

    listing_raw = stock.get("List date", "")               # "2026/04/16"
    listing_date = listing_raw.replace("/", "-") if listing_raw else ""

    status_label = stock.get("Status label", "")           # "5日後截止" / "招股中" 等
    phase = _infer_phase_etnet(status_label, listing_date)

    return {
        "key":         "_stub_" + _slug(name),
        "name":        name,
        "ticker":      f"{code}.HK" if code else "TBD",
        "aShare":      "",
        "sector":      "",
        "phase":       phase,
        "hearingDate": "",
        "subStart":    "",
        "subEnd":      "",
        "listingDate": listing_date,
        "ipoLow":      None,
        "ipoHigh":     None,
        "ipoPrice":    None,
        "mktCapNote":  "",
        "statusLabel": status_label,
        "source":      "etnet",
        "sourceDate":  TODAY,
    }


def _infer_phase_etnet(status_label: str, listing_date: str) -> str:
    """根据 etnet 状态标签推断 pipeline/subscribe/listing 阶段。"""
    if not status_label and listing_date:
        try:
            ld = datetime.strptime(listing_date, "%Y-%m-%d").replace(tzinfo=HKT)
            return "listing" if ld <= datetime.now(HKT) else "pipeline"
        except ValueError:
            return "pipeline"

    label = status_label.lower()
    if any(k in label for k in ["截止", "招股", "認購", "认购"]):
        return "subscribe"
    if any(k in label for k in ["半新", "上市", "掛牌"]):
        return "listing"
    return "pipeline"


# ── 数据源 B: AKShare ─────────────────────────────────────────────────────────

def fetch_akshare_ipo() -> list[dict]:
    """
    通过 AKShare 获取港股 IPO 数据。
    pip install akshare
    相关接口: stock_hk_ipo_em() — 东方财富港股 IPO 数据
    """
    try:
        import akshare as ak
        df = ak.stock_hk_ipo_em()   # 返回 DataFrame
        entries = []
        for _, row in df.iterrows():
            name        = str(row.get("股票简称", ""))
            code        = str(row.get("股票代码", ""))
            status      = str(row.get("状态", ""))
            listing_raw = str(row.get("上市日期", ""))
            sub_start   = str(row.get("招股开始日期", ""))
            sub_end     = str(row.get("招股截止日期", ""))
            ipo_price   = row.get("发行价格")
            listing_date = listing_raw[:10] if listing_raw != "nan" else ""

            phase = "pipeline"
            if "招股" in status or "认购" in status:
                phase = "subscribe"
            elif "上市" in status or listing_date and datetime.strptime(
                    listing_date, "%Y-%m-%d").replace(tzinfo=HKT) <= datetime.now(HKT):
                phase = "listing"

            entry = {
                "key":         "_stub_" + _slug(name),
                "name":        name,
                "ticker":      f"{code}.HK" if code else "TBD",
                "phase":       phase,
                "listingDate": listing_date,
                "subStart":    sub_start[:10] if sub_start != "nan" else "",
                "subEnd":      sub_end[:10]   if sub_end   != "nan" else "",
                "ipoPrice":    float(ipo_price) if ipo_price and str(ipo_price) != "nan" else None,
                "source":      "akshare",
                "sourceDate":  TODAY,
            }
            if _within_3months(listing_date or sub_start[:10] if sub_start != "nan" else ""):
                entries.append(entry)

        print(f"[OK] AKShare: {len(entries)} 条")
        return entries

    except ImportError:
        print("[WARN] akshare 未安装: pip install akshare")
        return []
    except Exception as e:
        print(f"[WARN] AKShare 失败: {e}")
        return []


# ─── 2. 新进入招股的公司 ───────────────────────────────────────────────────────

def load_existing_pitch_keys() -> set[str]:
    if not PITCHES_DIR.exists():
        return set()
    return {f.stem for f in PITCHES_DIR.glob("*.json")}


def find_new_subscriptions(entries: list[dict], existing_keys: set[str]) -> list[dict]:
    return [e for e in entries if e["phase"] == "subscribe" and e["key"] not in existing_keys]


# ─── 3. 搜索公司背景 ───────────────────────────────────────────────────────────

def fetch_company_background(name: str, sector: str) -> str:
    sources = []
    for url in [
        f"https://www.nbd.com.cn/search?q={requests.utils.quote(name + ' 港股 IPO')}",
        f"https://www.21jingji.com/search/?q={requests.utils.quote(name + ' 港股')}",
    ]:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                text = re.sub(r'<[^>]+>', ' ', resp.text)
                text = re.sub(r'\s+', ' ', text)[:2500]
                sources.append(text)
        except Exception:
            pass
        time.sleep(1)

    if not sources:
        return f"公司名称: {name}\n行业: {sector}\n（无法获取详细信息，请基于行业知识分析）"
    return "\n\n---\n\n".join(sources)


# ─── 4. Pitch 分析 Prompt ──────────────────────────────────────────────────────

def build_prompt(company: dict, background: str) -> str:
    return f"""你是专业的港股打新分析师，使用 MECE 评分框架（F/S/V/M）评估 IPO 投资价值。

## 公司信息
公司名称: {company['name']}
行业: {company.get('sector', '')}
A股代码: {company.get('aShare', '—')}
招股价区间: HK${company.get('ipoLow', '待公布')} – HK${company.get('ipoHigh', '待公布')}
招股日期: {company.get('subStart', '')} 至 {company.get('subEnd', '')}
市值估算: {company.get('mktCapNote', '待公布')}

## 公开背景资料
{background[:5000]}

---

请严格输出以下 JSON 格式的分析数据，不要有任何其他文字：

{{
  "name": "{company['name']}",
  "sector": "{company.get('sector', '')}",
  "rating": "BUY 或 WATCH 或 SKIP",
  "score": 0.0,
  "scoreColor": "var(--green) 或 var(--yellow) 或 var(--red)",
  "tagline": "一句话核心投资逻辑，中文，30字以内",
  "scorecard": [
    {{"label": "基本面质量 (F)", "weight": "35%", "score": 0.0, "max": 10, "color": "var(--green)", "note": "说明"}},
    {{"label": "IPO结构 (S)",    "weight": "30%", "score": 0.0, "max": 10, "color": "var(--green)", "note": "说明"}},
    {{"label": "估值合理性 (V)", "weight": "20%", "score": 0.0, "max": 10, "color": "var(--yellow)", "note": "说明"}},
    {{"label": "市场时机 (M)",   "weight": "15%", "score": 0.0, "max": 10, "color": "var(--green)", "note": "说明"}}
  ],
  "thesis": [
    {{"title": "投资逻辑1", "desc": "详细说明"}},
    {{"title": "投资逻辑2", "desc": "详细说明"}},
    {{"title": "投资逻辑3", "desc": "详细说明"}}
  ],
  "keyRisks": [
    {{"icon": "⚠️", "title": "风险1", "desc": "说明"}},
    {{"icon": "⚠️", "title": "风险2", "desc": "说明"}}
  ],
  "comps": {{
    "hk": {{
      "rows": [
        {{"name": "可比公司", "ticker": "XXXX.HK", "rel": "强相关", "peLtm": "NM", "pe": "52x", "ps": "8x", "evEbitda": "NM", "verdict": null}}
      ],
      "verdict": {{"type": "cheap", "text": "IPO隐含倍数 vs Comps说明"}}
    }},
    "a": {{"rows": [], "verdict": {{"type": "fair", "text": "A股对比"}}}}
  }},
  "sellRec": {{
    "action": "退出建议",
    "horizon": "建议持有期",
    "actionColor": "var(--green)",
    "ipoPrice": 0.0,
    "thesisVsPrice": {{
      "metric": "P/S",
      "ipoImplied": "Xx",
      "compsMedian": "Yx",
      "vs": "折价 −Z%",
      "verdict": "偏低估 CHEAP",
      "verdictClass": "cheap",
      "checks": [
        {{"point": "论点 (F/S/V/M 参考)", "result": "✓ 验证", "note": "说明", "ok": true}}
      ]
    }},
    "scenarios": [
      {{"type": "bear", "label": "熊市情景", "price": "HK$X", "upside": "+X%", "basis": "估值逻辑"}},
      {{"type": "base", "label": "基础情景", "price": "HK$Y", "upside": "+Y%", "basis": "估值逻辑"}},
      {{"type": "bull", "label": "牛市情景", "price": "HK$Z", "upside": "+Z%", "basis": "估值逻辑"}}
    ],
    "triggers": [
      {{"icon": "🎯", "title": "减持触发", "desc": "说明", "price": "≥ HK$X", "priceClass": "stp-sell"}},
      {{"icon": "🛑", "title": "止损触发", "desc": "说明", "price": "< HK$Y", "priceClass": "stp-sell"}}
    ]
  }}
}}

评分规则: 总分 = F×0.35 + S×0.30 + V×0.20 + M×0.15。BUY≥7.0，WATCH 5-6.9，SKIP<5.0 或孖展<10x。
禁止: 不写保荐人差、锁定期到期、定期业绩作为催化剂，comps 不含 P/B。"""


# ─── 5. AI 调用（三种后端） ────────────────────────────────────────────────────

def call_claude_oauth(prompt: str) -> str | None:
    """通过 Claude Code CLI + OAuth Token 调用 Claude（使用订阅计划）。"""
    token = os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
    if not token:
        return None
    try:
        # 把 prompt 写入临时文件避免 shell 转义问题
        prompt_file = "/tmp/pitch_prompt.txt"
        with open(prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt)

        result = subprocess.run(
            ["claude", "--print", "--no-markdown", f"@{prompt_file}"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": token}
        )
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"[WARN] claude CLI 错误: {result.stderr[:300]}")
            return None
    except FileNotFoundError:
        print("[ERROR] claude CLI 未安装。GitHub Actions 已在 workflow 中安装，本地请运行: npm install -g @anthropic-ai/claude-code")
        return None
    except subprocess.TimeoutExpired:
        print("[ERROR] claude CLI 超时")
        return None


def call_gemini(prompt: str) -> str | None:
    """通过 Google Gemini 2.5 Flash 免费 API 调用（完全免费备选）。"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        import google.generativeai as genai   # pip install google-generativeai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except ImportError:
        print("[ERROR] google-generativeai 未安装。请运行: pip install google-generativeai")
        return None
    except Exception as e:
        print(f"[ERROR] Gemini API 失败: {e}")
        return None


def call_anthropic_api(prompt: str) -> str | None:
    """通过 Anthropic API Key 直接调用（需单独 API 账号）。"""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic   # pip install anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except ImportError:
        print("[ERROR] anthropic 未安装。请运行: pip install anthropic")
        return None
    except Exception as e:
        print(f"[ERROR] Anthropic API 失败: {e}")
        return None


def generate_pitch(company: dict, background: str) -> dict | None:
    """按优先级尝试各 AI 后端，返回解析后的 pitch dict。"""
    backend = detect_ai_backend()
    if backend == "none":
        print("[SKIP] 无可用 AI 后端，跳过 pitch 生成")
        return None

    print(f"[AI] 使用后端: {backend}")
    prompt = build_prompt(company, background)

    dispatch = {
        "claude-oauth":  call_claude_oauth,
        "gemini":        call_gemini,
        "anthropic-api": call_anthropic_api,
    }
    raw = dispatch[backend](prompt)
    if not raw:
        return None

    # 提取 JSON
    match = re.search(r'\{[\s\S]+\}', raw)
    if not match:
        print(f"[ERROR] 输出中无 JSON: {raw[:200]}")
        return None
    try:
        data = json.loads(match.group())
        data["generatedAt"]  = TODAY
        data["generatedBy"]  = backend
        print(f"[OK] {company['name']} → 评级: {data.get('rating')}, 分数: {data.get('score')}")
        return data
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失败: {e}")
        return None


# ─── 6. 文件读写 ───────────────────────────────────────────────────────────────

def save_pitch(key: str, data: dict) -> None:
    PITCHES_DIR.mkdir(parents=True, exist_ok=True)
    path = PITCHES_DIR / f"{key}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 写入 {path.name}")


def load_existing_sidebar() -> dict:
    if SIDEBAR_JSON.exists():
        return json.loads(SIDEBAR_JSON.read_text(encoding="utf-8"))
    return {"lastUpdated": "", "activeSubscription": [], "hearingPassed": [], "archived": []}


def save_sidebar(active_sub: list, hearing: list, archived: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SIDEBAR_JSON.write_text(
        json.dumps({"lastUpdated": TODAY, "activeSubscription": active_sub,
                    "hearingPassed": hearing, "archived": archived},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print("[OK] sidebar.json 已更新")


# ─── 7. 主流程 ─────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*52}")
    print(f"  港股打新每日更新 — {TODAY}  [{detect_ai_backend()}]")
    print(f"{'='*52}\n")

    # 抓取（etnet → AKShare，无需任何账号）
    entries = fetch_ipo_data()
    if not entries:
        print("[WARN] 所有数据源无数据，退出")
        sys.exit(0)

    # 分组 + 窗口过滤
    in_window  = [e for e in entries if _within_3months(e.get("subStart") or e.get("hearingDate") or "")]
    active_sub = [e for e in in_window if e["phase"] == "subscribe"]
    hearing    = [e for e in in_window if e["phase"] == "pipeline"]
    listed     = [e for e in entries   if e["phase"] == "listing"]

    # 新进入招股的
    existing_keys = load_existing_pitch_keys()
    new_subs = find_new_subscriptions(active_sub, existing_keys)
    print(f"招股中: {len(active_sub)} 家（{len(new_subs)} 家需生成分析）")
    print(f"通过聆讯: {len(hearing)} 家\n")

    # 自动生成 pitch 分析
    generated = []
    for company in new_subs:
        print(f"── 新股: {company['name']} ──")
        bg = fetch_company_background(company["name"], company.get("sector", ""))
        time.sleep(2)
        pitch = generate_pitch(company, bg)
        if pitch:
            pitch.update({"ticker": company.get("ticker", "TBD"), "exchange": "香港主板",
                           "subStart": company.get("subStart", ""), "subEnd": company.get("subEnd", "")})
            save_pitch(company["key"], pitch)
            generated.append(company["name"])
        time.sleep(3)

    # 归档新上市
    existing = load_existing_sidebar()
    archived = existing.get("archived", [])
    existing_archive_keys = {a["key"] for a in archived}
    for item in listed:
        if item["key"] not in existing_archive_keys:
            archived.append({"key": item["key"], "name": item["name"],
                             "ticker": item.get("ticker", "TBD"),
                             "listingDate": item.get("listingDate", ""), "result": "待更新"})
            print(f"[ARCHIVE] {item['name']}")

    save_sidebar(active_sub, hearing, archived)

    # 摘要
    print(f"\n{'─'*40}")
    print(f"  招股中:        {len(active_sub)} 家")
    print(f"  通过聆讯:      {len(hearing)} 家")
    print(f"  新生成 pitch:  {len(generated)} 家  {generated or ''}")
    print(f"  已归档:        {len(archived)} 家")
    print(f"{'─'*40}\n")


def _within_3months(date_str: str) -> bool:
    if not date_str:
        return True
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=HKT)
        return dt <= CUTOFF_DT
    except ValueError:
        return True


def _slug(name: str) -> str:
    return name[:4].encode("utf-8").hex()[:8] if name else "unknown"


if __name__ == "__main__":
    main()
