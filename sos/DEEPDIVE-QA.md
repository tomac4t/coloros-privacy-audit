# 报警辅助 / SOS —— 七个追问的深入核查

承接 `README.md`。本文逐条回答七个问题，全部有代码出处。

---

## 1. 短信通道为什么发给 `1069030089933`？文案说的是发给紧急联系人

### 结论：**这是两条完全独立的链路，我把它们混在一起说过了，这里纠正**

| | 自动发送位置信息 | 报警辅助 |
|---|---|---|
| UI 开关 key | `pref_key_sos_send_message_merge` | `pref_key_alarm_assistance` |
| 接收方 | **你的紧急联系人** | **接处警中心（经位置网）** |
| 短信发往 | 你通讯录里存的号码 | **`1069030089933`**（固定接入号） |
| 短信号码来自 | `SOSUtils.getMyEmergencyContacts()` → `SmsManager.sendTextMessage(联系人号码, …)` | `prefs["sms_platform_number"]`，默认 `1069030089933` |
| 短信内容 | 明文：`【SOS 紧急联络】我遇到了紧急情况…点击链接查看我的位置：https://uri.amap.com/marker?position=lat,lon` | **二进制/RSA 加密**，接处警系统专有格式 |
| 代码位置 | `ee/a.java:143 h()` → `fe/a.java:90 i()` | `com/oplus/sos/utils/g.java:190 n()` |

所以：

- **"自动向你的紧急联系人发送"** → 对应 `自动发送位置信息` 开关，发给你存的联系人，走普通短信，
  位置是一个**高德地图链接**（`uri.amap.com/marker?position=`），不含 Wi-Fi MAC。
- **发给 `1069030089933`** → 对应 `报警辅助` 开关，发给位置网的短信网关，
  是给接处警中心用的机器可读格式。

`1069030089933` 是 1069 段增值电信短信接入号（1069 + 企业代码 030089933）。

### ⚠️ 但这里确实有一个文案问题

`报警辅助` 的说明文字是：

> 「拨打 110、120、119、122 时，自动向**接处警中心**发送当前位置等信息」

这是准确的。而 `自动发送位置信息` 的说明是：

> 「紧急情况下，自动向你的**紧急联系人**发送附带当前位置等信息的求助短信」

也是准确的。

**两个文案都对。** 我上一轮把它们各自描述的功能混在一起说成"文案说发给联系人但实际发给 1069…"，
这是我的表述错误，向你更正。

### 但真实存在的问题是这个

`自动发送位置信息` 发出去的短信里，位置是**高德地图链接**（`uri.amap.com`）。
也就是说：**你发给紧急联系人的位置，会经过高德的服务端**（用户点开链接才真正加载，但链接本身已经暴露了坐标）。

这个在文案里完全没提。用户以为是"一条带坐标的短信"，实际是一个指向第三方地图服务的 URL。

---

## 2. `disaster.romtest.wanyol.com` 明文 HTTP —— 是我发现的，还是 App 真的这么发？

> 你提出的三个疑问都是对的，上一轮那段写得很含糊、且真的自相矛盾。重写如下。

### 先回答三个疑问

**疑问 1：“取决于运行时开关” vs “零售机不走这条”，矛盾吗？**

不矛盾，但我写得太模糊了。“这条”指的是 **`disaster.romtest.wanyol.com` 这条内网测试链路**。

完整意思应该是：

| 层面 | 事实 |
|---|---|
| APK 里 | **带**了测试域名和明文放行配置（静态存在，确定的） |
| 运行时 | 用不用它，由一个**隐藏的偏好开关**决定 |
| 零售机 | 这个开关默认 `false` → **不用测试域名，用正式 HTTPS** |

两句合并成一句不会矛盾，只是我没说清“这条”指什么。

**疑问 2：“这是唯一一条 domain-config” —— 所以允许明文？**

把两件事拆开就清楚了：

```xml
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">      <!-- ① 只对这一个域名放开 -->
        <domain includeSubdomains="true">disaster.romtest.wanyol.com</domain>
    </domain-config>
    <!-- ② 没有 <base-config>，所以全局走 Android 9+ 默认值 -->
</network-security-config>
```

