# 第十三轮（F 组）：相机 / 相册

- **日期**：2026-11-06（**v3 整理版**）
- **样本**：`/tmp/app_backup/`（345 APK）
- **反编译输出**：`/tmp/jadx-out/{gallery3d,camera,pictureprocessing,cameraservice,ocrscanner,aiunit}`
- **E 组（运营商/合规）**：见 `report-phase13-e-group-carrier-compliance.md`

> **v3 说明**：v1 的若干结论已被推翻，但旧文保留在原稿里造成前后冲突。
> 本版**重写为一套自洽结论**，所有旧结论的修正过程统一记录在附录 A。
>
> **一句话总结**：
> 相册的云端文字识别**只在用户主动触发时发生**，没有后台批量上传；
> 长按选字走**本地模型**；用户有三层可用的关闭手段；真要兜底就靠 DNS 拦 2 个域名。

---

# 一、结论速览

| # | 结论 | 证据等级 |
|---|---|---|
| 1 | 相机（`com.oneplus.camera` 等 3 包）**零业务域名**，不联网 | ✅ 静态确认 |
| 2 | 相册后台扫描（OCR_SCAN）只做**本地** OCR，不产生任何网络请求 | ✅ 静态确认 |
| 3 | 云端文字识别共 **2 个域名**，都只在**用户主动动作**后触发 | ✅ 静态确认 |
| 4 | 长按拖拽框选文字 = **本地 `ocr_ar` 模型**，不联网 | ✅ 静态确认（待真机复验） |
| 5 | 国行机器 `canAccessInternet()` 恒 true，**系统 OCR 服务的开关不在相册里** | ✅ 静态确认 |
| 6 | 用户有 **3 层**退出选择（联网总闸 / 单功能授权 / 撤回全部） | ✅ 静态确认 |
| 7 | 最干净的方案 = **DNS 拦 2 个域名** | — 建议 |
| 8 | **`album-idcard` 是「AI 证件照」功能，不是“身份证识别”**；三道确认弹窗，且只传回人像抠图不上传证件原件 | ✅ 静态确认（见第三章 3.4） |

## 1.1 日常误触风险排序（Tom 最可能撞上的入口）

| 排序 | 入口 | 上云 | 误触难度 |
|---|---|---|---|
| 🥇 | **④ 扫一扫 / 取字** | ✅ 必定上云 | ⭐⭐⭐ 极易（顺手一扫） |
| 🥈 | **① 照片页长按选字** | ❌ **本地** | ⭐⭐⭐ 极易，但**不联网**，无需担心 |
| 🥉 | ② 照片页「识别文字」按钮 | ⚠️ 本地优先 | ⭐⭐ 中等 |
| 4 | ③ 照片页「超级文本编辑」→ 增强文本 → 识别文字 | ✅ 上云 | ⭐⭐ 中等（照片页菜单第一层） |
| 5 | ⑥ 编辑 → AI 证件照 | ✅ 上云（三道弹窗） | ⭐ 很难，且仅传回抠像结果 |

> **真正需要防的是 ③ 和 ④**。③ 在照片页菜单里找得到，一不小心就点了；
> ① 虽然极易触发但是本地；⑥ 藏得深且有弹窗。

---

# 二、相机：干净

| 包 | 大小 | Java 文件 | 敏感权限 | 业务域名 |
|---|---|---|---|---|
| `com.oneplus.camera` | 141 MB | 5,414 | 10 | **0** |
| `com.oneplus.camera.pictureprocessing` | 13 MB | 2,731 | 1 | **0** |
| `com.oneplus.camera.service` | — | 9 | 0 | 0 |

包内域名全是 XML 命名空间，没有任何网络上报：

```
37x  ns.adobe.com      ← XMP 元数据
 6x  aiim.org
 3x  w3.org / schemas.android.com
 2x  purl.org
 1x  npes.org
```

定位/麦克风权限用于拍照本身（GPS 写 EXIF、录像）。**相机不作为联网风险点。**

---

# 三、相册的 6 个识别入口：性质各不相同

> 这一节是全报告的核心。v1 最大的错误就是把这几个入口混为一谈。
> ①～⑤ 是文字识别（OCR），⑥ 是人像抠图（AI 证件照），性质完全不同。

