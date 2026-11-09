# SOS 紧急联络 / 报警辅助 逆向分析

审计对象：`com.oplus.sos`（SOS 紧急联络），APK 18.4 MB，来自一加 ColorOS 14 出厂系统（`app_backup.zip`）。
入口：设置 → SOS 紧急联络 → 位置共享。

本文重点是「**报警辅助**」（Emergency Services Assistant / `enhanced_service_alarm_assistance`），
顺带把「自动发送位置信息」和同 APK 内其他风险点一起过一遍。

---

## 一、功能架构

```
拨打 110 / 120 / 119 / 122
        │
        ├─ 电话 App 发广播  oplus.action.phone.EMERGERCY_DIALING
        ▼
EmergencyCallReceiver（com.oplus.sos.receiver）
        │  判断：号码是否在 PEM 白名单、是否备案、是否中国内地注册
        ▼
xc.c (ESAssistantManager)  —  统一的调度器
        │
        ├─ 分支 A：网络通道（默认优先）
        │     EmergencyCallService → LocationManagerHelper 持续定位
        │     → ed.a (AlarmAssistanceManager) 每次定位回调 → g.m() 组包
        │     → https://disaster.coloros.com/v4/warning/uploadCaseInfo
        │
        └─ 分支 B：短信通道（无网络 / 取不到本机号）
              g.n() 组二进制包 → RSA 加密 → 7-bit 转义
              → 发短信到 1069030089933
```

关键文件：

| 作用 | 文件 |
|---|---|
| 广播入口 | `com/oplus/sos/receiver/EmergencyCallReceiver.java` |
| 调度器 | `xc/c.java`（`ESAssistantManager.kt`） |
| 组包/加密/上报 | `com/oplus/sos/utils/g.java` |
| 定位服务 | `com/oplus/sos/service/EmergencyCallService.java` + `LocationManagerHelper` |
| 上报结果埋点 | `fd/a..l.java`、`we/d.java` |
| 用户协议文案 | `res/values-zh-rCN/strings.xml` |

---

## 二、触发条件（比说明书严格）

`xc/c.java` 里三道闸门，全部满足才会发：

```java
// 1. 号码必须命中 PEM 配置的紧急号码列表，默认 "110,119,120,122"
String numbers = prefs.getString("emergency_call_numbers", "110,119,120,122");

// 2. 必须是中国内地注册网络
TelephonyManager.getNetworkCountryIso() == "cn"

// 3. 用户必须同意过《报警辅助个人信息保护政策》，且没被服务端抑制
c0.L() >= 2            // 协议版本 must ≥ 2
checkSuppressConfig()  // 服务端可下发“本机型/本批次不要用”
```

另外两个条件影响走哪条通道：

```java
isNetworkAvailable = v0.b(context)              // 有无网络
isVaildMobNum      = h1.k(SOSUtils.getPhoneNumber(context, subId))  // 能否取到本机号码
```

> **注意**：`isSupportReport()` 只要 `getNetworkCountryIso()=="cn"` 就 return true，
> 不看 SIM 归属。所以**插着国内卡漫游到国外，只要注册在 CN 网络，仍会上报**；
> 反之用国内本地网络的境外卡也会上报。

---

## 三、网络通道：发什么

`g.m()` 组装的 JSON（POST `https://disaster.coloros.com/v4/warning/uploadCaseInfo`，
协议版本高时用 v4，否则 v2）：

```json
{
  "nationCode": "3166-2:CN",
  "mobilePrefix": "86",
  "mobile": "<本机手机号>",          // ← 明文
  "emergencyNum": "110",
  "channelName": "OPPO",
  "deviceId": "<auid_value>",        // 华为/OPPO 账号体系里的设备 ID
  "channelNo": "…",
  "clientVersion": "1.0.0",
  "locationList": [
    { "mode": 1, "longtitude": 120.155, "latitude": 30.274, "gmtCreated": 1759... }
  ],
  "netLocation": { "macs": "aa:bb:cc:dd:ee:ff|11:22:33:44:55:66|..." },
  "deviceInfo": { "model": "...", "osVersion": "...", "wifiMac": "...", "accuracy": ... },
  "pushData": "<ECIES 密文，含上面整个 JSON>",
  "aesKey": "<本轮随机 AES 密钥，被 ECIES 加密>",
  "channelNo": "…"
}
```

要点：

1. **外层的 `mobile`、`macs`、经纬度是明文字段**，但真正送出去的完整包在 `pushData` 里
   （ECIES，Tink，Hybrid 公钥硬编码）。
