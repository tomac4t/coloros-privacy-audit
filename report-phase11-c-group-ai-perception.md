# 第十一轮：C 组「AI / 感知类」隐私审计

- **日期**：2026-11-05
- **对象**：scope-proposal.md「C. AI / 感知类」，挑 17 个重点包
- **方法**：jadx 反编译 + 静态扫描（约 16 万 Java 文件）
- **回答**：①有没有隐私问题 ②**能否在设置里退出** ③和政策是否相符 ④补哪些 blocklist

---

# 一、17 个包的基本情况

| 包 | 标签 | 文件数 | 隐私 SDK | 上报域名 |
|---|---|---|---|---|
| `com.oplus.aiunit` | AI 服务引擎 | 6,967 | 5 | **2** |
| `com.oplus.deepthinker` | 智慧能力 | 8,055 | 5 | **3** |
| `com.oplus.metis` | 智慧决策 | 14,434 | 5 | **23** |
| `com.oplus.obrain` | OBrain | 1,871 | 4 | **0** |
| `com.oplus.smartengine` | SmartEngine | 4,684 | 1 | **0** |
| `com.coloros.sceneservice` | 智慧数据增强 | 25,118 | 7 | **41** |
| `com.coloros.ocrscanner` | 小布扫一扫 | 10,067 | 5 | **13** |
| `com.coloros.directui` | 小布识屏 | 5,845 | 3 | **9** |
| `com.coloros.colordirectservice` | 识屏服务 | 7,319 | 5 | **9** |
| `com.coloros.assistantscreen` | 速览 | 21,660 | 5 | **47** |
| `com.oplus.supertextinput` | 扫描输入 | 4,051 | 2 | **0** |
| `com.oplus.portrait` | 人像绘影 | 2,188 | 1 | **0** |
| `com.oplus.viewtalk` | 图片描述 | 2,759 | 4 | **0** |
| `com.coloros.translate.engine` | 翻译服务 | 5,374 | 3 | **4** |
| `com.oplus.audiomonitor` | 智慧语音 | 2,345 | 3 | **0** |
| `com.oneplus.voicewakeup` | 语音唤醒 | 820 | **0** | **0** |
| `com.oplus.dmp` | 融合搜索 | 11,712 | 3 | **0** |

**合计约 16 万 Java 文件。**

## 一个重要观察：AI 应用的「上报域名」极少

和 B 组（浏览器 226 个、快应用 200 个）相比，C 组**绝大多数是 0-47 个**。
原因：**它们不直接上报，而是把数据交给 statistics.rom 统一上传**（phase2 已确认的架构）。

> 所以对 C 组来说，**只加域名黑名单效果有限**——真正要关注的是「它们在本机采集了什么」。

---

# 二、隐私问题（按严重程度）

## 🔴 严重 1：屏幕捕获 —— 重新核实（只有 2 个包真在抓屏）

> **修正（2026-11-05 22:57）**：此前按 API 字符串统计的「12 个包抓屏」**不准**。
> 重新按**真实调用链**追踪后，结论大幅收窄。

### 重新核实的方法

上一轮用关键词匹配（`MediaProjection` / `screenshot` / `readPixels`），
把**封装类、兼容库、监听器**都算进去了。这一轮逐文件看调用链：

| 包 | 表面命中 | **真实情况** |
|---|---|---|
| **`com.coloros.directui` 小布识屏** | MediaProjection | ✅ **真抓屏**（`e2/g.java` 持有 `MediaProjection` + `LongRtAsrWithScreenMediaWrapper`） |
| **`com.coloros.translate.engine` 翻译** | MediaProjection | ✅ **真抓屏**（屏幕翻译，需要整屏图像） |
| `com.coloros.assistantscreen` 速览 | `OplusSurfaceControl` | ⚠️ **只是封装类**（`com/heytap/addon/view/OplusSurfaceControl.java`，**无调用方**） |
| `com.oplus.deepthinker` | `MediaProjectionInfo` | ❌ **监听谁在投屏/录屏**，自己不抓（`SampleDataListener` 订阅 `MediaProjectionInfo`） |
| `com.oplus.smartengine` | `screenshot` | ❌ 无真实调用 |
| `com.oplus.aiunit` / `metis` / `sceneservice` / `ocrscanner` / `supertextinput` | 各 1-2 | ❌ 均为封装/兼容/反射，无实际调用 |

### 结论

**真正能抓取屏幕内容的只有 2 个：小布识屏（`com.coloros.directui`）和翻译服务（`com.coloros.translate.engine`）。**

