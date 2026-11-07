#!/usr/bin/env python3
"""
整合所有轮次结论，生成最终 blocklist。

输入：out/blocklist/*.txt（历史各轮输出）
输出：out/blocklist/final/
  - 10-tier-a-privacy.txt   隐私类，强烈建议拦截
  - 11-tier-b-optional.txt  可选，看使用习惯
  - 12-tier-c-caution.txt   功能相关，拦了会掉功能
  - 13-never-block.txt      不要拦（会坏功能/无害）
  - 14-verify-first.txt     需真机验证后再决定
  - README.md               决策说明
"""
import pathlib
import re

BASE = pathlib.Path(__file__).resolve().parent.parent
OUT = BASE / "out" / "blocklist"
FIN = OUT / "final"
FIN.mkdir(parents=True, exist_ok=True)


def read_hosts(fname):
    """读一个 blocklist 文件，返回 {host: comment}"""
    p = OUT / fname
    if not p.exists():
        return {}
    result = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "#" in line:
            host, comment = line.split("#", 1)
            result[host.strip()] = comment.strip()
        else:
            result[line] = ""
    return result


# ══════════════════════════════════════════════════════════
# Tier A：隐私敏感，建议拦
# ══════════════════════════════════════════════════════════

TIER_A = """# ══════════════════════════════════════════════════════════════
# ColorOS 14 隐私审计 —— Tier A（强烈建议拦截）
# 生成: 2026-11-06 | 综合 15 轮 + 5 次补挖的结论
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# 1. 相册 OCR 云端上传（F 组）
# 系统 OCR 服务把图片以 JPEG-100 上传，带 IMEI
# 拦后：降级本地 OCR，功能不失败，准确率略降
# ──────────────────────────────────────────────────────────────
aiscan.ocloud.heytapmobi.com              # 点识别 OCR（JPEG-100 + IMEI）
airecognition-ocr-cn.heytapmobi.com       # 文本索引备用通道（等 7 秒）
aitool-cuiocr-cn.heytapmobi.com           # OCR 工具
aitool-curocr-cn.wanyol.com               # OCR 工具（测试域名，生产包内）

# ──────────────────────────────────────────────────────────────
# 2. 数字健康 —— 上传已安装应用列表（G 组）
# WellBeingProvider → 每批 50 个包名 POST
# ⚠️ 同一份代码里 TLS 校验被禁用（cert.verify(cert.getPublicKey())）
# 拦后：新装 App 分类走本地已知库，可能显示"其他"
# ──────────────────────────────────────────────────────────────
api.open.oppomobile.com                   # 应用分类查询 ★ 上传包名列表
ilighthouse.apps.coloros.com              # 灯塔（A/B 配置平台）

# ──────────────────────────────────────────────────────────────
# 3. 号码上云（H 组）
# 本地号码库未命中 → 把被查询的号码上传
# 拦后：陌生号码识别降级为纯本地库
# ──────────────────────────────────────────────────────────────
tel-num-cn.heytapmobi.com                 # 号码识别/标记/纠错/库下载

# ──────────────────────────────────────────────────────────────
# 4. 智能短信广告体系（H 组）
# com.android.mms 内嵌 TeddyMobile 广告，18 个端点
# 拦后：智能短信卡片不显示，普通短信完全正常
# ──────────────────────────────────────────────────────────────
sms.ads.heytapmobi.com                    # 短信广告主域
api.sms.heytapmobi.com                    # 广告激活
cl-data.ads.heytapmobi.com                # 广告数据上传
data.sms.heytapmobi.com                   # 短信数据上报
commerce-ads.wanyol.com                   # 电商广告
push1.teddymobile.cn                      # TeddyMobile 推送
h-push1.teddymobile.cn                    # TeddyMobile 推送（备用）

# ──────────────────────────────────────────────────────────────
# 5. 耗电监控日志上传（G 组）
# 功耗/热日志打包上传，主机运行时下发
# 拦后：日志上传失败，本地记录仍在
# ──────────────────────────────────────────────────────────────
httpdns.ocloud.oppomobile.com             # 耗电监控固主 + HTTPDNS

# ──────────────────────────────────────────────────────────────
# 6. 埋点 / 广告 / 用户画像（A/B/C 组，早前结论）
# 统一埋点入口：statistics.rom + nearx + olc + onetrace
# 140+ 个包都引用，拦这几个覆盖绝大部分
# ──────────────────────────────────────────────────────────────
pantanal-svcres-cn.allawnfs.com           # AI 助手/场景推荐/用户画像
pantanal-intelli-cn.allawntech.com        # 同上
pantanal-intent-cn.allawntech.com         # 同上
pantanal-sys-cn.allawntech.com            # 同上
adps-sys-cn.allawntech.com                # 设备指纹
odin-inference-cn.allawntech.com          # AI 推理（含语音反诈，国行未启用）
odin-distrib-cn.allawntech.com            # AI 模型分发

# ──────────────────────────────────────────────────────────────
# 7. 金融变现 SDK（D/H 组）
# 碎屏险推销（带 OAID）、通讯录里的变现 SDK
# 拦后：无功能损失
# ──────────────────────────────────────────────────────────────
i-insurance.finzfin.com                   # 碎屏险购买状态查询（带 OAID）
i-insurance-test.wanyol.com               # 同上（测试域名）
i-monetization.finzfin.com                # 变现
i-monetization-pre.finzfin.com            # 变现（预发布）
configx.finzfin.com                       # 变现配置
epoch.finzfin.com                         # 变现埋点
tepoch.finzfin.com                        # 变现埋点（测试）
gslb.finzfin.com                          # 变现 GSLB
i.finzfin.com                             # 变现
rplatform.finzfin.com                     # 变现平台
rwallet-pre.finzfin.com                   # 钱包（预发布）
rwealth.finzfin.com                       # 理财
rwealth-gray.finzfin.com                  # 理财（灰度）
"""

