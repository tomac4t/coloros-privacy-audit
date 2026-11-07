# 第十三轮（合并稿｜已拆分，历史版本）

> ⚠️ **2026-11-06 修订（v2）**：下文第四、六、十节把两件事混在一起了，现已分拆纠正，见文末
> 「十二、修订与触发条件」。**主结论：`aiscan.ocloud` 只在用户主动点「识别文字」时触发；
> 不存在“系统定时批量上传相册图片”的路径。**

- **日期**：2026-11-06
- **对象**：E 组 4 包 + F 组 5 包 + `com.ted.number`，共 10 个包
- **方法**：jadx 反编译（约 7.6 万 Java 文件）+ APK 权限/域名提取 + 关键调用链逐层追踪
- **重点回答**：**相册「文字识别服务」到底在哪、会不会自动上传、和联网开关什么关系**

---

# 第一批｜E 组：运营商 / 合规

## E1. `com.oppo.ctautoregist` —— 入网备案，**明文上报 IMEI**

### 上报目标

```java
// n/c.java:261
JSONObject c2 = j.c("https://zzhc.vnet.cn/", a2.getBytes(StandardCharsets.UTF_8));
```

`zzhc.vnet.cn` = **中国电信「终端自助核验/入网备案」服务**。这是工信部要求的入网登记流程。

### 上报字段（明文）

`o/a.java` 里逐个 put，完整清单：

| 字段 | 含义 |
|---|---|
| `IMEI1` / `IMEI2` | **双卡 IMEI** |
| `MEID` | CDMA 设备标识 |
| `SIM1LTEIMSI` / `SIM2LTEIMSI` | **IMSI（用户身份）** |
| `SIM1CDMAIMSI` / `SIM2CDMAIMSI` | CDMA IMSI |
| `SIM1ICCID` / `SIM2ICCID` | **SIM 卡序列号** |
| `MACID` | MAC 地址 |
| `MODEL` / `SWVER` / `OSVER` / `ROM` / `RAM` | 机型/版本/硬件 |
| `SIM1CELLID` / `SIM2CELLID` | **基站小区 ID（≈粗略位置）** |
| `SIM1VoLTESW` / `5GSW1` / `5GSW2` | 网络能力开关 |
| `REGDATE` / `ACCESSTYPE` / `NWTYPE1` / `NWTYPE2` | 注册时间/接入方式 |

### ⚠️ 关于"是否加密"的澄清

代码里能看到的 `n.e(...)` **不是加密，只是打码**：

```java
// p/n.java:30
public static String e(String str) {
    if (length > 7) {
        sb.append(str.substring(0, 3));
        sb.append("****");              // ← 只是把日志里的号码打码
        ...
}
```

而且最终返回的是 `jSONObject2`（**明文版**）：

```java
this.f244v = jSONObject2.toString();   // 明文
str = "CTAutoRegist_DeviceInfo";
n.d(str, "device info : " + jSONObject.toString());   // 打码版只进日志
return this.f244v;                     // ← 明文发出去
```

**结论：IMEI/IMSI/ICCID/MAC 以明文 JSON POST 到 `zzhc.vnet.cn`，仅靠 HTTPS 保护。**

### 触发条件

```java
// n/c.java
// 5G 开关变化、VoLTE 开关变化、换卡、开机时触发
private boolean i() {   // needRegisterForVoLTEChange
    if ((v2 == 1 || v3 == 1) && isWifiConnected) return true;
    ...
}
```

不是静默高频上报，是**换卡/开关变化/开机**时触发。

### 定性

- ✅ **工信部合规要求**，不是厂商私自采集
- ⚠️ 但**字段粒度很细**（IMEI+IMSI+ICCID+MAC+基站 ID 一次性打包）
- ⚠️ 明文传输，只有 TLS 保护
- ❌ **无用户开关**，这是法定义务，关不掉

**唯一可能的防护**：DNS/防火墙拦 `zzhc.vnet.cn`。但会影响入网备案（可能导致某些运营商服务异常）。

---

## E2. `com.coloros.bootreg` 开机注册 —— 干净