- ① **只有 `disaster.romtest.wanyol.com` 及其子域允许明文 HTTP**
- ② **其他所有域名仍然禁止明文**（因为没有 `base-config`，走系统默认：Android 9+ 默认 `cleartextTrafficPermitted=false`）

所以答案是：**“允许明文”——但只对那一个内网测试域名允许，不是全局放开。**

**疑问 3：“零售机上 `x()` 返回 false，走 HTTPS 正式域名” —— 是这意思吗？**

**是的，就是这个意思。** 正常国行零售机走的是：

```
https://disaster.coloros.com/aidCard/upload
```

而不是测试域名。而且官方 CA 验证，不会明文。

### 那 `x()` 到底看什么？（这才是关键）

```java
// od/d.java:300
public static final boolean x() {
    return PreferenceManager.b(...).getBoolean("test_key_for_first_aid_info", false)
        || v2.d();
}

// com/oplus/sos/utils/v2.java:28
public boolean d() {
    return PreferenceManager.b(...).getBoolean("test_key_for_sos", false);
}
```

两个条件：

| 键 | 默认值 | 存在哪 |
|---|---|---|
| `test_key_for_first_aid_info` | `false` | `com.oplus.sos_preferences` |
| `test_key_for_sos` | `false` | 同上 |

而 `PreferenceManager.b(context)` 走的是：

```java
context.getSharedPreferences(context.getPackageName() + "_preferences", 0)
// → /data/data/com.oplus.sos/shared_prefs/com.oplus.sos_preferences.xml
```

### 重要：我查过，App 自己从来没写过这两个键

全包搜 `putBoolean("test_key`，**一处都没有**。也就是说：

- 没有 UI 入口
- 没有广播
- 没有 adb 命令
- 代码里也没有默认写入

**只有手动改这个 xml 文件，或者工程机刷特定版本时预置，才可能为 true。**

这也意味着：**零售机上这两项永远是 false，`x()` 永远 false，永远走 HTTPS 正式域名。**

### 修正后的结论

| 说法 | 对不对 |
|---|---|
| “包里带着一个允许明文 HTTP 的测试域名配置” | ✅ 对，静态确定 |
| “你的手机正在明文上传医疗信息” | ❌ 错，需要手工改 prefs 才会发生 |
| “这是安全漏洞” | ⚠️ 准确说是**发布卫生问题**：不该带的东西带进生产包了 |
| “可被利用吗” | ⚠️ 需要先能写 `/data/data/com.oplus.sos/shared_prefs/`，即需要 root。有 root 的话威胁已经很大了，这一条不算增量风险 |

### 我说的“是我发现的”到底指什么

指：**我是从反编译的 `res/xml/network_config_for_test.xml` 里静态看到的**，
不是从流量里看到的。你的手机不会因此真的发明文。

---

## 3. "每收到一次定位回调就上报一次"—— 谁回调的？总共几次？

### 谁回调

`android.location.LocationManager` → `LocationManagerHelper` 内部的 `LocationListener.onLocationChanged()`。
两个 provider 都在监听：

- `requestLocationUpdates("gps", …)` —— `onLocationChanged` 由 GPS 芯片/HAL 驱动
- `requestLocationUpdates("network", 120000L, …)` —— 由网络定位（Wi-Fi/基站）驱动，**最小间隔 120 秒**

### 实际上报几次 —— 有节流，不是每次都发

`LocationManagerHelper.onLocationChanged()`（第 278 行）→ `b(location, location2)`（第 225 行）：

```java
private void b(Location location, Location location2) {
    boolean inCall = ed.a.c().f11479a.e();
    // 三个条件满足任一才上传：
    if (f9951h /*首次定位*/ || I(location2) /*位移够大*/ || !inCall /*已挂断*/) {
        ed.a.c().e(ed.l.a(location));    // ← 这里才真正发
    }
    ...
}
```

`I(location)` 就是距离判据（第 417 行）：

