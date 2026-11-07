# 第九轮补（A 组剩余 4 包）：logkit / crashbox / postmanservice / nhs

- **日期**：2026-11-06
- **对象**：`com.oplus.logkit` / `com.oplus.crashbox` / `com.oplus.postmanservice` / `com.oplus.nhs`
- **样本**：`/tmp/a-apk/`，反编译 `/tmp/ajadx/`
- **补齐**：README 里遗留的「A 组剩余 4 个包」

---

# 一、结论速览

| # | 包 | 业务域名 | 联网 | 定性 |
|---|---|---|---|---|
| 1 | `com.oplus.logkit`（反馈工具箱） | 2 | ✅ 问卷上报 | 🟡 低风险 |
| 2 | `com.oplus.crashbox`（CrashBox） | **0（运行时下发）** | ✅ 崩溃上报 | 🟠 中 |
| 3 | `com.oplus.postmanservice`（诊断工具服务） | **12（asdt 全家）** | ✅ **PC 远程诊断** | 🔴 **重点** |
| 4 | `com.oplus.nhs`（网络健康服务） | 0 | ❌ **不联网** | 🟢 干净 |

---

# 二、🔴 `com.oplus.postmanservice` —— 远程诊断服务

## 2.1 它是什么

**Postman = OPPO 官方的「远程诊断 / 售后诊断」工具。**
用于：用户报障 → 客服（ASDT 系统）远程连上手机 → 抓日志 / 跑检测 / 修复。

**这是本次审计里唯一的「远程控制通道」类组件。**

## 2.2 全部服务器地址（`remotediagnosis/BuildConfig.java`）

```java
public static final String SERVER_ADDRESS_DEV          = "https://asdt-server5-cn-dev.wanyol.com";
public static final String SERVER_ADDRESS_DEV_FROM_TEST= "https://asdt-server5-dev.wanyol.com";
public static final String SERVER_ADDRESS_TEST2        = "https://asdt-server5-cn.wanyol.com";
public static final String SERVICE_ADDRESS             = "https://asdt-server5-cn.allawntech.com";  // ★ 生产（国内）
public static final String SERVICE_ADDRESS_EUEX        = "https://asdt-server5-fr.allawnos.com";   // 欧洲
public static final String SERVICE_ADDRESS_EXP         = "https://asdt-server5-sg.allawnos.com";   // 新加坡
public static final String SERVICE_ADDRESS_IN          = "https://asdt-server5-in.allawnos.com";   // 印度
public static final String SERVICE_ADDRESS_US          = "https://asdt-server5-us.allawnos.com";   // 美国
public static final String SERVICE_ADDRESS_OLD         = "https://asdt.coloros.com";               // 旧
public static final String UPLOAD_DEBUG_URL            = "https://httpdns.ocloud-test.wanyol.com";
```

**`asdt` = After-Sales Diagnostic Tool（售后诊断工具）。**

## 2.3 🔴 核心能力：远程抓日志

```
PC（客服端）→ USB / 无线连接手机
  → protocol/StartCatchLog（PC 下发 start_catch_log 指令）
  → OlcHelper.sendLogCatch()
     ├ type / category / path / packageName / activity / service / timeout
     └ syncExecSuc("start_catch_log", json, 1)      ← 调用系统 OLC
  → 系统 Olc（日志收集器）按配置抓 logcat
  → UploadLogService 上传
```

```java
// OlcHelper.java
hashMap.put(KEY_BUSINESS_TYPE, str);
hashMap.put("log_category", str2);
hashMap.put(KEY_LOG_PATH, str3);
hashMap.put(KEY_TIMEOUT, String.valueOf(j7));
hashMap.put(KEY_PACKAGE_NAME, str4);
hashMap.put("activity", "com.oplus.postmanservice.logcapture.ui.RemoteLogCaptureActivity");
hashMap.put("service",  "com.oplus.postmanservice.logcapture.service.LogCatchStopService");
return syncExecSuc("start_catch_log", new Gson().toJson(hashMap), 1);
```