6 个域名，5 个是垃圾（`exoplayer.dev`/`dashif.org`/`schemas.microsoft.com`/`aomedia.org`/`developer.apple.com`）。

唯一真实的是 `fast-wallet.finzfin.com`，但那是**协议链接**：

```java
// OplusPayPage.java:95
k(spannableStringBuilder, string, "https://fast-wallet.finzfin.com/file/wallet/20200930/....html");
```

只是 TextView 里的超链接，**用户点击才跳**，不上报。

---

## E3. `com.oplus.customize.coreapp` —— **零域名**

0 个业务域名，1 个 `schemas.android.com`。干净。

---

## E4. `com.cmccslice.proxyapp`（移动切片代理）—— **零域名**

0 个业务域名，只有 2 个权限。干净。

---

## E5. `com.ted.number`（智能识别陌生号码）—— 关键：它不联网

### 它是什么

`BuildConfig` 暴露了定位：

```java
public static final String CRYPTO_HOST = "tel-num-cn.heytapmobi.com";
public static final String FLAVOR_region = "domestic";
public static final String VERSION_NAME = "15.30.10";
```

### 但它自己不联网

全包扫描：**没有任何 OkHttp/HttpURLConnection/网络调用代码**。两个域名只是 BuildConfig 常量。

它对外提供的是 **AIDL 服务**：

```java
// service/INumberService.java
RecognitionNumber queryNumberInfo(RequestData requestData);
String getNumberLocation(String number);
```

**它是被调用方，不是主动上报方。**

### 谁在用它

`blacklistapp`（骚扰拦截）：

```java
// dg/a.java:110
Intent intent = new Intent("com.ted.number.service");
intent.setPackage("com.ted.number");
```

### 「国家反诈中心拦截服务」开关在哪

```java
// z9/v.java:33 —— RecognitionEnableConfirmDialogHelper
intent.setComponent(new ComponentName(aa.c.f172c,
    "com.ted.number.ui.TedUpdateSettingActivity"));
intent.putExtra("highlight_update_stranger_switch", true);
```

**`com.ted.number.ui.TedUpdateSettingActivity`** = 你猜的那个「国家反诈中心拦截服务」设置页。

### 定性

- ✅ 号码库比对，**不接触通话内容**
- ✅ 组件本身不联网（联网在别处，可能是系统服务代理）
- ⚠️ `tel-num-cn.heytapmobi.com` 名字叫 crypto host，用途待确认（可能是号码库加密下发）

**待验证**：真正的号码库下载是在 `com.ted.number` 还是别的包。本包内没有网络代码。

---

# 第二批｜F 组：相机 / 相册

## F0. 总览

| 包 | 大小 | Java 文件 | 敏感权限 | 业务域名 |
|---|---|---|---|---|
| `com.coloros.gallery3d` 相册 | 189 MB | 46,484 | **10** | **48** |
| `com.oneplus.camera` 相机 | 141 MB | 5,414 | 10 | **0** |
| `com.oneplus.camera.pictureprocessing` | 13 MB | 2,731 | 1 | **0** |
| `com.oneplus.camera.service` | — | 9 | 0 | 0 |

### 相机：**零业务域名**

```
37x  ns.adobe.com      ← XMP 元数据命名空间
 6x  aiim.org
 3x  w3.org / schemas.android.com
 2x  purl.org
 1x  npes.org
```

**全是 XMP/EXIF 元数据的 XML 命名空间**，没有任何网络上报。

相机的定位/麦克风权限都用于**拍照本身**（地理位置写入 EXIF、录像）。

---

# 🔴 核心问题：相册「文字识别服务」

> **Tom 的问题**：
> 1. 隐私政策说"文字识别服务已联网…将图片上传至云端"，但我从没找到这个服务的地方
> 2. 是相册自带的吗？
> 3. 我因为查看定位打开了"相册-设置-联网权限"，文字识别就会自动联网？

## 一、隐私政策原文（你的版本，我找到了）

从相册资源里提取，一字不差：

