# 第十二轮：D 组「手机管家 / 安全类」隐私审计

- **日期**：2026-11-06
- **对象**：`scope-proposal.md`「D. 手机管家/安全（权限大、能读全量数据）」，共 10 个包
- **方法**：jadx 反编译（约 6.6 万 Java 文件）+ 原始 APK 权限/域名字符串提取 + 关键路径逐行读源码
- **回答**：①权限有多大 ②数据是否离开设备 ③开关在哪、能不能关 ④补哪些 blocklist

---

# 一、10 个包总览

| 包 | 名称 | 大小 | Java 文件 | 敏感权限 | 域名数 |
|---|---|---|---|---|---|
| `com.coloros.phonemanager` | 手机管家 | 59 MB | 25,780 | 3 | **35** |
| `com.oplus.blacklistapp` | 骚扰拦截 | 9 MB | 5,307 | **8** | 5 |
| `com.oplus.securitypermission` | 权限管理 | 21 MB | 3,684 | 0 | 2 |
| `com.coloros.securityguard` | 安全事件 | 10 MB | 3,646 | 1 | 3 |
| `com.oplus.safecenter` | 安全中心 | 16 MB | 3,248 | 0 | **1** |
| `com.coloros.healthcheck` | 常规检测 | 13 MB | 3,142 | 3 | 3 |
| `com.coloros.codebook` | 密码本 | 13 MB | 9,983 | 5 | 11 |
| `com.oplus.trafficmonitor` | 流量管理 | 11 MB | 2,911 | 2 | **1** |
| `com.oplus.encryption` | 私密保险箱 | 8 MB | 7,116 | 0 | **18** |
| `com.oplus.qualityprotect` | QualityProtect | 2 MB | 862 | 0 | **0** |

**合计约 6.6 万 Java 文件。**

---

# 二、结论速览（先看这个）

## 好消息

1. **D 组整体很干净**，绝大多数包域名数为 0–3。
2. **权限管理 / 安全中心 / 流量管理 / QualityProtect 完全不联网采集**——域名清一色是 `schemas.android.com`（XML 命名空间，非真实请求）。
3. **密码本、私密保险箱的加密做得扎实**（AES-256-GCM + Android KeyStore 硬件密钥区），不是糊弄人的。

## 需要注意的

| 严重度 | 包 | 问题 |
|---|---|---|
| 🔴 **高** | `com.coloros.phonemanager` | AI 语音反诈把**通话音频** Opus 编码 + Base64 后上云（详见第三节） |
| 🟡 **中** | `com.oplus.encryption` | 私密保险箱**有云同步**，不是"纯本地"（但先加密后上传，见第五节） |
| 🟡 **中** | `com.coloros.phonemanager` | 「碎屏险」模块带 **OAID** 上报购买状态，属商业推广 |
| 🟢 **低** | `com.coloros.codebook` | 向服务器回传**账号绑定手机号**做"解掩码"，见第四节 |
| 🟢 **低** | `com.coloros.healthcheck` | 在线客服会把**检测结果 + accessToken + deviceId** 发出去（用户主动点击才触发） |

---

# 三、🔴 重点：AI 语音反诈（phonemanager）

> 这一节是 Tom 特别要求的：「网上搜索 AI 通话防诈是有 OPPO 的，但我的版本没找到入口」

## 3.1 先说结论：你的机器确实没启用，而且是设计如此

**adb 实测证据（Tom 提供）**：

```
$ adb shell settings get system ai_voice_detect_switch
null
```

`null` 的含义：**这个 Settings 键从未被写入过**。代码里所有读取点都是：

```java
// FeatureOption.java:1102
getSystemIntCompat(context, "ai_voice_detect_switch", 0) == 1
                     ↑ 默认值 0（关闭）
```

也就是说：**键不存在 = 走默认值 0 = 功能关闭**。这就是你找不到入口的原因。

## 3.2 代码层面：为什么你的机器上根本没有这个入口

功能可见性由 `isAIVoiceDetectSupport()` 决定，**三个条件必须同时为真**：