```java
double dist = F(lastLat, lastLon, lat, lon);
if (f9952i != 1) needUpload = dist >= 100.0;   // 报警辅助(type=1) 用 100 米
else             needUpload = dist >= 50.0;    // 其他类型用 50 米
```

### 所以实际次数是

| 情况 | 上报次数 |
|---|---|
| 通话中你**没动** | 基本只有 **1 次**（首次定位成功后） |
| 通话中你**移动了 ≥100 米** | 每移动 100 米 **+1 次** |
| **挂断后** | 还会补发 **1 次**（`!inCall` 分支），然后 `N()` 停服务 |
| GPS 一直拿不到点 | 45 秒超时 → **0 次**，上报 `LOCATION_TIMEOUT` 埋点 |
| 通话超过 1 分钟 | 每分钟还会有一次"心跳式"上报（`postDelayed(this.f9949f, MILLS_OF_MIN)`） |

上限：`X()` 里有 10 分钟窗口判断（`currentTimeMillis - f9944a >= 600000`），
但**没有硬性次数上限** —— 长时间通话 + 持续移动，理论上可以发几十次。

我上一轮说"每收到一次回调就上报一次"**不准确**，实际是**距离节流（100 米）**。
向你更正。

---

## 4. `WRITE_SECURE_SETTINGS` 到底是什么权限？

### 权限本身

`android.permission.WRITE_SECURE_SETTINGS` 是 **signature|privileged** 级权限，允许**读写 `Settings.Secure` 表**。

`Settings.Secure` 是安卓里最敏感的那张表，存着：

| 键（举例） | 含义 |
|---|---|
| `android_id` | 设备唯一标识 |
| `enabled_accessibility_services` | 无障碍服务（**可被用来做自动化点击、读屏**） |
| `default_input_method` | 默认输入法（**可换成恶意键盘**） |
| `install_non_market_apps` | 是否允许装未知来源 |
| `mock_location` | 模拟位置 |
| `adb_enabled` | USB 调试 |
| `development_settings_enabled` | 开发者选项 |

拿到这个权限 = **能静默改掉上面任意一项**。

### 这个 App 用它做什么

我全量搜了 `com/oplus/sos` 包里的写入点，一共 3 处：

```java
// 1) utils/r2.java:44 —— 退出"专注模式/勿扰"
Settings.Secure.putInt(context.getContentResolver(), "exit_zen_mode", 2);

// 2) utils/c.java:161 —— 通用写入，key 由调用方传入
Settings.Secure.putInt(contentResolver, key, value);

// 3) utils/c.java:155 / 167 —— 同上，写 Settings.Global / Settings.System
```

第 1 处是明确用途：SOS 触发时**强制退出勿扰模式**，让铃声能响。合理。

第 2、3 处是 `AddonSupportApiManager` 里的通用封装：

```java
public static final boolean j(ContentResolver cr, String key, int value) {
    return g(30, 1) ? Settings.Secure.putInt(cr, key, value) : p9.b.a(key, value);
}
```

`key` 和 `value` **由调用方传入，代码里没有白名单**。这是个通用写入通道，
虽然当前调用点都是内部常量，但权限粒度给得太宽。

### 评价

- **逐个看得见：** 我搜到的所有写入点是 3 个，`key` 都是常量或内部来源，没发现恶意行为
- **权限给得过宽：** 为了"退出勿扰"这一个场景，申请了全表写权限。更合适的做法是
  用 `NotificationManager.setInterruptionFilter()` 或 `oppo.permission` 限定字段
- **风险等级：中。** 不是"恶意后门"，但属于权限最小化没做到位。
  任何能 hook 这个 App（或用同签名组件）的攻击者，都能借这个通道改 `android_id` 等关键设置。

---

## 5. 不开启报警辅助，会不会发基站定位？

### 结论：**不会。关了就一个字节都不发**

分三层看：

**第一层：`报警辅助` 关了，整条链路不启动**

`xc/c.java:271` 的 `isSupportReport()` 只是区域判断，真正的开关在：

