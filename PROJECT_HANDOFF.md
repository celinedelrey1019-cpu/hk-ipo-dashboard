# 港股打新工作流 — 项目交接文档
> 最后更新：2026-04-08 | 换机交接版

---

## 一、项目概述

**目标**：建立一套系统化的港股打新决策支持工具，涵盖选股评分 → IPO 分析 → 退出策略三个阶段。

**核心文件**：`hk_ipo_stock_pitch.html`（单文件 Bloomberg 深色主题仪表盘，纯 HTML + 原生 JS，无框架依赖）

**工作流程**：
```
HKEX 聆讯通过 → 侧边栏"通过聆讯"
      ↓
招股开始 → 侧边栏"招股中" + 补全 sellRec 分析
      ↓
定价公告 → 更新 comps TARGET 行 + subStats 卡片
      ↓
暗盘/上市 → 更新 thesisVsPrice checks + 归档
```

---

## 二、评分体系（MECE Scorecard）

| 维度 | 权重 | 评分要点 |
|------|------|----------|
| **F** 基本面质量 | 35% | 商业模式可持续性 · 财务健康度 · 竞争壁垒 |
| **S** IPO结构 | 30% | 孖展超购倍数 · 定价位置 · 保荐人质量 · 基石/Anchor |
| **V** 估值合理性 | 20% | 可比估值倍数 · PEG · 下行保护 |
| **M** 市场时机 | 15% | 板块周期位置 · 宏观环境 · 同期竞争新股 |

**一票否决红灯**：
- 孖展超购 < 10x → 直接 SKIP
- 保荐人历史破发率 > 60% → 直接 SKIP

---

## 三、Comps 表结构（4列）

| 列名 | 字段 | 说明 |
|------|------|------|
| P/E LTM | `peLtm` | 过去12个月市盈率（亏损公司填 NM） |
| P/E NTM | `pe` | 未来12个月预期市盈率 |
| EV/Revenue NTM | `ps` | 企业价值/未来营收 |
| EV/EBITDA NTM | `evEbitda` | 企业价值/未来EBITDA |

> ⚠️ P/B 已移除（之前版本有，现在不用）

---

## 四、退出策略框架（Exit Strategy）

每个 pitch 的 `sellRec` 包含三层：

### 1. `thesisVsPrice` — Pitch Thesis × IPO 定价交叉验证
```javascript
thesisVsPrice: {
  metric: "P/S",            // 主要估值倍数
  ipoImplied: "6.2x",       // IPO定价隐含的倍数
  compsMedian: "8.4x",      // 可比公司中位数（来自comps表）
  vs: "折价 −26%",          // 相对偏差
  verdict: "偏低估 CHEAP",  // CHEAP / FAIR / RICH
  verdictClass: "cheap",    // cheap / fair / rich（控制颜色）
  checks: [
    {
      point: "论点描述 (维度评分参考)",
      result: "✓ 验证 | ⚠ 待观察 | ✗ 未兑现",
      note: "具体说明",
      ok: true  // true=绿 / null=黄 / false=红
    }
  ]
}
```

### 2. `scenarios` — Bear / Base / Bull 三情景目标价
每个情景基于 comps 倍数区间推导，需明确说明是哪个 multiple 的哪个百分位。

### 3. `triggers` — 卖出/止损触发条件
**规则（已确立，不可违反）**：
- ❌ 不能写"保荐人质量差"作为触发条件
- ❌ 不能写"锁定期到期"作为卖出催化剂
- ❌ 不能写"定期业绩公布"作为催化剂（没有 specificity）
- ✅ 所有触发条件需有具体价格或倍数依据

---

## 五、侧边栏数据规则

### 显示原则
1. **只显示 3 个月窗口**（当前月 + 后2个月，目前是 4–6月2026）
2. **只显示事实确认的公司**，不放推断
3. **已递A1 不显示**（已移除该分类）