## 3.1 入口对照（最终版）

| 入口 | 用户动作 | 代码路径 | 引擎 | 联网 | 上传内容 |
|---|---|---|---|---|---|
| **① 照片页长按选字**（拖拽框选 → 复制） | 长按图片上的文字 | `PhotoSuperTextSection` → `SuperTextAbility.g()` → `SuperTextStatic(OCR_AUTO)` → `qrq.a()==true` → **AIUnit 本地** | 本地 `ocr_ar` | ❌ **否** | — |
| **② 照片页「识别文字」按钮** | 点按钮 | `SuperTextOcrAbility.a()` → `SuperTextStatic.a(z=true)` → 本地优先；`qrq.a()==false` 才退云端 | 本地优先 | ⚠️ 视 `ocr_ar` 状态 | 退云端时：JPEG100 + IMEI |
| **③ 照片页「超级文本编辑」→ 增强文本 → 识别文字** | 照片页菜单「超级文本编辑」 | `action_enhancetext` → `PhotoEditorType.ENHANCE_TEXT` → `"EnhanceText"` → `oq7`（`EditorEnhanceTextState`）→ `SuperTextOcrAbility.a(b, b, cb)` | **云端优先**（硬编码） | ✅ **是** | JPEG100 + IMEI |
| **④ 扫一扫 / 取字**（`com.oplus.scanner`） | 相机取景框扫描 | `SuperTextActivity` → `OcrCompatClient.L(…, isCompat=true)` → `ocrWithPriority` | **云端优先** | ✅ **是** | 图 + 请求头 |
| **⑤ 文本搜索索引**（后台） | 系统自动 | `GalleryScanSyncTaskManager` → `b2g`（OCR_SCAN） | **本地** | ❌ **否** | — |
| **⑥ 编辑器「AI 证件照」** | 编辑 → AI 证件照 | `AiIdPhotoManager` → `CloudPortraitGenerator` → `/v2/idcard/getToken` + `/idCardAnalysis` | **云端**（唯一选择） | ✅ **是** | **人像抠像结果**，见 3.4 |

**关键：只有 ③④⑥ 一定会发 DNS 查询；② 视本地模型状态；①⑤ 完全本机。**

## 3.2 为什么 ③ 是"云端优先"（硬编码）

> **③ 在哪？** 两个入口都能进：
> - 照片页 → 底部/更多菜单 →「**超级文本编辑**」（`action_enhancetext`）
> - 相册 → 选图 →「编辑」→ 底部「**增强文本**」
>
> 进去后底部有四个按钮：校正 / **识别文字** / 增强 / 转文档。
> 点「识别文字」识别完成后跳到纯文本页 `OcrResultActivity`（可校正、复制、转 Word/Excel/PPT）。
> 这条路的 `SuperTextStatic.a(..., z=true)` 中 `z` **硬编码为 true**，所以每次都云端优先。

```java
// SuperTextOcrAbility.java：z 硬编码 true
superTextStatic.a(new fs2(bitmap), callback, /* z = */ true, null);

// SuperTextStatic.java：透传
((OcrServiceApi) b0gVar.b.getValue()).process(bitmap2, 0, z2);

// OcrServiceApi.java：process() 默认 isFastScan = true
if ((i2 & 4) != 0) { z = true; }
getOcrClient().f(i, bitmap, /* z = */ z);

// OcrClient.java → ocrclient/b.java
if (z || z2) iOcrEngine.ocrWithPriority(...)   // ← 云端优先
else         iOcrEngine.ocr(...)               // ← 纯本地

// OcrEngine.java：ocrWithPriority → onlineEnable = true
public void ocrWithPriority(...) { ocr(bitmap, i10, z10, /* onlineEnable = */ true, 1, o); }

// OcrEngine.java:611 最终联网判定
Future cloud = (mOcrServiceRequestHelper != null
             && canCloud
             && onlineEnable                                  // true
             && AppStatusOwner.canAccessInternet()            // 国行恒 true
             && Utils.isUserSetupComplete(...)
             && NetworkUtil.isNetworkAvailable(...))
    ? submit(云端请求) : null;
Future local = submit(本地OCR);   // ← 本地是无条件并行的
```

