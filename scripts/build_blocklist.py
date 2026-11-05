#!/usr/bin/env python3
"""Phase 5: build DNS blocklist + inventory markdown."""
import os, json, re, collections

OUT = os.path.expanduser("~/.openclaw/workspace/projects/coloros-privacy-audit/out")
idx = {r["pkg"]: r for r in json.load(open(OUT + "/apk-index.json"))}
clean = json.load(open(OUT + "/hosts-clean.json"))
vendor = clean["vendor"]

# ---------- category rules (host substring -> (category, purpose, risk)) ----------
# ⚠️ 顺序很重要：先匹配先赢。HTTPDNS 类必须排在最前，
#    否则 support.browser.* 会被「浏览器」、httpdns.push.* 会被「推送」抢走。
RULES = [
    # ★ HTTPDNS —— 必须排第一，优先级最高
    (r"support\.browser|apisnd|httpdns|api\.dns\.|ocloud-httpdns|dcc-httpdns",
     "★HTTPDNS", "★ HTTPDNS 服务 —— 埋点域名的 DNS 引导，绕过系统 DNS",
     "强烈建议屏蔽；但需同时拦备用 IP（AdGuard 拦不住 IP 直连）"),
    # telemetry / tracking
    (r"mdup-usertrace|usertrace", "埋点追踪", "用户行为轨迹上报", "关掉统计开关后应消失；若仍出现说明有漏网"),
    (r"obus-", "埋点上报", "OBUS 运营埋点(曝光/点击)", "关个性化推荐可减；建议屏蔽"),
    (r"\.dc\.|dc\.heytapmobi|dc\.heytapmobile", "数据收集", "DC 数据采集(事件/日志)", "高价值屏蔽目标"),
    (r"\.cdo\.|cdo\.heytapmobi|epoch\.|epoch-", "数据收集", "CDO/epoch 统计流水", "高价值屏蔽目标"),
    (r"stat\.|stats\.|/stat", "统计", "统计上报", "高价值屏蔽目标"),
    (r"ads\.|adx\.|cpc\.|ssp-|\.ads$|cdo.*cpc|bsp-", "广告", "广告投放/程序化竞价", "强烈建议屏蔽，无副作用"),
    (r"stg-data", "广告数据", "广告数据回传", "强烈建议屏蔽"),
    (r"rest-cn-feedback|static-cn-feedback", "反馈", "反馈工具箱/问题上报(用户主动提交才用)", "非自动埋点，可不拦"),
    (r"nearx", "埋点上报", "NearX 埋点框架", "高价值屏蔽目标"),
    (r"ums-|telemetry", "遥测", "UMS/遥测", "高价值屏蔽目标"),
    (r"virusinfo|datasec|comsec|omes-|osec-|omkms|sec\.", "安全校验", "安全/风控校验", "屏蔽可能影响支付/登录"),
    (r"captcha", "验证码", "人机校验", "不要屏蔽，会坏登录"),
    (r"push\.|long-push|short-push|httpdns.*push|dc\.push", "推送", "消息推送通道", "屏蔽=收不到推送"),
    (r"sms\.|\.sms|long\.sms|short\.sms", "短信", "短信下发/校验", "不要屏蔽"),
    (r"jits", "实时通信", "JITS RTC 信令", "按需"),
    (r"ortc|rtcapi|rtc\.", "实时通信", "RTC 音视频", "按需"),
    (r"ocloud|cloud", "云服务", "云同步/云相册", "屏蔽会失去云功能"),
    (r"store\.|appstore|market|gamesdk|game\.", "应用商店", "商店/游戏中心 API", "屏蔽后商店不可用"),
    (r"theme\.|magazine|pictorial|pictorial", "内容推荐", "锁屏/杂志/主题内容", "可屏蔽，观感下降"),
    (r"search\.|\.search|searchfs|imgconvert-search|g\.search|i\.search", "搜索", "搜索/热搜", "可屏蔽"),
    (r"browser\.|ibreaker|cloudi\.browser|kernellog|readermode", "浏览器", "浏览器内核/日志", "按需"),
    (r"weather", "天气", "天气数据", "屏蔽后天气不更新"),
    (r"ocr|airecognition|aitool-cuiocr|album-idcard|translate|videoclip|pictureeditor|odin-", "AI识别", "OCR/翻译/视频剪辑(AI 上云)", "隐私敏感，建议屏蔽"),
    (r"bot-|andesbrain|ai-search|aiunit|\.ai$|deepthinker|pantanal|metis|sceneservice", "AI/推荐", "AI 助手/场景推荐/用户画像", "隐私敏感，建议屏蔽"),
    (r"location|geofence|tel-num|phonenoarea", "定位", "定位/号码归属地", "按需"),
    (r"asdt|hio\.|ua\.prof|adps|adps-sys", "设备画像", "设备指纹/用户画像", "隐私敏感"),
    (r"mapcom|fourier|ocar|carlink|traffic-operation|travel|trip-", "出行/车联", "车联/出行服务", "按需"),
    (r"health|sport\.health", "健康", "健康数据", "隐私敏感"),
    (r"find\.|ifind|find-pre", "查找手机", "查找设备", "按需"),
    (r"owork|preowork", "跨端工作台", "随身工作台", "按需"),
    (r"idl-|brand\.|chat\.|hd\.|e\.heytap|id\.heytap|muc\.|pay\.|wj\.|carlink", "账号/内容", "账号与内容 API", "按需"),
    (r"privacy\.", "隐私政策", "隐私政策站点", "可用作参考，不必屏蔽"),
    (r"www\.|bbs\.|support\.|after-sales", "官网", "官网/客服/论坛", "可屏蔽"),
    (r"mdp-appconf", "埋点配置", "★ 埋点配置下发总入口(决定真实上报域名)", "屏蔽=埋点断粮；可能影响主题/商店配置，需实测"),
    (r"cubefs", "日志存储", "Olc 日志包对象存储", "建议屏蔽"),
    (r"appconf", "埋点配置", "★ 埋点配置下发(决定真实上报域名)", "屏蔽=埋点断粮；可能影响主题/商店配置，需实测"),
    (r"ota|update|romupdate|sau|security-speed|dl-gs|download", "升级/下载", "系统升级/资源下载", "屏蔽=收不到更新"),
    (r"font|static|fs-|\.fs|dfs|dhfs|cdofs|adsfs|pagekit|cdn", "静态资源", "CDN/静态资源", "屏蔽可能白屏"),
]