### 分类
```
招股中      → 正在接受认购（以 HKEX 公告为准）
通过聆讯    → 已获聆讯批准，尚未开始招股（以 HKEX 披露为准）
已上市归档  → 折叠显示，已完成打新的历史案例
```

### 当前通过聆讯（2026-04-08 核实，来源：每经网+21经济网）
| 公司 | 聆讯日期 | A股代码 | 行业 |
|------|----------|---------|------|
| 群核科技（酷家乐）| 2026-03-29 | — | 空间设计SaaS |
| 胜宏科技 | 2026-03-29 | 300476.SZ | AI算力PCB |
| 思格新能源 | 2026-03-29 | — | AI+工商业储能 |
| 长光辰芯 | 2026-03-29 | — | CMOS图像传感器 |
| 华勤技术 | 2026-03-30 | 603296.SH | 消费电子ODM |
| 迈威生物-B | 2026-04-02 | 688062.SH | 肿瘤生物制药 |

---

## 六、已完成分析的 Pitch（归档）

| Key | 公司 | 代码 | 评级 | 分数 | IPO价 | 结果 |
|-----|------|------|------|------|-------|------|
| `huayan` | 华沿机器人 | 1021.HK | BUY | 8.6 | HK$28.80 | 首日+68% ✓ |
| `fourier` | 傅里叶 | 3625.HK | BUY | 7.8 | HK$18.30 | 暗盘+110% ✓ |
| `tongsf` | 铜师傅 | 0664.HK | SKIP | 2.3 | HK$2.40 | 首日-49% ✓ |
| `jishijiao` | 极视角 | 6636.HK | BUY | 8.2 | — | _stub |
| `deshi` | 德适-B | 2526.HK | BUY | 7.4 | — | _stub |
| `hantian` | 瀚天 | 2726.HK | WATCH | 6.2 | — | _stub |
| `guanghe` | 广合科技 | 1989.HK | WATCH | 6.5 | — | _stub |
| `tongren` | 同仁堂 | 2667.HK | SKIP | 4.1 | — | _stub |

> _stub = 数据骨架存在但尚未补全分析内容

---

## 七、两步更新工作流（每次招股）

### Step 1 — 招股期间（有招股价区间时）
- [ ] 侧边栏状态改为"招股中"
- [ ] 补全 `pitch` 完整数据（thesis / comps / scorecard / capitalStrategy）
- [ ] 填写 `sellRec.thesisVsPrice`：用发行价区间 **下限** 和 **上限** 分别算隐含倍数
- [ ] 更新 Bear/Base/Bull 情景的绝对价格目标
- [ ] 更新"本周"筛选器标签

### Step 2 — 定价公告后
- [ ] 更新 comps 表 TARGET 行（用实际市值反推 P/E / P/S / EV/EBITDA）
- [ ] 更新 `subStats` 卡片（孖展超购 / 国际配售 / 定价位置 / 暗盘）
- [ ] `subStats.timeline` 填入实际日期
- [ ] 确认 `thesisVsPrice` 数据用最终定价（非区间）

---

## 八、GitHub 托管方案（全自动，无需本机开机）

### 架构说明
**侧边栏更新（纯数据，不需要 Claude）**
HKEX/富途的 IPO 状态是结构化 JSON，Python 直接抓取写入 `sidebar.json`，无 LLM 依赖。

**Pitch 分析（需要 Claude，但也全自动）**
当脚本检测到新股进入「招股中」时，自动调用 **Anthropic API**（云端调用，不需要 Cowork/本机），生成完整 pitch 分析并写入 `data/pitches/{key}.json`。

```
GitHub Actions 每天 HKT 10:00 自动触发（云端，不需要你的电脑开机）
    ↓
Python 抓取富途/HKEX IPO 日历
    ↓ 发现新股进入「招股中」
搜索该公司公开信息（新闻 + 招股书摘要）
    ↓
调用 Anthropic API (claude-sonnet-4-6)  ←── 直接 API，不经过 Cowork
Claude 生成：thesis / scorecard / comps / sellRec / thesisVsPrice
    ↓
写入 data/pitches/{key}.json + data/sidebar.json
    ↓
Git auto-commit → GitHub Pages 自动部署
任何人打开链接即可看到最新数据
```

