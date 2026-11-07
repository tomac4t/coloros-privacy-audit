#!/usr/bin/env bash
# G 组（系统治理/诊断）批量反编译脚本
# 用法: bash decompile_g.sh [apk_dir] [out_dir]
set -u
JADX=~/.openclaw/workspace/tools/jadx/bin/jadx
APK_DIR=${1:-/tmp/g-apk}
OUT=${2:-/tmp/gref}

declare -A MAP=(
  [athena]=athena.apk
  [qtiLoc]=qtiLoc.apk
  [fused]=fused.apk
  [dw]=dw.apk
  [battery]=battery.apk
  [exsystem]=exsystem.apk
  [oplusloc]=oplusloc.apk
  [powermon]=powermon.apk
)

mkdir -p "$OUT"
for name in "${!MAP[@]}"; do
  apk="$APK_DIR/${MAP[$name]}"
  [ -f "$apk" ] || { echo "SKIP $name (missing $apk)"; continue; }
  dst="$OUT/out_$name"
  [ -d "$dst" ] && { echo "SKIP $name (already at $dst)"; continue; }
  echo ">>> decompiling $name ..."
  "$JADX" -d "$dst" -j 4 --no-res "$apk" > "$OUT/$name.log" 2>&1
  echo "    files: $(find "$dst" -name '*.java' 2>/dev/null | wc -l)"
done
echo "done."