def classify(h):
    for pat, cat, purpose, risk in RULES:
        if re.search(pat, h):
            return cat, purpose, risk
    return "其他", "未归类", "需人工判断"

# ---------- blocklist ----------
# Tier A: telemetry/ads/user-profiling -> safe to block
BLOCK_CATS = {"埋点追踪", "埋点上报", "数据收集", "统计", "广告", "广告数据", "遥测",
              "AI识别", "AI/推荐", "设备画像", "健康", "埋点配置", "日志存储", "★HTTPDNS"}
# Tier B: possibly breaks features
WARN_CATS = {"推送", "云服务", "应用商店", "内容推广", "内容推荐", "升级/下载", "静态资源",
             "浏览器", "搜索", "安全校验", "账号/内容"}

rows = []
for h, v in vendor.items():
    cat, purpose, risk = classify(h)
    rows.append({"host": h, "base": v["base"], "cat": cat, "purpose": purpose,
                 "risk": risk, "apps": v["apps"]})

a = sorted([r for r in rows if r["cat"] in BLOCK_CATS], key=lambda x: (x["base"], x["host"]))
b = sorted([r for r in rows if r["cat"] in WARN_CATS], key=lambda x: (x["base"], x["host"]))
c = sorted([r for r in rows if r["cat"] not in BLOCK_CATS | WARN_CATS], key=lambda x: (x["base"], x["host"]))

os.makedirs(OUT + "/blocklist", exist_ok=True)
with open(OUT + "/blocklist/01-telemetry-ads.txt", "w") as f:
    f.write("# ColorOS 14 隐私审计 - 埋点/广告/画像类域名\n")
    f.write("# 生成: 2026-11-05 | 来源: app_backup.zip 345 APK 静态扫描\n")
    f.write("# 建议: 直接加入 AdGuard Home 黑名单\n")
    for r in a:
        f.write(f"{r['host']}  # {r['cat']} | {r['purpose']}\n")

with open(OUT + "/blocklist/02-caution.txt", "w") as f:
    f.write("# ColorOS 14 - 功能相关域名（屏蔽会掉功能，谨慎）\n")
    for r in b:
        f.write(f"{r['host']}  # {r['cat']} | {r['purpose']} | {r['risk']}\n")

with open(OUT + "/blocklist/03-rest.txt", "w") as f:
    f.write("# ColorOS 14 - 其余/未归类域名（人工判断）\n")
    for r in c:
        f.write(f"{r['host']}  # {r['cat']} | {r['purpose']}\n")

# wildcard summary (base domain) for AdGuard `||domain^` style
# 只在"TierA 占该域绝对多数"时输出通配，否则会连带禁掉功能域名
base_all = collections.Counter(r["base"] for r in rows)
base_a = collections.Counter(r["base"] for r in a)
with open(OUT + "/blocklist/00-wildcard-tier-a.txt", "w") as f:
    f.write("# 通配版（按注册域名屏蔽）。仅包含 TierA 占该域 >=90% 的域名。\n")
    f.write("# 其余域名因含功能子域，请用 01-telemetry-ads.txt 逐条屏蔽。\n")
    for bd, n in base_a.most_common():
        if n / base_all[bd] >= 0.9:
            f.write(f"||{bd}^  # TierA {n}/{base_all[bd]}\n")
        else:
            f.write(f"# 跳过 {bd}: 仅 {n}/{base_all[bd]} 属 TierA，逐条屏蔽见 01\n")

json.dump({"tierA": a, "tierB": b, "tierC": c},
          open(OUT + "/blocklist/inventory.json", "w"), ensure_ascii=False, indent=1)

print(f"TierA (block): {len(a)}   TierB (caution): {len(b)}   TierC (other): {len(c)}")
print("\n== TierA by category ==")
for k, n in collections.Counter(r["cat"] for r in a).most_common():
    print(f"  {n:4d}  {k}")