```xml
<!-- res/values/strings.xml -->
<string name="settings_privacy_statement_1_3_2_3_gallery02">
当您使用文本搜索或超级文本的识别文字功能时，本应用需要使用系统提供的文字识别服务
来识别图片中的文字，以实现相应的功能。若您的设备的文字识别服务已联网，
为提高文字识别的准确度，我们可能需要收集您的/您可能需要向我们提供需要进行处理的图片，
并将图片上传至云端进行文字识别处理。若您的设备的文字识别服务未联网，
相册将在本地完成对图片的处理。在系统文字识别服务联网的情况下，
您使用识别文字功能时图片将被上传至云端，
当云端服务器完成图片文字识别处理后，上传的图片会被立刻销毁，
我们不会在云端存储您的图片等任何个人信息。
</string>
```

**关键措辞：「系统提供的文字识别服务」** —— 不是相册自己的能力。

## 二、这个服务到底是什么

### 它是独立系统组件，不是相册功能

```java
// AppStatusOwner.java
public static final String APP_ID_AIUNIT    = "com.oplus.aiunit";
public static final String APP_ID_OCRSERVICE = "com.coloros.ocrservice";   // ← 就是它
```

相册通过 **AIDL 绑定**到系统 OCR 服务：

```java
// com/oplus/ocrclient/OcrClient.java
IOcrService f17561a;      // AIDL 代理
IOcrEngine  b;
```

**所以答案 ②：不是相册自带的，是系统级服务 `com.coloros.ocrservice`（由 `com.oplus.aiunit` 提供 SDK）。**
相册只是"调用方"。这就是你在相册设置里找不到"文字识别"开关的原因 —— **它的开关不在相册里**。

### 真正的云端端点（Base64 混淆）

```java
// OcrServiceRequestHelper.java:47
private static final String ONLINE_OCR_URL_BASE64 =
    "aHR0cHM6Ly9haXNjYW4ub2Nsb3VkLmhleXRhcG1vYmkuY29tL3NjZW5lb2NyL3NjYW4td2ViL3YxL29jcl9yZWNvZ25pemU";
```

解码后：

```
https://aiscan.ocloud.heytapmobi.com/sceneocr/scan-web/v1/ocr_recognize
```

### 另外还有一个「定时识别」通道

```java
// OcrScheduleClient.java:446
https://airecognition-ocr-cn.heytapmobi.com/ai_screen_recognition/api/v1/upload
```

这个对应隐私政策里的**「定期识别图片中的文字」**（文本搜索索引）。

---

## 三、上传了什么

### 通道 A：`ocr_recognize`（点击识别）

```java
// OcrServiceRequestHelper.java:168
bitmap.compress(Bitmap.CompressFormat.JPEG, 100, byteArrayOutputStream);   // JPEG 质量 100
RequestBody.create(MediaType.parse("application/octet-stream"), bArr)
```

请求头：

```java
OCLOUD-IMEI  ← 设备标识
OCLOUD-GUID  ← UUID
OCLOUD-APPID ← "com.oplus.aiunit-<包名>"
OCLOUD-LANG  ← 语言
OCLOUD-CRC32 / OCLOUD-TIMESTAMP / OCLOUD-ENCRYPTKEY
```

**图片以 JPEG 100 质量上传（几乎无损），伴随 IMEI。**

### 通道 B：`ai_screen_recognition/upload`（定时索引）

```java
// OcrScheduleClient.java:522-538
oCRCloudParams.getFile().compress(Bitmap.CompressFormat.JPEG, 100, byteArrayOutputStream);
new MultipartBody.Builder()
    .addFormDataPart("phone_model", ...)        // ← 机型
    .addFormDataPart("source_language", ...)
    .addFormDataPart("image.jpg", RequestBody.create(image/jpeg, encryptFile))
```

字段：`phone_model` + `source_language` + `image.jpg`（同样 JPEG 100）。

---

## 四、🔴 最关键：**什么时候上传？**

### 判定代码（三处，逐层展开）

#### 第 1 层：超级文本入口 —— `z = true`