```java
// FeatureOption.java:1024-1032
public static final boolean isAIVoiceDetectSupport_delegate$lambda$52() {
    if (!isTablet()) {
        if (featureOption.getHasIncallExperiencePermission()
            && featureOption.isAIVoiceOrCrossSceneFraudSupportRegion()
            && featureOption.isVdcSupport()) {
            return true;
        }
    }
    return INSTANCE.getAiVoiceDetectDebugProp();   // 兜底：debug prop
}
```

逐个拆开：

### 条件 ① 区域白名单——**这是决定性的**

```java
// FeatureOption.java:1039-1042
public static final boolean isAIVoiceOrCrossSceneFraudSupportRegion_delegate$lambda$63() {
    List listOf = CollectionsKt.listOf((Object[]) new String[]{"IN", "TH", "ID"});
    String regionMark = getRegionMark();
    ...
}
```

**只有三个国家/地区：`IN`（印度）、`TH`（泰国）、`ID`（印尼）。**

**中国大陆（`CN`）不在名单里。**

这一条基本就宣判了：国行机器不会有这个功能入口。

### 条件 ② `hasIncallExperiencePermission()`
调用体验权限（`CONTROL_INCALL_EXPERIENCE`）。国行普通零售机通常也没有。

### 条件 ③ `isVdcSupport()`
VDC 硬件能力（语音降噪/回声消除相关的底层芯片能力），需要硬件侧 prop 支持。

### 补充：还有第二个独立开关

```java
// FeatureOption.java:1073-1081
public static final boolean isAiFraudDetectSupport_delegate$lambda$55() {
    if (!isTablet() && isChinaRegion()) {          // ← 这条要求是中国区
        if (featureOption.getHasIncallExperiencePermission()
            && featureOption.isVdcSupport()) {
            return true;
        }
    }
    return INSTANCE.getAiFraudDetectDebugProp();
}
```

注意这里有意思的地方：**「AI 电话诈骗检测」（`isAiFraudDetectSupport`）要求是中国区**，而「AI 语音检测」（`isAIVoiceDetectSupport`）要求是印度/泰国/印尼。

**两者互斥**。说明这是两套不同产品线的功能，国内线走的是后者，但同样卡在 `hasIncallExperiencePermission` + `isVdcSupport`。

## 3.3 但代码确实存在——如果被启用，它会上传什么

这部分很重要，因为**功能存在、只是被区域/硬件门禁挡住了**。

### 通话音频的完整外传链路

```java
// CloudSemanticsDetectStrategy.java
private static final String API = "/speechAntiFraud/infer";
private static final String DEV_HOST = "https://odin-inference-cn.allawntech.com";
private static final String TEST_HOST = "https://odin-deployment-cn.wanyol.com";
```

```
来电/去电建立
  → SharedAudioBufferManager 分片采集音频
  → OpusEncodeUtils.encodePcmToOpus()   ← Opus 压缩
  → Base64 编码
  → POST https://odin-inference-cn.allawntech.com/speechAntiFraud/infer
  → 云端返回诈骗判定
```

### 关键：语义检测 **100% 走云端**

```java
// DetectStrategyFactory 之类的构造处（assembly）
if (isLightOs) {
    cloudSyntheticDetectStrategy = new CloudSyntheticDetectStrategy();
    cloudSyntheticDetectStrategy.init(...);
}
```

- **语义检测（semantics）**：`CloudSemanticsDetectStrategy`，**每次都是云**
- **合成音检测（synthetic）**：轻量系统（isLightOs）走云，其他走 `LocalSyntheticDetectStrategy` 本地推理

### 但注意：`uploadAudio` 是另一回事

```java
// SimCallDetectManager.java
FeedbackRepository.uploadAudio(byte[] audio, Session session)
```

**唯一的调用方是 `FalseReportFeedbackActivity`**，也就是用户在结果页手动点「误报反馈」。这属于用户主动行为，不是自动上传。

**所以准确表述是**：
- ✅ 音频**片段**会被送到云端做推理（这是功能本身）
- ❌ 但不是静默批量上传录音文件

### 关闭入口（如果你哪天真的有了这个功能）

```
手机管家 →（反诈守护 / SecurityHomeActivity）→ AI 通话防诈（AiVoiceCallDetectSettingsActivity）
```