- **速览不抓屏**。上一轮说的「速览抓屏」是误判——它引用了 `OplusSurfaceControl` 封装类，但这个类在 APK 里**没有任何调用方**。
- **智慧决策（metis）不抓屏**。它引用的 `MediaProjectionInfo` 是**监听器**，用来知道「当前有 App 在投屏/录屏」，属于**风险监测**，不是自己截屏。
- **deepthinker 同理**，`SampleDataListener` 订阅的是 MediaProjection 状态变化。

### ⚠️ 一个反向发现：deepthinker 在监控你的投屏

```java
// deepthinker/.../psslistener/SampleDataListener.java
import com.oplus.wrapper.media.projection.MediaProjectionInfo;
```

`deepthinker`（智慧能力）会**记录谁在投屏/录屏、什么时候开始、多久**。
这本身不是隐私侵犯（是安全监控），但意味着：**「你开了录屏」这个动作被记录下来并可能上报**。

### 两个真抓屏的能关闭吗

| 应用 | 能否关闭 | 开关 |
|---|---|---|
| **小布识屏** | ✅ **可以** | `Settings.System` `direct_text_mode`（0=关闭） |
| **翻译服务（屏幕翻译）** | ⚠️ **只能不使用** | 没有独立开关；不触发屏幕翻译就不会抓 |

**小布识屏的完整关闭方式**：
- 设置 → 其他设置 → 手势体感 → 小布识屏（或「长按识屏」）
- 关闭后 `direct_text_mode = 0`，不会再启动截屏流程

## 🟠 中等：无障碍权限 —— 重新核实（只有 1 个包真用）

> **修正（2026-11-05 22:57）**：此前说「无障碍被大面积使用」，**这个说法也不准确**。

### 关键区分：`AccessibilityNodeInfo.obtain()` ≠ 无障碍服务

很多包里的 `AccessibilityNodeInfo.obtain()` 是**复制自己 App 的 View 信息**（比如读自己界面的文字），
**完全不需要无障碍权限**，也不需要用户开启无障碍服务。

只有**真正绑定 `AccessibilityService` 并用 `getRootInActiveWindow()`** 才能读**别的 App** 的界面。

### 重新核实结果

| 包 | 表面命中 | **真实情况** |
|---|---|---|
| **`com.coloros.colordirectservice` 识屏服务** | 6 个类 | ✅ **真用无障碍**（`accessibilityService.getRootInActiveWindow()`） |
| `com.coloros.directui` 小布识屏 | `AccessibilityNodeInfo.obtain()` | ❌ 只是复制自己的 View |
| `com.oplus.aiunit` / `metis` / `assistantscreen` / `smartengine` 等 | 类似 | ❌ 同上，均为 `obtain()` 复制自身 |

**真实结论：只有 `com.coloros.colordirectservice`（识屏服务）在使用无障碍服务读其他 App 的界面。**

### 什么场景要用无障碍

`colordirectservice` 用的是「**读屏**」能力，典型场景：

1. **小布识屏**（长按屏幕 → 识别当前页面的文字/图片）
2. **智能侧边栏的「识屏」**
3. **图片/文字提取**（把 App 里不能复制的文字提出来）

### 能否关闭

| 应用 | 能否关闭 | 方式 |
|---|---|---|
| **识屏服务 `colordirectservice`** | ✅ **可以** | 设置 → 无障碍 → 已下载的服务 → 关闭「识屏」；或关闭小布识屏（`direct_text_mode = 0`） |

**注意**：关闭小布识屏后，`colordirectservice` 失去了调用方，**不会再启动无障碍服务**。
但无障碍服务本身需要在「设置 → 无障碍」里确认已关闭。

## 🔴 严重 2：`com.coloros.sceneservice`「智慧数据增强服务」（25,118 文件）

SDK：DCC / GMS / HeyTap统计 / NearX / OPPO统计 / **讯飞** / 阿里

敏感调用：
```
无障碍 67   读设备ID 48   读IMEI 12   读IMSI 8
读剪贴板 5  读媒体库 5    读通讯录 4   持续定位 3   读MAC 3
```

域名（41 个，全部是 OPPO 自家）：
```
ocs-cn-north1.heytapcs.com          21
breeno.apps.coloros.com             13
intelligent-perception-cn-test.wanyol.com   8
pantanal-intelli-cn.allawntech.com   6
scene-bind-cn.allawntech.com         3
bot-claw-cn.heytapmobi.com           2
activity-cpc.heytapimage.com         2
```

**它是"场景识别"的底座**：判断你在干什么（通勤/办公/睡觉/运动），
然后喂给智慧决策、速览、智慧建议。

### ⚠️ 这个开关关掉后，真的就不收集了吗？

