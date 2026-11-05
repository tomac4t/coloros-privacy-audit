#!/usr/bin/env python3
"""Phase 3: aggregate scan results -> host inventory + vendor classification."""
import os, json, re, glob, collections

OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out")
rows = {r["pkg"]: r for r in json.load(open(OUT + "/apk-index.json"))}

# --- noise / third-party infra that never should be blocked individually, but flag ---
NOISE_PAT = re.compile(
    r"(^|\.)(schemas\.android\.com|android\.googlesource\.com|googlesource\.com|issuetracker\.google\.com|"
    r"apache\.org|w3\.org|slf4j\.org|llvm\.org|codehaus\.org|puppycrawl\.com|python\.org|unicode\.org|"
    r"netty\.io|jboss\.org|openjsse|json\.org|github\.com|githubusercontent\.com|stackoverflow\.com|"
    r"kotlinlang\.org|gradle\.org|maven\.org|oracle\.com|example\.com|localhost|"
    r"apple\.com|microsoft\.com|bing\.com|office\.com|live\.com|msn\.com|windows\.com|"
    r"amazonaws\.com|amazonaws\.com\.cn|cloudfront\.net|akamai\.net|akamaized\.net|"
    r"gstatic\.com|googleapis\.com|google\.com|googleusercontent\.com|ggpht\.com|google-analytics\.com|"
    r"crashlytics\.com|firebaseio\.com|app-measurement\.com|doubleclick\.net|googletagmanager\.com|"
    r"bugly\.qq\.com|umeng\.com|umengcloud\.com|umsns\.com|"
    r"taobao\.com|tmall\.com|alipay\.com|alicdn\.com|alibaba\.com|aliyun\.com|alibabacloud\.com|"
    r"jd\.com|360buyimg\.com|weixin\.qq\.com|qq\.com|qpic\.cn|gtimg\.cn|myapp\.com|"
    r"bilibili\.com|hdslb\.com|douyin\.com|bytedance\.com|byteimg\.com|snssdk\.com|"
    r"amap\.com|autonavi\.com|baidu\.com|bdstatic\.com|"
    r"hihonor\.com|huawei\.com|hicloud\.com|vmall\.com|world\.126\.net|163\.com|126\.net)"
)
# infra / toolchain junk
JUNK_PAT = re.compile(
    r"(\.so$|\.kt$|\.java$|\.dex$|^\d+[a-z]|^(lib|os|java|javax|persist|sys|ro|dalvik|dalvikvm)\.|"
    r"^[a-z]+\.(name|app|org|net|link|com\.ai)$|"
    r"\.(name|id)$)"
)

def is_vendor_host(h):
    return bool(re.search(r"(oplus|oppo|heytap|coloros|nearme|oneplus|realme|oplusmobi|heytapmobi|hz-|"
                          r"allaw|itic\.cn|myoppo|oppomobile|coloros)", h))

agg = collections.defaultdict(lambda: {"apps": set(), "kind": set()})
privacy = collections.defaultdict(set)
toggles = collections.defaultdict(set)
trackers = collections.defaultdict(set)

for f in glob.glob(OUT + "/scan/*.json"):
    d = json.load(open(f))
    pkg = d["pkg"]
    for h in d["hosts"]:
        agg[h]["apps"].add(pkg)
    for u in d["urls"]:
        m = re.match(r"https?://([^/:?#]+)", u)
        if m:
            agg[m.group(1).lower()]["apps"].add(pkg)
    for p in d["privacy_links"]:
        privacy[pkg].add(p)
    for t in d["toggle_keys"]:
        toggles[pkg].add(t)
    for t in d["trackers"]:
        trackers[pkg].add(t)

# filter
clean = {}
for h, v in agg.items():
    if JUNK_PAT.search(h):
        continue
    if len(h) < 6 or "." not in h:
        continue
    clean[h] = v

vendor = {h: v for h, v in clean.items() if is_vendor_host(h)}
third = {h: v for h, v in clean.items() if not is_vendor_host(h) and not NOISE_PAT.search(h)}
noise = {h: v for h, v in clean.items() if NOISE_PAT.search(h)}

json.dump({"vendor": {k: sorted(v["apps"]) for k, v in vendor.items()},
           "thirdparty": {k: sorted(v["apps"]) for k, v in third.items()},
           "noise": sorted(noise)},
          open(OUT + "/hosts.json", "w"), ensure_ascii=False, indent=1)

print(f"vendor hosts: {len(vendor)}")
print(f"thirdparty hosts: {len(third)}")
print(f"noise hosts: {len(noise)}")
print(f"privacy links found in: {len(privacy)} pkgs")
print(f"pkgs with toggles: {len(toggles)}")