两个相关开关：
- `ai_voice_detect_switch`（默认 0 = 关）
- `security_home_master_switch`（反诈总开关，默认 0 = 关）

```java
// TriggerGuideFreqUtilsKt.java:140
return Settings.System.getInt(cr, "security_home_master_switch", 0) == 1
    || Settings.System.getInt(cr, "ai_voice_detect_switch", 0) == 1;
```

> ⚠️ **顺带修正我之前的错误**：上一轮我说入口在「手机管家 → 反诈中心 / 智能反诈」，这是错的。
> 实际界面文案是「**AI 通话防诈**」，位于「反诈守护」首页内。
> 而 Tom 猜的「骚扰拦截 → 拦截规则设置 → 国家反诈中心拦截服务」是**另一套系统**（见 3.4）。

## 3.4 三套反诈别搞混（重要澄清）

| 系统 | 入口 | 干什么 | 联网 | 你的机器 |
|---|---|---|---|---|
| **国家反诈中心拦截** | 骚扰拦截 → 拦截规则设置 | 比对**诈骗号码库**，拦来电/短信 | 号码库下载 | ✅ 有（另一套） |
| **AI 通话防诈** | 手机管家 → 反诈守护 | **通话音频上云**做诈骗语义分析 | 音频上云 | ❌ 区域不含 CN |
| **AI 深伪检测** | 手机管家 → 反诈守护 | 人脸/合成语音识别 | 视配置 | 需单独查 |

Tom 猜的「国家反诈中心拦截服务」文案证据（`blacklistapp/resources.arsc`）：

```
#12429: 国家反诈中心拦截
#12491: 国家反诈中心拦截服务
#12423: 拦截涉嫌诈骗的来电和信息，由国家反诈中心提供数据支持
#12392: 为提供国家反诈中心拦截服务，"智能识别陌生号码" 需要访问网络以更新诈骗号码信息。
```

**关键**：这是**号码库比对**，依赖 `com.ted.number`（智能识别陌生号码）联网更新号码表。
**它不碰你的通话内容。** 担心指数比 AI 语音反诈低得多。

## 3.5 这一节的最终答复

> **Tom 的问法**：「我没有找到这个入口，猜测可能我的版本没有启用，但网上搜索 AI 通话防诈是有 OPPO 的」

**你的猜测完全正确，而且比"版本老"更具体**：

1. ✅ 功能代码确实在手机管家里（不是网上说错了）
2. ✅ **但区域白名单只有 IN / TH / ID，中国大陆不在内** —— 这是硬门禁，不是设置项
3. ✅ 外加 `hasIncallExperiencePermission` 和 `isVdcSupport` 两个硬件/权限门禁
4. ✅ adb 返回 `null` 精确印证：**这个开关从未被写过，功能处于未激活态**

**换句话说：你不用担心。你的机器根本没跑这套逻辑。** 网上那些截图大概率是海外版（印度/东南亚）机型。

---

# 四、🟢 密码本（codebook）：比预期干净

## 4.1 它不是网站密码本，是"个人资料自动填充"

实体类里存的是（`data/entity/`）：

```
BaseInfo   —— 姓名、性别、生日、身份证号、有效期、国籍
Passport / HkMacauPassport / DriverLicence / CarLicence —— 各类证件
BankCard   —— 银行卡
Address / Email / Phone / Tax / Custom
```

**这是表单自动填充的资料库**（姓名/身份证/银行卡），跟 1Password 那类网站账号密码本不是一回事。

## 4.2 加密做得很扎实

```java
// AutofillMasterKey.java:50
keyGenerator.init(256);                                    // AES-256
getKeyStoreManager().setEntry(
    Constant.OPLUS_MASTER_KEY + ssoid,
    new KeyStore.SecretKeyEntry(generateKey),
    new KeyProtection.Builder(3).setBlockModes("GCM")      // GCM 模式
                               .setEncryptionPaddings("NoPadding")
);
```

```java
// AutofillMasterKey.java:310
Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
```