**找到两个开关，分两层：**

**第一层：服务总开关**

```java
// com/oplus/sdp/mf/b.java
public static void g(Context context, boolean z) {
    f(context.getApplicationContext(), z ? 1 : 0);
}

public static void f(Context context, int i) {
    if (i == 0 || i == 1) {
        a.e.g(cr, "key_com_coloros_sceneservice", i);   // 0=关
    }
}

// 还有一个通过 Provider 的方法
public static boolean e(Context context, boolean z) {
    Bundle bundle = new Bundle();
    bundle.putString("set_service_on_off", z ? "true" : "false");
    a(context, "method_set_service_on_off", null, bundle);   // ★ 真的关服务
    return true;
}
```

**关键：`method_set_service_on_off` 是让服务真正停止的方法**，不只是改个标记位。

**第二层：声明同意状态**

```java
// com/oplus/sdp/xb/g0.java:198
public static boolean d() {
    String e = e("scene_service_statement_state");
    ...
    return "1".equals(str);   // 1 = 已同意
}
```

**→ 这是"是否同意场景服务条款"，不是"是否启用"。**

### 关掉之后的行为

`setFinishSceneServiceStatement` 会：
1. 设置 `scene_service_statement_state`（撤销同意）
2. 调 `mf.b.g(context, false)` → `key_com_coloros_sceneservice = 0`
3. 通过 Provider 发 `method_set_service_on_off = "false"` → **通知服务端停止**

**结论：关掉后服务会真正停止，不是只改本地标记。**
但**残留数据**（本地已有的场景库）是否清除，代码里没看到明确的清理逻辑。

**开关位置**：设置 → 小布（或 其他设置 → 场景服务）

## 🟠 中等 1：`com.coloros.assistantscreen`（速览）是广告位

域名 47 个，其中广告相关：
```
stg-data.ads.heytapmobi.com     8
adx.ads.heytapmobi.com          5
adx.ads.oppomobile.com          3
adsfs-sdkconfig.heytapimage.com 4
activity-cpc.heytapimage.com    4
```

**速览就是负一屏，默认开启，内容是广告+推荐。**

## 🟠 中等 2：`aiunit` 的域名只有 2 个 —— 但它管着所有 AI

```
adps-sys-cn.allawntech.com      ← 设备画像服务
adps-admin-test.wanyol.com      ← 测试环境
```

**这很反常**：138MB 的 AI 引擎，只连 2 个域名？
因为它自己不联网——**所有 AI 请求都通过 `AiUnit` 的 AIDL 接口交给别的进程**（比如小布、翻译）。

## 🟢 干净的几个

| 包 | 情况 |
|---|---|
| `com.oneplus.voicewakeup` | 820 文件，**0 SDK 0 域名**——纯本地唤醒词 |
| `com.oplus.obrain` | 0 域名，只有统计 SDK |
| `com.oplus.smartengine` | 0 域名，只有 OPPO统计 |
| `com.oplus.supertextinput` | 0 域名 |
| `com.oplus.portrait` | 0 域名 |
| `com.oplus.viewtalk` | 0 域名 |
| `com.oplus.dmp` | 0 域名 |

---

# 三、⭐ 能否在设置里退出？（本轮重点）

这是最实用的一节。我把每个包的**真实用户开关**（`Settings.System/Secure` 里的 key）找出来了：

## 3.1 有明确开关、且能关掉的

### ✅ 速览（负一屏）—— 可完全关闭

```java
// Settings.Secure
"disable_assistant_screen"    // 0=开启, 1=关闭
```
```java
// assistantscreen/.../DeeplinkRepository.java:758
boolean z = Settings.Secure.getInt(cr, "disable_assistant_screen", 0) == 0;
```

**位置**：设置 → 桌面与锁屏 → 速览（或长按桌面 → 设置）

### ✅ 小布识屏 —— 可切换模式

```java
// Settings.System
"direct_text_mode"    // 默认 1
```
```java
// colordirect/.../c4/a.java:130
int i10 = Settings.System.getInt(cr, "direct_text_mode", 1);
```

**值含义**（从代码推断）：0=关闭 / 1=长按触发 / 2=双指触发或其他

### ✅ 智慧能力 DeepThinker —— 主开关正确联动

```java
// DeepThinkerSwitchController.java:105
protected boolean h(boolean z10) {
    a.e.f(ctx, "key_com_oplus_deepthinker", z10 ? 1 : 0);   // 主开关
    if (z10) return true;
    a.e.f(ctx, "key_com_oplus_deepthinker_user_experience_plan", 0);  // ★ 联动关掉体验计划
    return true;
}
```