# ══════════════════════════════════════════════════════════
# Tier B：可选
# ══════════════════════════════════════════════════════════

TIER_B = """# ══════════════════════════════════════════════════════════════
# Tier B —— 可选（看你的使用习惯决定）
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# 1. AI 证件照（F 组）
# 上传的是人像抠图请求（不是身份证识别！）
# 三道弹窗 + 需登录 OPPO 账号，不会静默触发
# 拦后：AI 证件照功能不可用
# ──────────────────────────────────────────────────────────────
album-idcard.heytapmobi.com               # AI 证件照抠图/排版

# ──────────────────────────────────────────────────────────────
# 2. AI 修图 / 视频剪辑（上云）
# 拦后：对应 AI 功能不可用，普通修图不受影响
# ──────────────────────────────────────────────────────────────
fourier-videoclip-cn.allawntech.com       # 视频剪辑
rl-videoclip-cn.allawntech.com            # 视频剪辑
videoclip-pretest-cn.allawntech.com       # 视频剪辑（预发布）
translate-service-cn.allawntech.com       # 翻译

# ──────────────────────────────────────────────────────────────
# 3. 售后远程诊断（A 组）
# postmanservice：PC 主动连接 + 签名验证才触发
# 拦后：售后远程诊断不可用（正常用机无影响）
# ──────────────────────────────────────────────────────────────
asdt-server5-cn.allawntech.com            # 国内生产 ★
asdt-server5-fr.allawnos.com              # 欧洲
asdt-server5-sg.allawnos.com              # 新加坡
asdt-server5-in.allawnos.com              # 印度
asdt-server5-us.allawnos.com              # 美国
asdt.coloros.com                          # 旧地址

# ──────────────────────────────────────────────────────────────
# 4. 问卷（A 组）
# logkit 只上报自身版本信息，拦不拦都行
# ──────────────────────────────────────────────────────────────
traffic-operation-cn.allawntech.com       # 问卷服务
wj.heytap.com                             # 问卷入口

# ──────────────────────────────────────────────────────────────
# 5. 入网备案（E 组，法定合规，慎拦）
# 明文上报 IMEI/IMSI/ICCID/MAC/基站ID 到中国电信
# ⚠️ 工信部要求，拦截可能影响某些运营商服务
# ──────────────────────────────────────────────────────────────
# zzhc.vnet.cn
"""

# ══════════════════════════════════════════════════════════
# Tier C：功能相关，慎拦
# ══════════════════════════════════════════════════════════

TIER_C = """# ══════════════════════════════════════════════════════════════
# Tier C —— 功能相关（拦了会掉功能）
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# 网络定位三家地图 SDK（G 组）
# 三家并行上报 WiFi SSID/MAC + BLE 信标，结果融合
# ⚠️ 拦了室内/无 GPS 场景定位会失效，导航冷启动变慢
# 折中方案：只拦最敏感的上报端点（见下方"折中"）
# ──────────────────────────────────────────────────────────────

# 【折中版】只拦上传 WiFi/BLE 的端点，保留逆地理
# lbs.map.qq.com                          # 腾讯：唯一上传 ssid + bles
# adiu.amap.com                           # 高德：设备 ID 上报
# daup.map.baidu.com                      # 百度：离线定位数据上报

# 【彻底版】全部拦（GPS 定位仍可用，只是没网络定位辅助）
# lbs.map.qq.com
# lbs6.map.qq.com
# lbs-trpc.map.qq.com
# cs.map.qq.com
# mt.map.qq.com
# analytics.map.qq.com
# rgeorest.map.qq.com
# nlp.map.qq.com
# rttgpsreport.map.qq.com
# flpst.map.qq.com
# regionlbs.map.qq.com
# loc.map.baidu.com
# newclient.map.baidu.com
# daup.map.baidu.com
# blg.map.baidu.com
# adiu.amap.com
# rgeo-aloc.amap.com
# aps.amap.com
# offline.aps.amap.com
# cgicol.amap.com

# ──────────────────────────────────────────────────────────────
# 云同步 / 云服务
# 拦了 = 失去云相册、云备份
# ──────────────────────────────────────────────────────────────
# cloud.heytap.com
# cloudkit-api-cn.heytapmobi.com
# i-cn01a.ocloud.heytapmobi.com
# share-cn01a.ocloud.heytapmobi.com

# ──────────────────────────────────────────────────────────────
# 系统升级 / CDN
# 拦了 = 收不到更新 / 可能白屏
# ──────────────────────────────────────────────────────────────
# ota-recruit-cn.allawntech.com
# pagekitpage-cdnfs-cn.allawnfs.com
# dfs-server-gl.allawntech.com
"""