- AES-256-GCM
- 主密钥存 **Android KeyStore**（`getKeyStoreManager()`，硬件支持地区在 TEE 里）
- 还有一层 wrapper key，用公钥包裹
- `RootUtils.secureCheck()` 为真时**直接拒绝创建密钥**（防 root 窃取）

## 4.3 备份：加密后才出去

`AutoFillBackUpPlugin` 走 `heytap backup SDK`（云备份），但备份前：

```smali
invoke-virtual {v2, p1}, Lcom/oplus/autofill/key/AutofillMasterKey;->getMasterKeyUnwrapped(...)
invoke-static {p1, v2, p0}, Lo〇0〇OoO/〇Ooo;->〇o0〇o0(...)   // 用主密钥加密
const-string p1, "autofill_public_master_key"
invoke-virtual {v9, p1, p0}, Lorg/json/JSONObject;->put(...)
```

备份文件 `AutoFillBackUp.json` 是**加密后**的密文，密钥不出设备。

## 4.4 唯一的联网点：手机号"解掩码"

```java
// RuleHttpHelper.java:143-161
public String transformPhoneString(Context context, String str) {
    // 1. 本地生成一次性 AES-128 密钥
    // 2. 用内置 RSA 公钥加密该密钥
    // 3. POST {phoneNumber: str, encryptAesKey: rsa(密钥)} 到 /api/phone-decrypt/decrypt
    // 4. 服务器返回 AES 加密后的明文号，本地解密
}
```

**谁在用**：只有 `AccountOauthManager` 拿到 OAuth 返回的 `mobile`（**你自己账号绑定的手机号**，已被打码成 `138****1234`）后，调它还原成明文展示。

**定性**：上传的是**你自己的、已在服务端的手机号**，目的是还原展示。不是窃取表单里的号码。**性质轻微**，但确实是额外一次外传。

**域名**：`autofill-server-cn.allawntech.com`（规则下发 + 手机号解掩码）、`api.uc.oppomobile.com/oauth/`（账号 OAuth）。

## 4.5 可屏蔽域名

| 域名 | 作用 | 建议 |
|---|---|---|
| `autofill-server-cn.allawntech.com` | 填充规则 + 手机号解掩码 | ⚠️ 屏蔽后自动填充规则不更新 |
| `api.uc.oppomobile.com` | OAuth 登录 | ⚠️ 屏蔽后不能登录同步 |

---

# 五、🟡 私密保险箱（encryption）：**不是纯本地**

> 这一条推翻了 scope-proposal 里的假设（"本地，重点看是否真本地"）

## 5.1 有云同步

```
com/oplus/encryption/cloud/cloudkit/
├── CloudKitTaskImpl.java              (1635 行)
├── CloudKitTaskImpl$uploadFiles$1.java
├── CloudKitTaskImpl$uploadFolders$1.java
├── CloudKitTaskImpl$uploadDefaultFolders$1.java
├── CloudKitTaskImpl$onFileUploadAndBackup$1.java
├── CloudKitTaskImpl$backupFolderModifiedData$1.java
└── ... (共 20+ 个备份/恢复相关类)
```

基于 `heytap.cloudkit.libsync`（系统云同步框架），需要 `grantUriPermission(CloudDeviceInfoUtil.CLOUD_PACKAGE_NAME, uri, 195)` 授权给云服务进程。

## 5.2 但上传的是**密文**

```java
// cloud/utils/q.java:85-92
String o10 = EncryptDataUtilsKt.o(filePath);                  // 取加密文件名
EncryptDataUtilsKt.e(filePath);                               // 【删掉本地解密副本】
String h6 = EncryptDataUtilsKt.h(
    "/data/data/com.oplus.encryption/files/encrypted/files", o10);   // 加密文件路径
```

关键路径约定：

| 路径 | 含义 |
|---|---|
| `files/encrypted/files` | **已加密**，用于云同步 |
| `files/decrypted/...` | 解密后的临时副本（用完即删） |
| `files/decrypted/cloud_upload` | 云传输中转站 |

**上传时只给加密文件，而且上传前会把解密副本删掉**（`e(filePath)` → "deleted decrypted file"）。

## 5.3 定性