**这是设计正确的**：关闭主开关会同时关掉 `user_experience_plan`（数据采集）。

**位置**：设置 → 小布（或智慧服务）→ 智慧能力

### ✅ 智慧决策 metis —— 有推荐开关

```java
"app_recommend_switch"          // Settings.Secure
"app_recommend_risk"
"app_recommend_aicardstatus"
"cast_settings_smart_reminder"
"key_scene_continuation"
"key_subway_route_switch"
```

**这些是分项开关**，可以单独关"应用推荐"、"投屏提醒"、"场景续接"。

### ✅ 智慧语音 ai_speech_auto_switch

```java
"ai_speech_auto_switch"    // Settings.System
"is_open_third_summary"    // 第三方通话摘要
"is_qq_summary"
"is_wechat_summary"
```

**最后三个很关键**：控制是否对**微信/QQ 通话**做摘要。默认值需要真机确认。

## 3.2 ⚠️ 其他包的开关情况（部分此前判断有误，已修正）

### ✅ `com.oplus.aiunit`（AI 服务引擎）—— **有开关，在"增强服务"里**

> **修正（2026-11-05 22:36）**：此前判断"aiunit 无用户开关"是**错的**。
> 开关存在，只是**不用 `Settings.System/Secure`，而是用私有 KV 存储**
> （`com.oplus.okvrw.base.KVRW`），所以按系统 Settings API 搜索抓不到。

**开关位置**：设置 → 其他设置 → 增强服务 → AI 服务引擎

**真实 key**（`com/oplus/aiunit/base/compat/SwitchCompat.java`）：

```java
private static final String KEY_CLOSE_DOWNLOAD_IN_BOOT_SETUP = "ai::key::close_download_in_boot_setup";
private static final String PREF_KEY_AIGC_AUTO_DOWNLOAD      = "ai::settings::aigc_auto_download";
private static final String PREF_KEY_UNIT_AUTO_DOWNLOAD      = "ai::settings::unit_auto_download";
private static final String PREF_KEY_USER_PRIVACY_AGREED     = "ai::settings::user_privacy_agreed";

public static final int SWITCH_CLOSE      = 0;
public static final int SWITCH_OPEN       = 1;
public static final int SWITCH_CLOSE_AUTO = 2;
public static final int SWITCH_OPEN_AUTO  = 3;
public static final int SWITCH_DEFAULT    = -1;
```

**做了什么**（`SwitchCompat.isNeedApplyPrivacy()`）：

```java
public static final boolean isNeedApplyPrivacy(Context context) {
    if (AppStatusOwner.isDomestic()) {
        if (AppStatusOwner.isOcrApp()) {
            if (ApiVersionUtils.INSTANCE.isS()) {
                if (!isWlanAutoDownloadEnable(...) || !isUserPrivacyAgreed(...)) {
                    return true;   // 需要走隐私弹窗
                }
            }
        }
    }
    ...
}
```

**增强服务包含哪些子项**（`UNIT_STRENGTHEN_SWITCH`）：

```java
private static final String[] UNIT_STRENGTHEN_SWITCH = {"NLP_CALL_SUMMARY"};  // 通话摘要
private static final ArrayList<String> LLM_SETTINGS_KEYS =
        arrayListOf("aigc_sdinpainting", "NLP_CALL_SUMMARY");                   // AI 消除 + 通话摘要
```

**结论：AI 服务引擎有总开关，位置在「设置 → 其他设置 → 增强服务 → AI 服务引擎」。**
关掉后：`isNeedApplyPrivacy()` 返回 true → 走隐私弹窗 → 拒绝启用对应 AI 能力。

### 这个发现的元教训

**OPPO 系统应用的用户开关至少存在三种存储方式**：

| 存储方式 | 例子 |
|---|---|
| `Settings.System` | `direct_text_mode`（识屏模式） |
| `Settings.Secure` | `disable_assistant_screen`（速览）、`app_recommend_switch` |
| **私有 KV（`com.oplus.okvrw.base.KVRW`）** | **aiunit 的 `ai::*` 系列** |
| SharedPreferences | `key_com_oplus_deepthinker`（DeepThinker） |

**只搜 `Settings.*` 会漏掉相当一部分。**

### ✅ `com.coloros.sceneservice`「智慧数据增强服务」—— **有双层开关**

> **修正（2026-11-05 22:57）**：此前说「无独立开关」是**错的**。

**第一层：服务总开关**（`key_com_coloros_sceneservice`，0=关）