```java
// SOSEmergencyCallSettingFragment 开关逻辑
case "pref_key_alarm_assistance":
    if (!booleanValue) {       // 关掉
        r0(l, false);          // 撤回协议
        le.b.b();              // 停服务
    }
```

同时 `x.h().l()` 读的是 `key_com_oplus_sos_alarm_assistance`，false 时
`EmergencyCallReceiver.b()` 里的 `x.h().l() || z12` 判断不通过 → 直接 return。

**第二层：这个 App 根本不采基站信息**

我搜了 `com/oplus/sos` 全包，**没有一处** `getCellLocation()`、`getAllCellInfo()`、
`TelephonyManager.getCellLocation` 调用。它只用：

- `LocationManager.getLastKnownLocation("gps"/"network")` ← 系统给的坐标
- `WifiManager.getScanResults()` ← 周边 Wi-Fi MAC

`network` provider 的坐标**由系统的网络定位服务（`com.oplus.location`）算出来**，
算的时候用了基站 + Wi-Fi，但那是**系统定位服务**做的，不是这个 App，
而且结果只是一个经纬度，基站 ID 不会传出去。

**第三层：真正发基站的是运营商，不是你手机**

这一点很重要：

- **你打 110，运营商侧本来就能做基站定位**（三角测量 / Timing Advance），
  精度 100–500 米，这是**不需要手机配合**的。全球所有蜂窝网络都是这样。
- 报警辅助做的事情是：把**比基站更准的 GPS 坐标 + Wi-Fi 指纹**主动送到接处警平台上。

所以：**关了报警辅助 ≠ 接处警看不到你的位置**。
它退回到"运营商基站定位"这个基线，精度差很多（室外几百米、室内可能不可用），
但通话记录 + 基站 ID 依然是完整存在的。

---

## 6. 每个功能的选择退出点在哪

### 6.1 报警辅助

| 退出方式 | 路径 | 效果 |
|---|---|---|
| 关开关 | 设置 → SOS 紧急联络 → 位置共享 → **报警辅助** 关 | 不加区域限制地停用；同时撤回协议 |
| 撤回协议 | 同上 → 「关于报警辅助」→ 撤回 | `e0()` 清 `alarm_assistance_version` = -1 |
| 撤销权限 | 设置 → 应用 → SOS 紧急联络 → 权限 → 位置 / 短信 | 功能会引导你重新授权 |
| 卸载/禁用 | `adb shell pm disable-user --user 0 com.oplus.sos` | ⚠️ **会把 SOS 紧急呼叫一起废掉** |

**代码验证**（`c0.e0()`）：
```java
public final void e0() {
    W(false);      // sos_alarm_assistance_license = false
    X(-1);         // alarm_assistance_version = -1
}
```
关掉后 `c0.L()` 返回 -1，`xc/c.j()` 里 `h() >= 2` 不成立 → 走不了。

### 6.2 自动发送位置信息

- 同一页面顶部开关 `pref_key_sos_send_message_merge`
- 关掉后 `c0.V()` 返回 false，`ee/a.java` 的发短信流程不启动
- 但**长期未使用 / 低电量**两条短信仍有独立开关（`pref_key_longtime_no_used_auto_warning`、`switch_key_lowbattery_settings`）

### 6.3 医疗信息

- 设置 → SOS 紧急联络 → **个人医疗信息** → 清空 / 不填
- ⚠️ **没有独立开关**。它跟着"报警辅助"一起生效：
  `AlarmAssistanceManager` 判定 `FirstAidInformationPrefs.L()`（是否有内容）就上传。
  想让它不上传，**只能把填的内容删干净**。

  这是我上一轮说的"文案没提"的具体落点 —— 而且**连退出方式都没有独立的**。

### 6.4 地震预警（顺带）

- `pref_key_natural_disasters_warning`，有独立开关和独立协议

### 6.5 服务端抑制

- `checkSuppressConfig()`：服务端可下发 `suppressEmergencyAssistant=true` 静默关掉
- **用户看不到、也无法关闭这个远程开关**

---

## 7. 三个深挖点

### 7.1 报警辅助埋点：完整字段