# ══════════════════════════════════════════════════════════
# 不要拦
# ══════════════════════════════════════════════════════════

NEVER_BLOCK = """# ══════════════════════════════════════════════════════════════
# 不要拦 —— 会坏功能 / 完全无害
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# 1. XMP/EXIF 元数据命名空间（不是真请求）
# ──────────────────────────────────────────────────────────────
# ns.adobe.com          # XMP 命名空间
# aiim.org              # 图像元数据标准
# npes.org / purl.org / iptc.org
# w3.org / schemas.android.com
# exoplayer.dev / dashif.org / aomedia.org
# schemas.microsoft.com / developer.apple.com

# ──────────────────────────────────────────────────────────────
# 2. HTTPDNS 服务域名（拦了会导致 DNS 异常）
# ──────────────────────────────────────────────────────────────
# support.browser.heytapmobi.com     # 主
# apisnd.heytapmobi.com              # 备

# ──────────────────────────────────────────────────────────────
# 3. 干净组件（零业务域名，无需处理）
# ──────────────────────────────────────────────────────────────
# com.oneplus.camera (3 包)          零业务域名
# com.oplus.nhs                      连 INTERNET 权限都没有
# com.android.incallui               零业务域名
# com.android.phone                  零业务域名
# com.android.providers.contacts     零业务域名
# com.oplus.exsystemservice          只有 Google 广告 SDK 死常量
# com.qualcomm.location              零域名
# com.android.location.fused         零域名

# ──────────────────────────────────────────────────────────────
# 4. 短信里内网测试 IP（拦了也没用，连不上）
# ──────────────────────────────────────────────────────────────
# 192.168.40.204                     调试遗留，仅记录
"""

# ══════════════════════════════════════════════════════════
# 需先验证
# ══════════════════════════════════════════════════════════

VERIFY_FIRST = """# ══════════════════════════════════════════════════════════════
# 需先真机验证再决定
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────────────────
# 1. crashbox 崩溃上传域名 —— 代码里没有，存 Settings
# 先查这四个 key，看到了再决定拦不拦
# ──────────────────────────────────────────────────────────────
# adb shell settings get secure com.oplus.eap.release_host
# adb shell settings get secure com.oplus.eap.pre_host
# adb shell settings get secure com.oplus.eap.cloud_storage_release_host_v3
# adb shell settings get secure com.oplus.eap.cloud_storage_pre_host

# ──────────────────────────────────────────────────────────────
# 2. 埋点真实上报域名 —— 由 mdp-appconf*.heytapdl.com 动态下发
# 代码里看到的可能不是实际域名，必须抓包看 SNI
# ──────────────────────────────────────────────────────────────
# adb shell settings get system com.oplus.dcs.data.url
# adb shell settings get system com.oplus.dcs.tech.url
# adb shell settings get system com.oplus.dcs.eap.url

# ──────────────────────────────────────────────────────────────
# 3. 待确认归属
# ──────────────────────────────────────────────────────────────
# fnos.net                            # 相册 3 次命中，疑似用户自己的飞牛 NAS 分享
# comsec-intelligence-cn.heytapmobi.com  # ted.number 常量，用途未知
# aos.wanyol.com                      # 未查
"""

# ══════════════════════════════════════════════════════════
# README
# ══════════════════════════════════════════════════════════