```java
// SuperTextOcrAbility.java:77（相册的「识别文字」功能）
superTextStatic.a(new fs2(bitmap), callback, true, null);
//                                              ↑ z = true
```

#### 第 2 层：透传到 OcrServiceApi

```java
// SuperTextStatic.java:316
OcrCompatResult process = ((OcrServiceApi) b0gVar.b.getValue()).process(bitmap2, 0, z2);
//                                                                              ↑ true
```

#### 第 3 层：决定用哪个引擎

```java
// OcrClient.java:327
public final void f(int i, Bitmap bitmap, boolean z) {
    b(new com.oplus.ocrclient.b(this, bitmap, z, z, i));
    //                                      ↑ z2  ↑ z
}

// ocrclient/b.java:39-50
boolean z = this.b;
if (z || this.c) {                       // true || true → 成立
    iOcrEngine.ocrWithPriority(bitmap2, i, z, ...);   // ← 走优先（云端）
} else {
    iOcrEngine.ocr(bitmap3, i2, z, ...);              // ← 走普通（纯本地）
}
```

#### 第 4 层：`ocrWithPriority` → `onlineEnable = true`

```java
// OcrEngine.java:421
public void ocrWithPriority(Bitmap bitmap, int i10, boolean z10, IOcrObserver o) {
    ocr(bitmap, i10, z10, true, 1, o);
    //                    ↑ z11 = onlineEnable = true
}

// :322 普通 ocr
public void ocr(Bitmap bitmap, int i10, boolean z10, IOcrObserver o) {
    ocr(bitmap, i10, z10, false, 0, o);   // ↑ false = 纯本地
}
```

#### 第 5 层：最终联网判断

```java
// OcrEngine.java:611
Future submit = (mOcrServiceRequestHelper != null
              && z10                          // canCloud
              && this.d                       // onlineEnable ← 这里为 true
              && AppStatusOwner.canAccessInternet()
              && Utils.isUserSetupComplete(...)
              && NetworkUtil.isNetworkAvailable(...))
    ? submit(云端OCR) : null;

// ↓ 注意：本地 OCR 是无条件并行的，不是 else 分支
Future submit2 = submit(本地OCR);
```

### **结论：相册「超级文本 / 识别文字」默认就走云端**

`z = true` 是**硬编码在 `SuperTextOcrAbility` 里的**，不看任何设置。

---

## 五、🔴 回答你的第三个问题：联网权限开关

### 你的猜测**部分正确，但方向反了**

你说："如果我为查看定位打开了相册-设置-联网权限，那文字识别服务就会自动联网？"

**答案：不是"打开联网权限才上传"，而是——国行机器上传被硬编码为允许。**

```java
// AppStatusOwner.java:104
public static final boolean canAccessInternet() {
    return isDomestic() || !SwitchCompat.isNeedApplyPrivacy(...);
    //     ↑ 国行直接 true，短路，右边根本不执行
}

public static final boolean isDomestic() {
    return Intrinsics.areEqual(region, "domestic");
}
```

**`isDomestic()` 为真 → 直接 `return true`。**

也就是说：
- **国行机器**：`canAccessInternet()` 恒为 `true`，**联网开关不影响云端 OCR**
- **海外机器**：才会看 `isNeedApplyPrivacy()`（隐私同意状态）

### 那"相册-设置-联网权限"到底是什么

它是**按功能逐个弹出的授权**，不是全局开关。资源里每个联网功能都有独立文案：

```xml
<string name="authorizing_cloud_sync_statement">
为提供相册自动同步功能，本应用需要联网并收集、使用您的照片和视频…</string>
<string name="authorizing_gallery_map_statement">
为提供地图相册功能，本应用需要联网并使用百度定位 SDK…</string>
<string name="authorizing_enhance_text_statement">
为提供超级文本功能，本应用需要联网并获取您选择的图片，并上传至服务器进行处理…</string>
```

**注意最后一条 `authorizing_enhance_text_statement`**：超级文本**确实有**联网授权弹窗。

但它只控制 `OcrCloudClient`（超级文本自己的云增强），**不控制系统 OCR 服务那条路**。