**结论**：③ 这条路在国行机器上**每次点识别都会先发云端请求**，本地只是并行兜底。
这条链**无法通过相册内任何开关改变**（它读的是系统服务的 `canAccessInternet()`）。
唯一手段是 DNS 拦。

## 3.3 为什么 ① 是纯本地

```java
// VersionUtils.ocrStaticSupport
public static final boolean a(Context context) {
    boolean isDeviceSupported = AIUnit.isDeviceSupported(context);
    DetectData d = AIUnit.getDetectData(context, "ocr_ar", extras);
    return isDeviceSupported && d.getIsSupport() && d.getIsAvailable();
}

// SuperTextStatic.a()：OCR_AUTO 分支
if (qrq.a(context)) {
    handler.post(new t3d(...));      // ← 本地 AIUnit 推理，不碰 OcrServiceApi
    return;
}
// 只有 else 才走 OcrServiceApi → 云端
```

`ocr_ar` 是随系统下发的**设备端 OCR 模型**。它在 → 本地推理，**一个 DNS 查询都没有**。

辅助佐证：
- 结果落本地缓存 `Pictures/OcrScanner`（`aoo.java`），云端方案不需要这套缓存
- 复制是 `InvokeTextView.c()` → `ClipboardManager.setPrimaryClip()`，纯系统 API

**风险点**：`ocr_ar` 被清（清数据 / OTA 重置 / 存储清理）→ 静默退云端。见第五章验证方法。

## 3.4 `album-idcard.heytapmobi.com` —— 它不是“身份证识别”

> ⚠️ v1～v3 前几版一直把它写成“身份证识别（敏感证件）”，**这是误判**。
> 端到端追完调用链后确认：它是 **「AI 证件照」** 功能的后端。

### 3.4.1 它到底是什么

```java
// xg0.java（AiIDPhotoManager）:209
j29 portraitGenerator = new j29(
    new yj4(context, /* 仅当已登录账号时才给 URL */ xj1.e().getF1262a() != null
        ? "https://album-idcard.heytapmobi.com" : null));
```

**两个 API**（`android:exported` 外均为相册内部）：

| 端点 | 类 | 用途 |
|---|---|---|
| `/v2/idcard/getToken` | `wcc` | 先服务端换一个临时 token |
| `/v2/idcard/idCardAnalysis` | `ucc` | 拿 token 换取“抠像/排版”结果 |

请求体（AES 加密后 Base64，密钥本地生成）：

```java
// ucc.RequestPortraitForm
requestId / picString / token / sdkVersion / picMd5
```

### 3.4.2 触发路径（完整界面路径）

```
相册 → 选一张照片 → 编辑 → 底部「AI 证件照」
  → EditorAiIdPhotoState（相册里的证件照面板）
    → AiIdPhotoSheet.k0()
      → 【弹窗 1】隐私授权  authorize_ai_id_photo
      → 【弹窗 2】联网授权  authorizing_request_network_ai_id_photo
      → 【弹窗 3】移动网络提醒 picture3d_aiidphoto_dialog_mobile_network_use_title
      → AiIDPhotoManager
        → CloudPortraitGenerator (yj4)
          → POST /v2/idcard/getToken      ← 网络请求 1
          → POST /v2/idcard/idCardAnalysis ← 网络请求 2（带图）
```

**三道弹窗的文案（原文）**：

> **① 隐私**：为提供 AI 证件照功能，本应用需要联网并获取您选择的图片以上传至服务器进行编辑处理。若您选择“不同意”，您将无法使用上述功能。
> **② 联网**：“相册”需要联网以使用 AI 证件照功能。
> **③ 移动网络**：移动网络进行证件照处理将消耗流量

代码位置（`gh0.j0()`）：

```java
j61Var.a(new hbk(k0, "authorize_ai_id_photo", R$string.authorizing_ai_id_photo_statement, ...));
j61Var.a(new kof(baseActivity, R$string.authorizing_request_network_ai_id_photo, 0, ...));
j61Var.a(new mxe(baseActivity, R$string.picture3d_aiidphoto_dialog_mobile_network_use_title, ...));
```

