# 第十四轮（G 组）：系统治理 / 诊断

- **日期**：2026-11-06
- **对象**：8 个包 —— Athena / 耗电监控 / 电池 / 系统服务 / 数字健康 / 网络定位服务 / Qualcomm Location / fused location
- **方法**：APK 权限提取 + dex 字符串域名扫描 + jadx 反编译逐类追踪
- **样本**：`/tmp/app_backup/`，反编译输出 `/tmp/gref/out_*`

---

# 一、结论速览

| # | 包 | 业务域名 | 联网 | 风险定性 |
|---|---|---|---|---|
| 1 | `com.oplus.athena` | **0** | ❌ **完全不联网** | 🟡 权限极高但不出网 |
| 2 | `com.oplus.battery` | **0** | ❌ **完全不联网** | 🟡 权限极高，本地杀手 |
| 3 | `com.oplus.exsystemservice` | 0（只有 Google 广告 SDK 残留常量） | ❌ | 🟢 干净 |
| 4 | `com.qualcomm.location` | **0** | ❌ | 🟢 干净 |
| 5 | `com.android.location.fused` | **0** | ❌（只有 142 个字符串的壳） | 🟢 干净 |
| 6 | `com.oplus.location`（网络定位服务） | **42 个**（高德/腾讯/百度三套 SDK） | ✅ **主动上报** | 🔴 **重点** |
| 7 | `com.coloros.digitalwellbeing`（数字健康） | 3 个真实端点 | ✅ **上传已安装应用列表** | 🔴 **重点** |
| 8 | `com.oplus.powermonitor`（耗电监控） | 1 个 DNS + 运行时下发主机 | ✅ **上传功耗/热日志** | 🟠 中 |

**两个真正的隐私重点：数字健康（上传应用列表）+ 网络定位（三套地图 SDK 上报位置）。**

---

# 二、先说干净的（4 个包）

## 2.1 `com.oplus.athena` —— 权限怪物，但一条网络请求都没有

**它是内存管理/进程杀手/省电策略的核心**（OplusAthenaSystemService）。

**权限清单（挑最狠的）**：

```
REBOOT                     重启设备
MANAGE_USERS               管理所有用户
INTERACT_ACROSS_USERS_FULL 跨用户全权限
SET_PROCESS_LIMIT          设置进程上限
CHANGE_APP_IDLE_STATE      强制 App 进入 idle
GET_TASKS                  查看正在运行的任务
READ_PRIVILEGED_PHONE_STATE 读特权电话状态
QUERY_ALL_PACKAGES         枚举所有应用
ACCESS_NETWORK_STATE       （唯一与网络相关的权限，且只读状态）
```

**联网验证**：

- dex 里 `newCall(` / `openConnection(` / `OkHttpClient.Builder` 出现次数 = **0**
- 之前用 `strings` 扫到的 623 个 `okhttp` 命中，**全是误报**：逐个检查后发现只是
  `import okhttp3.internal.ws.RealWebSocket;` / `Http2` / `Http2Connection` 这类**常量类 import**，
  业务代码没有一处真正建连接。

```java
// 例：com/oplus/athena/client/action/oplusguardelf/l.java（TrafficUtil）
import okhttp3.internal.ws.RealWebSocket;   // ← 只是用了里面的常量
```

**结论**：Athena 不是隐私出口，但它是**权限最危险的系统组件之一**。
真要担心，担心的应该是它能否被别的 App 调用（Binder 接口），而不是它自己上网。

## 2.2 `com.oplus.battery` —— 同样零联网，但能杀你任何 App

**权限（危险度排序）**：

```
KILL_UID                杀死指定 UID 的进程
FORCE_STOP_PACKAGES     强制停止任意包
DEVICE_POWER            直接操作电源状态
MANAGE_APP_OPS_MODES    修改任意 App 的权限状态
WRITE_SECURE_SETTINGS   写系统安全设置
STATUS_BAR / EXPAND_STATUS_BAR  控制状态栏
TETHER_PRIVILEGED       管理热点
READ_PRIVILEGED_PHONE_STATE
BATTERY_STATS
```

**联网验证**：dex 里 URL 只有 2 条 `schemas.android.com`（XML 命名空间），业务域名 **0**。

**结论**：不联网，但是**本地权限最大的组件**。`KILL_UID` + `FORCE_STOP_PACKAGES` 意味着
它可以以系统身份杀掉任何进程，包括输入法（会被重启）、Helper、甚至你的自动化脚本。

