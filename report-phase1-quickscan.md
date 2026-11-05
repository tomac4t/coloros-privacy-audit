# ColorOS 14（一加 8T）系统应用隐私审计 —— 第一轮：快扫报告

- **日期**：2026-11-05
- **样本**：`/home/admin/Downloads/app_backup.zip` → 345 个 APK / 4.9 GB（解压到 `/tmp/app_backup/`）
- **方法**：静态快扫（dex 字符串 / resources.arsc / AndroidManifest / assets / .so 中的 URL 与主机名）
  - **未反编译**，所以以下结论都是"代码里出现了什么"，不是"运行时真的发了什么"
- **范围**：OEM 签名 332 个（Oplus 271 / OPPO 42 / HeyTap 11 / OnePlus 5 / nearme 2 / Baidu 1）
  - 其中 104 个是 <200 KB 的 RRO overlay 桩包，无代码
  - 非 OEM 13 个（Google、Microsoft、高通、讯飞）**已排除**（按 Tom 要求，这些 App 不用）
  - AOSP 组件（settings/systemui/launcher/permissioncontroller 等）**按 Tom 要求一起快扫**

---

## 一、最重要的发现

### 1. 埋点基础设施高度集中

所有厂商 App 的埋点都收敛到同一套系统级 SDK，340 个包里有 140+ 个引用它：

| 组件 | 角色 |
|---|---|
| `com.oplus.statistics.rom` 数据基础服务 | OPPO 系统统计 SDK 宿主。内含上传队列 SQLite 表、动态 URL 配置、HttpDNS |
| `com.oplus.nearx` | 埋点上报框架（`com.oplus.nearx.track.internal.upload.net` 出现在 **39 个包**里） |
| `com.oplus.olc` | 日志/行为采集 |
| `com.oplus.onetrace` | 全链路追踪 |
| `com.oplus.dcs` | DCS 设备云，统计协议的服务端 |
| `com.heytap.htms` / `com.heytap.mcs` | HeyTap 移动服务 / 消息推送通道 |

**推论**：只要屏蔽 cdo/epoch/dc 这几个域名族，就能掐断绝大部分系统埋点，不需要逐个 App 处理。

### 2. 数据回传的域名模式（`com.oplus.statistics.rom` 里直接读出的上报路径）

```
/v1/stat/%sAppLog       应用日志
/v1/stat/%sException    异常
/v1/stat/%sappList      已安装应用列表   ← 隐私敏感
/v1/stat/%sclientStart  客户端启动
/v1/stat/%sdau          日活
/v1/stat/%sdcs          DCS 事件
/v1/stat/%sdynamic      动态配置
/v1/stat/%sinstall      安装事件      ← 隐私敏感
/v1/stat/%slaunch       启动
/v1/stat/%sosLaunch     系统启动
/v1/stat/%sosdau        系统日活
/v1/stat/%spageVisit    页面访问
/v1/stat/%sstatic       静态参数
/v3_1/dcs/%sappList     已安装应用（新版本）
/v3_1/dcs/%sinstall / unInstall
/v3_1/dcs/%sosFirstLaunch
/v3_1/dcs/%sfile
/v3_1/dcs/preAppList / preLaunch / preUninstall
/v3/balance/            DCS 配额
/api/dcc-conf/v1/get    动态配置下发
```

本地落盘路径（这些是"数据先存在我机器上"的证据，不一定外发）：
`/data/misc/ostats/packet_files`、`/data/oplus/kevent`、`/data/persist_log/DCS/kevent`

### 3. 域名分族（Tier A 可安全屏蔽，共 128 条）

| 域名族 | 含义 | 条数 |
|---|---|---|
| `*.cdo.heytapmobi.com` / `*.cdo.oppomobile.com` / `epoch.*` | CDO/epoch 统计流水 | 40 |
| `*.ads.heytapmobi.com` / `adx.*` / `cpc.*` / `ssp-*` / `bsp-*` | 广告投放 / 程序化竞价 | 26 |
| `bot-*.heytapmobi.com` / `*.ai` / `oplus.ai` / `pantanal-*` / `sceneservice-*` | AI 助手 / 场景推荐 / 用户画像 | 23 |
| `*ocr*` / `album-idcard` / `translate-service-*` / `videoclip*` / `odin-*` | OCR / 翻译 / 视频剪辑（图片视频上云） | 13 |
| `asdt*` / `adps*` / `hio.oppo.com` / `ua.prof.oppo.com` | 设备指纹 / 用户画像 | 10 |
| `obus-*` / `mdp-usertrace-*` / `nearx` | 行为埋点 / 用户轨迹 | 9 |
| `ums-*telemetry*` | 遥测 | 2 |
| `rest-cn-feedback` / `static-cn-feedback` | 反馈上报 | 2 |
| `sport.health` / `stat.browser` | 健康数据 / 浏览器统计 | 2 |