### 3.4.3 ⚠️ 上传的到底是什么（最关键）

**不是身份证原件。** 从 `RequestPortraitForm` 的字段和后续处理看：

| 字段 | 含义 |
|---|---|
| `picString` | 上传图（加密） |
| `picMd5` | 原图 MD5（用于校验） |
| `token` | getToken 拿到的临时凭证 |

而 `AiIDPhotoManager.d()` 回来的结果是 **`bkl`（portraitInfo）**，后续走的是：

```java
// xg0.java
private final void preCrop(...)      // 人像预裁剪
private final void adjustForPrint(...) // 打印尺寸适配
```

→ **服务端做的是「人像抠图 + 背景/尺寸排版」，返回的是处理后的证件照结果**。
证件上的**文字信息（号码、地址、有效期）不会被识别或提取** —— 那是超级文本/OCR 的活，跟这个功能无关。

**所以之前把 `album-idcard` 当“身份证识别”去 block 是误伤**：拦了它，坏的是“AI 证件照”功能，
并不会阻止任何证件信息读取（因为根本没读）。

### 3.4.4 开关与代价

| 项目 | 内容 |
|---|---|
| 授权标志 | `authorize_ai_id_photo`（在 `bbk.d` 列表内） |
| 关闭方式 A | 弹窗 ① 点“不同意” |
| 关闭方式 B | 隐私 → 撤回全部授权（`p0()` 全清） |
| 关闭代价 | AI 证件照不可用，**其他功能不受影响** |
| 前置条件 | 必须已登录 OPPO 账号（`xj1.e().getF1262a() != null`），否则 URL 直接给 null、不联网 |
| 特性开关 | `feature_is_support_ai_id_photo`——不支持该特性的机型根本没有入口 |

### 3.4.5 结论

| 问题 | 答案 |
|---|---|
| 是“身份证识别”吗？ | **不是**，是「AI 证件照」的人像抠图/排版服务 |
| 什么时候上传？ | 只有用户在编辑器里主动进「AI 证件照」并连过三道弹窗 |
| 上传什么？ | 加密后的图 + MD5 + 临时 token；**不是证件信息提取** |
| 会偷偷跑吗？ | **不会**。依赖 OPPO 登录 + 三道弹窗 + 特性开关 |
| 要不要 block？ | **看你用不用 AI 证件照**。不用 → 可以 block；用 → 别 block |

---

# 四、两个云端域名的真相

## 4.1 `aiscan.ocloud.heytapmobi.com` — 主动识别

```java
// OcrServiceRequestHelper.java（在 com.oplus.aiunit 内）
private static final String ONLINE_OCR_URL_BASE64 =
    "aHR0cHM6Ly9haXNjYW4ub2Nsb3VkLmhleXRhcG1vYmkuY29tL3NjZW5lb2NyL3NjYW4td2ViL3YxL29jcl9yZWNvZ25pemU";
// 解码 → https://aiscan.ocloud.heytapmobi.com/sceneocr/scan-web/v1/ocr_recognize
```

| 项 | 内容 |
|---|---|
| 触发者 | 上表 ②（本地不可用）和 ③（云端优先） |
| 触发时机 | **用户主动点识别**，无定时器 |
| 上传体 | `bitmap.compress(JPEG, 100)` — 几乎无损 |
| 请求头 | `OCLOUD-IMEI` / `OCLOUD-GUID` / `OCLOUD-APPID` / `OCLOUD-LANG` / `OCLOUD-CRC32` / `OCLOUD-TIMESTAMP` / `OCLOUD-ENCRYPTKEY` |
| 超时 | 8 秒（`OCR_TIMEOUT`） |

## 4.2 `airecognition-ocr-cn.heytapmobi.com` — 主动识别的备用通道

```java
// OcrScheduleClient.java:446
https://airecognition-ocr-cn.heytapmobi.com/ai_screen_recognition/api/v1/upload
```

| 项 | 内容 |
|---|---|
| 触发者 | 仅 `SuperTextStatic.h`（`new OcrScheduleClient(context, "ocr_ar")`，全包唯一实例） |
| 触发时机 | **用户主动识别时**，与主通道并行发出 |
| 逻辑 | `if (cloudResultTimeOut > 0) { 先上传; waitOcrFinish(7s); }` 然后本地兜底 |
| 上传体 | multipart：`phone_model` + `source_language` + `image.jpg`（JPEG 100，KMS 加密） |

