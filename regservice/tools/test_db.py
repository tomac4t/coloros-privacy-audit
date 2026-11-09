#!/usr/bin/env python3
"""用合成数据验证 dm_decode.py 的 db 分析能力（不会接触任何真实数据）"""
import random
import sqlite3
import sys
from pathlib import Path

out = Path("/tmp/dm_test.db")
out.unlink(missing_ok=True)

conn = sqlite3.connect(out)
conn.execute(
    """CREATE TABLE app_info_1759800000000 (
    _id INTEGER PRIMARY KEY, _pkgName TEXT, app_name TEXT, _uid INTEGER,
    _launchCount INTEGER, _useTime INTEGER, _mobile_rx INTEGER, _mobile_tx INTEGER,
    _wifi_rx INTEGER, _wifi_tx INTEGER, _app_flags INTEGER)"""
)
rows = [
    ("com.eg.android.AlipayGphone", "支付宝", 10001, 412, 92831, 8_400_000, 1_200_000, 44_000, 9_100, 0),
    ("com.tencent.mm", "微信", 10002, 1877, 412_000, 210_000_000, 51_000_000, 3_100_000, 900_000, 0),
    ("com.icbc", "中国工商银行", 10003, 33, 5_400, 120_000, 30_000, 1_200, 400, 0),
    ("com.tencent.tmgp.sgame", "王者荣耀", 10004, 210, 51_000, 0, 0, 2_200_000, 700_000, 0),
    ("com.android.systemui", "系统界面", 1000, 0, 0, 0, 0, 0, 0, 1),
    ("com.zhiliaoapp.musically.fake", "抖音", 10005, 640, 210_000, 0, 0, 8_900_000, 1_100_000, 0),
    ("com.dxy.patient", "丁香医生", 10006, 12, 900, 10_000, 2_000, 300, 90, 0),
]
for r in rows:
    conn.execute(
        "INSERT INTO app_info_1759800000000 "
        "(_pkgName, app_name, _uid, _launchCount, _useTime, _mobile_rx, _mobile_tx, _wifi_rx, _wifi_tx, _app_flags) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        r,
    )

conn.execute(
    """CREATE TABLE table_name_wifi_list (
    _id INTEGER PRIMARY KEY, _wifi_list TEXT, _timestamp INTEGER)"""
)
conn.execute(
    "INSERT INTO table_name_wifi_list (_wifi_list, _timestamp) VALUES (?, ?)",
    ('[{"bssid":"00:11:22:33:44:55","ssid":"Home-5G","rssi":"-48"}]', 1759800100000),
)
conn.execute(
    """CREATE TABLE table_name_network (netcard TEXT, net_type1 TEXT, cellid1 TEXT, lac1 TEXT)"""
)
conn.execute("INSERT INTO table_name_network VALUES (?,?,?,?)", ("0", "13", "123456789", "4096"))
conn.commit()
conn.close()

sys.path.insert(0, "tools")
import dm_decode  # noqa: E402

dm_decode.analyze_db(out, Path("/tmp/dm_test-report.md"))
print("\n---- 敏感分类命中检查 ----")
s = Path("/tmp/dm_test-report.md").read_text()
for expect in ["银行/支付/证券", "医疗健康", "IM/通讯", "短视频/长视频"]:
    print(f"{expect:12s}", "OK" if expect in s else "MISS")
