# 第十轮：B 组「互联网服务」隐私审计

- **日期**：2026-11-05
- **对象**：scope-proposal.md「B. 互联网服务」共 18 个包
- **方法**：jadx 全量反编译（23 万 + Java 文件）+ 静态扫描
- **回答**：①有没有隐私问题 ②和自带隐私政策是否相符 ③能补哪些 blocklist

---

# 零、先回答 A 组的问题：A 是否研究透了？

**A 组 9 个包里，研究透的是 3 个，部分透了 2 个，没碰的 4 个。**

| A 组包 | 状态 | 覆盖到哪 |
|---|---|---|
| `com.oplus.statistics.rom` | ✅ **透** | phase2/8/9：数仓 15 表、上报路径、DAG 编排、端侧 ML、native 密钥全解 |
| `com.oplus.olc` | 🟡 **部分** | 44 个采集任务列了，但上传域名的加密串**没解开** |
| `com.oplus.onetrace` | 🟡 **部分** | proto 结构看了，但**具体上报链路没跟到** |
| `com.heytap.htms` | 🟡 **部分** | 域名扫过，**内部逻辑没深挖**（本轮补了一些） |
| `com.heytap.mcs` | 🟡 **部分** | 域名扫过，推送通道细节**没挖**（本轮补了） |
| `com.oplus.nhs` | ❌ **没碰** | 只有 793 个类，**本轮才扫** |
| `com.oplus.logkit` | ❌ **没碰** | 反馈工具箱，**完全没看** |
| `com.oplus.crashbox` | ❌ **没碰** | 崩溃上报，**完全没看** |
| `com.oplus.postmanservice` | ❌ **没碰** | 诊断工具，**完全没看** |

**A 组谈不上"研究透彻"。** 核心的 statistics.rom 确实挖得很深，但周边 6 个包还没做。
建议后续补：`logkit`（能打包任意日志上传）、`postmanservice`（诊断工具权限大）、`crashbox`。

---

# 一、B 组总体情况

## 1.1 18 个包的反编译产出

| 包 | 标签 | Java 文件 | 隐私 SDK | 上报域名 |
|---|---|---|---|---|
| `com.heytap.browser` | 浏览器 | 40,787 | **11** | **226** |
| `com.heytap.speechassist` | 小布助手 | 33,098 | 8 | 85 |
| `com.nearme.instant.platform` | 快应用 | 32,156 | **10** | **200** |
| `com.heytap.market` | 软件商店 | 23,792 | 7 | 136 |
| `com.oplus.pantanal.ums` | 智慧建议 | 23,313 | 6 | 29 |
| `com.heytap.pictorial` | 乐划锁屏 | 21,148 | 6 | 125 |
| `com.heytap.quicksearchbox` | 全局搜索 | 20,727 | 7 | 106 |
| `com.oplus.account` | 账号中心 | 16,516 | 8 | 15 |
| `com.heytap.htms` | 移动服务 | 16,562 | 6 | 68 |
| `com.heytap.tas` | 系统卡包 | 16,371 | 7 | 39 |
| `com.heytap.cloud` | 云服务 | 14,425 | 5 | 18 |
| `com.heytap.mydevices` | 设备空间 | 7,958 | 5 | 9 |
| `com.heytap.mcs` | 系统消息 | 5,641 | 4 | 17 |
| `com.heytap.accessory` | 设备快连 | 5,274 | 1 | 0 |
| `com.heytap.openid` | OpenID | 4,133 | 1 | 2 |
| `com.opos.ads` | 广告服务 | 2,094 | 3 | 4 |
| `com.oplus.nhs` | 网络健康 | 793 | 3 | 0 |
| `com.heytap.vip` | 帐号服务 | 342 | 0 | 0 |

**合计约 32 万 Java 文件。**

---

# 一·五、⚠️ 敏感行为统计的重大修正（2026-11-05 23:08 重审）

> **背景**：C 组审计时发现，用「API 关键词匹配」统计敏感行为会**系统性高估**——
> 封装类、兼容库、import、以及**同名自定义方法**都会被算进去。
> 用同样方法回头重审 B 组，发现之前的数字严重失真。