2. `netLocation.macs` = 周边 Wi-Fi BSSID 列表，`g1.c()` 取 `getScanResults()`，
   按信号强度降序、去重、最多 **10** 个。
3. `deviceId` 来自 `PreferenceManager` 的 `auid_value` —— **不是安卓 ID，是 OPPO/华为账号体系的设备标识**，
   换机重装都可能跟着走。
4. 注释里写着 `longtitude`（拼写错误），是真实的字段名，解析时别写对。

### 定位精度与坐标

- `LocationManagerHelper.X()` 同时开两个 provider：
  - `gps` —— 间隔 `f9947d`、最小位移 0、超时 **45 秒** → 超时后上报 `RESULT_REPORT_ALARM_ASSIST_LOCATION_TIMEOUT`
  - `network` —— 最小间隔 **120 秒**、最小位移 0
- **首次定位成功后的 6 秒**（`handler.postDelayed(new c(), 6000L)`）会再做一次处理，
  推测是等第一次 fix 稳定再上报。
- `ed.a.e()` 在每次定位回调里都会触发上报，**不是一个点，是一条轨迹**。
  通话中如果持续坐在不同位置，会连续发多个点给接处警中心。
  （具体节流规则：`LocationManagerHelper.I()` —— **位移 ≥100 米**才再发；
  静止时基本只发首定位 1 次，挂断后补发 1 次。详见 `DEEPDIVE-QA.md` 第 3 节。）
- 如果 App 里有 GCJ-02 坐标，会优先用 GCJ-02（`ed.j` 的 `type=2`），否则 WGS-84 转 GCJ-02。
- 网络通道里 **`mode=1`** 表示用 WGS-84 原始点、由服务端转换的语义（`e(lVar, f())`，`f()` 返回 1 或 2）。
- `X()` 里有 `System.currentTimeMillis() - f9944a >= 600000` 的判断 —— 距上次请求超过 10 分钟才重置某些状态，
  避免同一通话反复初始化。

---

## 四、短信通道：最值得看的一块

> ⚠️ **先澄清一个易混淆点**：本节讲的短信（发往 `1069030089933`）**只属于「报警辅助」**。
> 另一个开关「自动发送位置信息」是**另一条链路**，发给**你自己的紧急联系人**，内容是明文 + 高德地图链接（`uri.amap.com`）。
> 两者互不相干，完整对比见 [`DEEPDIVE-QA.md`](DEEPDIVE-QA.md) 第 1 节。

当 `isVaildMobNum` 为 false（取不到本机号）或网络不通、且 `isReportByNetworkFirst()` 为 false 时走这条。
`g.n()` 的完整结构（`tools/alarm_sms.py` 可解析）：

### 4.1 外层：7-bit 转义（`com/oplus/sos/utils/i2.java`）

```java
byte[] out = new byte[140];
int i = 0, o = 0;
while (i < src.length * 8) {
    if (i % 15 == 0) out[o++] = 0;      // 每 15 bit 插一个 0 结束位
    out[o++] = (src[i/8] >> (7 - i%8)) & 1;
    i++;
}
```

结果 131 字节 → 140 字节，正好能塞进 **1 条长短信**（140 字节 = 20 个 septet 槽位 × 7）。这是为了绕开运营商的二进制短信审核做的特殊编码。

### 4.2 内层：131 字节二进制

| 偏移 | 长度 | 内容 |
|---|---|---|
| 0 | 3 | 魔数 `06 0D 03` |
| 3 | 128 | RSA-1024 加密块（PKCS#1 v1.5） |

RSA 明文（117 字节）：

| 偏移 | 长度 | 内容 |
|---|---|---|
| 0 | 2 | 紧急号码（去区号，`110`/`119`/`120`/`122`） |
| 2 | 2 | 区号（去除前导 0；如 0571 → 571，无区号填 0） |
| 4 | 8 | 纬度 float64 |
| 12 | 8 | 经度 float64 |
| 20 | 8 | 时间戳位域：低 14 位 = 拨号后经过秒数；高位 = 拨号时刻（epoch/1000） |
| 28 | 1 | 标志位：bit0-1 = 上报渠道；bit2 = 是否 120 呼叫 |
| 29 | 1 | SIM 槽位（1/2） |
| 30 | 1 | Wi-Fi 数量 n（≤10） |
| 31 | 7n | Wi-Fi 列表：6 字节 BSSID + 1 字节 RSSI(int8) |

**RSA 公钥硬编码在源码里**（`g.n()` 的字符串常量），1024 位，只用于加密不做签名。