> ⚠️ v1 曾把这条写成"定时扫描相册并上传"，**错**。全包没有第二处实例化，也没有定时器调用它。

## 4.3 后台 OCR 扫描（OCR_SCAN）—— 不联网

```java
// GalleryScanSyncTaskManager.createScanners()
if ((i3 & 32) == 32 && checkOCRScanAuthorizedIfNeed()) {
    arrayList.add(new b2g(this.mContext));   // OCR_SCAN
}
```

`b2g` 通过本地 AIUnit 做 OCR 建文本索引，**没有 aiscan / airecognition 的任何引用**。
所以它跑得再多 AdGuard 也不会有日志 —— 与实测一致。

---

# 五、为什么 AdGuard 里看不到这两个域名

三种可能，任一即可解释：

1. **触发频率本来就低** —— 只有手动点识别才有，日常几乎为零
2. **系统走 HTTPDNS** —— `httpdns.ocloud.heytapmobi.com` 在云端解析，AdGuard 只看到 IP 直连，
   看不到独立域名查询（该域名已在报告 04 中记录）
3. **系统 DNS 缓存** —— TTL 内不重复查询

**验证方法**：

```bash
# A. 确认本地模型状态（决定 ① 是否真的本地）
adb logcat -s VersionUtils | grep ocrStaticSupport
#   deviceSupport=true, supportOcr=true  → 本地，不会上云
#   supportOcr=false                     → 会退云端，赶紧拦

# B. 复现 ③（照片页 → 超级文本编辑 → 识别文字）
#   手机开相册 → 点一张有字的图 → 菜单「超级文本编辑」→ 底部「识别文字」
#   同时盯 AdGuard 实时日志过滤 "heytapmobi"，或看 netstat

# C. 抓包（有 SSL pinning，需 hook）
adb shell settings put global http_proxy <host>:<port>
```

---

# 六、用户能关到什么程度（三层开关）

> v1 说"没有开关"、v2 说"有 3 层"，本版统一为后者，并把每层边界说清楚。

## 6.1 三层结构

```
第 1 层  相册 → 更多功能 → 联网权限          （use_open_network，默认 false）
         ├─ 控：相册自身（搜索入口弹窗、部分后台扫描）
         └─ 不控：系统 OCR 服务 com.coloros.ocrservice

第 2 层  「文本搜索」授权弹窗                （authorize_text_ocr_service）
         ├─ 控：后台 OCR_SCAN 扫描器是否创建
         └─ 不控：主动点识别（③）那一条

第 3 层  相册 → 设置 → 隐私 → 撤回个人信息保护政策同意
         └─ 控：一次性清空 16 项 authorize_* 标志
```

## 6.2 第 1 层：联网权限

```xml
<!-- res/xml/setting_album_settings.xml -->
<COUISwitchPreference android:key="pref_key_open_network"
    android:title="@string/setting_category_network_permission_title"
    android:summary="@string/setting_pref_open_network_summary"
    android:defaultValue="false" />   <!-- ⚠️ 默认关闭 -->
```

- 中文标题：**联网权限**
- 中文摘要：开启后，可以查看照片的位置信息及精彩回忆等内容
- 存储键：`use_open_network`（`NetworkPermissionManager.hpf.d()`）

```java
public static final boolean d() {
    Boolean b = cache; if (b != null) return b;
    boolean v = f9f.a("use_open_network", false);   // 默认 false
    cache = v; return v;
}
```

**⚠️ 边界（两版都说过，这里给定论）**：
- 对**相册自己**有效 —— `SearchActivity.J0()` 联网未开时先弹授权；`GalleryScanSyncTaskManager` 各扫描器启动条件含 `hpf.d()`
- 对**系统 OCR 服务**无效 —— `com.coloros.ocrservice` 有自己的 `canAccessInternet()`，不读相册开关

## 6.3 第 2 层：「文本搜索」授权弹窗

首次使用相册搜索时弹出（`SearchPermissionHelper.b()`）：

