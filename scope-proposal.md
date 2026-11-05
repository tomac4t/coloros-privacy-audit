# 研究范围建议：ColorOS 14（一加 8T）系统应用隐私审计

数据来源：`/home/admin/Downloads/app_backup.zip`（3.1 GB，解压后 4.9 GB，345 个 APK）
已解压到：`/tmp/app_backup/`（文件名已修正为正确 UTF-8，直接平铺 345 个 apk）
索引文件：`out/apk-index.json`（每个包的签名者、体积、entry 数）

> 关于乱码：zip 内的文件名原本就是**正常 UTF-8 字节**（`AI 服务引擎_com.oplus.aiunit.apk`），
> 但 zip 没设 GP-Bit 11 标志，`unzip` 按本地 locale 用 GBK 解码，把 UTF-8 字节当 GBK 解释才成了乱码。
> 用 Python `zipfile`（默认按 cp437 无损解码）重解一遍就正常了。

---

## 一、按签名者分组（筛查结果）

| 签名者 | 数量 | 说明 |
|---|---|---|
| **Oplus (OSTeam)** | 271 | 主签名。里面**混着大量 AOSP/高通/Google 模块**，被 OPPO 重签过 |
| **OPPO (ColorOS)** | 42 | 自家业务 App + 框架组件 |
| **HeyTap** | 11 | 互联网服务（浏览器/商店/云/广告）—— **重点** |
| **OnePlus** | 5 | 相机、人脸、壁纸 |
| **nearme** | 2 | 快应用平台 |
| **Baidu** | 1 | 百度输入法定制版 |
| Google / AOSP | 9 | ARCore、Talkback、ConfigUpdater、ext.shared 等 |
| Microsoft | 2 | 连接至 Windows、DeviceIntegrationService |
| Qualcomm | 1 | Adreno 驱动 |
| Iflytek | 1 | 讯飞语音设置 |

**OEM 签名合计 332 个，其中 104 个是 <200 KB 的 overlay/桩包，有实际代码的 228 个。**

## 二、需要排除的类型（机械规则）

1. **RRO overlay**：包名含 `.overlay` / `frameworkres` / `systemui.overlay` / 体积 < 200 KB
   → 104 个，纯资源包，无代码，一律排除。
2. **AOSP 框架组件**：`com.android.providers.*`、`com.android.phone`、`bluetooth`、`nfc`、
   `telecom`、`settings`、`systemui`、`launcher`、`packageinstaller`、`permissioncontroller`、
   `networkstack`、`rkpdapp`、`cts.*` 等 —— 上游 AOSP，不是厂商埋点主体
   （但 launcher/systemui/settings 可能被厂商改过，可视需要留作"对照"）
3. **高通/IMEI 相关**：`com.qualcomm.*`、`com.qti.*`、`vendor.qti.*`、`org.codeaurora.*`
4. **第三方签名**：Google(9)、Microsoft(2)、Qualcomm 驱动、讯飞语音设置、百度输入法

## 三、核心研究候选（厂商数据收集能力集中区）

按"业务性质"分类，不是按签名者：

### A. 埋点/统计框架本体（必须看，端点是主目标）
- `com.oplus.statistics.rom` 数据基础服务 —— **OPPO 系统级统计 SDK 宿主，几乎每个包都引了它**
- `com.oplus.onetrace` OneTrace —— 全链路追踪
- `com.oplus.olc` Olc —— 日志/行为采集
- `com.oplus.nhs` 网络健康服务
- `com.heytap.htms` 移动服务（MCS 推送/统计）
- `com.heytap.mcs` 系统消息（推送通道）
- `com.oplus.logkit` 反馈工具箱（日志上报）
- `com.oplus.crashbox` CrashBox（崩溃上报）
- `com.oplus.postmanservice` 诊断工具服务

### B. 互联网服务（数据量大，隐私政策最长）
- `com.heytap.browser` 浏览器
- `com.heytap.market` 软件商店
- `com.heytap.cloud` 云服务
- `com.oplus.account` 账号中心
- `com.heytap.vip` 账号服务
- `com.heytap.openid` OpenID（设备唯一标识下发）
- `com.heytap.pictorial` 乐划锁屏（**锁屏广告/推荐**）
- `com.heytap.quicksearchbox` 全局搜索
- `com.heytap.speechassist` 小布助手（语音数据）
- `com.opos.ads` 广告服务（Commercial Service）
- `com.heytap.contextualwidget`(如存在)、`com.oplus.pantanal.ums` 智慧建议服务（泛舟/UMS 场景推荐）
- `com.nearme.instant.platform` 快应用平台

### C. AI / 感知类（最可能上传原始数据）
- `com.oplus.aiunit` AI 服务引擎（141 MB，最大单体之一）
- `com.oplus.deepthinker` 智慧能力服务
- `com.oplus.metis` 智慧决策服务
- `com.oplus.obrain` OBrain
- `com.oplus.smartengine` SmartEngine
- `com.coloros.sceneservice` 智慧数据增强服务
- `com.coloros.ocrscanner` 小布扫一扫（**图片 OCR 上传**）
- `com.coloros.directui` 识屏（**屏幕内容识别**）
- `com.coloros.colordirectservice` 识屏服务
- `com.coloros.assistantscreen` 速览（-1 屏）
- `com.oplus.supertextinput` 扫描输入
- `com.oplus.portrait` 人像绘影
- `com.oplus.viewtalk` 图片描述
- `com.coloros.translate.engine` 翻译服务
- `com.oplus.audiomonitor` 智慧语音
- `com.oneplus.voicewakeup` 语音唤醒
- `com.oplus.dmp` 融合搜索服务
- `com.oplus.interconnectcollectkit` 互联采集套件（名字带 collect）