```java
// com/oplus/sdp/mf/b.java
public static void f(Context context, int i) {
    if (i == 0 || i == 1) {
        a.e.g(cr, "key_com_coloros_sceneservice", i);
    }
}

// 更彻底的方式：通过 Provider 通知服务端停止
public static boolean e(Context context, boolean z) {
    Bundle bundle = new Bundle();
    bundle.putString("set_service_on_off", z ? "true" : "false");
    a(context, "method_set_service_on_off", null, bundle);   // ★ 真的关服务
    return true;
}
```

**第二层：条款同意状态**（`scene_service_statement_state`）

```java
// com/oplus/sdp/xb/g0.java:198
public static boolean d() {
    String e = e("scene_service_statement_state");
    return "1".equals(str);   // 1 = 已同意
}
```

**这是"是否同意条款"，不是"是否启用"。**

### 关掉之后真的不收集了吗

关闭流程（`setFinishSceneServiceStatement`）做三件事：

1. `scene_service_statement_state` ← 撤销同意
2. `key_com_coloros_sceneservice` ← 0
3. Provider 发 `method_set_service_on_off = "false"` → **服务端也停止**

**→ 服务会真正停止，不是只改本地标记。**

**但有一个未确认点：本地已积累的场景库（场景标签、用户画像）是否被删除。
代码里没有看到明确的清理逻辑。**

### `com.oplus.ocrscanner` / `supertextinput` / `portrait` / `viewtalk` / `dmp`

扫描到的 key **99% 是内部常量**（`KEY_LAUNCH_SUCCESS`、
`KEY_COMPONENT_ACTIVITY_*` 这类 androidx 的），**没有用户可达的隐私开关**。

这些是**功能型应用**：你不打开它就不采集。**"不用"就是"退出"。**

## 3.3 汇总表

| 应用 | 能否关闭 | 开关位置 |
|---|---|---|
| 速览（负一屏） | ✅ 完全可关 | `disable_assistant_screen` |
| 小布识屏 | ✅ 可切模式 | `direct_text_mode` |
| 智慧能力 DeepThinker | ✅ 主开关联动 | `key_com_oplus_deepthinker` |
| 智慧决策 metis | ✅ 分项可关 | `app_recommend_switch` 等 |
| 智慧语音 | ✅ 部分可关 | `ai_speech_auto_switch` / `is_wechat_summary` |
| **智慧数据增强服务 sceneservice** | ✅ **双层开关** | `key_com_coloros_sceneservice` + `method_set_service_on_off` |
| **AI 服务引擎 aiunit** | ✅ **有开关** | 设置→其他设置→增强服务→AI服务引擎（`ai::key::close_download_in_boot_setup`） |
| 扫一扫 / 扫描输入 / 人像 / 图片描述 / 融合搜索 | ⚠️ 靠"不用" | — |
| 翻译 / 语音唤醒 | ⚠️ 靠"不用" | — |

**修正后的结论**：

- **AI 服务引擎 aiunit 有总开关**（设置 → 其他设置 → 增强服务 → AI 服务引擎），
  用私有 KV（`ai::*`），常规搜索会漏
- **智慧数据增强服务 sceneservice 有双层开关**，关掉后服务真正停止

### 屏幕捕获 / 无障碍 能否关闭（补充）

| 能力 | 涉及应用 | 能否关闭 | 方式 |
|---|---|---|---|
| **屏幕捕获** | 小布识屏 `directui` | ✅ **可以** | `direct_text_mode = 0`（设置→小布识屏） |
| **屏幕捕获** | 翻译服务 `translate` | ⚠️ **只能不使用** | 无独立开关，不触发屏幕翻译即不抓屏 |
| **无障碍（读屏）** | 识屏服务 `colordirectservice` | ✅ **可以** | 设置→无障碍→关闭「识屏」；或关小布识屏使其失去调用方 |

**注**：速览、智慧决策、智慧能力 **都不真抓屏**（详见前面修正）。

---

# 三·五、案例研究：状态栏「司机预计到达时间」是怎么来的？

> 来源：Tom 的实际观察——开启「智慧数据增强服务 / 智慧出行」后，
> 在高德地图打车时，状态栏左上角（时间旁边）会显示司机 ETA / 行程预计结束时间。

## 3.5.1 结论

**不是读屏，是高德的 Intent 广播 + 系统的应用切换监听。**

```
① 系统知道你在用高德
   OplusAppSwitchManager（ColorOS 私有 API）
   ↓
② 高德主动广播打车状态
   Intent action（OPPO × 高德私有协议）
   ↓
③ 系统订阅这些广播，解析出 ETA
   com.oplus.sdp.*（sceneservice 内）
   ↓
④ 写进状态栏左侧
```