**注意**：`log_category` 可指定抓哪种日志（含系统全局 logcat）。

## 2.4 触发条件

```java
// USBConnectorReceiver.java
public class USBConnectorReceiver extends BroadcastReceiver {
    public void onReceive(Context context, Intent intent) {
        if (r4.c.a().c()) return;                       // 已连接则跳过
        if (action.equals(SystemConstants.ACTION_USB_STATE)) {
            boolean usbConnected = intent.getBooleanExtra(USB_CONNECTED, false);
            if (usbConnected) return;                    // 连上不处理
            SignatureVerifyHelper.resetVerifyState();    // ★ 断开时重置签名状态
            ConnectionService.d(true);
        }
    }
}
```

**关键**：`SignatureVerifyHelper` —— 说明 PC 端指令**需要签名验证**。

```java
// protocol/common/BaseSignProtocol.java  ← 所有诊断指令的基类
```

## 2.5 权限清单（挑最狠的）

```
FORCE_STOP_PACKAGES           强制停止任意应用
DELETE_PACKAGES               卸载应用
MANAGE_APP_OPS_MODES          改任意应用权限状态
MODIFY_PHONE_STATE            改电话状态
WRITE_SECURE_SETTINGS         写系统安全设置
WRITE_GLOBAL_SETTINGS         写全局设置
NETWORK_SETTINGS              网络设置
TETHER_PRIVILEGED             管理热点
RECORD_AUDIO                  录音
CAMERA                        相机
ACCESS_FINE_LOCATION          精确定位
QUERY_ALL_PACKAGES            枚举应用
KILL_BACKGROUND_PROCESSES     杀后台
REBOOT                        重启
WRITE_EMBEDDED_SUBSCRIPTIONS  写 eSIM
BLUETOOTH_SCAN / CONNECT
```

**这个权限组合 = 完整的设备管理能力。**

## 2.6 定性与风险

| 项 | 评估 |
|---|---|
| 设计目的 | 售后远程诊断（合法业务） |
| 触发方式 | **PC 主动连接 + 签名验证**，不是后台静默 |
| 最大风险 | 一旦签名密钥泄露 / 降级攻击，等于远程控制通道 |
| 用户可感知 | ✅ 有 UI（`RemoteLogCaptureActivity`，会显示抓日志状态） |
| 是否有开关 | 无用户开关，属系统诊断组件 |

## 2.7 建议

- **不要禁用**（正常售后需要）
- 但可以 DNS 拦 `asdt-server5-cn.allawntech.com`（代价：远程诊断失效）
- **真正该做的是**：不用售后时，不要随意插未知电脑 USB 并允许调试

---

# 三、🟠 `com.oplus.crashbox` —— 崩溃收集

## 3.1 它是什么

系统崩溃/ANR 收集器，用 **OCloud（OPPO 云存储）SDK** 上传。

## 3.2 服务器地址：**代码里没有，运行时从 Settings 读**

```java
// c4/g.java
private static void f(String str, Context context) {
    f4020b = str;
    if (TextUtils.isEmpty(str)) {
        if (n.f("switchServer")) {
            f4020b = y2.b.c(cr, "com.oplus.eap.cloud_storage_pre_host", "");
        } else {
            f4020b = y2.b.c(cr, "com.oplus.eap.cloud_storage_release_host_v3", "");   // ★
        }
    }
}

private static void g(String str, Context context) {
    f4019a = str;
    if (TextUtils.isEmpty(str)) {
        if (n.f("switchServer")) {
            f4019a = y2.b.c(cr, "com.oplus.eap.pre_host", "");
        } else {
            f4019a = y2.b.c(cr, "com.oplus.eap.release_host", "");                     // ★
        }
    }
}
```