## 2.3 `com.oplus.exsystemservice` —— 干净

**权限**：`MANAGE_USERS` / `REBOOT` / `INSTALL_EXISTING_PACKAGES` / `STATUS_BAR` / `WRITE_SECURE_SETTINGS`
（同样权限很高）

**联网验证**：dex 里唯一的外域是

```
https://pagead2.googlesyndication.com/pagead/gen_204?id=gmob-apps
```

这是 **Google Mobile Ads 的 SDK 版本上报常量**，是某个第三方库（`com.oplus.linker.synergy` 附近）
编译时带进来的**死常量**，业务代码没有调用。**实际不联网。**

## 2.4 `com.qualcomm.location` / `com.android.location.fused` —— 零域名

- `com.qualcomm.location`：dex 里只有 `schemas.android.com`，**无任何业务端点**
- `com.android.location.fused`：**整个 APK 只有 142 个 dex 字符串**，是个纯壳，
  真正的逻辑在 AOSP 的 `com.android.location.fused` 系统组件里

---

# 三、🔴 重点 1：`com.coloros.digitalwellbeing`（数字健康）上传应用列表

## 3.1 它做什么（业务层面）

数字健康 = 屏幕使用时间统计。要统计「哪个 App 用了多久」「哪个是游戏」，它需要知道每个 App 的**分类**。

分类逻辑：**本地库查不到 → 问服务器**。

## 3.2 完整调用链

```
WellBeingProvider.fetchGameTypeApp(context)
  └ v1.a.c(context)                     // AppObtain.c()
     ├ x1.b.c(context)                  // 枚举所有已安装应用
     │   └ s.l(context) → queryIntentActivities() → 包名列表
     │       （排除 set.s() 黑名单、g(str) 过滤）
     ├ v1.a.b(...)                      // 先查本地数据库
     │   └ content://.../app_package → 本地分类库命中就移除
     └ 剩下的「本地不知道分类的 App」→ c10（未知列表）
  └ v1.a.d(context, c10.f16079b)        // 对未知列表分批请求云端
     └ v1.a.a(context, list, list2)     // 重试 3 次
        └ x1.a.a(list)                  // AppClassifyServer
           └ x1.a.b(list)               // 超过 50 个就分批
              └ s1.a.d(list)            // ★ 真正发 HTTP
```

## 3.3 ★ 真正上传的代码

```java
// s1/a.java（NetWorkUtils）—— 类名 "DigitalNetWorks"
private String c(List<String> list) {
    if (!k(context) || !l(context)) return "";      // 网络 + 前置条件检查

    String ts = String.valueOf(System.currentTimeMillis());
    // 签名：固定 key + 固定 salt + 时间戳 + 路径 + 长度
    sb2.append("e6e3f0c2f147cceb")
       .append("b619ee4de932fa420360f6ec7621da39")
       .append(ts)
       .append("/security/app-summarys/type")
       .append(sb2.length());

    t params = new t.a()
        .a("oak",  "e6e3f0c2f147cceb")
        .a("sign", b.e(sb2.toString()))
        .a("t",    ts)
        .a("ch",   "2607")                                  // ← 渠道号
        .a("mobile", Uri.encode(Build.MODEL))                // ← 机型
        .a("os",   Uri.encode(Integer.toString(q.a())))      // ← OS 版本
        .a("androidos", Uri.encode(b.b()))                   // ← Android 版本
        .d();

    ArrayMap body = new ArrayMap();
    body.put("pkgs", list);                                  // ★★★ 已安装应用包名列表

    return a(z.a.l("https://api.open.oppomobile.com/security/app-summarys/type")
              .d(params).f(json).a());
}
```

**上传内容**：

| 字段 | 内容 | 敏感度 |
|---|---|---|
| `pkgs` | **该 App 的包名数组**（分批，每批 50 个） | 🔴 **应用清单泄露** |
| `mobile` | 机型（`Build.MODEL`） | 🟡 |
| `os` / `androidos` | ColorOS 版本 / Android 版本 | 🟡 |
| `ch` | 渠道号 `2607` | 🟡 |
| `t` / `sign` | 时间戳 + 签名 | — |

**目的**：服务器返回每个包名的**分类**（游戏 / 社交 / 视频 …），用于「游戏时长限制」等功能。

## 3.4 🔴 更严重：这里有个**禁用了证书校验**的 TrustManager

