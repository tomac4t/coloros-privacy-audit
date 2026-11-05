import os, json, re, struct, subprocess
from collections import Counter

D = "/tmp/app_backup"
OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out")
rows = json.load(open(OUT + "/apk-index.json"))

def v2cert(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - 4 << 20 if False else max(0, size - 4194304)))
        tail = f.read()
    i = tail.rfind(b"APK Sig Block 42")
    if i <= 0:
        return None
    blk = tail[:i - 8]
    for m in re.finditer(b"\x30\x82", blk):
        s = m.start()
        ln = struct.unpack(">H", blk[s + 2:s + 4])[0]
        der = blk[s:s + 4 + ln]
        p = subprocess.run(["openssl", "x509", "-inform", "DER", "-noout", "-subject"],
                           input=der, capture_output=True)
        if p.returncode == 0:
            return p.stdout.decode().strip()
    return None

for r in rows:
    if r["cert"] == "UNKNOWN":
        s = v2cert(os.path.join(D, r["file"]))
        if s:
            r["cert"] = s

def vendor(c):
    if "Qualcomm" in c: return "Qualcomm"
    if "O = Oplus" in c: return "Oplus"
    if "O = OPPO" in c or "oppo@oppo" in c: return "OPPO"
    if "O = HeyTap" in c: return "HeyTap"
    if "O = OnePlus" in c: return "OnePlus"
    if "CN = nearme" in c: return "nearme"
    if "Baidu" in c: return "Baidu"
    if "Iflytek" in c: return "Iflytek"
    if "Google" in c or "android@android.com" in c: return "Google/AOSP"
    if "Microsoft" in c: return "Microsoft"
    return "UNKNOWN"

for r in rows:
    r["vendor"] = vendor(r["cert"])
json.dump(rows, open(OUT + "/apk-index.json", "w"), ensure_ascii=False, indent=1)
for k, v in Counter(r["vendor"] for r in rows).most_common():
    print(v, k)
print()
for r in rows:
    if r["vendor"] == "UNKNOWN":
        print(r["label"], r["pkg"])