### 完整判定（`isNeedApplyPrivacy`）

```java
// SwitchCompat.java:125
public static final boolean isNeedApplyPrivacy(Context context) {
    if (AppStatusOwner.isDomestic()) {
        if (AppStatusOwner.isOcrApp()) {        // appId == "com.coloros.ocrservice" ?
            if (isS()) {
                if (!isWlanAutoDownloadEnable(...) || !isUserPrivacyAgreed(...)) return true;
            } else if (!isUserPrivacyAgreed(...)) return true;
        } else if (isUserCloseDownloadInBootSetup() || !isUserPrivacyAgreed(true)) {
            return true;
        }
    } else if (!isUserPrivacyAgreed(false)) {
        return true;
    }
    return false;
}
```

但 **`canAccessInternet()` 在第一层就用 `isDomestic()` 短路了**，这个函数根本不会被调用（国行）。

---

## 六、🔴 定时识别：这才是"自动"的部分

### 默认就上传

```java
// OcrTimeConfig.java
private static final long DEFAULT_CLOUD_TIME_OUT = 7;
private long cloudResultTimeOut = DEFAULT_CLOUD_TIME_OUT;   // ← 默认 7 秒

// OcrScheduleCallback.java
public static OcrTimeConfig getOcrTimeConfig(OcrScheduleCallback cb) {
    return new OcrTimeConfig();        // ← 默认实例，cloudResultTimeOut = 7
}
```

### 判定

```java
// OcrScheduleClient.java:864
if (callback.getOcrTimeConfig().getCloudResultTimeOut() > 0) {   // 7 > 0 → 成立
    上传云端（并行发起）；
    waitOcrFinish(7);                // 等 7 秒
    if (hasCloudData()) return;      // 拿到云端结果就用
}
handleLocal(...);                     // 否则本地兜底
```

**⚠️ 关键：上传在 `if` 里面就先发生了，不是"云端失败才本地"，而是"先传上去，等 7 秒，没结果再用本地"。**

### appId

```java
// SuperTextStatic.java:216
new OcrScheduleClient(context, "ocr_ar");     // ← 相册/超级文本
```

---

## 七、代码行为 vs 隐私政策：符合吗？

| 政策表述 | 代码实际 | 是否相符 |
|---|---|---|
| "使用**系统提供的**文字识别服务" | `com.coloros.ocrservice` AIDL 绑定 | ✅ **相符** |
| "若文字识别服务**已联网**，将图片上传至云端" | `canAccessInternet()` 国行恒 true | ⚠️ **相符但等于"总是联网"** |
| "若**未联网**，相册在本地处理" | `onlineEnable=false` 时纯本地 | ✅ 存在该分支，但正常流程不走 |
| "图片会被**立刻销毁**，不在云端存储" | 无法从静态代码验证 | ❓ **待验证** |
| "定期识别图片中的文字" | `OcrScheduleClient` 默认 7 秒超时即上传 | ✅ 相符 |
| 用户可关闭 | **未找到相册内开关** | ❌ **不相符（可及性差）** |

### 核心矛盾

**政策说"若已联网"是条件句，给人"联网是可选项"的印象。**
**代码里国行机器恒为已联网，没有对应的关闭入口。**

---

## 八、相册其他联网点（48 个域名拆解）

| 域名 | 用途 | 备注 |
|---|---|---|
`api.map.baidu.com` / `map.baidu.com` / `daohang.map.baidu.com` | 地图相册 | 已在你 blocklist |
`cloud.heytap.com` / `cloud.oppo.com` / `cloudkit-api-cn.heytapmobi.com` | **云同步** | 相册备份 |
`i-cn01a.ocloud.heytapmobi.com` / `share-cn01a.ocloud.heytapmobi.com` | 共享相册 | |
`httpdns.ocloud.heytapmobi.com` / `ocloud-httpdns-cn.heytapmobi.com` | HTTPDNS | 已在 04 |
`airecognition-ocr-cn.heytapmobi.com` | **云端 OCR（定时）** | 🔴 **新发现** |
`aitool-cuiocr-cn.heytapmobi.com` / `aitool-curocr-cn.wanyol.com` | OCR 工具 | 🔴 **新发现** |
`aip-gw-cn.allawntech.com` | AI 网关 | |
`fourier-videoclip-cn` / `rl-videoclip-cn` / `videoclip-*` | 视频剪辑 | 已在 01 |
`album-idcard.heytapmobi.com` | **身份证识别** | 🔴 **新发现** |
`ai-repair.ocloud.heytapmobi.com` | AI 修复 | |
`muc.heytap.com` | 账号/隐私政策 | |
`rest-cn-feedback` / `static-cn-feedback` | 反馈 | |
`fnos.net` | ?（3 次） | 待查 |
`open.weixin.qq.com` / `long.open.weixin.qq.com` | 微信分享 | |