```java
// s1/a.java:47-84
class C0230a implements X509TrustManager {

    private void a(X509Certificate[] chain, String authType) throws CertificateException {
        if (chain == null) return;                    // ← 空链直接放过
        for (X509Certificate cert : chain) {
            try {
                cert.checkValidity();
                cert.verify(cert.getPublicKey());     // ← ★ 用「自己的公钥」验证自己
            } catch (Throwable ignored) { }           // ← 异常全部吞掉
        }
    }

    @Override
    public void checkServerTrusted(X509Certificate[] chain, String authType) {
        a(chain, authType);                           // ← 永远不抛异常
    }

    @Override
    public X509Certificate[] getAcceptedIssuers() {
        return new X509Certificate[0];
    }
}
```

**这段代码等于完全关闭 TLS 证书校验**：

1. `cert.verify(cert.getPublicKey())` —— 拿证书自己的公钥验自己的签名，**这是个恒真的自签校验**，
   任何自签证书都能通过
2. 异常被 `catch (Throwable ignored)` 吞掉，**校验失败也不报错**
3. `checkServerTrusted` 永远不抛 `CertificateException`

也就是说：**这条上报通道存在被中间人劫持的风险**。任何能劫持 DNS/网络的人都能
伪造一个 `api.open.oppomobile.com` 的假证书，拿到你的**完整应用列表**。

> 注：这段代码的 TrustManager 用于 `h(trustManager)` → `SSLContext.getInstance("SSL")`，
> 需要进一步确认是否被实际用于竖立连接（`f()` 单例里同时有正常 OkHttp 客户端）。
> 但**代码存在本身就是安全缺陷**，即使当前没走这条路。

## 3.5 触发条件

| 条件 | 说明 |
|---|---|
| 什么时候 | `WellBeingProvider` 的 `fetchGameTypeApp` 被调用时（数字健康统计/游戏时长功能） |
| 频率 | 有本地 DB 缓存，**只在遇到「未知分类的新 App」时才请求** |
| 批量 | 每批最多 50 个包名（`if (list.size() <= 50)` 才一次发） |
| 重试 | 最多 3 次（`int i10 = 3`），拿到结果就写入本地库 `w2.d.r(...)` |
| 网络 | 必须联网 |

**实际频率**：装一个新 App → 下次打开数字健康 → 上传一次（1 个包名）。**不是高频上报。**

## 3.6 另外两个端点

```
https://ilighthouse.apps.coloros.com      // 灯塔（A/B 配置/埋点平台），作为备用 host
https://beian.miit.gov.cn                 // 工信部备案链接（常量，不请求）
```

---

# 四、🔴 重点 2：`com.oplus.location`（网络定位服务）—— 三套地图 SDK

## 4.1 它是什么

`com.oplus.location` = ColorOS 的**网络定位服务**，负责「无 GPS 时用 WiFi/基站粗定位」。
它不自己算，而是**接入三家第三方地图 SDK**：

| 供应商 | SDK 包 | 域名数 |
|---|---|---|
| **高德** | `com.amap.location.*` | 12 |
| **腾讯地图** | `o0.*`（`lbs.map.qq.com` 等） | 13 |
| **百度地图** | `com.baidu.location.*` / `v7/e` | 9 |

**这是最值得关注的：一台手机同时内置三家的定位 SDK。**

## 4.2 腾讯定位的上报内容（已确认）

```java
// o0/u0.java:230-268 —— OnlineLocationManager
JSONObject put "bles" : [ {mac, major, minor, rssi, time}, ... ]   // ★ BLE 信标
JSONObject put "wlan" :  {mac, rssi, ssid}                          // ★ WiFi

String url = "https://lbs.map.qq.com/loc?c=1&mars=10&obs=1";
byte[] body = 加密(e10.getBytes("GBK"));      // GBK 编码 + 自定义加密
```

**请求内容**：

| 字段 | 内容 | 敏感度 |
|---|---|---|
| `wlan.mac` | **当前连接的 WiFi BSSID** | 🔴 **可用于物理定位**（WiFi 地理位置库） |
| `wlan.ssid` | **WiFi 名称** | 🔴 **常含家庭/公司名** |
| `wlan.rssi` | 信号强度 | 辅助定位 |
| `bles[]` | 周围所有 **BLE 信标**的 MAC / major / minor / rssi / 时间 | 🔴 **商场/机场室内定位** |