### 4.3 短信发送目标

```
SOSUtils.getSmsPlatformNumber(context)
  → prefs "sms_platform_number"，默认 "1069030089933"
```

`1069030089933` 不是普通手机号，是**增值电信业务短信接入号**（1069 段 + 企业代码）。
这个值还能被 ROM 更新 XML 改写（`ne/c.java` 的 `hot_line_global_number` 分支）。

### 4.4 这条短信里没有手机号

有趣：**短信通道不带手机号**，因为短信本身有发送方号码，接处警中心能直接拿到。
而网络通道必须明文带 `mobile` 才能对上。两套设计思路不同。

---

## 五、医疗信息上报（顺带发现）

用户填的「个人医疗信息」（`first_aid_information`）也会被上传，**在 120 呼叫时自动带上**：

`ed/i.java` 组 `MedicalAidCard`，字段包括：

```
name, gender, bloodType, rhBloodType, height, weight, birthYear,
organDonation, note, medicalDetail, drugDetail, allergyDetail,
mobile, device, deviceAuid, emergencyNum, areaCode, callMillisTime, sendMillisTime
```

上传地址：`https://disaster.coloros.com/aidCard/upload`

加密方式：`AES/CTR/NoPadding`（随机密钥），密钥再用 **ECIES（Tink，hybrid key）** 加密后放在 `aesKey` 字段。

⚠️ 这一块涉及**健康+身份证级别的敏感信息**：血型、病史、用药、过敏、器官捐献意愿、出生年份。
虽然走的是同一家服务商，但**和"位置共享"合成一个开关管理**，开关说明里只写「发送当前位置等信息」，
**没提医疗信息**。这是我认为最需要改进的文案问题。

---

## 六、埋点：每一次紧急呼叫都被打标

`we/d.java` 通过 `OplusTrack`（就是 ColorOS 的统一埋点 SDK）上报：

| 事件 ID | 含义 | 字段 |
|---|---|---|
| `2108` | 报警辅助触发 | `number`(Police/Fire/Medical/Traffic)、`service_provider_used` |
| `2109` | 上报结果 | `send_result`、`send_channel`(network/sms)、`send_time`（毫秒级）、`service_provider_used`、`response_msg`、`send_mode`、`current_call_status` |
| `1025` | 协议同意/拒绝 | `emergency_services_assistant` = agree/disagree |

`2109` 的 `send_time` 是 **`System.currentTimeMillis() - 拨号时刻`**，精确到秒 ——
连"从拨号到上报成功花了多久"都被记录。

这些埋点走 `com.oplus.statistics` 那条链路，和之前审计的埋点四件套同一个管道。

---

## 七、其他发现的问题

### 🔴 1. 公开接口 + 硬编码公钥，任何人可构造上报

`uploadCaseInfo` 是**无鉴权公开接口**，加密只用硬编码公钥。
拿到 APK 就能构造任意 `mobile` + 任意经纬度 + 任意 Wi-Fi MAC 列表的合法上报包。

风险：**伪造报警信息**灌入接处警系统。虽然实际效果取决于服务端校验，但客户端零防护。

### 🔴 2. Wi-Fi MAC 用于定位，不经二次确认

`getScanResults()` 取周边 Wi-Fi BSSID —— 这是经典的**Wi-Fi 指纹定位**手法（类似 Google/Apple 的 WPS）。
说明书里写的是「包括你的位置」和「MAC 地址」，但**没有说明周边 Wi-Fi 是用来反推位置的**。
技术上是诚实的（写了 MAC），但用户理解成本很高。

### 🟠 3. `WRITE_SECURE_SETTINGS` 权限

Manifest 申请了 `android.permission.WRITE_SECURE_SETTINGS`（`AndroidManifest.xml:62`）。
SOS 功能本身**不需要**写安全设置 —— 这是与「报警辅助」无关的额外能力，值得单独问一句。

### 🟠 4. 服务端可远程抑制

`checkSuppressConfig()`：服务端可以下发 `suppressEmergencyAssistant=true`，让功能静默失效。
一个**安全功能**可以被远程关掉，需要注意。

### 🟡 5. 协议版本 & 服务商变更历史

- `<string name="statement_content_alarm_assistance">`：只写「深圳位置网科技有限公司」
- `<string name="statement_content_alarm_assistance_v2">`：变成「深圳位置网科技有限公司**和中国信息通信研究院**」，
  且新增字段「手机终端设备型号、手机厂商」

也就是说 v2 协议新增了设备信息采集。v1 同意的用户会被要求重新同意（`c0.U()`），逻辑是对的。