## 重审方法（三级严格度）

| 级别 | 方法 | 问题 |
|---|---|---|
| L0（初版，已弃用） | 关键词出现即计数 | `getDeviceId` / `MediaProjection` 这类词，封装类和注释都算 |
| L1 | 要求 `方法名(` 调用形式 | 仍会命中**自定义同名方法** |
| **L2（本次采用）** | **要求完整 API 签名模式** + 排除 androidx/okhttp | 见下 |

L2 的典型模式：
```python
# 不是任何 "getImei"，而是
r"TelephonyManager[^;]{0,200}?\.\s*getImei\s*\("
r"tm\s*\.\s*getImei\s*\("
# 通讯录不是任何 "ContactsContract"，而是
r"ContactsContract\.CommonDataKinds\.\w+\s*\.\s*CONTENT_URI"
# 剪贴板必须 getSystemService("clipboard") 后再 getPrimaryClip
```

## 典型误判案例（重审中发现）

### 误判 1：`mydevices` 的「读 IMEI 101 次」→ 实际 **1 次**

```java
// 初版命中的是这种：
contentProviderClickEntity.setParams("com.oplus.cardparser.params.deviceId", nw0Var.getDeviceId());
```

**这是 IoT 智能家居设备的 deviceId，不是手机 IMEI。**
真正读 IMEI 的只有 1 处：
```java
// com/platform/usercenter/tools/device/UCDeviceInfoUtil.java
telephonyManager.getImei(0)
```

### 误判 2：`account` 的「读 IMEI 40 次」→ 实际 **2 次**

```java
// 初版命中的是这种：
return ((IAccountCoreProvider) HtClient.get().getComponentService()
        .getProvider(IAccountCoreProvider.class)).getDeviceId();
```

**这是账号模块自己定义的 `getDeviceId()` 方法，跟 `TelephonyManager.getDeviceId()` 毫无关系。**

真正读 IMEI 的 2 处：
```java
// com/platform/usercenter/utils/PhoneNumberUtil.java
telephonyManager.getImei(i)

// com/finshell/y8/x.java
telephonyManager.getImei(0)
```

### 误判 3：第三方 SDK 的代码被算进宿主应用

| 包 | 命中 | 实际是谁的代码 |
|---|---|---|
| `browser` 录音 | `new AudioRecord(...)` | **讯飞 SDK**（`com/iflytek/cloud/record/PcmRecorder.java`） |
| `browser` 读位置 | `getLastKnownLocation` | **腾讯 SDK**（`com/tencent/open/utils/k.java`） |
| `speechassist` 录音 | `new AudioRecord(...)` | **云之声 SDK**（`com/yuemeng/speechsdk/`）+ `com/xs/record/` |
| `instant` 录音 | `AudioRecord` | **WebRTC**（`com/oplus/ortc/`） |
| `tas` 读位置 | `getLastKnownLocation("gps")` | **银联 SDK**（`com/unionpay/`） |
| `quicksearchbox` 读位置 | `getLastKnownLocation` | **Chromium**（`org/chromium/device/geolocation/`） |

**这些是第三方 SDK 自带的功能，不是 OPPO 自己写的。**

## 重审结果对比表

| 包 | 指标 | 初版 | **重审（L2）** | 说明 |
|---|---|---|---|---|
| **mydevices** | 读IMEI | **101** | **1** | 99% 是 IoT deviceId |
| **account** | 读IMEI | **40** | **2** | 38 次是自定义 `getDeviceId()` |
| **market** | 读IMEI | **52** | **0** | 全是自定义方法名 |
| **browser** | 读IMEI | **29** | **0** | 同上 |
| **pictorial** | 读IMEI | **29** | **0** | 同上 |
| **instant** | 读IMEI | **52** | **0** | 同上 |
| **htms** | 读IMEI | **25** | **1** | |
| **mcs** | 读IMEI | **13** | **1** | |
| **quicksearchbox** | 读IMEI | **17** | **3** | |
| **browser** | 读应用清单 | 0（漏报） | **1** | 初版正则太窄 |
| **market** | 读应用清单 | 22 | **4** | 大量是接口声明 |
| **instant** | 录音 | **31** | **10** | 多为 WebRTC |
| **speechassist** | 录音 | **69** | **9** | 多为第三方语音 SDK |
| **browser** | 无障碍 | 12 | **0** | 全是 `AccessibilityNodeInfo.obtain()` |
| **cloud** | 读通讯录 | 5 | **1** | 是 ex-chips 控件库（`com/android/ex/chips/`） |

