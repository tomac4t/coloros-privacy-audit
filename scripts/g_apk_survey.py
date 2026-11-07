#!/usr/bin/env python3
"""G 组 APK 快速体检：提取权限 + 域名（含 dex 字符串扫描）。"""
import re
import subprocess
import sys
import zipfile


def get_manifest_strings(apk):
    try:
        out = subprocess.run(
            ["unzip", "-p", apk, "AndroidManifest.xml"],
            capture_output=True, timeout=60,
        ).stdout
    except Exception:
        return ""
    # binary XML: 尝试 utf-16-le 和 utf-8
    for enc in ("utf-16-le", "utf-8"):
        try:
            s = out.decode(enc, errors="ignore")
            if "android.permission" in s or "activity" in s:
                return s
        except Exception:
            pass
    return ""


def get_dex_strings(apk):
    chunks = []
    with zipfile.ZipFile(apk) as z:
        for n in z.namelist():
            if n.endswith(".dex"):
                chunks.append(z.read(n))
    data = b"".join(chunks)
    # 提取可打印 ASCII 串
    return set(re.findall(rb"[ -~]{6,}", data))


DOMAIN_RE = re.compile(
    rb"[a-z0-9][a-z0-9.-]{2,60}\."
    rb"(?:heytapmobi|oppomobile|coloros|heytap|oppo|allawntech|wanyol|"
    rb"googleapis|amap|map\.qq|baidu|cn|com|net)\b"
)


def main(apk, name):
    man = get_manifest_strings(apk)
    perms = sorted(set(re.findall(r"android\.permission\.[A-Z_]+", man)))

    strings = get_dex_strings(apk)
    domains = set()
    urls = set()
    for s in strings:
        if b"://" in s:
            m = re.search(rb"https?://[^\s\x00\"']+", s)
            if m:
                try:
                    urls.add(m.group(0).decode("ascii", "ignore"))
                except Exception:
                    pass
        for m in DOMAIN_RE.finditer(s):
            domains.add(m.group(0).decode("ascii", "ignore"))

    # 过滤明显的包名/类名噪音
    noise = re.compile(r"^(com|cn|net|org)\.[a-z]+\.[a-z]+$")
    domains = {d for d in domains if not noise.match(d)}

    print(f"### {name}")
    print(f"APK: {apk}")
    print(f"dex strings: {len(strings)}")
    print("\n**权限**")
    for p in perms:
        print(" -", p)
    print(f"\n**URL（{len(urls)}）**")
    for u in sorted(urls)[:40]:
        print(" -", u)
    print(f"\n**域名（{len(domains)}）**")
    for d in sorted(domains)[:60]:
        print(" -", d)
    print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else sys.argv[1])