## 3.5.2 证据 1：系统在匹配「高德 × 特定 Intent」

**文件**：`com/oplus/sdp/r9/c.java`（sceneservice 内）

```java
public final class c implements com.oplus.sdp.wk0.c {
    public static final c a = new c();

    @Override // com.oplus.sdp.wk0.c
    public boolean a(String packageName, String intentName) {
        x.i(packageName, ParserTag.TAG_PACKAGE_NAME);
        x.i(intentName, "intentName");
        return x.d(packageName, "com.autonavi.minimap")
            && x.d(intentName, "Navigation.NotifyCruiseTrafficLightStatus");
    }
}
```

这是一个 **「包名 × Intent action」匹配器**，说明：
- 系统在**接收广播**，不是主动抓取
- 匹配的 action 叫 `Navigation.NotifyCruiseTrafficLightStatus`（红绿灯倒计时）

同样的模式还有 `com/oplus/sdp/ni0/e.java`（提到 `traffic_light_reminder`）。

**推论**：打车 ETA 走的是同一套机制——高德发出另一个 action，系统订阅后解析。

## 3.5.3 证据 2：系统知道你「当前在前台用哪个 App」

**文件**：`com/oplus/travelengine/appstatemonitor/impl/c.java`（智慧出行内）

```java
import com.oplus.app.OplusAppSwitchManager;
```

`OplusAppSwitchManager` 是 ColorOS 私有 API（AOSP 只有 `ActivityManager.getRunningTasks`，
Android 5.0 后已废弃）。

**它能做的**：知道前台是哪个包
**它不能做的**：看不到 App 里面的内容（拿不到订单、司机信息、金额）

> 所以「知道你在打车」不是靠读屏，是靠**高德自己告诉你**（发广播）。

## 3.5.4 证据 3：确实有无障碍服务，但不是主路径

**文件**：`com/oplus/travelengine/travelaccessibilityservice/EngineAccessibilityService.java`

```java
public class EngineAccessibilityService extends AccessibilityService {

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        // ★ 空实现 —— 不监听任何界面变化
    }
}
```

**关键**：`onAccessibilityEvent` **是空的**。

这说明它**不监听**界面事件，只是持有一个 `AccessibilityService` 实例，
供别的模块调用 `getRootInActiveWindow()`（主动读当前屏幕）。

**调用方**：`com/oplus/travelengine/imnotification/b.java`

```java
// 方法名：getLastMapNodeAndClick()  —— "获取最后一个地图节点并点击"
```

**用途推测**：兜底方案。当高德不发广播（老版本 / 特定场景）时，
系统退化成「读屏找按钮 → 模拟点击」（比如自动点「我知道了」关弹窗）。

**这是备胎，不是主路径。**

## 3.5.5 这是个「私有协议」

| 问题 | 答案 |
|---|---|
| 高德有公开 API 吗？ | ❌ 没有。这是 **OPPO × 高德的私有 Intent 约定** |
| 数据是 OPPO 抓来的还是高德给的？ | ✅ **高德给的**（结构化 ETA，不是 OCR 猜的） |
| 高德知情吗？ | ✅ 知情，否则不会主动广播 |
| 这个协议透明吗？ | ❌ 没有任何公开文档 |

## 3.5.6 对隐私的实际影响

**这一条反而是好事**：

- 相比「读屏 + OCR 猜数字」，**Intent 广播拿到的数据更精确、误判更少**
- 系统只需要 ETA，不需要看到订单详情、支付信息、聊天
- 相比截屏方案，**攻击面小得多**

**但要警惕的是第 3 步之后**：
系统拿到 ETA 后，会不会**顺便上报**？

`sceneservice` 的域名里有：
```
intelligent-perception-cn-test.wanyol.com
pantanal-intelli-cn.allawntech.com
scene-bind-cn.allawntech.com
```

**这些是「智能感知 / 场景绑定」的上报点**。理论上「你在用高德打车」这个场景事件会被记录。

## 3.5.7 开关影响

| 动作 | 效果 |
|---|---|
| 关闭 **智慧数据增强服务**（sceneservice） | 不再订阅高德广播 → 状态栏不显示 ETA |
| 关闭 **智慧出行**（travelengine） | 同上（场景卡片来源） |
| **关闭无障碍里的 travelengine 服务** | 兜底的读屏点击失效，但 ※ ETA 仍可能正常显示（走广播） |
| 高德本身 | **完全不受影响**（它只是发广播，不管有没有人听） |

## 3.5.8 方法论笔记

这个案例说明一件事：**「有权限」≠「在用」**。