---

# 九、需要补进 blocklist 的

```
# ===== F 组：相册 OCR 云端（核心发现）=====
# 系统 OCR 服务上传图片（JPEG 100）做文字识别
aiscan.ocloud.heytapmobi.com
airecognition-ocr-cn.heytapmobi.com
aitool-cuiocr-cn.heytapmobi.com
aitool-curocr-cn.wanyol.com
# 身份证识别（敏感证件）
album-idcard.heytapmobi.com

# ===== E 组 =====
# 入网备案，明文上报 IMEI/IMSI/ICCID/MAC
zzhc.vnet.cn
# 号码库 crypto host
tel-num-cn.heytapmobi.com
```

## ⚠️ 屏蔽后的影响

| 域名 | 屏蔽后果 |
|---|---|
`aiscan.ocloud.*` | 超级文本/识别文字**降级为本地**（质量下降但不失败） |
`airecognition-ocr-cn` | 文本搜索索引改本地，**搜索准确率下降** |
`album-idcard` | 身份证识别功能不可用 |
`zzhc.vnet.cn` | 可能影响入网备案（**建议谨慎**） |
`tel-num-cn` | 陌生号码识别/归属地可能失效 |

**推荐做法**：先只拦 `aiscan.ocloud.heytapmobi.com` + `airecognition-ocr-cn.heytapmobi.com`，
试几天看超级文本和文本搜索是否正常。这两个是"上传原图"的主力。

---

# 十、给你的直接答复（三条）

### Q1：相册的文字识别服务在哪？我从没找到

**它在系统里，不在相册里。** 包名 `com.coloros.ocrservice`，
由 `com.oplus.aiunit` 提供 SDK，相册通过 AIDL 调用。

**找它的方法**：
```bash
adb shell pm list packages | grep -i ocr
adb shell dumpsys package com.coloros.ocrservice | head -50
```

### Q2：是相册自带的吗？

**不是。** 相册只是调用方。所以相册设置里找不到开关是正常的——开关不在相册。

### Q3：打开联网权限后，文字识别会自动联网吗？

**不是"打开才联网"，而是国行机器本来就总是联网。**

```java
canAccessInternet() = isDomestic() || ...
// 国行 → 直接 true，短路
```

**联网授权弹窗（`authorizing_*_statement`）只对你主动点的那一个功能生效**，
不控制系统 OCR 服务那条路。

**你真正能做的三件事**：

1. **DNS 拦** `aiscan.ocloud.heytapmobi.com` → 点击识别降级本地
2. **DNS 拦** `airecognition-ocr-cn.heytapmobi.com` → 定时索引降级本地
3. **关"文本搜索"功能**（相册设置 → 搜索/智能分类），能减少定时扫描

---

# 十一、待验证

1. **`ocr_recognize` 是否真的"处理完即销毁"** —— 需要抓包看服务端响应，或查隐私政策更新
2. **`tel-num-cn.heytapmobi.com` 的真实用途** —— 名字叫 CRYPTO_HOST，但包内无网络代码
3. **`fnos.net`（3 次命中）** —— 疑似飞牛 NAS，需要确认是否是相册的第三方分享
4. **`canAccessInternet()` 在海外版的实际行为** —— 手头只有国行 APK
5. **相册"设置-联网权限"的实际 UI 位置** —— 需要真机截图确认它控制哪些功能
6. **关闭文本搜索后，`OcrScheduleClient` 是否真的停止** —— 需要动态验证
7. **关闭相册的「文本识别/智能分类」开关后，OCR_SCAN 是否真的不启动** —— `authorize_text_ocr_service`
   返回 false 时会跳过该扫描器，**这条静态链是成立的**（已复核），但仍建议真机验证

