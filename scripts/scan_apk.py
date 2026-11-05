#!/usr/bin/env python3
"""Phase 1: fast static scan of every APK -> out/scan/<pkg>.json"""
import os, re, json, zipfile, sys

APKDIR = "/tmp/app_backup"
OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out/scan")
os.makedirs(OUT, exist_ok=True)

URL_RE = re.compile(rb"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]{4,220}")
TLD = (rb"com|cn|net|org|io|cc|tv|me|co|info|top|xyz|vip|site|club|online|tech|app|dev|ai|hk|"
       rb"sg|us|jp|kr|tw|de|uk|cloud|link|pro|biz|mobi|name|shop|store|fun|live|life|world|"
       rb"work|space|icu|ink|pw|one|plus|pub|asia|so|gg|fm|tv|cyou|cc|vip")
HOST_RE = re.compile(rb"(?<![A-Za-z0-9.\-])((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.){1,}(?:" + TLD + rb"))(?![A-Za-z0-9\-])")

# things that are dex-level namespaces masquerading as hosts -> drop
FAKE_SUFFIX = (b"android.app", b"android.net", b"androidx.", b"java.", b"javax.", b"kotlin",
               b"com.android.", b"libcore.", b"python.org", b"apache.org", b"w3.org",
               b"amazonaws.com", b"slf4j.org", b"llvm.org", b"codehaus.org", b"puppycrawl.com",
               b"schemas.android.com", b"unicode.org", b"netty.io", b"google.com",
               b"googleapis.com", b"gstatic.com", b"openjsse", b"org.openjsse")
# hostnames that look like reverse-DNS classnames: com.x.y.z / org.x / android.support.*
CLASSNAME_RE = re.compile(r"^(com|org|net|android|androidx|java|javax|kotlin\w*|libcore)\.")

REAL_TLD = set("""com cn net org io cc tv me co info top xyz vip site club online tech app
dev ai hk sg us jp kr tw de uk cloud link pro biz mobi name shop store fun live life world work
space icu ink pw one plus pub asia so gg fm cyou eu in ru br au ca fr nl se no fi dk pl cz it es
pt gr tr ae sa il id th vn my ph mx ar cl pe za eg ng ke ua kz by""".split())

def looks_like_classname(h):
    parts = h.split(".")
    return parts[-1] not in REAL_TLD
# noise words that regex catches from type ids
NOISE = {b"file.name", b"field.name", b"method.name", b"class.java.name", b"channel.name",
         b"context.name", b"config.name", b"entry.name", b"duid.name", b"imei.name",
         b"it.name", b"ouid.name", b"spec.name", b"r.name", b"action.com", b"mobile.com",
         b"mobi.com", b"com.ai", b"code.co", b"cpython.app", b"os.link", b"com.cloud",
         b"com.android.org", b"com.google.android.gms.org", b"clazz.name"}

TRACKER = {
    "com.oplus.statistics": "OPPO 系统统计SDK",
    "com.oplus.onetrace": "OPPO OneTrace 全链路追踪",
    "com.oplus.olc": "OPPO Olc 日志/行为采集",
    "com.oplus.dcs": "OPPO DCS 设备云",
    "com.oplus.nearx": "OPPO NearX 埋点上报",
    "com.heytap.statistics": "HeyTap 统计",
    "com.nearme.statistics": "Nearme 统计(旧)",
    "com.umeng": "友盟",
    "com.tencent.bugly": "腾讯 Bugly",
    "com.tencent.stat": "腾讯 MTA",
    "com.tencent.beacon": "腾讯灯塔",
    "com.tencent.matrix": "腾讯 Matrix",
    "com.sensorsdata": "神策",
    "cn.jpush": "极光推送",
    "com.igexin": "个推",
    "com.getui": "个推新版",
    "com.baidu.mobstat": "百度统计",
    "com.baidu.location": "百度定位",
    "com.amap": "高德",
    "com.bytedance": "字节 SDK",
    "com.alibaba": "阿里SDK",
    "com.aliyun": "阿里云",
    "com.huawei.hms": "华为HMS",
    "com.huawei.agconnect": "华为AGC",
    "com.google.android.gms": "GMS",
    "com.google.firebase": "Firebase",
    "com.facebook.appevents": "FB Events",
    "com.adjust.sdk": "Adjust",
    "com.appsflyer": "AppsFlyer",
    "com.netease.nis": "网易易盾",
    "com.growingio": "GrowingIO",
    "cn.thinkingdata": "ThinkingData",
    "com.qiyukf": "七鱼客服",
    "com.sobot": "智齿客服",
    "com.uc.crashsdk": "UC崩溃SDK",
    "com.oplus.crashbox": "OPPO CrashBox",
    "com.oplus.logkit": "OPPO 反馈工具箱",
    "com.oplus.postmanservice": "OPPO 诊断工具",
    "com.oplus.nhs": "OPPO 网络健康",
    "com.coloros.sau": "系统升级",
    "com.oplus.deepthinker": "OPPO DeepThinker",
    "com.heytap.mcs": "HeyTap 推送通道",
}