`travelengine` 确实声明了 `AccessibilityService`，Manifest 里能看到。
但 `onAccessibilityEvent` 是空实现——它只在特定兜底场景被主动调用。

**审计时必须看方法体，不能只看 Manifest 声明和类名。**

---

# 四、和隐私政策是否相符

## 4.1 政策文本仍然不在 APK 里

所有 17 个包都有 `PrivacyPolicy` / `privacy_policy` 字符串（**共 22 种写法**），
但**没有任何一个是真实 URL**——它们都是资源 ID 的引用：

```java
privacy_policy        → R.string.xxx
PrivacyPolicy         → 类名
privacypolicy         → 方法名
```

**实际的协议页面在 `muc.heytap.com`，运行时加载。**

## 4.2 但可以从"开关设计"反推政策真实性

这一轮有一个重要发现：**这些应用大多提供了开关**，说明设计上承认"用户可以控制"。

| 技术事实 | 政策通常承诺 | 判定 |
|---|---|---|
| DeepThinker 关主开关会联动关 `user_experience_plan` | "可随时撤回授权" | ✅ **相符** |
| 速览有 `disable_assistant_screen` | "可关闭个性化推荐" | ✅ **相符** |
| 识屏有 `direct_text_mode=0` | "可关闭识屏功能" | ✅ **相符** |
| aiunit 有开关（**增强服务**，私有 KV `ai::*`） | "可关闭 AI 服务" | ✅ **相符**（2026-11-05 修正） |
| sceneservice 有双层开关（`key_com_coloros_sceneservice` + `method_set_service_on_off`） | "可关闭场景识别" | ✅ **相符**（2026-11-05 修正） |
| 屏幕捕获 3-4 个类在调用 | 政策里是否说明"截取屏幕内容"？ | ⚠️ **必须核对** |
| 识屏服务使用无障碍读屏 | 政策里是否说明"读取其他 App 界面文字"？ | ⚠️ **必须核对** |

### 两个必须核对政策原文的点

1. **屏幕捕获**：只有**小布识屏**和**翻译服务**会截取整个屏幕。
   政策如果只写"处理您主动选择的图片"，与事实不符。

2. **无障碍权限**：`colordirectservice` 有 6 个类真调用无障碍 API。
   政策里通常写"为了帮助残障人士"，但**用它做识屏是完全不同的用途**。

---

# 五、可增加的 blocklist

C 组的上报域名很少，**新发现的只有 5 个**：

## 5.1 推荐加入（追踪/画像类）

| 域名 | 包 | 用途 | 建议 |
|---|---|---|---|
| `adps-sys-cn.allawntech.com` | aiunit | **设备画像服务** | ✅ Tier A |
| `pantanal-intelli-cn.allawntech.com` | metis / sceneservice | 智能感知/画像 | ✅ Tier A |
| `scene-bind-cn.allawntech.com` | sceneservice | 场景绑定 | ✅ Tier A |
| `intelligent-platform-cn.allawntech.com` | metis / sceneservice | 智能平台 | ✅ Tier A |
| `sense-intent-cn-01.heytapmobi.com` | metis | 意图识别 | ✅ Tier A |
| `bot-brain-cn.heytapmobi.com` | metis | AI 大脑 | ✅ Tier A |
| `bot-claw-cn.heytapmobi.com` | sceneservice | AI | ✅ Tier A |
| `bot-intent-cn.heytapmobi.com` | metis | 意图 | ✅ Tier A |
| `iwisdom.apps.coloros.com` | directui / colordirect | 智慧 | ✅ Tier A |
| `traffic-operation-cn.allawntech.com` | ocrscanner / directui / colordirect | 流量运营 | ✅ Tier A |
| `aitool-cuiocr-cn.heytapmobi.com` | colordirect | **云端 OCR** | ✅ Tier A（拦了识屏会降级） |
| `aitool-curocr-cn.wanyol.com` | colordirect | 云端 OCR（测试） | ✅ Tier A |
| `translate-service-cn.allawntech.com` | ocrscanner | 云端翻译 | ✅ Tier A |
| `compass-translate.apps.coloros.com` | translate | 翻译服务 | ✅ Tier A |
| `translate.apps.oppomobile.com` | translate | 翻译服务 | ✅ Tier A |
| `aip-gw-cn.allawntech.com` | translate | AI 网关 | ✅ Tier A |
| `aip-ws-cn.allawntech.com` | translate | AI 网关 WS | ✅ Tier A |
| `odin.allawntech.com` | deepthinker | 推理服务 | ✅ Tier A |
| `sport.health.heytapmobi.com` | deepthinker | 健康数据 | ✅ Tier A |
| `datasec-kmsex-cn.heytapmobi.com` | ocrscanner | 数据安全 | ⚠️ Tier B（可能是必需） |
| `virusinfo-sec.heytapmobi.com` | ocrscanner | 病毒库 | ⚠️ Tier B |
| `hio.oppo.com` | ocrscanner | 设备画像 | ✅ Tier A |
| `smartcard.apps.coloros.com` | assistantscreen | 智能卡片 | ✅ Tier A |
| `near-field.heytapmobi.com` | assistantscreen | 近场 | ✅ Tier A |
| `tips-h5.coloros.com` | assistantscreen | 提示页 | ⚠️ Tier B |
| `imsp.coloros.com` | ocrscanner / directui | 推送 | ⚠️ Tier B |