---

**报告完成时间**：2026-11-06
**样本**：`/tmp/app_backup/`（345 APK）
**反编译输出**：`/tmp/jadx-out/{gallery3d,camera,tednumber,ctautoregist,bootreg,custcore,cmccslice,pictureprocessing,cameraservice}`

---

# 十二、修订与触发条件（2026-11-06 v2）

> 起因：Tom 说 AdGuard Home 日志里（含近 24h）从没见过这两个域名的请求。
> 复核后确认：**原文把两个域名当成了同等性质的“定时上传”，这是错的。**

## 12.1 复核结论

| 域名 | 真实触发条件 | 是否后台自动 |
|---|---|---|
| `aiscan.ocloud.heytapmobi.com` | 用户**主动**使用「识别文字 / 超级文本 / 扫一扫取字」 | ❌ **不自动** |
| `airecognition-ocr-cn.heytapmobi.com` | 用户**主动**识别文字且**等待 7 秒超时**后才发 | ❌ **不自动** |
| 相册后台 OCR 扫描（`b2g` / `OCR_SCAN`） | 相册后台扫描 | ⚠️ 只做**本地** OCR，仅产出文本索引 |

### 关键代码再确认

**① `aiscan` 上传链（来源 `com.oplus.aiunit`，非相册本体）**

```
SuperTextOcrAbility（用户点「识别文字」）
  → SuperTextStatic.a(bitmap, cb, z=true)
    → OcrServiceApi.process(bitmap, 0, true)
      → OcrClient.f(...) → ocrclient/b.java: if (z || z2) → iOcrEngine.ocrWithPriority(...)
        → OcrEngine.ocrWithPriority() → ocr(bitmap, i, z, onlineEnable=true, ...)
          → 条件：canCloud && onlineEnable && AppStatusOwner.canAccessInternet() && 联网
            → mProcessExecutor.submit(云端请求)  // aiscan.ocloud.../ocr_recognize
```

这条链的**唯一入口是用户点击**。没有定时器、没有 JobScheduler、没有相册后台扫描调用它。

**② `OcrScheduleClient`（`airecognition-ocr-cn`）**

```java
// OcrScheduleClient.process(): 用户主动识别时被调用
if (callback.getOcrTimeConfig().getCloudResultTimeOut() > 0) {   // 默认 7
    发起云端上传（airecognition-ocr-cn/.../upload）;
    waitOcrFinish(7);          // 等 7 秒
}
handleLocal(...)               // 本地兜底
```

而且：
- 全包里 `new OcrScheduleClient(...)` **只有一处**：`SuperTextStatic.h`（相册超级文本）
- 它**不是**文本搜索索引的定时器，次类扫描走的是 `OcrScanner`（`b2g`），**纯本地**
- 所以“定时扫描相册并上传”这个说法**不成立**，之前读错了

**③ 后台 OCR 扫描 `b2g`（相册 `GalleryScanSyncTaskManager`）**

```java
// createScanners
if ((i3 & 32) == 32 && checkOCRScanAuthorizedIfNeed()) {
    arrayList.add(new b2g(this.mContext));   // OCR_SCAN
}
```

`b2g` 做的是**本地 OCR → 文本索引**（图片按像素在本地处理），**没有 aiscan / airecognition 域名**。
所以就算它跑，AdGuard 也**看不到任何请求** —— 与 Tom 的观察一致。

### 为什么日志里看不到