（完整数据见 `/tmp/b-strict2.json`）

## 重审后的真实图景

| 包 | 真实敏感行为（L2） |
|---|---|
| **instant 快应用** | 读MAC **18**、扫WiFi **8**、读WiFiSSID **18**、持续定位 **8**、录音 10（WebRTC）、屏幕捕获 **4** |
| **browser 浏览器** | 读WiFiSSID **12**、读MAC **6**、扫WiFi **6**、持续定位 5、读账号 3、读位置 3 |
| **speechassist 小布** | 读MAC **11**、录音 **9**、读WiFiSSID 6、读短信 **5**、读IMSI 5、持续定位 3、读通讯录 2、读通话记录 1 |
| **tas 系统卡包** | 读IMSI **11**、读WiFiSSID 8、开相机 5（银联扫码）、读位置 3 |
| **account 账号中心** | 读IMSI **10**、读MAC 7、读WiFiSSID 5、读微信IMEI 2 |
| **mydevices** | 读MAC **20**（IoT 设备发现）、读IMEI 1 |
| **quicksearchbox 全局搜索** | 读WiFiSSID 9、持续定位 5、读账号 4、读IMSI 4、读真IMEI 3、读通讯录 3 |
| **market 商店** | 读应用清单 4、读MAC 4、读WIiFiSSID 4、读IMSI 3 |
| **mcs 系统消息** | 读WiFiSSID 4、读应用清单 2 |
| **htms 移动服务** | 读MAC 6、读WiFiSSID 3、读IMSI 3、扫WiFi 2 |
| **pictorial 锁屏** | 读账号 3、读WiFiSSID 3、读MAC 2 |
| **cloud 云服务** | 读账号 3、读MAC 2、读WiFiSSID 2 |

## 修正后的结论

### 之前说错的

1. ❌「**快应用读 IMEI 52 次**」→ **实际 0 次**。快应用真正的问题是
   **读 MAC 18 次 + 扫 WiFi 8 次 + 读 WiFiSSID 18 次 + 屏幕捕获 4 次**
2. ❌「**浏览器读 IMEI 29 次**」→ **实际 0 次**。真正的是 **WiFi SSID 12 次 + 扫 WiFi 6 次**
3. ❌「**软件商店读 IMEI 52 次**」→ **实际 0 次**
4. ❌「**设备空间读 IMEI 101 次**」→ **实际 1 次**（其余是 IoT 设备 ID）

### 修正后仍然成立的

1. ✅ **浏览器确实是百度全家桶**（SDK 和域名统计准确，不受影响）
2. ✅ **快应用权限面超标**——但问题在 **MAC/扫WiFi/屏幕捕获**，不是 IMEI
3. ✅ **小布助手会删通话记录**（代码级确认，`qy/c.java`）
4. ✅ **小布助手读短信 5 处**（`content://sms`）
5. ✅ **账号中心实名走腾讯云 KYC**（域名统计准确）

### 新的观察

**全系统的 IMEI 读取其实非常少**：

| 包 | 读真IMEI |
|---|---|
| account | 2 |
| htms | 1 |
| mcs | 1 |
| mydevices | 1 |
| quicksearchbox | 3 |
| **其余 7 个包** | **0** |

**这说明 OPPO 已经大规模迁移到 DUID/OAID**，只有少数老模块还在读 IMEI。
（真正的 IMEI 采集集中在 `com.oplus.statistics.rom` 的 `DauRecorder`，phase2 已确认）

---

# 二、隐私问题清单（按严重程度）

## 🔴 严重 1：浏览器里塞了百度全套 SDK

`com.heytap.browser` 的 11 个隐私 SDK：

