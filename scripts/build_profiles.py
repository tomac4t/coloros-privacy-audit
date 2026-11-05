#!/usr/bin/env python3
"""Phase 6: per-package privacy profile - domains, SDKs, privacy policy URLs, toggle keys."""
import os, json, glob, re, collections

OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out")
idx = {r["pkg"]: r for r in json.load(open(OUT + "/apk-index.json"))}
clean = json.load(open(OUT + "/hosts-clean.json"))
inv = json.load(open(OUT + "/blocklist/inventory.json"))

host2cat = {}
for tier in ("tierA", "tierB", "tierC"):
    for r in inv[tier]:
        host2cat[r["host"]] = (r["cat"], tier)

profiles = {}
for f in glob.glob(OUT + "/scan/*.json"):
    d = json.load(open(f))
    pkg = d["pkg"]
    info = idx.get(pkg, {})
    # vendor + thirdparty hosts only
    hosts = {}
    for h in d["hosts"]:
        if h in clean["vendor"]:
            cat, tier = host2cat.get(h, ("其他", "tierC"))
            hosts[h] = {"owner": "vendor", "cat": cat, "tier": tier}
        elif h in clean["thirdparty"]:
            hosts[h] = {"owner": "thirdparty", "cat": "第三方", "tier": "-"}
    profiles[pkg] = {
        "label": info.get("label", pkg),
        "vendor_sig": info.get("vendor", "?"),
        "size_kb": (info.get("size", 0) // 1024),
        "trackers": d["trackers"],
        "privacy_links": d["privacy_links"],
        "toggle_keys": d["toggle_keys"],
        "vendor_hosts": sorted(h for h, v in hosts.items() if v["owner"] == "vendor"),
        "third_hosts": sorted(h for h, v in hosts.items() if v["owner"] == "thirdparty")[:50],
    }

json.dump(profiles, open(OUT + "/profiles.json", "w"), ensure_ascii=False, indent=1)

# summary table
tops = sorted(profiles.items(), key=lambda x: -len(x[1]["vendor_hosts"]))[:30]
print(f"{'pkg':42s} {'vh':4s} {'3rd':4s} {'trackers'}")
for pkg, p in tops:
    print(f"{pkg:42s} {len(p['vendor_hosts']):<4d} {len(p['third_hosts']):<4d} {','.join(p['trackers'])[:60]}")

print("\n== privacy links ==")
for pkg, p in profiles.items():
    if p["privacy_links"]:
        print(pkg, "->", p["privacy_links"][:2])