**这就是「WiFi 定位」的原料**：把 SSID+BSSID 发给腾讯，腾讯返回经纬度。
**只要开着网络定位，你周围的 WiFi 名和蓝牙设备就在往外送。**

## 4.3 高德 & 百度

| 端点 | 用途 |
|---|---|
`https://adiu.amap.com/ws/device/adius` | **高德设备 ID 上报**（`adiu` = Adiu 设备标识服务） |
`https://rgeo.amap.com/wps/2014` | 高德逆地理编码 |
`http://cgicol.amap.com/dataPipeline/uploadData` | 高德数据回传 |
`http://aps.testing.amap.com/collection/collectData` | **高德采集数据上报**（测试域名，生产可能也有） |
`https://api.map.baidu.com/reverse_geocoding/v3/` | 百度逆地理编码 |
`https://loc.map.baidu.com/sdk.php` | 百度定位 SDK 主接口 |
`http://blg.map.baidu.com/ofloc/offdis/stat` | 百度离线定位统计 |

## 4.4 触发条件

| 场景 | 是否上报 |
|---|---|
| GPS 已定位成功 | ❌ 不需要网络定位 |
| **GPS 弱/无信号 + 任一 App 请求定位** | ✅ **触发**（WiFi/基站粗定位） |
| 纯 WiFi 环境 | ✅ 上报 WiFi 列表到腾讯 |
| 关闭「位置信息」总开关 | ❌ 系统级关闭 |

**关键**：这不是「某个 App 偷偷定位」，而是**系统定位服务本身**在用第三方 SDK。
任何 App 请求定位（地图、外卖、天气），都可能触发它。

---

# 五、🟠 中：`com.oplus.powermonitor`（耗电监控）上传功耗/热日志

## 5.1 结构

```
com.oplus.powermonitor.standbymonitor
 ├ uploadthermalinfo/UploadHeatEvent      // 发热事件收集
 ├ customlog/CustomLogManagerService      // 自定义日志（1565 行，核心）
 │   ├ TaskRecord / UploadFileRecord      // 任务/文件记录
 │   ├ job/PowerDataSyncJobService        // JobScheduler 定期任务（默认 18 秒间隔起）
 │   └ job/PreCompressionLogJob           // 预压缩
 └ powerstats/diagnostics/MultiSubsystemDiagnostics
```

## 5.2 上传链路

```
PowerDataSyncJobService.onStartJob()
  └ new b(context).start()                // 拿 wakelock
     └ CustomLogManagerService 处理 TaskRecord
        └ t0.d.i(...) → t0.d.l(...) → 发 HTTP
```

```java
// t0/d.java（FileSyncModel）
public static b0 i(e eVar, String str, JSONObject json, String ct, m mVar) {
    a0 body = a0.c(w.f(ct), json.toString());
    if (debug) {
        log("postAsync() url = " + str);
        log("postAsync() body = " + json.toString());   // ⚠️ 调试时会打完整 body
    }
    ...
    return t0.b.d().b(aVar.i(eVar).f(body).j(str).b());
}
```

**Upload 请求头**：

```java
// t0/d.java:260
String ota = SystemProperties.get("ro.build.version.ota");
if (!TextUtils.isEmpty(ota)) aVar.c("OCLOUD-OTA-VERSION", ota);
// u0/o.java, u0/b.java
mVar.d("OCLOUD-BUCKET", bucket);
```

## 5.3 主机是**运行时下发**的（这点要注意）

```java
// u0/p.java —— ServerConfigManager
JSONObject jSONObject = new JSONObject();
jSONObject.put("appId", ...);
jSONObject.put("sdkVersion", "1.1.9");
jSONObject.put("serverVersion", ...);
// 请求：{httpdnsHost}/logservice/v1/get_common_conf
```

```java
// t0/g.java —— 各 API 路径
{host}/logservice/v1/get_access_token      // 取上传 token
{host}/logservice/v1/get_common_conf       // ★ 取服务器配置（含 hostName / bucket）
{host}/logservice/v1/delete                // 删远端文件
```

```java
// t0/c.java —— 第一步解析的是 httpdns
public static String c(Context context) {
    jSONObject.put("regionCode", 区域码);
    jSONObject.put("isOPPOExp", 是否体验版);
    // POST {httpdns}/httpdns/v1/get_region_dns
}
```

**固定域名只有一个**：`https://httpdns.ocloud.oppomobile.com`
（`t0/e.java:10`，`/httpdns/v1/get_region_dns`）