```
「同意以下功能对信息的处理」
 ☐ 人物智能分类      → authorize_face_scan
 ☐ 读取地点信息      → authorize_location_resolve
 ☐ 文本搜索          → authorize_text_ocr_service     ← 就是它
   本功能需要将您的图片上传至服务器进行处理，以提升文字识别的准确率。
 [同意并使用]  [不同意]
```

文案原文（`values-zh-rCN/strings.xml:502-504`）：

> 为提供文本搜索功能，本应用需要联网并将您的图片上传至服务器进行处理，
> 以提升文字识别的准确率。**若您选择"不同意"，您将无法使用上述功能。**

**点「不同意」= `authorize_text_ocr_service = false`**，全包共 4 处消费该标志：

| 位置 | 作用 |
|---|---|
| `GalleryScanSyncTaskManager.checkOCRScanAuthorizedIfNeed()` | 决定是否创建 OCR_SCAN ✅ |
| `SearchActivity.J0()` | 决定是否重弹授权 |
| `c.b()` / `c.c()` | 弹窗文案与勾选项 |
| `cbk.a()` → `aVar.B(...)` | 写进 AI 插件配置 |

## 6.4 第 3 层：撤回全部授权

路径：**相册 → 设置 → 隐私 → 撤回个人信息保护政策同意**（`pref_key_cancel_all_authorizations`）

```java
// bbk.p0()：一次清空 16 项
for (k : d) f9f.d(FALSE, k);   // 含 authorize_text_ocr_service / authorize_enhance_text
for (k : e) f9f.d(FALSE, k);   // authorize_face_scan / travel_scan / gallery_map
```

代价（官方文案）：
> 您将无法使用本应用提供的查看地点信息和地图、地点搜索、下载贴纸素材等资源等功能…
> 但您的撤回并不会影响基础功能…仍可以使用本应用的基本功能。

## 6.5 ⚠️ 设计缺陷：没有逐项开关

`res/xml/setting_privacy.xml` 里**只有三项**：隐私政策链接、用户协议链接、撤回全部授权。
**没有任何 per-feature 开关**。

`authorize_text_ocr_service` 和 `authorize_enhance_text` 都是**只能拒一次**（首次弹窗），
**事后无法单独修改** —— 想改只能走第 3 层"撤回全部"再重新触发弹窗。

---

# 七、方案矩阵（最终版）

| 方案 | 拦 ③ 云端识别？ | 拦 ① 长按选字？ | 副作用 | 可逆 |
|---|---|---|---|---|
| 相册 → 更多功能 → 关「联网权限」 | ❌ 不拦 | ❌ 本来就不联网 | 地图相册、精彩回忆失效 | ✅ |
| 文本搜索弹窗点「不同意」 | ❌ 不拦 | ✅ 无影响 | 文本搜索不可用 | ⚠️ 只能撤回全部重来 |
| 隐私 → 撤回全部授权 | ❌ 不拦 | ✅ 无影响 | AI 修图/证件照/贴纸下载全失效 | ✅ 可重新同意 |
| **DNS 拦 2 个域名** | ✅ **拦** | ✅ 无影响（本地） | 识别降级本地，准确率略降 | ✅ |
| 卸载/禁用 `com.oplus.aiunit` | ✅ | ⚠️ 会打断 | 小布/AI 全线失效 | ❌ 不建议 |

**关键洞察：前三个开关都拦不住 ③（云端优先），因为 ③ 由系统 OCR 服务决定，不读相册开关。**

## 7.1 推荐 blocklist

```
# ===== F 组：相册 OCR 云端（核心）=====
aiscan.ocloud.heytapmobi.com
airecognition-ocr-cn.heytapmobi.com

# ===== F 组：AI 证件照（可选，看你用不用）=====
album-idcard.heytapmobi.com      # 「AI 证件照」人像抠图/排版，不是证件信息识别
```

## 7.2 屏蔽后果

| 域名 | 后果 |
|---|---|
| `aiscan.ocloud.*` | 超级文本/识别文字**降级为本地**（质量下降但不失败） |
| `airecognition-ocr-cn` | 备用通道失效，主通道不受影响，**几乎无感** |
| `album-idcard` | **AI 证件照功能不可用**（不影响其他功能，也不涉及证件信息读取） |