TOGGLE_RE = re.compile(
    rb"(?i)(user_?experience|ux_?improve|analytics_?enabled|statistics_?enabled|"
    rb"collect_?data|data_?collection|telemetry|personaliz\w+|"
    rb"recommend\w*_?switch|opt_?out|track\w*_?enabled|diagnostic\w*|"
    rb"privacy_?policy|improve_\w+)")

PRIVACY_RE = re.compile(rb"(?i)(https?://[^\s\"'<>]{0,140}(?:privacy|policy|protocol|agreement|private)[^\s\"'<>]{0,80})")

def clean_host(h):
    h = h.lower()
    for f in FAKE_SUFFIX:
        if h == f.decode() or h.endswith("." + f.decode()):
            return None
    if len(h) < 6 or h.count(".") == 0:
        return None
    if any(h.encode() == n for n in NOISE):
        return None
    # drop .so / .io-ish false hits and classname-shaped strings
    if h.endswith((".so", ".io")) or h.startswith(("lib", "persist.", "os.", "java.")):
        return None
    if looks_like_classname(h):
        return None
    return h

def scan_apk(path):
    res = {"urls": set(), "hosts": set(), "trackers": set(), "toggle_keys": set(),
           "privacy_links": set(), "files": 0, "bytes_scanned": 0, "errors": []}
    try:
        z = zipfile.ZipFile(path)
    except Exception as e:
        res["errors"].append(f"open: {e}")
        return res
    names = z.namelist()
    res["files"] = len(names)
    for n in names:
        low = n.lower()
        if not (low.endswith(".dex") or low.endswith(".arsc") or low == "androidmanifest.xml"
                or low.endswith(".xml") or low.endswith(".json") or low.endswith(".js")
                or low.endswith((".html", ".htm", ".properties", ".txt", ".pb", ".bin", ".conf", ".cfg"))
                or "/assets/" in low or low.endswith(".so")):
            continue
        try:
            with z.open(n) as f:
                data = f.read(60 * 1024 * 1024)
        except Exception as e:
            res["errors"].append(f"{n}: {e}")
            continue
        res["bytes_scanned"] += len(data)
        for m in URL_RE.finditer(data):
            u = m.group().decode("utf-8", "ignore")
            if len(u) >= 10:
                res["urls"].add(u[:200])
        for m in HOST_RE.finditer(data):
            h = clean_host(m.group(1).decode("ascii", "ignore"))
            if h:
                res["hosts"].add(h)
        for k in TRACKER:
            if k.encode() in data:
                res["trackers"].add(k)
        for m in TOGGLE_RE.finditer(data):
            res["toggle_keys"].add(m.group().decode("utf-8", "ignore").lower()[:60])
        for m in PRIVACY_RE.finditer(data):
            res["privacy_links"].add(m.group().decode("utf-8", "ignore")[:200])
    for k in ("urls", "hosts", "trackers", "toggle_keys", "privacy_links"):
        res[k] = sorted(res[k])
    return res

def main():
    files = sorted(f for f in os.listdir(APKDIR) if f.endswith(".apk"))
    only = sys.argv[1:]
    if only:
        files = [f for f in files if any(o in f for o in only)]
    for i, f in enumerate(files, 1):
        pkg = f[:-4].rsplit("_", 1)[-1]
        dest = os.path.join(OUT, pkg + ".json")
        if os.path.exists(dest):
            print(f"[{i}/{len(files)}] skip {pkg}", flush=True)
            continue
        r = scan_apk(os.path.join(APKDIR, f))
        r["file"] = f
        r["pkg"] = pkg
        json.dump(r, open(dest, "w"), ensure_ascii=False)
        print(f"[{i}/{len(files)}] {pkg}  urls={len(r['urls'])} hosts={len(r['hosts'])} trackers={len(r['trackers'])}", flush=True)

if __name__ == "__main__":
    main()