### 目标
- 任何人通过链接可访问仪表盘（GitHub Pages）
- 每天自动抓取 HKEX 数据更新侧边栏（GitHub Actions）
- 新股进入招股中时自动生成 pitch 分析（Anthropic API）

### 仓库结构
```
hk-ipo-dashboard/
├── index.html                  # 主仪表盘（就是现在这个 html 文件）
├── data/
│   ├── sidebar.json            # 每日自动更新（聆讯/招股状态）
│   └── pitches/                # 手动维护（每个 pitch 的分析数据）
│       ├── huayan.json
│       ├── fourier.json
│       └── ...
├── scripts/
│   └── scrape_hkex.py          # 每日抓取脚本
└── .github/
    └── workflows/
        └── daily-update.yml    # GitHub Actions 自动化
```

### 需要在 GitHub 做的事

**第一步：建仓库**
```bash
# 1. 在 GitHub 新建 public 仓库：hk-ipo-dashboard
# 2. 把 html 文件改名为 index.html 并上传
# 3. Settings → Pages → Source: main branch / root
# 4. 访问 https://[你的用户名].github.io/hk-ipo-dashboard/
```

**第二步：分离数据**

目前 `hk_ipo_stock_pitch.html` 的侧边栏数据是硬编码在 JS 里的。
需要把侧边栏状态提取到 `data/sidebar.json`，让 HTML 在加载时 `fetch('/data/sidebar.json')`。

`sidebar.json` 结构示例：
```json
{
  "lastUpdated": "2026-04-08",
  "activeSubscription": [],
  "hearingPassed": [
    {
      "key": "_stub_qunhe",
      "name": "群核科技",
      "alias": "酷家乐",
      "ticker": "TBD",
      "sector": "空间设计SaaS",
      "valuationNote": "估值175亿HKD",
      "hearingDate": "2026-03-29",
      "month": "2026-04",
      "week": "2026-W16",
      "badge": "buy"
    }
  ],
  "archived": [
    { "key": "huayan", "ticker": "1021.HK", "name": "华沿机器人", "result": "+68.4%", "listingDate": "2026-03-30" }
  ]
}
```

**第三步：选择 AI 后端并存入密钥（三选一）**

---

**✅ 方案一（最推荐）：Claude Code OAuth — 用你现有的 Claude 订阅**

> 需要 Claude Pro 或 Max 订阅。完全不需要额外付费或 API 账号。

```bash
# 1. 本地安装 Claude Code CLI（只需做一次）
npm install -g @anthropic-ai/claude-code

# 2. 生成长期 OAuth Token（有效期 1 年）
claude setup-token
# → 复制输出的 token 字符串

# 3. 存入 GitHub Secrets
仓库页面 → Settings → Secrets and variables → Actions
→ New repository secret
→ Name:  CLAUDE_CODE_OAUTH_TOKEN
→ Value: 上面复制的 token
```

---

**方案二（免费备选）：Google Gemini API — 完全免费，无需任何订阅**

> Gemini 2.5 Flash 免费额度：250次/天，对每日打新检查完全够用。

```bash
# 1. 获取免费 API Key（不需要信用卡）
打开 https://aistudio.google.com/app/apikey → 创建 API Key

# 2. 存入 GitHub Secrets
→ Name:  GEMINI_API_KEY
→ Value: 上面的 key

# 3. 在 workflow 里把注释改一下
# 把 CLAUDE_CODE_OAUTH_TOKEN 那行注释掉
# 把 GEMINI_API_KEY 那行取消注释
```

---

**方案三：Anthropic API Key（需要单独 API 账号，按量付费）**

> 费用估算：每次分析约 $0.04–0.08，每月约 $1–2。
> API key 从 https://console.anthropic.com/settings/keys 获取。
> 存入 GitHub Secrets 为 `ANTHROPIC_API_KEY`。