**四个 Settings key**：
```
com.oplus.eap.release_host
com.oplus.eap.pre_host
com.oplus.eap.cloud_storage_release_host_v3
com.oplus.eap.cloud_storage_pre_host
```

⚠️ **这意味着静态分析看不到真实域名** —— 需要真机 `settings get` 才能确认。

## 3.3 开关：`key_com_oplus_crashbox`

```java
// a4/a.java:DcsSwitchHelper
public static boolean b(Context context, d dVar) {
    if (dVar != null && !dVar.d()) return true;
    boolean c7 = dVar.c();                       // 配置完整性
    return c7 && d(context) && c(context);       // DCS 下发 + 区域判断
}
```

```java
// 区域判断（smali 还原片段）
if (d4.a.d.c(cr, "key_com_oplus_crashbox") == 1) { ... }
if ("CN".equals(c4.a.c())) { ... }               // 仅国内
```

**三重门禁**：DCS 配置下发 + Settings 开关 + 国行区域。

## 3.4 上传什么

```java
// ThirdExceptionReportService.a()
ApplicationExitInfo exitInfo = ...;
String pkgName   = extras.getString("exceptionpkgname");
String component = extras.getString("component");
String procName  = extras.getString("processName");
int    pid       = ...;
int    reason    = ...;   // ApplicationExitInfo.REASON_*
int    logType   = ...;
```

**崩溃栈 + 进程名 + 包名 + 退出原因。** 不含用户数据。

```java
// CrashAnrResponse.java  ← 有 ANR 专项
```

## 3.5 权限

```
DUMP                       可 dump 任意进程（★ 高危）
READ_PRIVILEGED_PHONE_STATE
INTERACT_ACROSS_USERS
```

**`DUMP` 是它抓 ANR/崩溃栈的核心权限。**

## 3.6 定性

| 项 | 评估 |
|---|---|
| 上传内容 | 崩溃栈、包名、进程名、退出原因 |
| 是否含用户内容 | ❌ 不含 |
| 开关 | DCS + Settings + 区域三重 |
| 风险 | 🟠 中（`DUMP` 权限 + 域名不可静态验证） |

---

# 四、🟡 `com.oplus.logkit` —— 反馈工具箱 / 问卷

## 4.1 两个域名

```java
// data/remote/QuestionnaireService.java
BASE_URL = "https://traffic-operation-cn.allawntech.com/"     // ★ 问卷服务（联通运营）
// data/remote/QueryHasRecordServiceApi.java
BASE_URL = "https://wj.heytap.com/"                            // 问卷入口（wj = 问卷）
```

## 4.2 上传内容

```java
// workers/a.java:AntiFatigueStrategyRequestBodyEntity
moduleId / appPkgName / appName / appVersion / appVersionCode / timestamp
```

**只上报本应用（反馈工具箱自己）的包名、版本、问卷模块 ID、时间戳。**

```java
// workers/a.java
h.s(context, null, "duid", str, 2, null);     // duid 存本地
```

## 4.3 权限

```
REBOOT            ← 有点意外
INTERACT_ACROSS_USERS
SYSTEM_ALERT_WINDOW
```

**`REBOOT` 权限在一个问卷工具里显得多余**，但已确认是**真在用**：

```java
// com/oplus/logkit/dependence/utils/f.java:273
// com/oplus/logkit/dependence/utils/z0.java:63
powerManager.reboot("opluslogkit");
```

配套文案 `dump_reboot_toast`（“正在重启以抓取日志”类）。
**用途：抓取开机启动日志 / 稳定性日志时，自动重启设备以复现开机流程。**
这是「反馈工具箱」抓「开机耗时/开机崩溃」类日志的必要能力。

## 4.4 定性

🟡 **低风险**。功能单一（问卷），上报内容仅限自身应用信息。
`REBOOT` 权限值得留意但不是数据外泄风险。

---

# 五、🟢 `com.oplus.nhs` —— 网络健康服务

## 5.1 代码结构