### 4. 各 App 埋点密度排行（按域名数）

| App | 厂商域名 | 第三方域名 | SDK |
|---|---|---|---|
| 软件商店 `com.heytap.market` | 109 | 50+ | 阿里/字节/GMS/OPPO统计 |
| 浏览器 `com.heytap.browser` | 79 | 50+ | 阿里/高德/百度定位/字节/Bugly/MTA/华为HMS |
| 乐划锁屏 `com.heytap.pictorial` | 75 | 50+ | 阿里/GMS/腾讯MTA |
| 全局搜索 `com.heytap.quicksearchbox` | 67 | 50+ | 百度定位/Bugly/OPPO统计 |
| 快应用 `com.nearme.instant.platform` | 63 | 50+ | 阿里/高德/百度定位/字节/腾讯MTA |
| 小布助手 `com.heytap.speechassist` | 60 | 50+ | 阿里/高德/百度定位/**7 个 SDK** |
| 移动服务 `com.heytap.htms` | 51 | 50+ | 阿里/网易易盾/OPPO统计 |
| 智慧建议 `com.oplus.pantanal.ums` | 39 | 50+ | 阿里/网易/OPPO统计 |
| 智慧数据增强 `com.coloros.sceneservice` | 39 | 50+ | 同上 |
| 帮助与反馈 `com.coloros.operationManual` | 38 | 43 | 阿里/MTA |
| 相册 `com.coloros.gallery3d` | 37 | 50+ | 阿里/易盾/OPPO统计 |
| 速览 `com.coloros.assistantscreen` | 33 | 50+ | GMS/DeepThinker |
| 手机管家 `com.coloros.phonemanager` | 26 | 50+ | 阿里/阿里云/字节/**15 个 SDK**（最多） |

### 5. 第三方 SDK 混入情况（值得单独提）

| SDK | 出现在 |
|---|---|
| **百度定位** `com.baidu.location` | 浏览器、全局搜索、小布助手、信息、系统卡包、快应用 — **一个 OPPO 系统 App 用百度定位，很可疑** |
| **字节跳动** `com.bytedance` | 浏览器、快应用、手机管家、视觉服务、智慧决策 |
| **阿里** `com.alibaba` | 30+ 个包 |
| **网易易盾** `com.netease.nis` | 相册、手机管家、视觉服务、智慧决策 等 |
| **腾讯 Bugly / MTA** | 浏览器、全局搜索、乐划锁屏、账号中心 |
| **华为 HMS** | 浏览器、快应用（说明这两个是华为生态移植的） |
| 高德 `com.amap` | 浏览器、小布助手、快应用、查找手机 |

### 6. 隐私政策链接（51 个包内嵌，已抓取）

主要落点：

- `https://muc.heytap.com/document/heytap/privacyPolicy/privacyPolicy_zh-CN.html` ← **ColorOS 总隐私政策**
- `https://muc.heytap.com/agreement/privacy-policy/account/mainland/v20240331/index.html?language=zh-CN` ← 账号政策
- `https://muc.heytap.com/document/heytap/accountPolicyUpdate/accountSDK/privacyPolicySdk_zh-CN.html` ← 账号 SDK 政策
- `https://privacy.oppo.com/cn/policy` / `https://www.oppo.com/cn/privacy-feedback/`
- `https://www.oneplus.com/global/legal/privacy-policy`
- 支付类：`https://muc.heytap.com/agreement/privacy-policy/pay/mainland/final/index.html`
- 第三方：`https://www.faceunity.com/policy.html`（Omoji 用的相芯科技）、`https://privacy.wps.cn/policies/privacy/kdocs`（随身工作台）

### 7. 开关 Key（85 个包里有，但**这不等于"开关有效"**）

高频 key（大小写不统一，同一语义有多种写法）：

| 语义 | Key 变体 | 出现在 |
|---|---|---|
| 追踪总开关 | `KEY_TRACK` / `key_track` / `KeyTrack` / `keyTrack` | 56 个包 |
| 个性化推荐 | `KEY_RECOMMEND` / `key_recommend` / `personalized_recommend` / `PersonalizedRecommend` / `KEY_PERSONALIZE` | 19+ |
| 个人信息收集 | `collect_personal_info` / `CollectPersonalInfo` / `pref_key_collect` / `COLLECT_PERSONAL_INFO` | 14+ |
| 隐私开关 | `PrivacySwitch` / `privacy_switch` / `PREF_KEY_PRIVACY` | 13 |
| 广告 ID / OAID | `KEY_OAID` / `KEY_AD_ID` / `KEY_ADID` / `KEY_AD_PERSONAL` | 12 / 11 / 8 |
| 统计 | `KEY_STATISTIC` / `key_statistic` / `KeyStatistic` | 10 |
| 用户体验改进 | `USER_EXPERIENCE_IMPROVE` / `key_user_experience` / `KEY_IMPROVE` | 7 |
| 撤回授权 | `KEY_WITHDRAW` / `key_revoke` / `key_withdraw` / `KEY_REVOKE` | 5+ |

其中**开关最多的 App**：浏览器(14)、手机管家(13)、小布助手(12)、设置(11)、软件商店(11)、相册(10)

> ⚠️ **重要局限**：这里只证明"代码里存在这些开关的 key"，**不能证明**关掉开关后真的停止上报。
> 判断"是否允许退出 / 退出后是否还发包"必须靠：①反编译看 key 的实际读取点 ②真机抓包对比。
> 这一条已按 Tom 要求标注为**待验证项**。

### 8. 与 AOSP 的差异（厂商改动的痕迹）

- `com.android.settings` 里有 `key_collect_diagnostics`、`privacy_dashboard_page` —— 厂商加的诊断采集开关
- `com.android.systemui` 引用了 `com.oplus.statistics`（AOSP 原版没有）
- `com.android.mms` / `com.android.contacts` / `com.android.phone` 全部引用 `com.oplus.statistics` + 内嵌 `muc.heytap.com` 隐私政策页
- `com.android.phone` 有 `oplus_privacy_call_introduction`、`key_policy_personal_info_collection_list`
- `com.android.providers.downloads` 引用 `com.oplus.statistics`
- **结论：AOSP 组件确实被加了埋点和隐私声明，不是纯净上游**

---

## 二、交付物

```
projects/coloros-privacy-audit/
├── README.md                       本次审计的索引与使用方法
├── scope-proposal.md               研究范围论证（签名分组、排除规则）
├── report-phase1-quickscan.md      本文件
├── out/
│   ├── apk-index.json              345 个包的签名者/体积/entry 数
│   ├── hosts-clean.json            分类清洗后的域名清单（vendor 568 / thirdparty 8067）
│   ├── profiles.json               每包画像：域名/SDK/隐私链接/开关 key
│   ├── privacy-toggles.json        隐私政策 URL + 开关 key 原始提取
│   ├── scan/<pkg>.json             每包原始扫描结果
│   └── blocklist/
│       ├── 00-wildcard-tier-a.txt  通配版（按注册域名，覆盖面大）
│       ├── 01-telemetry-ads.txt    ★ 推荐直接用：128 条埋点/广告/画像域名
│       ├── 02-caution.txt          197 条功能相关域名（屏蔽会掉功能）
│       ├── 03-rest.txt             243 条其余/未归类
│       └── inventory.json          带分类/用途/风险的结构化数据
└── scripts/
    ├── scan_apk.py                 快扫主程序
    ├── aggregate.py                域名聚合
    ├── refine.py                   主机名清洗 + 厂商域名判定
    ├── build_blocklist.py          黑名单分级输出
    ├── build_profiles.py           每包画像
    └── mine_privacy.py             隐私政策 + 开关 key 挖掘
```

---

## 三、下一轮建议

1. **先上黑名单做实验**：`01-telemetry-ads.txt`（128 条）直接导入 AdGuard Home，
   观察 1-2 天，确认没有功能损坏（重点盯：天气、商店、浏览器、相册）
2. **挑 3-5 个 App 精扫**（jadx），验证"开关关掉后是否仍上报"：
   建议 `com.heytap.browser`（开关最多）、`com.oplus.statistics.rom`（所有埋点的根）、
   `com.coloros.phonemanager`（SDK 最多）、`com.heytap.speechassist`（语音/隐私最敏感）
3. **隐私政策条文对照**：已拿到 51 个包内的官方链接，下一步是抓 `muc.heytap.com` 政策原文，
   按"收集项 / 目的 / 第三方共享 / 是否可撤回"逐条与本报告的域名表比对
4. **真机验证**：用 AdGuard Home 的查询日志看被拦截的实际请求，反推哪些域名真在用、哪些只是代码里的死代码