---

脚本会自动检测环境变量，按优先级选用可用后端，无需改代码。

**第四步：GitHub Actions 每日抓取 + 自动分析**

`.github/workflows/daily-update.yml`：
```yaml
name: Daily HKEX IPO Update

on:
  schedule:
    - cron: '0 2 * * 1-5'   # 每个工作日 UTC 02:00 = HKT 10:00
  workflow_dispatch:          # 允许手动触发

jobs:
  update-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install requests beautifulsoup4 lxml

      - name: Run scraper
        run: python scripts/scrape_hkex.py

      - name: Commit updated data
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/sidebar.json
          git diff --staged --quiet || git commit -m "chore: daily IPO data update $(date +%Y-%m-%d)"
          git push
```

**第四步：抓取脚本逻辑**

`scripts/scrape_hkex.py` 需要抓取的数据源：

| 数据 | 来源 | URL |
|------|------|-----|
| 新上市公司 | HKEX 新上市公司列表 | `https://www.hkex.com.hk/Market-Data/Securities-Prices/Equities` |
| 聆讯结果 | HKEX 聆讯公告搜索 | `https://www.hkex.com.hk/Listing/Rules-and-Guidance/Listing-decisions` |
| 招股信息 | 富途 IPO 日历 | `https://www.futunn.com/quote/market/ipo` |
| 孖展数据 | HKEX 配售公告 | 招股结束后第二天发布 |

> ⚠️ 注意：部分 HKEX 页面是动态渲染的（JS），`requests` 抓不到，可能需要 `selenium` 或直接用 HKEX API（如果有的话）。备选：抓取 AAStocks / 富途 H5 版本的 JSON API。

---

## 九、Cowork 每日定时任务（本地版）

除了 GitHub Actions，也在 Cowork 设置了每日提醒，每个工作日 HKT 09:30 执行以下检查：

**任务内容**：
1. 搜索 HKEX 当日聆讯公告 → 有新通过聆讯的公司则更新侧边栏
2. 搜索 Futu/Tiger IPO 日历 → 有新开始招股的则更新状态 + 提示补全分析
3. 搜索今日是否有招股截止 → 有则提示等待孖展超购数字
4. 搜索今日是否有定价公告 → 有则更新 comps TARGET + subStats

---

## 十、关键设计决策（不要改变）

1. **不显示已递A1公司** — 数据太早、不确定性太高，容易误导
2. **只显示3个月窗口** — 防止信息过载
3. **所有侧边栏条目必须有事实来源** — 不放推断、不放猜测
4. **comps 不含 P/B** — 已移除（科技/机器人公司 P/B 无参考意义）
5. **不评价保荐人质量好坏** — 只用超购倍数做客观评分
6. **锁定期到期/定期业绩不作为催化剂** — 必须有具体事件才能写

---

## 十一、文件清单

| 文件 | 位置 | 说明 |
|------|------|------|
| `hk_ipo_stock_pitch.html` | 港股打新工作流/ | 主仪表盘，约2900行 |
| `PROJECT_HANDOFF.md` | 港股打新工作流/ | 本文档 |

---

## 十二、下一步行动清单

- [ ] **GitHub**: 建 public 仓库 `hk-ipo-dashboard`，上传 index.html，开启 Pages
- [ ] **数据分离**: 把侧边栏状态提取为 `data/sidebar.json`，HTML 改为 fetch 加载
- [ ] **scraper**: 写 `scrape_hkex.py`，优先抓取富途 IPO 日历（比 HKEX 官网更结构化）
- [ ] **GitHub Actions**: 设置 `0 2 * * 1-5` cron（HKT 10:00）每日自动更新
- [ ] **_stub pitches**: 补全极视角、德适-B、瀚天、广合科技的完整分析数据
- [ ] **通过聆讯 pitches**: 等6家公司陆续开始招股，依次补全 `sellRec.thesisVsPrice`

---

*由 Claude (Cowork) 于 2026-04-08 生成*