埋点走 `OplusTrack.onCommon()`（ColorOS 统一埋点 SDK，就是我们之前审计的"四件套"那条管道）。

事件 ID 全部带前缀 `20160`，实际调用形式 `onCommon(ctx, "20160", "20160" + page, "20160" + eventId, map)`：

| 事件 | 含义 | 触发点 |
|---|---|---|
| `2107` | 用户点击开关 | `SOSEmergencyCallSettingActivity:94`、`AlarmAssistanceNotificationReceiver:44` |
| `2108` | 报警辅助触发 | `xc/c.java:268` |
| `2109` | 报警辅助上报结果（4 种） | `fd/b,c,d,e` |
| `2110` | 医疗信息上报结果（4 种） | `fd/g,h,i,j` |
| `1025` | 协议同意/拒绝 | `we/d.java:83` |

#### `2108`（触发）字段

```java
HashMap:
  "number"                 = "Police" | "Fire" | "Medical" | "Traffic"
  "service_provider_used"  = "weizhiwang" 或 "weizhiwang,gongxinbu"
```

`service_provider_used` 由协议版本决定（`we/d.i()`）：

```java
StringJoiner j = new StringJoiner(",");
j.add("weizhiwang");                    // 深圳位置网
if (version >= 2) j.add("gongxinbu");   // 中国信息通信研究院
```

#### `2109` / `2110`（结果）字段

```java
"send_result"          = "yes" | "no"
"send_channel"         = "network" | "sms"
"send_time"            = (now - 拨号时刻) / 1000        // 秒级
"service_provider_used"= "weizhiwang[,gongxinbu]"
"response_msg"         = <见下>
"send_mode"            = "normal" | "tiantong_satellite"
"current_call_status"  = String.valueOf(TelephonyInterfaceManager.e())
```

#### `response_msg` 里到底放什么

这是最关键的，两个分支（`g.java:253 r()` 和 `:255 q()`）：

**成功分支**（`g.r()`）：
```java
ed.r resp = ed.r.e(jsonObject);          // 解析 {"responseCode":int, "body":String, "errorMsg":String}
if (resp.d())                            // responseCode == 200
    str = resp.a();                      // ← body 原样放进 response_msg
else
    str = resp.c() + "," + resp.b();     // ← errorMsg + "," + body
```

**失败分支**（`g.q()`），即网络异常：
```java
str = String.valueOf(volleyError.networkResponse.statusCode);   // ← 只有 HTTP 状态码
```

所以 `response_msg` 的实际内容：

- 成功 → **服务端返回的 `body` 字段，原样，未截断**
- 业务失败 → `errorMsg,body`
- 网络失败 → `"404"` / `"500"` 之类

`body` 是位置网服务端自定义的字符串，从代码里看不出格式 —— 要看真实流量才知道。
**考虑到埋点会发到 OPPO 的统计服务器，服务端业务报错信息被带进埋点这件事本身值得注意**
（可能包含内部错误码、请求 ID、甚至部分回显数据）。

#### `send_mode` 和卫星

```java
"send_mode" = (h.f10858a.g() == 2) ? "tiantong_satellite" : "normal"
```

`tiantong_satellite` = **天通卫星模式**（`qe/l.java` 的 `SatelliteWorkModeConfig`）。
这个模式下 `suppressEmergencyAssistant = true` —— 即**卫星模式下报警辅助默认被抑制**。

另外 `SOSHelperApp` 里引用 `com.huania.sdk`（"华尼亚"SDK），是卫星通信那套。

### 7.2 `auid_value` 怎么来的，能不能重置

#### 生成方式

```java
// SOSHelperApp$b.run()
HeytapIDSDK.init(context);
if (HeytapIDSDK.isSupported()) {
    String auid = HeytapIDSDK.getAUID(context);
    g1.e(auid);              // → prefs.put("auid_value", auid)
}
```

`HeytapIDSDK` 是**欢太（HeyTap）账号体系的设备标识 SDK**，和 OPPO/一加账号绑定。
`getAUID()` 返回的是账号维度的设备 ID（Account-scoped Unique ID），不是 Android ID。