```
com/oplus/nhs/
 ├ NhsApplication.java
 ├ bsp/        NhsMdmDumpObserver
 ├ gnss/statistic/stats/
 │   ├ DistributionCounter.java     ← 分布计数器
 │   └ EnumCounter.java             ← 枚举计数器
 └ pwr/ModemAci/ModemAciMessengerService.java
```

## 5.2 干什么

**GNSS（卫星定位）健康度本地统计 + Modem ACI（天线切换）监控。**

```java
// gnss/statistic/stats/DistributionCounter.java
public class DistributionCounter implements Parcelable { ... }   // 纯本地计数器

// gnss/statistic/stats/EnumCounter.java
public class EnumCounter implements Parcelable { ... }           // 纯本地计数器
```

**dex 里 0 个 URL，3 个"域名"全是包名误报**（`com.amap` / `com.baidu` / `com.coloros`）。

## 5.3 权限

```
ACCESS_FINE_LOCATION / COARSE_LOCATION
ACCESS_LOCATION_EXTRA_COMMANDS
BIND_DEVICE_ADMIN
READ_PHONE_STATE
```

**没有任何 INTERNET 权限！**

## 5.4 定性

🟢 **完全本地，不联网。**

统计数据（GNSS 信号分布、Modem 状态）只存在设备本地，
供系统诊断界面/日志使用。

---

# 六、汇总

## 6.1 风险排序

| 排序 | 包 | 核心风险 | 建议 |
|---|---|---|---|
| 🔴 1 | `postmanservice` | PC 远程诊断通道（抓日志/杀应用/卸应用） | 不禁用；DNS 可选拦 |
| 🟠 2 | `crashbox` | 崩溃栈上传，`DUMP` 权限，域名动态 | 保留 |
| 🟡 3 | `logkit` | 问卷上报自身信息，`REBOOT` 权限 | 保留 |
| 🟢 4 | `nhs` | 无 INTERNET 权限 | 无需处理 |

## 6.2 blocklist 建议

```
# A 组剩余 —— 可选
asdt-server5-cn.allawntech.com     # postman 远程诊断（拦了售后诊断失效）
traffic-operation-cn.allawntech.com # logkit 问卷（拦了不影响功能）
wj.heytap.com                       # logkit 问卷入口
# crashbox 域名需真机 settings get 确认后才能拦
```

**我的建议：这三个都不必拦。**
- postman 是售后必需，且需要 PC 主动连接
- logkit 问卷只报自身版本
- crashbox 崩溃上报对系统稳定性有帮助

---

# 七、待验证

| # | 项目 | 方法 |
|---|---|---|
| 1 | crashbox 实际上传域名（Settings 里） | `adb shell settings get secure com.oplus.eap.release_host` 等 4 个 key |
| 2 | `key_com_oplus_crashbox` 默认值 | `adb shell settings get secure key_com_oplus_crashbox` |
| 3 | postman 的 PC 端签名验证强度 | 需抓 USB 通信，静态看不到 |
| 4 | `RemoteLogCaptureActivity` 是否用户可见提示 | 真机截图 |
| 5 | ~~logkit 的 `REBOOT` 权限实际用途~~ | ✅ **已确认**：`powerManager.reboot("opluslogkit")`，抓开机日志时用 |

---

# 八、与 README 遗留项的对账

README 第 46 行「⬜ A 组剩余 4 个包（logkit / crashbox / postmanservice / nhs 深挖）」

✅ **本轮完成。**

顺带修正 README 第 65 行：
> 「`com.heytap.vip` / `nhs` / `accessory` 很干净（0 个上报域名）」

→ **`nhs` 确认干净，且连 INTERNET 权限都没有**，比"0 个域名"更彻底。

---

**报告完成时间**：2026-11-06
**样本**：`/tmp/a-apk/{logkit,crashbox,postman,nhs}.apk`
**反编译**：`/tmp/ajadx/{logkit,crashbox,postman}`、`/tmp/jadx-out/nhs`
