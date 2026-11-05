#!/usr/bin/env python3
"""Phase 7: privacy-policy URL + toggle-key mining, per package.
Only accept URLs whose path strongly implies privacy/agreement docs.
"""
import os, json, zipfile, re, glob, collections

APKDIR = "/tmp/app_backup"
OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out")
os.makedirs(OUT, exist_ok=True)

URL_RE = re.compile(rb"https?://[A-Za-z0-9\-._~:/?#@!$&'()*+,;=%\[\]]{8,200}")
GOOD = re.compile(r"(?i)(privacy|private.?policy|policy|agreement|protocol|terms|consent|statement|"
                  r"legal|eula|permission|declaration|授权|隐私|协议)")

TOGGLE_KEYS = [
    r"(?i)key_?user_?experience", r"(?i)user_?experience_?improve", r"(?i)ux_?_?improve",
    r"(?i)key_?collect_?diag", r"(?i)collect_?personal_?info", r"(?i)personal_?info_?collect",
    r"(?i)key_?personalize", r"(?i)personalized_?recommend", r"(?i)key_?recommend",
    r"(?i)key_?analytics", r"(?i)key_?statistic", r"(?i)key_?track",
    r"(?i)key_?ad_?personal", r"(?i)key_?improve", r"(?i)key_?diagnostic",
    r"(?i)key_?data_?sharing", r"(?i)key_?cloud_?analysis", r"(?i)key_?smart_?service",
    r"(?i)key_?ai_?service", r"(?i)key_?withdraw", r"(?i)key_?revoke",
    r"(?i)privacy_?switch", r"(?i)key_?ad_?id", r"(?i)key_?oaid",
    r"(?i)pref_?key_?collect", r"(?i)pref_?key_?privacy", r"(?i)key_?usage_?data",
]
TOGGLE_RE = [re.compile(k.encode()) for k in TOGGLE_KEYS]

def urls_in(data):
    out = set()
    for m in URL_RE.finditer(data):
        try:
            u = m.group().decode("utf-8")
        except Exception:
            continue
        if GOOD.search(u):
            out.add(u)
    return out

result = {}
files = sorted(f for f in os.listdir(APKDIR) if f.endswith(".apk"))
for f in files:
    pkg = f[:-4].rsplit("_", 1)[-1]
    links, keys = set(), set()
    try:
        z = zipfile.ZipFile(os.path.join(APKDIR, f))
        for n in z.namelist():
            low = n.lower()
            if not (low.endswith((".dex", ".arsc", ".xml")) or "/assets/" in low):
                continue
            try:
                data = z.read(n)
            except Exception:
                continue
            links |= urls_in(data)
            for r in TOGGLE_RE:
                for m in r.finditer(data):
                    keys.add(m.group().decode("utf-8", "ignore")[:80])
    except Exception as e:
        pass
    if links or keys:
        result[pkg] = {"privacy_links": sorted(links), "toggle_keys": sorted(keys)}

json.dump(result, open(OUT + "/privacy-toggles.json", "w"), ensure_ascii=False, indent=1)
print("pkgs with hits:", len(result))
print("pkgs with privacy links:", sum(1 for v in result.values() if v["privacy_links"]))
print("pkgs with toggle keys:", sum(1 for v in result.values() if v["toggle_keys"]))