1. **国行机器上这两个域名本来就低概率出现** —— 只有 Tom 手动点“识别文字”才会触发
2. AdGuard Home 只记录 **DNS 查询**。如果：
   - 系统走 **HTTPDNS**（`httpdns.ocloud.heytapmobi.com`，已在报告 04 里列过）→ 域名查询在云端完成，
     AdGuard 上看不到独立的 `aiscan.*` 查询，只会看到 IP 直连
   - 或者结果被系统 DNS 缓存（TTL 内不再查）
   → **客户端行为已发生，但 AdGuard 无日志**
3. 二者任一就足以解释“24h 内搜不到”

**验证建议**：
- 真机开「相册 → 点一张图 → 识别文字」，然后 `adb shell dumpsys netstats` 或 AdGuard 实时日志
  过滤 `heytapmobi`，看是否出现
- 或者用 `adb shell settings get global http_proxy` + charles/mitm 抓（注意 SSL pinning）

## 12.2 到底是哪个 App 在上传？

| 角色 | 包名 | 职责 |
|---|---|---|
| **上传代码所在** | `com.oplus.aiunit`（AIGC 引擎包） | 持有 `OcrServiceRequestHelper` / `OcrScheduleClient`，真正发 HTTP |
| **OCR 服务进程** | `com.coloros.ocrservice` | AIDL 服务端，海关「是否允许云端的」判断（`canAccessInternet()`） |
| **调用方** | `com.coloros.gallery3d`（相册） | 只负责把 bitmap 递过去 |

⚠️ **注意**：`com.oplus.aiunit` 不是普通用户 App，它是系统级 AIGC 服务（设置里叫「AI 服务」），
**卸载/禁网会影响：小布助手、AI 修图、识屏、扫一扫、超级文本、AI 摘要等一大片功能。**

## 12.3 能不能靠“禁用某个 App 的联网权限”解决？

**❌ 不能，这条路在国行机器上不成立。** 三个原因：

**① 国行的联网开关不拦它**

```java
// AppStatusOwner.java
public static final boolean canAccessInternet() {
    return isDomestic() || !SwitchCompat.isNeedApplyPrivacy(...);
    //     ↑ 国行直接 true，短路，右侧永不执行
}
```

相册的“联网权限”开关管的是相册自己的云同步/地图相册，**不控 `com.oplus.aiunit` 的云端 OCR**。

**② 就算禁了相册的权限，aiunit 仍可自行联网**（它是独立进程/独立包）

**③ 系统组件不能像普通 App 一样“禁网”**（除非用 pm disable-user 断开整个组件，代价太大）

## 12.4 真正有效的做法

| 方案 | 有效 | 代价 | 推荐 |
|---|---|---|---|
| DNS 拦 `aiscan.ocloud.heytapmobi.com` | ✅ 点识别降级本地 | 识别质量下降 | ⭐ 首选 |
| DNS 拦 `airecognition-ocr-cn.heytapmobi.com` | ✅ 索引降级本地 | 影响很小 | ⭐ 首选 |
| 相册设置里关掉与 OCR 相关的授权（`authorize_text_ocr_service`） | ✅ 后台 OCR 扫描不启动 | 文本搜索能力下降 | ⭐ 推荐 |
| 关掉相册「文本搜索 / 智能分类」 | ✅ 减少后台本地扫描 | 无云端影响 | ⭐ 推荐 |
| pm disable 相册或 aiunit | ⚠️ 能断但副作用巨大 | 相册/AI 功能大面积失效 | ❌ 不推荐 |
| 断 `com.oplus.aiunit` 联网权限 | ⚠️ 部分 ROM 支持“后台联网限制” | AI 全线异常 | ❌ 不推荐 |

**一句话**：要的就是“**拦域名 + 关功能开关**”，而不是“关 App 联网权限”。

## 12.5 报告需修正的表述

原文第四节“结论：相册「超级文本 / 识别文字」默认就走云端” → 应改为
**「用户主动点识别时走云端」**；
原文第六节“定时扫描并上传” → 应改为 **「用户识别后、云端 7 秒超时」**；
原文“核心矛盾”中“政策说条件句”的指责成立，但措辞应弱化为
**「默认云端优先，找不到用户可见开关」**，而不是暗示后台持续上传。

---

**修订时间**：2026-11-06
