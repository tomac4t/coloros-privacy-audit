#!/usr/bin/env python3
"""
RegService (com.coloros.regservice) 上报流量解码 / 离线分析工具
================================================================

用途：
  1. 解开该 APK 用 AES 加密的上报 body，还原成明文 JSON
  2. 解析本地 cmcc_dm.db（sqlite），把「按 UID 归一」的数据还原成包名
  3. 生成可手工分析的 Markdown 报告

密钥来源（已静态确认，见 README §密码学）：
  libaes-jni.so  .rodata = "134e3265829ff82daf16e7b740a600b5"
  AesUtil.encodeAES(src, key)
      keyBytes = MD5(key)            # 32 位小写 hex 字符串的 ASCII，32 字节
      Cipher AES/ECB/PKCS5Padding
      return Base64(密文)

另一种：GZIPJsonRequest 先 gzip 再 AES，解密后要 gunzip。

用法：
  # 解密一段 base64 密文
  python3 dm_decode.py decrypt 'BASE64...'
  python3 dm_decode.py decrypt --file body.b64
  python3 dm_decode.py decrypt --file body.b64 --key 你的key

  # 解密并自动 gunzip / JSON 格式化
  python3 dm_decode.py decrypt --file body.b64 --json

  # 加密（用来自测 / 或构造回放包）
  python3 dm_decode.py encrypt '{"a":1}'

  # 分析 cmcc_dm.db（先 adb pull）
  python3 dm_decode.py db cmcc_dm.db --out report.md

  # 分析数据目录里所有 json / 明文
  python3 dm_decode.py scan ./regservice_data
"""

import argparse
import base64
import gzip
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

DEFAULT_KEY = "134e3265829ff82daf16e7b740a600b5"

try:
    from Crypto.Cipher import AES  # pycryptodome
except ImportError:
    AES = None


# --------------------------------------------------------------------------
# 密码学
# --------------------------------------------------------------------------
def _aes_key(key: str) -> bytes:
    """与 AesUtil.encodeAES 完全一致：SecretKeySpec(MD5(key) 的 ASCII, "AES")"""
    return hashlib.md5(key.encode("utf-8")).hexdigest().encode("ascii")


def aes_decrypt(b64_text: str, key: str = DEFAULT_KEY) -> bytes:
    if AES is None:
        raise RuntimeError("需要 pycryptodome: pip install pycryptodome")
    raw = base64.b64decode(b64_text.strip())
    cipher = AES.new(_aes_key(key), AES.MODE_ECB)
    padded = cipher.decrypt(raw)
    return unpad_pkcs5(padded)


def aes_encrypt(text: str | bytes, key: str = DEFAULT_KEY) -> str:
    if AES is None:
        raise RuntimeError("需要 pycryptodome: pip install pycryptodome")
    data = text.encode("utf-8") if isinstance(text, str) else text
    cipher = AES.new(_aes_key(key), AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad_pkcs5(data))).decode()


def pad_pkcs5(data: bytes, block: int = 16) -> bytes:
    n = block - len(data) % block
    return data + bytes([n]) * n


def unpad_pkcs5(data: bytes) -> bytes:
    if not data:
        return data
    n = data[-1]
    if 1 <= n <= 16 and data[-n:] == bytes([n]) * n:
        return data[:-n]
    return data


def guess_body_bytes(decrypted: bytes) -> bytes:
    """自动识别是否 gzip（GZIPJsonRequest 路径）"""
    if decrypted[:2] == b"\x1f\x8b":
        return gzip.decompress(decrypted)
    return decrypted


# --------------------------------------------------------------------------
# URL 签名（可以据此判断某个 token 是否由「真实 IMEI」算出）
# --------------------------------------------------------------------------
def url_token(imei: str, timestr: str) -> str:
    """MobileUtil.getVerifyMD5: MD5(imei1 + last8(timestr))"""
    return hashlib.md5((imei + timestr[-8:]).encode()).hexdigest()


# --------------------------------------------------------------------------
# cmcc_dm.db 分析
# --------------------------------------------------------------------------
# 上报字段顺序（bean/a.java C0000a.a(Context) 的 logAppAry 拼接顺序）
#   pkgName|appName|launchCount|useTime|mobileRx|mobileTx|uid|appFlags|wifiRx|wifiTx
APP_ROW_FIELDS = [
    "pkgName", "appName", "launchCount", "useTimeSec",
    "mobileRx", "mobileTx", "uid", "appFlags", "wifiRx", "wifiTx",
]