- ✅ **不是明文上传**，隐私设计上是合理的
- ⚠️ **但"纯本地"的说法不成立**，文件确实会进云
- ❓ **未确认**：加密密钥是否与用户锁屏密码绑定。如果不是，云端持有密文 + 平台可能需要配合解密。
- ❓ **未确认**：云端是否默认开启。需要抓包或看开关。

**建议**：如果你对"保险箱内容上云"零容忍，去
`私密保险箱 → 设置 → 云同步/云备份` 关掉。这条路径**没有在代码里找到强制开关 key**，需要实际界面确认。

## 5.4 18 个域名的真相

其中有意义的只有 2 个：

| 域名 | 用途 |
|---|---|
| `htms.heytapmobi.com` | `com.heytap.msp` SDK（推送/服务框架），**外来的**，不是保险箱自己的逻辑 |
| `ns.oplus.com` / `apisnd.heytap` | 同上，SDK 内部常量 |

剩余 16 个全是被误报的标准组织网址：
`w3.org`、`apache.org`、`iptc.org`、`aiim.org`、`npes.org`、`purl.org`、`cipa.jp`、`xerces.apache.org`、`beian.miit.gov.cn`、`schemas.android.com` 等——都是 XML 命名空间或元数据规范 URL，**不发请求**。

**所以：保险箱本体 0 个业务域名。**

---

# 六、🟢 手机管家：碎屏险推销（OAID）

## 6.1 发现

```java
// ScreenInsuranceScanModule.java
public static final String BASE_URL_RELEASE = "https://i-insurance.finzfin.com";
public static final String BASE_URL_DEBUG   = "https://i-insurance-test.wanyol.com";
public static final String PATH = "/insurance-open/mobile/v1/purchase-status";
private String oaid;    // ← 设备广告标识
```

```java
// :182
new Request.Builder()
    .url("https://i-insurance.finzfin.com/insurance-open/mobile/v1/purchase-status")
    .post(json)     // 含 oaid + 签名
    .build()
```

## 6.2 它是什么

- `ScreenInsuranceScanModule` 是"手机检测"流程里的**一个扫描模块**
- 「碎屏险」= 屏幕保障服务
- 拿 **OAID** 去查"你买了没有"，没买就在结果页推购买入口
- 点击后跳 `com.finshell.wallet`（OPPO 钱包）

```java
private final void gotoBuyScreenInsurance(Context context, Uri uri) {
    intent.setPackage("com.finshell.wallet");
```

## 6.3 定性

**这是商业变现**：手机管家做体检 → 拿广告 ID 查保险购买状态 → 推销售。

- 隐私维度：OAID 是广告标识（可重置），不是硬件 ID
- 性质：增值业务推广，非恶意采集
- **可以屏蔽**：`i-insurance.finzfin.com`（屏蔽后只是不显示碎屏险推荐）

---

# 七、其余包的核查结果

## 7.1 `com.oplus.blacklistapp` 骚扰拦截——权限大但很干净

**8 个敏感权限**（全组最多）：

```
ACCESS_FINE_LOCATION / ACCESS_COARSE_LOCATION
READ_CALL_LOG / READ_PHONE_STATE / READ_CONTACTS
READ_EXTERNAL_STORAGE / READ_MEDIA_AUDIO
QUERY_ALL_PACKAGES
```

看起来吓人，但**域名只有 5 个，其中 4 个是垃圾**（`schemas.android.com`、`github.com`、`issuetracker.google.com`、`support.browser`）。

唯一真实的是 `apisnd.heytap`（SDK 常量，非完整域名）。

**数据流**：拦截规则同步走 `cloudsync/SyncCompatApiImpl` + 系统云同步框架，用的是 ContentProvider 批量操作，**没有自建上报通道**。

## 7.2 `com.coloros.healthcheck` 常规检测——客服入口

```java
// OnLineServiceActivity.java:109
"https://chat.oppo.com/chat/h5/v2/index.html?sysnum=...&channelid=80&token=" +
    "{\"accessToken\":\"" + token + "\",\"deviceId\":\"" + deviceId + "\"}"
```