之后的日志上传主机、bucket 全是**服务器下发**的，静态代码里看不到。
**所以 AdGuard 里看到的 eff.com/ocloud 域名可能和这个有关。** —— 这条待真机验证。

## 5.4 上传什么

从类名和字段推断（`UploadFileRecord` / `TaskRecord` / `UploadHeatEvent`）：

- **功耗统计**（`powerstats`）
- **发热事件**（`heatReason:` 开头的字符串缓冲）
- **自定义日志文件**（`CustomLogManagerService` 打包上传）
- 设备 OTA 版本号（请求头）

属于**设备诊断数据**，不是用户内容。但确实是「自动上传」，且**没有用户开关**。

---

# 六、G 组总结：什么才是真问题

## 6.1 风险排序

| 排序 | 包 | 问题 | 你能做什么 |
|---|---|---|---|
| 🔴 1 | `com.coloros.digitalwellbeing` | **上传已安装应用列表** + **TLS 校验被禁用** | DNS 拦 `api.open.oppomobile.com` |
| 🔴 2 | `com.oplus.location` | **WiFi SSID/MAC + BLE 信标**发给腾讯 | 关「位置信息」或 DNS 拦三家域名 |
| 🟠 3 | `com.oplus.powermonitor` | 自动上传功耗/热日志，无开关 | DNS 拦 `httpdns.ocloud.oppomobile.com` |
| 🟡 4 | `com.oplus.athena` | 权限极高（REBOOT/MANAGE_USERS）但**零联网** | 无法处理，属系统核心 |
| 🟡 5 | `com.oplus.battery` | 权限极高（KILL_UID/FORCE_STOP）但**零联网** | 无法处理，属系统核心 |
| 🟢 6 | exsystem / qtiLoc / fused | 干净 | — |

## 6.2 建议补进 blocklist

```
# ===== G 组：数字健康 → 上传应用列表 =====
api.open.oppomobile.com
ilighthouse.apps.coloros.com

# ===== G 组：耗电监控 → 功耗日志 =====
httpdns.ocloud.oppomobile.com

# ===== G 组：网络定位 → 三家地图 SDK（慎用，会影响定位）=====
# 拦了这些，室内/无 GPS 场景定位会失效
# lbs.map.qq.com
# lbs6.map.qq.com
# cs.map.qq.com
# analytics.map.qq.com
# api.map.baidu.com          ← 相册地图也在用
# loc.map.baidu.com
# adiu.amap.com
# aps.amap.com
# rgeo.amap.com
```

⚠️ **定位那组要慎重**：拦了会导致导航、外卖、打车定位失败。
如果只是不想让 WiFi 名外泄，更实际的做法是**关掉系统「位置信息」总开关**，
或用「模糊定位」。

## 6.3 优先级建议

**建议只拦前两个（数字健康 + 耗电监控）**，代价极小：

| 拦的域名 | 影响 |
|---|---|
| `api.open.oppomobile.com` | 数字健康分类改本地已知库，**新装 App 可能被当成"其他"** |
| `ilighthouse.apps.coloros.com` | 灯塔 A/B 配置拉不到，用默认值 |
| `httpdns.ocloud.oppomobile.com` | 耗电监控日志上传失败（本地记录仍在） |

---

# 七、待验证

| # | 项目 | 方法 |
|---|---|---|
| 1 | 数字健康的上报**实际频率**（是否只在装新 App 时） | 真机 AdGuard 日志观察 3 天 |
| 2 | 那个 `C0230a` TrustManager 是否真的用于**生产连接** | 追 `h()` 的调用方，或抓包验证 |
| 3 | 耗电监控的**实际上传域名**（运行时下发，需真机） | AdGuard 日志 + `adb logcat -s FileSyncModel` |
| 4 | 网络定位三家 SDK 哪个是**主用**、哪个只是备用 | 真机观察各域名的请求量 |
| 5 | `com.android.location.fused` 真实逻辑在哪 | 查 AOSP 源码对应组件 |
| 6 | Kennel/Athena 的 Binder 接口是否被第三方 App 调用 | `adb shell dumpsys activity services com.oplus.athena` |

---

# 附录：复现脚本

- `scripts/g_apk_survey.py` —— 单包权限 + 域名扫描
- `scripts/g_survey_all.py` —— 批量 8 包
- `scripts/decompile_g.sh` —— 批量 jadx 反编译到 `/tmp/gref/out_*`

**报告完成时间**：2026-11-06