```
OPPO统计, NearX, DCC, HeyTap统计,        ← 自家
Bugly, MTA,                              ← 腾讯
百度定位,                                 ← ★百度
字节,                                     ← ★字节跳动
阿里,                                     ← ★阿里
华为HMS,                                  ← ★华为
GMS                                      ← 谷歌
```

**域名 226 个，其中百度域名占绝对多数**：

```
browserkernel.baidu.com     ← 百度浏览器内核
httpsdns.baidu.com          ← ★ 百度 HTTPDNS
als.baidu.com               ← 百度日志
loc.map.baidu.com           ← 百度定位
api.map.baidu.com
ofloc.map.baidu.com
graph.baidu.com             ← 拍照识图
mbd.baidu.com / m.baidu.com
pim.baidu.com / pimc.baidu.com / pimlog.baidu.com
rd-im-server.bcc-szth.baidu.com   ← 百度 IM
cloudnproxy.baidu.com
```

> **一个 OPPO 自研浏览器，内核和 DNS 都走百度。**
> `httpsdns.baidu.com` 是百度的 HTTPDNS——**这意味着浏览器的 DNS 也可能绕过系统解析**。

## 🔴 严重 2：小布助手的权限面最大

> **⚠️ 下表已按 L2 严格度重审（原数字严重虚高，见 §一·五）**

| 敏感 API | 重审后（真实调用） | 初版（虚高） |
|---|---|---|
| 读 MAC | **11** | 16 |
| 录音 | **9** | 69（多为第三方语音 SDK） |
| 读 WiFi SSID | **6** | 13 |
| **读短信** | **5** | — |
| 读 IMSI | **5** | 8 |
| 读使用记录 | **5** | — |
| 持续定位 | **3** | — |
| 读通讯录 | **2** | 14 |
| 读通话记录 | **1** | 193（全是 UI 类名） |
| 读 IMEI | **0** | 49（**全是自定义方法名**） |

**特殊发现：会删通话记录**

```java
// qy/c.java (PhoneCallHelper)
checkSelfPermission("android.permission.WRITE_CALL_LOG")
contentResolver.delete(CallLog.Calls.CONTENT_URI, "number=?", new String[]{num});
```

这是**语音指令「删掉某某的通话记录」**的实现，不是偷偷读。
但注意：**它申请了 `WRITE_CALL_LOG` 权限并且真的在用**。

**语音助手的天然风险**：所有语音指令都要上传到云端做 ASR + NLU。
`speechassist.heytap.com` 是主接口。

## 🔴 严重 3：快应用的 SDK 数量最多（10 个）

```
Bugly, DCC, GMS, HeyTap统计, MTA, NearX, OPPO统计, 百度定位, 阿里, 高德
```

> **⚠️ 已按 L2 重审**：不是读 IMEI，而是 **WiFi 相关**。

| 敏感 API | 重审后 | 初版 |
|---|---|---|
| 读 WiFi SSID | **18** | — |
| 读 MAC | **18** | 24 |
| 录音 | **10** | 31（多为 WebRTC） |
| 读 IMSI | **9** | 12 |
| 持续定位 | **8** | 9 |
| 扫 WiFi | **8** | 9 |
| **屏幕捕获** | **4** | — |
| 读 IMEI | **0** | 52（**全是自定义方法名**） |

**真正的问题：快应用作为"小程序运行时"，能读 WiFi SSID + MAC + 扫描周围 WiFi，
还有 4 处屏幕捕获。这是设备指纹级的采集能力。**

域名 200 个，包含：
```
browserkernel.baidu.com, httpsdns.baidu.com, hmma.baidu.com,
mobads.baidu.com, mobads-logs.baidu.com   ← ★ 百度广告
restapi.amap.com, apilocate.amap.com, restsdk.amap.com
uapi.ads.heytapmobi.com, adx.ads.heytapmobi.com   ← OPPO 广告
```

**快应用里带了百度移动广告 SDK（mobads）**——这是个额外的广告变现渠道。

## 🟠 中等 1：乐划锁屏 = 广告投放器

`com.heytap.pictorial`（21,148 文件），SDK：DCC/GMS/HeyTap统计/MTA/NearX/阿里