SENSITIVE_PKG_PATTERNS = [
    (r"bank|icbc|ccb|abchina|boc\.|cmb|spdb|cebbank|psbc|bocom|pingan|"
     r"alipay|unionpay|epay|citics|htsc|swhy|galaxy|zszq|mszq", "银行/支付/证券"),
    (r"hospital|doctor|health|medical|dxy|chunyuyisheng|haodf|jhzl", "医疗健康"),
    (r"sex|health\b|qy|yuepao|tantan|momo|soul", "交友/约会（弱匹配）"),
    (r"tinder|grindr|blued|hornet", "LGBT 交友"),
    (r"pregnan|menstrual|period|due\.date", "生理健康"),
    (r"weixin|tencent\.mm|telegram|whatsapp|signal|session|threema", "IM/通讯"),
    (r"vpn|clash|v2ray|xray|shadowsocks|wireguard|surfboard|stash", "翻墙/VPN"),
    (r"tor|orbot|onion", "匿名网络"),
    (r"\bwps|office|documents", "文档"),
    (r"camera|gallery|photo|album", "相册/相机"),
    (r"douyin|musically|kuaishou|bilibili|iqiyi|youku", "短视频/长视频"),
    (r"taobao|pinduoduo|jingdong|jd\.|tieba", "电商/社区"),
    (r"torrent|thunder|magnet", "下载/BT"),
    (r"dating|marriage|jiayuan|zhenai", "婚恋"),
]


def db_list_tables(conn):
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r[0] for r in cur.fetchall()]


def db_dump_table(conn, table):
    cur = conn.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in cur.description]
    return cols, cur.fetchall()


def read_app_rows(conn, table):
    """app_info_<ts> 表 → list[dict]，字段名按 DbConstants 兜底映射"""
    cur = conn.execute(f'SELECT * FROM "{table}"')
    cols = [d[0] for d in cur.description]
    rows = []
    for r in cur.fetchall():
        d = dict(zip(cols, r))
        # 两种列名风格：带下划线（DbConstants 的 COLUMN_*）或裸名
        norm = {
            "pkgName": d.get("_pkgName") or d.get("package_name") or d.get("pkgName"),
            "appName": d.get("app_name") or d.get("appName"),
            "launchCount": d.get("_launchCount"),
            "useTimeSec": d.get("_useTime"),
            "mobileRx": d.get("_mobile_rx"),
            "mobileTx": d.get("_mobile_tx"),
            "uid": d.get("_uid"),
            "appFlags": d.get("_app_flags"),
            "wifiRx": d.get("_wifi_rx"),
            "wifiTx": d.get("_wifi_tx"),
        }
        rows.append(norm)
    return rows


def classify(pkg: str, label: str) -> list[str]:
    hits = []
    blob = f"{pkg or ''} {label or ''}".lower()
    for pat, name in SENSITIVE_PKG_PATTERNS:
        if re.search(pat, blob):
            hits.append(name)
    return hits