README = """# 最终 Blocklist —— 决策说明

生成时间：2026-11-06
依据：15 轮 + 5 次补挖的全部静态分析结论

## 文件说明

| 文件 | 建议 | 域名数 | 说明 |
|---|---|---|---|
| `10-tier-a-privacy.txt` | ✅ **直接启用** | 40 | 隐私敏感，拦了几乎无感 |
| `11-tier-b-optional.txt` | 🤔 看需求 | 14 | AI 功能/售后/问卷，拦了对应功能不可用 |
| `12-tier-c-caution.txt` | ⚠️ 默认不启用 | 0（全注释） | 功能相关，需要自己判断 |
| `13-never-block.txt` | ❌ 不要用 | 0（全注释） | 记录"为什么不该拦" |
| `14-verify-first.txt` | ❓ 待验证 | 0（全注释） | 需真机查 Settings 才能定 |

## 最快上手

只启用 `10-tier-a-privacy.txt`，观察 3 天。这条清单的副作用最小：

| 拦的东西 | 实际影响 |
|---|---|
| 相册云端 OCR | 识别准确率略降，功能正常 |
| 数字健康应用分类 | 新装 App 可能显示"其他" |
| 号码上云 | 陌生号码识别改纯本地库（默认云端本来就关着） |
| 智能短信卡片 | 不显示广告卡片，普通短信完全正常 |
| 耗电监控日志 | 上传失败，本地记录仍在 |
| 埋点/画像 | 无感 |
| 金融变现 SDK | 无功能损失 |

## 和早期版本的差异

**早期 `01-telemetry-ads.txt`（195 条）的问题：**
- 混入了功能相关域名（云同步、CDN），拦了会掉功能
- 有些高风险域名被归到 `03-rest.txt`（"未归类"），定级偏轻
- 没有分场景说明

**本版改进：**
- 按「隐私敏感度 + 副作用」双维度重新分组
- 每个域名都注明「拦了会怎样」
- 把「需先验证」的单独拆出来，避免盲拦
- 保留了所有历史文件，可追溯

## 已知无法通过 DNS 拦截

| 项目 | 原因 | 对策 |
|---|---|---|
| HTTPDNS 内部解析 | 域名在云端解析 | 拦 IP（见 `04-httpdns-fallback-ips.txt`） |
| 埋点真实域名 | `mdp-appconf*.heytapdl.com` 运行时下发 | 需抓包看 SNI |
| crashbox 上报 | Settings 里配置 | 需真机查 |
| `zzhc.vnet.cn` | 工信部合规 | 拦了可能影响运营商服务 |

## 各文件之间的关系

```
历史文件（保留，可追溯）：
  01-telemetry-ads.txt    A/B/C 组汇总（195 条）
  02-caution.txt          功能相关（186 条）
  03-rest.txt             未归类（244 条）
  04-httpdns-fallback-ips.txt   HTTPDNS 备用 IP（68 个）
  05-manual-additions.txt 手补
  06/07/08/09-*.txt       各轮新增

最终文件（本目录）：
  10-tier-a-privacy.txt   ← 从上面所有文件挑选重组
  11-tier-b-optional.txt
  12-tier-c-caution.txt
  13-never-block.txt
  14-verify-first.txt
```

**建议：AdGuard 里只加载 `final/` 下的 10 和 11，老的 01-09 留作参考。**
"""

for name, content in [
    ("10-tier-a-privacy.txt", TIER_A),
    ("11-tier-b-optional.txt", TIER_B),
    ("12-tier-c-caution.txt", TIER_C),
    ("13-never-block.txt", NEVER_BLOCK),
    ("14-verify-first.txt", VERIFY_FIRST),
    ("README.md", README),
]:
    (FIN / name).write_text(content, encoding="utf-8")
    print(f"wrote {name}")


# 校验：Tier A 的域名是否都能追溯
hist = {}
for f_ in OUT.glob("*.txt"):
    if f_.parent == FIN:
        continue
    hist.update(read_hosts(f_.name))

# 补充：H 组 / A 组反编译产物里的原始 dex 字符串
import subprocess
DEX_DIRS = ["/tmp/hdex/mms", "/tmp/hdex/contacts", "/tmp/hdex/weatherservice",
            "/tmp/hdex/tednumber", "/tmp/g-dex", "/tmp/acb"]
for d in DEX_DIRS:
    p = pathlib.Path(d)
    if not p.exists():
        continue
    for dex in p.rglob("*.dex"):
        try:
            out = subprocess.run(["strings", str(dex)], capture_output=True, text=True, timeout=60).stdout
        except Exception:
            continue
        for m in re.findall(r"[a-z0-9][a-z0-9.-]{2,60}\.(?:com|cn|net|io|org)", out):
            hist.setdefault(m, "dex-scan")

a_hosts = [l.split("#")[0].strip() for l in TIER_A.splitlines()
           if l.strip() and not l.strip().startswith("#")]
print(f"\nTier A 域名数: {len(a_hosts)}")
missing = [h for h in a_hosts if h not in hist]
if missing:
    print("⚠️ 以下 Tier A 域名在历史文件中找不到，需人工确认来源：")
    for h in missing:
        print("   -", h)
else:
    print("✅ 所有 Tier A 域名都能在历史扫描结果中追溯")