> `aitool-cuiocr-cn.heytapmobi.com` / `aitool-curocr-cn.wanyol.com` 本次未深查，
> 在 v1 里被归为“OCR 工具”，保留观望；要拦的话建议单独测试。

**建议**：先只拦前两个，观察几天超级文本和长按选字是否正常。

---

# 八、隐私政策 vs 代码

政策原文（`settings_privacy_statement_1_3_2_3_gallery02`）：

> 当您使用文本搜索或超级文本的识别文字功能时，本应用需要使用系统提供的文字识别服务…
> 若您的设备的文字识别服务已联网，为提高文字识别的准确度，我们可能需要收集您的图片，
> 并将图片上传至云端进行文字识别处理。若未联网，相册将在本地完成对图片的处理…
> 当云端服务器完成处理后，上传的图片会被立刻销毁。

| 政策表述 | 代码实际 | 相符？ |
|---|---|---|
| "使用**系统提供的**文字识别服务" | `com.coloros.ocrservice` AIDL | ✅ |
| "**若**已联网，将图片上传云端" | 国行 `canAccessInternet()` 恒 true，等于"总是联网" | ⚠️ **措辞给人"可选"的错觉** |
| "若未联网，相册在本地处理" | 分支存在，但国行正常流程不走 | ⚠️ 名义存在 |
| "图片会被**立刻销毁**" | 静态代码无法验证 | ❓ 待验证 |
| "定期识别图片中的文字" | 实际只有用户主动触发，**没有定期后台识别** | ⚠️ 描述与实际不符（代码更保守） |
| "用户可关闭" | 相册内确实无 per-feature 开关 | ❌ 可及性差 |

**核心矛盾**：政策的条件句"若已联网"在国行等于"永远联网"，
而相册内没有对应开关 —— 这就是官方客服难以回应的问题所在。

**反向发现**：政策写得像"定期后台识别"，但代码实际只在用户主动时识别（更保守）。
**可以认为厂商在收集范围上比政策声明更克制。**

---

# 九、相册其他联网点（48 个域名中值得关注的）

| 域名 | 用途 | 备注 |
|---|---|---|
| `api.map.baidu.com` / `daohang.map.baidu.com` | 地图相册 | 已在旧 blocklist |
| `cloud.heytap.com` / `cloudkit-api-cn.heytapmobi.com` | 云同步 | 相册备份 |
| `i-cn01a.ocloud.heytapmobi.com` / `share-cn01a.*` | 共享相册 | |
| `httpdns.ocloud.heytapmobi.com` | HTTPDNS | 已在报告 04 |
| `airecognition-ocr-cn` / `aitool-cuiocr-*` | 云端 OCR | 见第七章 |
| `album-idcard.heytapmobi.com` | **AI 证件照**（非证件识别） | ⚠️ 仅使用该功能时才联网 |
| `ai-repair.ocloud.heytapmobi.com` | AI 修复 | |
| `aip-gw-cn.allawntech.com` | AI 网关 | |
| `videoclip-*` / `fourier-videoclip-cn` | 视频剪辑 | 已在报告 01 |
| `muc.heytap.com` | 账号/隐私政策 | |
| `fnos.net` | ?（3 次） | 待查，疑似飞牛 NAS 分享 |

---

# 十、相册还有什么值得继续研究（F 组收口）

## 10.1 已完成，不用再查

| 项目 | 结论 |
|---|---|
| 相机 3 包 | 零业务域名，干净 |
| 相册 6 个识别入口 | 已逐个追完（见第三章） |
| 后台扫描器清单（21 个） | 全部 grep 过 `http/https/heytap/OkHttp`，**无一联网**（Local ML/Database 本地） |
| 联网开关三层 | 已说清边界 |
| 云端域名 | 2 个 OCR + 1 个证件照，已定性 |

## 10.2 留待有需要再看（优先级低）