def fmt_bytes(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def fmt_secs(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return str(n)
    if n < 60:
        return f"{n}s"
    if n < 3600:
        return f"{n // 60}m{n % 60}s"
    return f"{n // 3600}h{(n % 3600) // 60}m"


def analyze_db(path: Path, out_md: Path | None):
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    tables = db_list_tables(conn)
    lines = [f"# cmcc_dm.db 分析报告\n", f"文件: `{path}`\n"]

    app_tables = [t for t in tables if t.startswith("app_info_")]
    other_tables = [t for t in tables if not t.startswith("app_info_")]

    lines.append(f"## 表清单（{len(tables)} 张）\n")
    for t in tables:
        try:
            _, rows = db_dump_table(conn, t)
            n = len(rows)
        except Exception:
            n = "?"
        kind = "应用采集周期" if t.startswith("app_info_") else "其他"
        lines.append(f"- `{t}` ({kind}, {n} 行)")
    lines.append("")

    # ---- 应用采集
    all_sensitive = {}
    total_apps = 0
    lines.append("## 应用使用数据\n")
    lines.append("字段含义：安装启动次数 / 前台累计时长 / 按 UID 统计的移动+WiFi 收发字节\n")
    for t in sorted(app_tables):
        rows = read_app_rows(conn, t)
        total_apps += len(rows)
        lines.append(f"### `{t}` —— {len(rows)} 个应用\n")
        if not rows:
            continue
        rows_sorted = sorted(rows, key=lambda r: (r["useTimeSec"] or 0), reverse=True)
        lines.append("| 包名 | 应用名 | 启动次数 | 前台时长 | 移动↑↓ | WiFi↑↓ | 敏感分类 |")
        lines.append("|---|---|---|---|---|---|---|")
        for r in rows_sorted[:60]:
            cls = classify(r["pkgName"], r["appName"])
            for c in cls:
                all_sensitive.setdefault(c, set()).add((r["pkgName"], r["appName"]))
            lines.append(
                f"| `{r['pkgName']}` | {r['appName']} | {r['launchCount']} | "
                f"{fmt_secs(r['useTimeSec'])} | {fmt_bytes(r['mobileRx'])}/{fmt_bytes(r['mobileTx'])} | "
                f"{fmt_bytes(r['wifiRx'])}/{fmt_bytes(r['wifiTx'])} | {', '.join(cls)} |"
            )
        if len(rows_sorted) > 60:
            lines.append(f"| … | 共 {len(rows_sorted)} 行 | | | | | |")
        lines.append("")

    lines.append(f"## 敏感应用命中汇总（全库 {total_apps} 行）\n")
    if all_sensitive:
        for cls, items in sorted(all_sensitive.items(), key=lambda kv: -len(kv[1])):
            lines.append(f"### {cls} —— {len(items)} 个\n")
            for pkg, name in sorted(items)[:40]:
                lines.append(f"- `{pkg}` {name}")
            if len(items) > 40:
                lines.append(f"- …共 {len(items)} 个")
            lines.append("")
    else:
        lines.append("（未命中，可能库里是包名以外的标识）\n")

    # ---- 其他表
    lines.append("## 其他表内容\n")
    for t in other_tables:
        cols, rows = db_dump_table(conn, t)
        lines.append(f"### `{t}` ({len(rows)} 行)\n")
        lines.append(f"字段: {', '.join(cols)}\n")
        for r in rows[:5]:
            sample = {c: (str(v)[:120] if v is not None else None) for c, v in zip(cols, r)}
            lines.append(f"```json\n{json.dumps(sample, ensure_ascii=False, indent=2)}\n```")
        lines.append("")

    text = "\n".join(lines)
    if out_md:
        out_md.write_text(text, encoding="utf-8")
        print(f"已写入 {out_md}")
    else:
        print(text)
    conn.close()


# --------------------------------------------------------------------------
# 目录扫描：找出所有可能是密文的文件并尝试解密
# --------------------------------------------------------------------------
def scan_dir(root: Path):
    suspicious = re.compile(r"^[A-Za-z0-9+/=\s]{40,}$")
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.stat().st_size > 8 * 1024 * 1024:
            continue
        try:
            head = p.read_bytes()[:4000]
        except Exception:
            continue
        if head[:2] == b"\x1f\x8b":
            try:
                print(f"[gzip] {p}")
                print(gzip.decompress(p.read_bytes())[:800].decode("utf-8", "replace"))
            except Exception:
                pass
            continue
        if head[:1] in (b"{", b"["):
            print(f"[json] {p}")
            continue
        try:
            txt = head.decode("ascii")
        except UnicodeDecodeError:
            continue
        if suspicious.match(txt):
            try:
                plain = guess_body_bytes(aes_decrypt(p.read_text()))
                print(f"[aes→] {p}")
                print(plain[:800].decode("utf-8", "replace"))
            except Exception:
                pass


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="RegService 上报解码工具")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("decrypt", help="AES 解密上报 body")
    d.add_argument("text", nargs="?", help="base64 密文")
    d.add_argument("--file", help="从文件读 base64")
    d.add_argument("--key", default=DEFAULT_KEY)
    d.add_argument("--json", action="store_true", help="JSON 美化输出")

    e = sub.add_parser("encrypt", help="AES 加密（自测用）")
    e.add_argument("text")
    e.add_argument("--key", default=DEFAULT_KEY)

    t = sub.add_parser("token", help="计算 URL token = MD5(imei+last8(timestr))")
    t.add_argument("imei")
    t.add_argument("timestr")

    b = sub.add_parser("db", help="分析 cmcc_dm.db")
    b.add_argument("path")
    b.add_argument("--out", help="输出 Markdown 文件")

    s = sub.add_parser("scan", help="递归扫描数据目录并尝试解密")
    s.add_argument("path")

    args = ap.parse_args()

    if args.cmd == "decrypt":
        data = args.text if args.text else Path(args.file).read_text()
        plain = guess_body_bytes(aes_decrypt(data, args.key))
        try:
            s_ = plain.decode("utf-8")
        except UnicodeDecodeError:
            print(plain.hex())
            return
        if args.json:
            try:
                print(json.dumps(json.loads(s_), ensure_ascii=False, indent=2))
                return
            except json.JSONDecodeError:
                pass
        print(s_)

    elif args.cmd == "encrypt":
        print(aes_encrypt(args.text, args.key))

    elif args.cmd == "token":
        print(url_token(args.imei, args.timestr))

    elif args.cmd == "db":
        analyze_db(Path(args.path), Path(args.out) if args.out else None)

    elif args.cmd == "scan":
        scan_dir(Path(args.path))


if __name__ == "__main__":
    main()
