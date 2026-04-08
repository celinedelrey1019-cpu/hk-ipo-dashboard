#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  港股打新仪表盘 — GitHub 一键初始化脚本
#  使用方法: 把这个脚本丢给 Claude Code 执行
#  前提: 已安装 gh CLI 并已登录 (gh auth login)
# ═══════════════════════════════════════════════════════════════

set -e  # 任何步骤失败即停止

REPO_NAME="hk-ipo-dashboard"
GITHUB_USER=$(gh api user --jq '.login')
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"  # 脚本所在目录 = 港股打新工作流/

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  港股打新仪表盘 GitHub 一键初始化         ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "GitHub 用户: $GITHUB_USER"
echo "仓库名:      $REPO_NAME"
echo "本地目录:    $REPO_DIR"
echo ""

# ── Step 1: 检查依赖 ─────────────────────────────────────────────────────────
echo "▶ Step 1/6  检查依赖..."

if ! command -v gh &> /dev/null; then
  echo "  ✗ gh CLI 未安装。请先运行: brew install gh && gh auth login"
  exit 1
fi

if ! gh auth status &> /dev/null; then
  echo "  ✗ GitHub 未登录。请先运行: gh auth login"
  exit 1
fi

echo "  ✓ gh CLI 已就绪，已登录为 $GITHUB_USER"

# ── Step 2: 创建 GitHub 仓库 ─────────────────────────────────────────────────
echo ""
echo "▶ Step 2/6  创建 GitHub 仓库..."

if gh repo view "$GITHUB_USER/$REPO_NAME" &> /dev/null; then
  echo "  ℹ 仓库已存在，跳过创建"
else
  gh repo create "$REPO_NAME" \
    --public \
    --description "港股打新工作流 — HK IPO Daily Dashboard" \
    --confirm 2>/dev/null || \
  gh repo create "$REPO_NAME" \
    --public \
    --description "港股打新工作流 — HK IPO Daily Dashboard"
  echo "  ✓ 仓库已创建: https://github.com/$GITHUB_USER/$REPO_NAME"
fi

# ── Step 3: 初始化 git 并推送文件 ────────────────────────────────────────────
echo ""
echo "▶ Step 3/6  推送文件到 GitHub..."

cd "$REPO_DIR"

# 重命名主文件为 index.html（GitHub Pages 需要）
if [ -f "hk_ipo_stock_pitch.html" ] && [ ! -f "index.html" ]; then
  cp hk_ipo_stock_pitch.html index.html
  echo "  ✓ hk_ipo_stock_pitch.html → index.html"
fi

# 创建必要的目录结构
mkdir -p data/pitches
mkdir -p .github/workflows

# 创建初始 sidebar.json（如果不存在）
if [ ! -f "data/sidebar.json" ]; then
  cat > data/sidebar.json << 'EOF'
{
  "lastUpdated": "init",
  "activeSubscription": [],
  "hearingPassed": [],
  "archived": []
}
EOF
  echo "  ✓ 创建 data/sidebar.json 初始文件"
fi

# 创建 .gitignore
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.env
.DS_Store
/tmp/
EOF

# git 初始化 & 推送
REMOTE_URL="https://github.com/$GITHUB_USER/$REPO_NAME.git"

if [ ! -d ".git" ]; then
  git init
  git remote add origin "$REMOTE_URL"
else
  # 确保 remote 指向正确
  git remote set-url origin "$REMOTE_URL" 2>/dev/null || git remote add origin "$REMOTE_URL"
fi

git add -A
git diff --staged --quiet && echo "  ℹ 无新变更" || {
  git commit -m "init: 港股打新仪表盘初始化"
  git branch -M main
  git push -u origin main
  echo "  ✓ 文件已推送到 GitHub"
}

# ── Step 4: 开启 GitHub Pages ────────────────────────────────────────────────
echo ""
echo "▶ Step 4/6  开启 GitHub Pages..."

gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/$GITHUB_USER/$REPO_NAME/pages" \
  -f "source[branch]=main" \
  -f "source[path]=/" \
  2>/dev/null && echo "  ✓ GitHub Pages 已开启" || echo "  ℹ GitHub Pages 已存在或正在生效（可忽略）"

PAGES_URL="https://$GITHUB_USER.github.io/$REPO_NAME/"
echo "  🌐 访问地址: $PAGES_URL（约1分钟后生效）"

# ── Step 5: 生成 Claude OAuth Token ─────────────────────────────────────────
echo ""
echo "▶ Step 5/6  生成 Claude Code OAuth Token..."
echo "  （会打开浏览器进行授权，完成后自动继续）"
echo ""

TOKEN_OUTPUT=$(claude setup-token 2>&1)
OAUTH_TOKEN=$(echo "$TOKEN_OUTPUT" | grep -oE 'sk-ant-oat[A-Za-z0-9_-]+' | head -1)

if [ -z "$OAUTH_TOKEN" ]; then
  # 尝试其他 token 格式
  OAUTH_TOKEN=$(echo "$TOKEN_OUTPUT" | grep -oE '[A-Za-z0-9_-]{40,}' | head -1)
fi

if [ -z "$OAUTH_TOKEN" ]; then
  echo "  ⚠ 无法自动提取 token，请手动复制 claude setup-token 的输出并运行："
  echo "    gh secret set CLAUDE_CODE_OAUTH_TOKEN --body \"<your-token>\""
  echo ""
  echo "  claude setup-token 输出内容："
  echo "$TOKEN_OUTPUT"
else
  echo "  ✓ Token 已获取"
fi

# ── Step 6: 存入 GitHub Secrets ──────────────────────────────────────────────
echo ""
echo "▶ Step 6/6  存入 GitHub Secrets..."

if [ -n "$OAUTH_TOKEN" ]; then
  echo "$OAUTH_TOKEN" | gh secret set CLAUDE_CODE_OAUTH_TOKEN \
    --repo "$GITHUB_USER/$REPO_NAME"
  echo "  ✓ CLAUDE_CODE_OAUTH_TOKEN 已存入 GitHub Secrets"
else
  echo "  ⚠ 请手动设置 secret（见上方说明）"
fi

# ── 完成 ─────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ 初始化完成！                                          ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
printf "║  🌐 仪表盘地址: %-40s ║\n" "$PAGES_URL"
printf "║  📦 GitHub 仓库: %-40s ║\n" "https://github.com/$GITHUB_USER/$REPO_NAME"
echo "║                                                          ║"
echo "║  ⏱  GitHub Actions 每天 HKT 10:00 自动运行              ║"
echo "║  📊 新股进入招股中时自动生成 pitch 分析                   ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