| # | 项目 | 为什么现在不深入 |
|---|---|---|
| 1 | `fnos.net`（3 次命中） | 很可能是用户自己装的飞牛 NAS 分享，不是相册行为 |
| 2 | `aitool-cuiocr-cn` / `aitool-curocr-cn` | v1 归为“OCR 工具”，但未追调用链；可能是其他 App 写的常量 |
| 3 | 云同步/共享相册具体内容 | 属于账号体系，不是本次“文字识别”主题 |
| 4 | 相册 48 个域名中剩余小域名 | 低价值，已在报告 01/04 覆盖大部分 |

**结论：F 组（相机/相册）可收口，转入 G 组。**

---

# 十一、待验证

| # | 项目 | 方法 |
|---|---|---|
| 1 | `ocr_ar` 本地模型在一加 8T 上是否始终可用（决定 ① 是否真本地） | `adb logcat -s VersionUtils \| grep ocrStaticSupport` |
| 2 | ③ 云端识别是否每次都发请求（还是只有首次/特定机型） | AdGuard 实时日志 + 真机操作复现 |
| 3 | `ocr_recognize` 服务端是否真的"处理完即销毁" | 抓包看响应 / 查隐私政策更新 |
| 4 | 第 2 层「不同意」后，③ 是否仍然上云（预期：仍然上云） | 真机操作对比 |
| 5 | `fnos.net`（3 次命中）归属 | 抓包看 SNI/证书 |
| 6 | 清空 `ocr_ar` 后 ① 是否静默退云端 | 清 `com.oplus.aiunit` 数据后测 |

---

# 附录 A：v1 → v3 结论修正记录

> 保留可追溯性。已过时的原文见 `report-phase13-e-f-camera-gallery.md`（合并稿，标注为历史版本）。

| # | v1 的错误结论 | v3 的正确结论 | 关键证据 |
|---|---|---|---|
| 1 | "相册超级文本/识别文字**默认**就走云端"（暗示后台自动） | 只有**用户主动点识别**时走云端；长按选字是本地 | `qrq.a()` → 本地分支；`SuperTextStatic` 无定时器 |
| 2 | "`OcrScheduleClient` 是**定时识别**通道" | 它只在用户主动识别流程内，先传后等 7 秒 | 全包唯一实例 `SuperTextStatic.h` |
| 3 | "后台定时扫描相册并上传" | 后台 OCR_SCAN（`b2g`）**纯本地**，无域名 | `b2g` 无 aiscan/airecognition 引用 |
| 4 | "相册里**没有**文字识别开关" | 有 **3 层**：联网权限 / 文本搜索授权 / 撤回全部 | `setting_album_settings.xml`、`SearchPermissionHelper` |
| 5 | "联网权限开关管不到 OCR" | 对**相册自身**有效，对**系统 OCR 服务**无效——要分开说 | `hpf.d()` vs `canAccessInternet()` |
| 6 | "政策说'定期识别'，代码也定期上传，符合" | 政策说定期，代码反而只在主动时识别 —— 代码更保守 | `GalleryScanSyncTaskManager` |
| 7 | 未区分"超级文本编辑页"和"照片页长按选字" | 是两个入口，一个云端优先一个纯本地 | `SuperTextOcrAbility.a()` vs `SuperTextAbility.g()` |
| 8 | `album-idcard.heytapmobi.com` = "**身份证识别**（敏感证件）" | 实际是 **「AI 证件照」**（`/v2/idcard/getToken` + `/idCardAnalysis`），做的是人像抠图/排版，**不提取证件文字** | `AiIdPhotoManager` → `CloudPortraitGenerator` |
| 9 | （未提及） | 新增入口 ⑥「AI 证件照」：三道确认弹窗 + 需 OPPO 登录，不会静默触发 | `AiIdPhotoSheet.j0()` |

**方法论教训**：
1. 看到"上传函数"≠"会自动上传"，必须追到调用方入口
2. "有没有开关"要查 UI 资源和存储键，而不是只看判断函数
3. 判断"是否联网"要追到**最内层**的引擎选择（`ocrWithPriority` vs `ocr`），
   中间层（`SuperTextStatic.a(z=true)`）的 `z` 只是意图，不是结果

---

**报告版本**：v3（系统性整理版）
**整理时间**：2026-11-06
**历史版本**：`report-phase13-e-f-camera-gallery.md`（v1 合并稿 + v2 补丁，仅作追溯）