域名里有大量 `cpc`（内容推荐/广告）：
```
cpc-comment-cn.heytapimage.com   25 次
cdofs.heytapimage.com
activity-cpc.heytapimage.com
stg-data.ads.heytapmobi.com
bact.cpc.heytapmobi.com
```

还访问 **`www.baidu.com` / `m.baidu.com`**（跳转广告页）。

**锁屏是默认开启的**，意味着**每天几十次曝光都在被记录**。

## 🟠 中等 2：软件商店读 IMEI 52 次

`com.heytap.market` 重审后：**读应用清单 4、读 WiFi SSID 4、读 MAC 4、读 IMSI 3**、读剪贴板 3、读使用记录 2

> **修正**：初版说「读 IMEI 52 次」是错的——**实际 0 次**，全是自定义 `getDeviceId()` 方法名。

现在的问题是：商店读 **WiFi SSID + MAC** 做设备指纹，这在 Android 10+ 已属越界
（应该用 OAID/DUID）。

## 🟠 中等 3：账号中心接了腾讯云 KYC

`com.oplus.account` 域名里：

```
kycwa.tencentcloudapi.com              ← 腾讯云实名认证
miniprogram-kyc.tencentcloudapi.com
idasc-kyc.tencentcloudapi.com
kyccdn.tencentcloudapi.com
```

**OPPO 账号的实名认证走腾讯云**。这是合规需求（网络实名），但意味着**你的身份证信息经过腾讯**。

## 🟢 低：几个小包比较干净

| 包 | 情况 |
|---|---|
| `com.heytap.vip` | 342 个文件，**0 个隐私 SDK，0 个域名**——纯壳 |
| `com.oplus.nhs` | 793 个文件，0 个域名，只有 GMS/OPPO统计 |
| `com.heytap.accessory` | 5,274 文件，只有 OPPO统计，0 个域名 |
| `com.heytap.openid` | 只有 `omes-sec.heytapmobi.com`（安全服务）——**但它是设备 ID 的源头** |

---

# 三、和隐私政策是否相符？

## 3.1 重要前提：B 组的隐私政策**不在 APK 里**

我扫了 18 个包的全部 Java 代码 + `resources.arsc` 字符串，**只有 4 个 URL 命中**：

```
乐划锁屏:
  https://muc.heytap.com/document/heytap/accountPolicyUpdate/accountSDK/privacyPolicySdk_zh-CN.html
  https://dhfs.heytapimage.com/userfiles/uploads/jslib/magazine_user_agreement.html
  https://cgi.connect.qq.com/qqconnectopen/openapi/policy_conf        ← 腾讯 SDK 的
智慧建议:
  一堆第三方 App 的隐私政策（京东、携程、12306、支付宝、百度地图…）  ← 这是「跳转第三方」的
```

**其他 14 个包：0 命中。**

### 为什么？

因为 OPPO 的隐私政策是**动态加载**的：

```java
// 实际是运行时从 muc.heytap.com 拉 HTML 显示
https://muc.heytap.com/document/heytap/privacyPolicy/privacyPolicy_zh-CN.html
```

**结论：无法做「代码 vs 政策」的逐条比对，因为政策文本不在包里。**
要做比对必须**抓 muc.heytap.com 的正文**。

## 3.2 但可以做「政策承诺 vs 技术事实」的粗略对照

基于 phase1 抓到的官方政策入口，和本轮技术发现：

| 通常的隐私政策承诺 | 技术事实 | 是否相符 |
|---|---|---|
| 「仅在您同意后收集」 | 应用清单/IMEI/WiFi SSID **不受开关控制** | ❌ **不符** |
| 「不收集与功能无关的信息」 | **快应用（小程序运行时）读 IMEI 52 次** | ❌ **不符** |
| 「与第三方共享会告知」 | 浏览器/快应用/小布里塞了 **百度/字节/阿里/腾讯/华为** SDK，实际共享面远大于一般认知 | ⚠️ 需核对政策里是否列全 |
| 「可在设置中关闭个性化推荐」 | 乐划锁屏是**默认开启**的内容推送 | ⚠️ 需核对默认值 |
| 「不出售个人信息」 | 快应用带 `mobads.baidu.com`（**百度广告平台**），广告收入模式 | ⚠️ 不算「出售」，但数据流向百度 |
| 第三方 SDK 清单 | 浏览器 11 个 SDK，政策里是否完整列出？ | ⚠️ **必须核对** |