缓存位置：`PreferenceManager` 的 `auid_value` 键，由 `g1.e()` 写入。
上传到 `uploadCaseInfo` 的 `deviceId` 和医疗卡片的 `deviceAuid` 都是它。

#### 能不能重置

| 方法 | 效果 |
|---|---|
| 清除 SOS 紧急联络的数据 | 只是 `auid_value` 被清空，**下次 `HeytapIDSDK.getAUID()` 会返回同一个值** |
| 退出欢太账号 | 会变（账号维度） |
| 恢复出厂 / 换账号 | 会变 |
| 改 `android_id` | **不影响** —— 它不是从 android_id 派生的 |

结论：**这个 ID 跟账号走，不是能靠清数据重置的。** 想摆脱它只能不登录欢太账号。

代码里也没有任何"重置 auid"的入口。

### 7.3 `disaster.coloros.com` 的响应里能看出转发给谁吗

**不能。** 从反编译里看不到。

原因：

1. 客户端只解析三个字段：`responseCode`、`body`、`errorMsg`（`ed/r.java:35-37`）
2. `body` 内容直接进埋点，**客户端不做任何语义解析**
3. 服务端的转发逻辑（位置网 → 接处警平台 → 具体接入的公安/消防/急救中心）
   全在 `disaster.coloros.com` 后端，反编译看不到

能推断的只有这些：

- 服务商有两个：`weizhiwang`（深圳位置网）、`gongxinbu`（中国信通院），
  协议 v2 之后两家都在链路上
- 请求体里有 `channelName: "OPPO"`、`channelNo` —— 说明平台按渠道（厂商）区分
- 有 `nationCode: "3166-2:CN"` —— 说明是面向全国的分发

**要真看清转发链路，只有两个办法：**
1. 抓一次真实上报的响应（需要你手机 + 代理）
2. 查位置网 / 信通院的公开资料（"报警辅助"这类业务是应急管理部推的，搜 "位置网 报警辅助 接处警" 能找到一些）

---

## 更正汇总

上一轮我说错/说得不准的地方，这里统一修正：

| 上一轮说法 | 更正 |
|---|---|
| "短信通道发给 1069…，但文案说是发给紧急联系人" | **两个不同功能**：紧急联系人短信是另一个开关，内容是高德链接；1069 是报警辅助专用 |
| "每收到一次定位回调就会上报一次"（README 中亦有此表述） | 有 **100 米位移节流**，静止时基本只发 1 次 |
| "测试域名和明文 HTTP 配置进入了正式包（暗示在用）" | 配置在包里，**但零售机不走这条**（`x()` 开关控制） |

---

## 对 README 的修正（已同步）

README 里这几处直接改掉，避免以后误导：

1. 「四、短信通道」开头补一句：**本通道与「自动发送位置信息」无关，后者发短信给你自己的紧急联系人。**
2. 「定位精度与坐标」里的轨迹描述改为距离节流（100 米 / 50 米）。
3. 「其他发现」第 6 条补：测试域名仅在内测/工程机生效。

## 反复验证过的代码出处

| 结论 | 文件:行 |
|---|---|
| 两个开关的 key | `res/xml/sos_emergency_call_preference.xml` |
| 紧急联系人短信走高德链接 | `ge/f.java:56` `uri.amap.com/marker?position=` |
| 报警辅助短信目标号码 | `com/oplus/sos/utils/SOSUtils.java:319` |
| 100 米节流 | `com/oplus/sos/data/LocationManagerHelper.java:428` |
| 医疗信息上传字段 | `firstaidinformation/data/MedicalAidCard.java` |
| auid 来源 | `SOSHelperApp.java:82` `HeytapIDSDK.getAUID()` |
| 埋点事件表 | `fd/b..j.java`、`we/d.java`、`xc/c.java:268` |
| WRITE_SECURE_SETTINGS 写入点 | `utils/r2.java:44`、`utils/c.java:155-167` |
| 服务端抑制 | `workmode/f.java:24`、`workmode/a.java:91` |
