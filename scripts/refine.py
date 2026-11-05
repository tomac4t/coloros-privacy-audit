#!/usr/bin/env python3
"""Phase 4: refine host classification.
Rules:
 - vendor host = registrable domain in VENDOR_DOMAINS, OR explicitly listed as known vendor infra
 - kill classname artifacts: label ends with common java type suffix and parent looks like namespace,
   or starts with a digit, or has >=5 labels with no /-service prefix
"""
import os, json, re, collections

OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out")
d = json.load(open(OUT + "/hosts.json"))

VENDOR_DOMAINS = {
    "heytapmobi.com", "heytapmobile.com", "heytap.com", "heytapimage.com", "heytapimg.com",
    "heytapdownload.com", "heytapdl.com", "heytapcs.com", "heytap.cloud",
    "oppomobile.com", "oppo.com", "oppo.cn", "opposhop.cn", "oppoer.me", "myservices.oppo.com",
    "allawntech.com", "allawnos.com", "allawnfs.com",
    "coloros.com", "coloros.cloud", "nearme.com.cn", "nearx.net",
    "oneplus.com", "oneplus.cn", "onetest.com",
    "realme.com", "realmemobile.com",
    "oplus.com", "oplus.ai", "oplus.vip", "oplus.app",
    "wanyol.com", "opposugar.com", "oppoer.com",
    "heytapinc.com", "oppomobile.net", "heytap.net",
}

JAVA_TAIL = {"app", "net", "info", "cloud", "store", "ai", "live", "online", "tv", "one",
             "work", "file", "dev", "top", "link", "vip", "pro", "cn", "com", "org",
             "biz", "sdk", "api", "service", "provider", "manager", "util", "impl",
             "base", "core", "common", "model", "entity", "task", "data", "engine",
             "protocol", "bean", "result", "label", "integrate", "capability", "fence",
             "recorder", "settings", "bussiness", "details", "dum", "dump"}

TLDS = {"com", "cn", "net", "org", "io", "me", "tv", "cc", "info", "vip", "top", "site",
        "club", "online", "tech", "app", "dev", "ai", "hk", "sg", "us", "jp", "kr", "tw",
        "de", "uk", "cloud", "link", "pro", "biz", "mobi", "name", "shop", "store", "fun",
        "live", "life", "world", "work", "space", "icu", "ink", "pw", "one", "plus", "pub",
        "asia", "so", "gg", "fm", "cyou", "me", "co"}

def base_domain(h):
    p = h.lower().split(".")
    if len(p) >= 3 and p[-2] in ("com", "net", "org", "gov", "edu") and len(p[-1]) == 2:
        return ".".join(p[-3:])
    return ".".join(p[-2:])

def looks_fake(h):
    p = h.lower().split(".")
    if any(re.match(r"^\d", x) for x in p):
        return True
    # last label must be a real TLD
    if p[-1] not in TLDS:
        return True
    if h.endswith(".so"):
        return True
    # label that is a Java camelCase identifier -> classname
    for lab in p:
        if re.search(r"[a-z][A-Z]", lab):
            return True
    # reverse-dns namespace: com.foo.bar.<java word> where 4th-last is com/org/net
    if len(p) >= 5 and p[-5] in ("com", "org", "net", "cn") and p[-4] in (
            "oplus", "coloros", "heytap", "nearme", "oneplus", "oppo", "androidx", "android"):
        return True
    return False

vendor, third, junk = {}, {}, []
for h, apps in d["vendor"].items():
    if looks_fake(h):
        junk.append(h)
        continue
    b = base_domain(h)
    if b in VENDOR_DOMAINS:
        vendor[h] = {"apps": apps, "base": b}
print("vendor kept:", len(vendor), "| dropped-as-fake:", len(junk))

# thirdparty: remove fakes too
thirdclean, tjunk = {}, []
for h, apps in d["thirdparty"].items():
    if looks_fake(h):
        tjunk.append(h)
        continue
    thirdclean[h] = {"apps": apps, "base": base_domain(h)}
print("thirdparty kept:", len(thirdclean), "| dropped:", len(tjunk))

json.dump({"vendor": vendor, "thirdparty": thirdclean, "dropped": sorted(junk + tjunk)},
          open(OUT + "/hosts-clean.json", "w"), ensure_ascii=False, indent=1)

c = collections.Counter(v["base"] for v in vendor.values())
print("\n== vendor base domains ==")
for k, n in c.most_common():
    print(f"{n:4d}  {k}")