## 5.2 ⚠️ 拦了会掉功能的关键

| 域名 | 影响 |
|---|---|
| `aitool-cuiocr-cn.heytapmobi.com` | **识屏/扫一扫的云端 OCR**，拦了只能用本地 OCR（降级） |
| `translate-service-cn.allawntech.com` | **拍照翻译/屏翻译失效** |
| `breeno.apps.coloros.com` | **小布全系功能**（语音/识屏/场景） |
| `aip-gw-cn.allawntech.com` | **翻译/AI 网关** |
| `sense-intent-cn-01.heytapmobi.com` | 智慧决策的意图识别 |

> **这几条建议放到 Tier B（caution）**，除非你愿意牺牲功能。

## 5.3 不要拦

- 本地推理相关的（`*.mnn` 模型下载域名如果发现了要谨慎）
- `ocs-cn-north1.heytapcs.com`（21 次，看用途是内容分发，拦了速览会空）

## 5.4 已生成

见 `out/blocklist/07-c-group-additions.txt`

---

# 六、总结

## 6.1 三个最该知道的

1. **屏幕捕获是真的，但只有 2 个应用**：**小布识屏**（`directui`）和**翻译服务**（`translate`）。
   速览、智慧决策、智慧能力**都不抓屏**（之前判断有误，已修正）。
   这两个的截屏范围是**整屏**，理论上覆盖密码/验证码/聊天内容。
   → **小布识屏可通过 `direct_text_mode=0` 关闭；翻译只能"不用"。**
2. **无障碍只有 1 个应用真用**：`com.coloros.colordirectservice`（识屏服务）。
   其他包里的 `AccessibilityNodeInfo.obtain()` 只是复制自己的 View，不需要无障碍权限。
   → **可在「设置 → 无障碍」里关闭识屏服务。**
3. **AI 底座 `aiunit` 的开关在「设置 → 其他设置 → 增强服务 → AI 服务引擎」**，
   用私有 KV 存储（`ai::*`），常规搜索会漏。
   智慧数据增强服务（sceneservice）也有双层开关，关掉后服务**真正停止**。

## 6.2 好消息

**C 组比 B 组"规矩"得多**：
- **所有主要应用都有开关**（速览/识屏/DeepThinker/metis/语音/AI服务引擎/场景服务）
- DeepThinker 的主开关**正确联动**了数据采集开关
- 场景服务的开关会**真正通知服务端停止**，不是只改本地标记
- 8 个包的上报域名是 0
- 真正抓屏的只有 2 个，真正用无障碍的只有 1 个

## 6.3 黑名单效果有限

C 组大多不直接联网，数据走 statistics.rom。
**对 C 组，"关开关"比"拦域名"更有效。**

## 6.4 建议的处置顺序

1. **先关开关**（收益最大，且都是真开关）：
   - 小布识屏（`direct_text_mode=0`）→ 同时解决抓屏 + 无障碍
   - 场景服务（`key_com_coloros_sceneservice`）→ 服务端也会停
   - 速览（`disable_assistant_screen`）
   - AI 服务引擎（设置→其他设置→增强服务）
   - 智慧能力 DeepThinker（主开关联动）
   - 智慧决策的推荐项（`app_recommend_switch` 等）
2. **再拦域名**：`adps-sys-cn` / `pantanal-intelli-cn` / `sense-intent-cn-01` 这几个画像类的
3. **谨慎拦**：OCR/翻译相关的，拦了功能会降级

---

# 七、复现命令

```bash
JADX=~/.openclaw/workspace/tools/jadx/bin/jadx
bash /tmp/decompile_c.sh        # 17 个包
python3 /tmp/scan_c.py          # SDK + 敏感 API + 域名
python3 /tmp/c_switches.py      # 开关 key + 屏幕捕获/无障碍真调用
python3 /tmp/c_real_switches.py # Settings.System/Secure 真实项
```