### 🟡 6. 测试环境域名

```xml
<!-- res/xml/network_config_for_test.xml -->
<domain-config cleartextTrafficPermitted="true">
    <domain includeSubdomains="true">disaster.romtest.wanyol.com</domain>
</domain-config>
```

`disaster.romtest.wanyol.com` 是**内网测试域名**（`wanyol.com` 是位置网的域名），
并且**允许明文 HTTP**。正式版不应该带这段，切换逻辑靠 `od/d.x()` / `v2.b()` 判断。
这是很常见的"测试代码带到生产"问题。

> 补充：零售机上 `x()` 返回 false，走的是 `https://disaster.coloros.com`，**并不会实际用明文**。
> 影响面限于"包里带了不该带的配置"，而非"正在明文传输"。

### 🟡 7. 通知栏持续提示

`alarm_assistance_continuous_location_notification_content`：
「正在获取并发送你的求救信息给接处警中心…」

这个设计是好的 —— 用户能看到正在发生什么。但要注意它是否覆盖整个通话过程。

---

## 八、和「自动发送位置信息」的区别（顺带核对）

| 项 | 自动发送位置信息 | 报警辅助 |
|---|---|---|
| 接收方 | **你的紧急联系人** | **接处警中心**（经位置网） |
| 通道 | 短信（普通文本） | 网络（JSON）+ 短信（二进制） |
| 内容 | 位置 + 求助信息 | 位置 + 周边 Wi-Fi MAC + 手机号 + 设备型号 + 医疗信息 |
| 触发 | 通过 SOS 功能拨打紧急号码 | 直接拨 110/120/119/122 也可 |
| 服务商 | OPPO / 你的运营商 | 深圳位置网 + 中国信通院 |

说明书里「自动发送位置信息」的实现是 `auto_send_location_information_summery_second`：
「通过 SOS 拨打公共紧急号码后，自动向你的紧急联系人发送附带当前位置等信息的求助短信」
—— 是普通短信，不走位置网。**这两个是独立的两条链路**，不要混淆。

---

## 九、结论

**功能本身是合理的**：紧急呼叫时发位置给接处警中心，这在很多国家都是标配（E911/AML）。
**实现上有几个值得注意的点**：

1. 文案没提「医疗信息」和「Wi-Fi MAC 用于反推位置」，知情同意不充分
2. 公开接口 + 硬编码公钥，可被伪造
3. 服务端可远程关闭这个安全功能
4. 带了 `WRITE_SECURE_SETTINGS` 这个与功能无关的高危权限
5. 测试域名和明文 HTTP 配置进了正式包
6. 每次紧急呼叫 + 上报结果都打埋点，精确到秒

**对使用者**：
- 如果你在意「呼叫时把周围 Wi-Fi 指纹发给第三方」，可以关掉
- 但**关掉会显著降低紧急情况下的定位精度**（基站定位在室内很难用）
- 我个人的判断：**保持开启**，但要清楚它传了什么。

---

## 十、可复现命令

```bash
# 拿 APK
unzip -o ~/Downloads/app_backup.zip 'app_backup/*com.oplus.sos*' -d /tmp/sos

# 反编译
~/.openclaw/workspace/tools/jadx/bin/jadx -d jadx --no-res /tmp/sos/SOS*.apk
java -jar ~/.openclaw/workspace/tools/apktool.jar d -f -o apktool /tmp/sos/SOS*.apk

# 解析一条报警辅助短信（如果有）
python3 tools/alarm_sms.py parse "<短信文本>"
python3 tools/alarm_sms.py self-test

# 查当前开关状态（设备上）
adb shell settings get secure emergency_call_numbers
adb shell "dumpsys telephony.registry | grep -i emergency"
```

## 证据链

```
sos/
├── SOS.apk                 原包（18.4MB，来自 app_backup.zip）
├── evidence/               关键证据副本（2026-11-09 精简）
│   ├── sos-handout/        values-zh-rCN 文案 + res/xml 首选项
│   ├── regres-handout/     RegService 解码后 Manifest + strings/public
│   └── regservice-raw/     RegService 的 classes.dex + libaes-jni.so
└── tools/alarm_sms.py      短信二进制结构解析器（含自测）
```

> ⚠️ **2026-11-09 清理**：`apktool/`（129MB）与 `jadx/sources/`（49MB，5766 个 Java 文件）
> 已删除，可随时用上面的命令从 `SOS.apk` 重建；需要引用的资源片段已存到 `evidence/`。