### D. 手机管家/安全（权限大、能读全量数据）
- `com.coloros.phonemanager` 手机管家
- `com.oplus.safecenter` 安全中心
- `com.coloros.securityguard` 安全事件
- `com.coloros.healthcheck` 常规检测
- `com.oplus.qualityprotect` QualityProtect
- `com.oplus.securitypermission` 权限管理
- `com.oplus.trafficmonitor` 流量管理
- `com.oplus.blacklistapp` 骚扰拦截
- `com.oplus.encryption` 私密保险箱（本地，重点看是否真本地）
- `com.coloros.codebook` 密码本（同上）

### E. 运营商/合规类（会有 CTA 上报）
- `com.oppo.ctautoregist` CTAutoRegist（**入网备案自动注册，会往工信部/厂商上报设备信息**）
- `com.coloros.bootreg` 开机注册（**开机即上报**）
- `com.oplus.customize.coreapp` CustCoreApp（定制/运营商下发）
- `com.cmccslice.proxyapp` 移动切片代理

### F. 相机/相册（EXIF、AI 处理、云端同步）
- `com.oneplus.camera` / `com.oneplus.camera.service` / `.pictureprocessing`
- `com.coloros.gallery3d` 相册（**最大包 194 MB**）
- `com.oplus.aiunit`（上文已列）

### G. 系统治理/诊断（可选项，价值中等）
- `com.oplus.athena` / `com.oplus.exsystemservice` / `com.oplus.powermonitor` / `com.oplus.battery`
- `com.coloros.digitalwellbeing` 数字健康（**使用时长/APP 使用记录**）
- `com.oplus.location` 网络定位服务 / `com.qualcomm.location`

## 四、初步静态扫描线索（dex 里出现的第三方 SDK 关键字）

不用反编译，直接扫 dex 字符串就能看出：`com.oplus.statistics` 出现在 **140+ 个包**里；
`com.google.android.gms` 在 80+ 包里出现（多为 adservices 相关，非 GMS 本体）；
`com.alibaba`、`com.netease`（易盾）、`com.tencent.bugly`、`com.tencent.stat`、
`com.huawei.hms`（**浏览器里有华为 HMS，说明是从华为生态移植的第三方 SDK**）、`com.bytedance` 出现在几个大包里。

→ **结论：真正需要深挖的是"端点在哪儿"，而不是"有没有埋点"**。这套系统 90% 的包都埋了，重点是
把 `com.oplus.statistics.rom` / `olc` / `onetrace` 三件套的域名、以及各业务 App 自建上报域名摸出来。

---

## 五、需要你确认的几个问题

1. **签名者口径**：
   - a) 只审 Oplus + OPPO + HeyTap + OnePlus + nearme（厂商自有签名）= 331 个？—— 其中 108 个 overlay 再剔掉，实际 ~220 个
   - b) 还是**也审第三方签名的**（百度输入法、讯飞语音设置、Microsoft × 2）？这几个虽然签名是第三方，但确实是出厂预装、收集数据最赤裸的（百度输入法尤其）
   - c) AOSP 框架组件（settings / systemui / launcher / permissioncontroller）要不要审？它们是 OPPO 重签的，改过代码

2. **研究深度**：
   - 快扫：只扫 dex 字符串 + manifest + assets 里的域名/URL（半天级，200+ 包都过得去）
   - 精扫：jadx 反编译 + 分析上报逻辑（每包 3-10 分钟，适合 15-25 个重点包）
   - 全量反编译 345 个包不现实（按体积算 ~20-30 GB，时间以天计）

3. **黑名单粒度**：域名级（`data.oplus.com`）、子域级（`*.oplus.com`）、还是带路径（域名 + `/v1/xxx`）？
   AdGuard Home 只支持域名/通配，所以我会额外给一份"域名 + 用途 + 对应 App + 误伤风险"的表。

4. **隐私政策对照**：需要我抓 ColorOS 隐私政策原文（`privacy.oppo.com` / `privacy.heytap.com`）做条文比对吗？
   还是只做"技术上收集了什么"，政策对照你自己来？

5. **"是否允许退出"**：指①用户能否关闭"用户体验改进计划"②能否关掉个性化推荐③关掉后是否还有流量。
   这个静态分析只能给出"有没有开关"（看 manifest/资源里的 setting key），实际关掉后的行为需要真机抓包。
   要不要我把"开关 key + 对应偏好项"也整理出来，方便你在真机上验证？

我的建议：**先 2b 快扫全量 + 2c 精扫 A/B/C 三组约 30 个包**，先出 DNS 黑名单初版，再迭代。
等你确认上面 5 个问题我就开工。