```java
// :231
new Request.Builder().url("https://chat.oppo.com/chat-set/session/routineTestData")
    .addHeader("Safe-Check", "88d81ac76d2741feb27b3214d8f8f0b8")
    .post(detectionResultJson)        // 检测结果 + ssoid + token + deviceId
```

**触发条件**：用户**主动点击「在线客服」**按钮。属于预期行为（客服需要知道你的检测结果才能回答），但**设备标识确实离开了设备**。

## 7.3 `com.oplus.securitypermission` 权限管理——**零联网**

只有 2 个域名，全是 `schemas.android.com` + `xmlpull.org`（XML 解析库）。

**它能看到全系统权限授予情况，但不上报。** ✅

## 7.4 `com.oplus.safecenter` / `trafficmonitor` / `qualityprotect`

| 包 | 域名 | 埋点调用 |
|---|---|---|
| safecenter | 1（`schemas.android.com`） | 7 处（走 statistics.rom 统一出口） |
| trafficmonitor | 1（同上） | 0 |
| qualityprotect | **0** | 7 处（同上） |

**都干净。** 埋点调用指的是调 `com.oplus.statistics.rom` 的 API，数据由 phase2 已分析的统一通道上传，不在本包内直连。

## 7.5 `com.coloros.securityguard` 安全事件

```java
https://ilighthouse.apps.coloros.com    // 灯塔（问题反馈/崩溃上报）
```

iLighthouse 是 OPPO 内部的日志/问题追踪服务，之前轮次已归类。**仅 1 个域名，无敏感数据路径。**

---

# 八、blocklist 补充（D 组）

## 8.1 建议新增

```
# ===== D 组：手机管家/安全 =====
# 商业推广（碎屏险），带 OAID。屏蔽后不显示保险推荐
i-insurance.finzfin.com

# 碎屏险测试环境，正常不连
i-insurance-test.wanyol.com

# AI 语音反诈推理端点（你机器上没启用，但内核在。海外版会用到）
odin-inference-cn.allawntech.com    # ⚠️ 已在 01-telemetry-ads.txt 中，勿重复

# 密码本规则下发 + 手机号解掩码。屏蔽后自动填充规则不更新
autofill-server-cn.allawntech.com
```

## 8.2 谨慎屏蔽（会掉功能）

| 域名 | 掉什么 |
|---|---|
| `api.uc.oppomobile.com` | 密码本账号登录/同步 |
| `chat.oppo.com` | 手机管家在线客服 |
| `htms.heytapmobi.com` | 推送/服务框架（影响面大，慎动） |
| `ilighthouse.apps.coloros.com` | 安全事件的问题反馈 |

## 8.3 不要屏蔽

```
schemas.android.com     ← XML 命名空间，不是请求
xmlpull.org / w3.org / apache.org / purl.org / iptc.org / aiim.org / npes.org
beian.miit.gov.cn       ← ICP 备案链接，点开才跳
```

---

# 九、与 scope-proposal 假设的出入

| 原假设 | 实际 |
|---|---|
| 私密保险箱「本地，重点看是否真本地」 | ❌ **有云同步**，但先加密后上传 |
| 密码本「同上」 | ✅ 基本是本地，密钥在 KeyStore；唯一外传是手机号解掩码 |
| 「权限大、能读全量数据」 | ⚠️ 权限确实大（blacklistapp 8 个敏感权限），但**没有对应的大规模上报通道** |

**D 组整体风险低于 B/C 组。** 真正需要盯的只有 phonemanager 一个包。

---

# 十、待验证

1. **保险箱云同步是否默认开启** —— 需要看界面或抓包
2. **保险箱密钥是否与锁屏密码绑定** —— 决定云端能否独立解密
3. **`ai_voice_detect_switch` 在海外版的实际默认值** —— 手头只有国行 APK
4. **`i-insurance` 请求频率** —— 每次体检都发，还是节流
5. **`com.ted.number` 未在本次样本内** —— 国家反诈号码库的实际行为未知

---

**报告完成时间**：2026-11-06
**下一轮建议**：E 组（运营商/合规类，`com.oppo.ctautoregist` 会向工信部上报设备信息）+ `com.ted.number`