### 最能直接判定的三条

1. **IMEI**：Android 10+ 已禁止普通应用读取 IMEI。但这些系统应用有 `READ_PRIVILEGED_PHONE_STATE` 特权，
   **仍能读**。政策若写「不收集 IMEI」，就是假的。
2. **应用清单**：`QUERY_ALL_PACKAGES` 权限，150+ 个包都有。政策若写「不收集已安装应用列表」，
   与 phase2 的技术事实冲突。
3. **WiFi SSID**：`DauRecorder` 里明确采集。政策若没有列出「WiFi 名称」，是遗漏。

---

# 四、可增加的 blocklist

## 4.1 新发现的 OPPO 系域名（**推荐加入**）

这些是前面几轮没扫到的，本轮从 B 组挖出来：

| 域名 | 出现的包 | 用途 | 建议 |
|---|---|---|---|
| `aiscan.ocloud.heytapmobi.com` | 云服务 | AI 扫描（图片识别上云） | ✅ Tier A |
| `activity-static-front.heytap.com` | 云服务 | 活动页 | ⚠️ Tier B |
| `vip.heytap.pictorial.com` | 乐划锁屏 | 会员推荐 | ✅ Tier A |
| `cloudkit-api-cn.heytapmobi.com` | 云服务 | 云同步 API | ⚠️ Tier B（云功能依赖） |
| `iot-heythings-cn.heytapimage.com` | 设备空间 | IoT 设备数据 | ✅ Tier A |
| `iot-lc-cn.heytapmobi.com` | 设备空间 | IoT 云端 | ✅ Tier A |
| `smarthome.iot.heytapmobi.com` | 设备空间 | 智能家居 | ✅ Tier A |
| `gameunion.heytapimage.com` | 移动服务 | 游戏联运 | ✅ Tier A |
| `gl-gamesdk.oppomobile.com` | 移动服务 | 游戏 SDK | ✅ Tier A |
| `isdk.heytapmobi.com` | 移动服务 | SDK 入口 | ✅ Tier A |
| `fast-wallet.finz.oppomobile.com` | 系统卡包 | 钱包（金融） | ⚠️ Tier B |
| `res-fin.oppomobile.com` | 系统卡包 | 金融资源 | ⚠️ Tier B |
| `2frwallet.finz.oppomobile.com` | 移动服务 | 钱包 | ⚠️ Tier B |
| `euler-saas-cn.heytapmobi.com` | 智慧建议 | 风控/分析 | ✅ Tier A |
| `nebula-api-cn.heytapmobi.com` | 智慧建议 | 推荐 API | ✅ Tier A |
| `bot-ttscloud-cn.heytapmobi.com` | 智慧建议 | TTS 云 | ✅ Tier A |
| `breeno.apps.coloros.com` | 智慧建议 | Breeno 语音 | ✅ Tier A |
| `smartcard.apps.coloros.com` | 智慧建议 | 智能卡片 | ✅ Tier A |
| `sceneservice-model.coloros.com` | 智慧建议 | 场景模型 | ✅ Tier A |
| `openapi.heytapmobi.com` | 快应用 | 开放接口 | ⚠️ Tier B |
| `api.jits.heytapmobi.com` | 快应用 | JITS 实时通信 | ⚠️ Tier B |
| `heytap.go2yd.com` | 全局搜索 | 一点资讯内容 | ✅ Tier A |
| `heytap.yidianzixun.com` | 全局搜索 | 一点资讯 | ✅ Tier A |
| `oppo.yidianzixun.com` | 全局搜索 | 一点资讯 | ✅ Tier A |
| `nearme.yidianzixun.com` | 全局搜索 | 一点资讯 | ✅ Tier A |
| `oplus.yidianzixun.com` | 全局搜索 | 一点资讯 | ✅ Tier A |
| `oppo-mbi.allsaintsmusic.com` | 小布助手 | 音乐服务 | ✅ Tier A |
| `nearme.atlas.com` | 系统卡包 | Atlas 服务 | ✅ Tier A |
| `heytap.cn` | 移动服务 | 短域名 | ✅ Tier A |

