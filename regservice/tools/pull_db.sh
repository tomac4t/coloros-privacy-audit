#!/usr/bin/env bash
# 拉取 RegService 的本地采集库 / 动态包，用于本地离线分析
# 用法: bash tools/pull_db.sh [输出目录]
#
# 不会修改设备、不会上传任何东西，只做 adb pull。
set -u
OUT=${1:-./regservice_data}
PKG=com.coloros.regservice

mkdir -p "$OUT"

echo "== 0. 设备连接检查"
adb devices | sed -n '2,$p'
if ! adb shell pm path "$PKG" >/dev/null 2>&1; then
  echo "!! 找不到包 $PKG，或设备未授权"; exit 1
fi
adb shell pm path "$PKG"

echo
echo "== 1. 关键：有没有被下发过动态包（有 = 远程代码已激活）"
adb shell "run-as $PKG ls -l files/dynamic/ 2>&1" || true

echo
echo "== 2. 数据库目录（注意 -wal / -shm 也要拿）"
adb shell "run-as $PKG ls -l databases/ 2>&1" || true

echo
echo "== 3. 导出数据库"
# 第一选择：run-as 直接 cat 到 stdout，adb exec-out 会做二进制透传、不会破坏换行
if adb exec-out "run-as $PKG cat databases/cmcc_dm.db" > "$OUT/cmcc_dm.db" 2>"$OUT/.err" && \
   [ -s "$OUT/cmcc_dm.db" ] && head -c 15 "$OUT/cmcc_dm.db" | grep -q "SQLite format 3"; then
  echo "   run-as cat 成功"
else
  echo "   run-as 不可用（系统应用常被禁 run-as）。尝试其他路径："
  rm -f "$OUT/cmcc_dm.db"

  # 第二选择：真机已 root（Magisk su）
  if adb shell "su -c 'ls /data/data/$PKG/databases/cmcc_dm.db'" >/dev/null 2>&1; then
    echo "   -> 检测到 root，走 su"
    adb exec-out "su -c 'cat /data/data/$PKG/databases/cmcc_dm.db'" > "$OUT/cmcc_dm.db"

  # 第三选择：设备可 adb root（仅 userdebug 版）
  elif adb root >/dev/null 2>&1 && adb wait-for-device && \
       adb shell "ls /data/data/$PKG/databases/cmcc_dm.db" >/dev/null 2>&1; then
    echo "   -> adb root 生效"
    adb exec-out "cat /data/data/$PKG/databases/cmcc_dm.db" > "$OUT/cmcc_dm.db"

  # 第四选择：debuggable 包走 run-as cp 到 sdcard，再 pull
  elif adb shell "run-as $PKG cp databases/cmcc_dm.db /data/local/tmp/cmcc_dm.db" >/dev/null 2>&1 \
       && adb shell "cat /data/local/tmp/cmcc_dm.db" > "$OUT/cmcc_dm.db" 2>/dev/null; then
    echo "   -> run-as cp 到 /data/local/tmp 成功"
  else
    echo "!! 全部失败。设备大概率：系统应用禁止 run-as + 未 root + 非 userdebug。"
    echo "   可选方案见下方提示。"
    exit 1
  fi
fi

# WAL 模式：最新数据在 -wal 里，缺了就看不到刚采集的这批
for f in cmcc_dm.db-wal cmcc_dm.db-shm; do
  if adb shell "su -c 'ls /data/data/$PKG/databases/$f'" >/dev/null 2>&1; then
    adb exec-out "su -c 'cat /data/data/$PKG/databases/$f'" > "$OUT/$f" 2>/dev/null || true
  fi
done

echo
echo "== 4. 校验"
ls -l "$OUT"/cmcc_dm.db* 2>/dev/null

echo
echo "== 5. 生成分析报告"
python3 "$(dirname "$0")/dm_decode.py" db "$OUT/cmcc_dm.db" --out "$OUT/db-report.md"

echo
echo "完成。报告: $OUT/db-report.md"
echo "⚠️ $OUT 含真实使用记录，请勿外传，分析完记得删除。"