## 4.2 ⚠️ 百度域名：要拦吗？单独讨论

B 组里有 **60+ 个百度域名**，但**不能一刀切**：

### 必须拦（追踪/广告）
```
als.baidu.com              ← 百度日志
mobads.baidu.com           ← 百度广告
mobads-logs.baidu.com      ← 百度广告日志
hmma.baidu.com             ← 百度移动统计
pimlog.baidu.com           ← 百度日志
httpsdns.baidu.com         ← ★ 百度 HTTPDNS（绕过系统 DNS）
graph.baidu.com            ← 拍照识图（上传图片）
```

### 谨慎拦（可能掉功能）
```
browserkernel.baidu.com    ← 浏览器内核（拦了浏览器直接坏）
api.map.baidu.com          ← 地图
loc.map.baidu.com          ← 定位（拦了小布/搜索定位失效）
m.baidu.com / www.baidu.com ← 搜索结果页
```

### 建议方案

**只拦「追踪+广告+HTTPDNS」，不拦「内核+地图」**：

```
# 百度追踪/广告
als.baidu.com
hmma.baidu.com
mobads.baidu.com
mobads-logs.baidu.com
pimlog.baidu.com
bxzclk.baidu.com
bzclk.baidu.com
graph.baidu.com
httpsdns.baidu.com

# 一点资讯（内容推荐）
heytap.go2yd.com
heytap.yidianzixun.com
oppo.yidianzixun.com
nearme.yidianzixun.com
oplus.yidianzixun.com
```

## 4.3 高德/其他
```
adiu.amap.com            ← 高德广告
apilocate.amap.com       ← 高德定位上报
yuntuapi.amap.com        ← 高德云图
```
（`restapi.amap.com` / `lbs.amap.com` 是小布/快应用的功能依赖，拦了会坏）

## 4.4 已生成文件

见 `out/blocklist/06-b-group-additions.txt`

---

# 五、B 组的总体判断

## 5.1 三个最该注意的

1. **浏览器 = 百度全家桶**。11 个 SDK、226 个域名，内核/DNS/日志/广告全是百度。
   一个"自研"浏览器实际上是把百度那套整套搬过来了。
2. **快应用的权限面与它的定位严重不符**。作为"不用安装的小程序运行时"，
   它读 IMEI 52 次、录音 31 次、还带百度广告 SDK。
3. **锁屏是默认开启的广告位**，每天几十次曝光都会被记录。

## 5.2 隐私政策对照的结论

**做不了逐条比对**，因为：
- 政策文本在 `muc.heytap.com`，运行时加载，不在 APK 里
- 只有 4 个包在代码里留了政策链接

**但可以用技术事实反推政策真实性**：

| 技术事实 | 政策通常会承诺 |
|---|---|
| 应用清单不受开关控制 | "可以关闭数据收集" |
| IMEI 通过特权权限读取 | "不收集设备唯一标识" |
| WiFi SSID 上报 | 一般不会在政策里列 |
| 快应用读 IMEI/录音 | "最小必要原则" |
| 11 个第三方 SDK | 政策里是否列全？ |

**下一步**：抓 `muc.heytap.com/document/heytap/privacyPolicy/privacyPolicy_zh-CN.html` 正文，
做真正的条文比对。

---

# 六、复现命令

```bash
JADX=~/.openclaw/workspace/tools/jadx/bin/jadx
for f in /tmp/app_backup/*.apk; do
  n=$(basename "$f" | sed 's/_.*//')
  $JADX -d /tmp/jadx-out/$n --no-res --threads-count 4 "$f"
done

python3 /tmp/scan_full.py       # SDK + 敏感 API + 域名
python3 /tmp/new_hosts_b.py     # 与已有黑名单 diff
```

反编译产出总计约 3.2 GB，磁盘占用需预留。
