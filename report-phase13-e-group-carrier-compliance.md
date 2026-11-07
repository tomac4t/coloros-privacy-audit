# 第十三轮（E 组）：运营商 / 合规类系统组件

- **日期**：2026-11-06
- **拆分说明**：原报告 `report-phase13-e-f-camera-gallery.md` 把 E 组（运营商/合规）与 F 组（相机/相册）
  合并分析。两者性质完全不同——E 组是法定合规上报，F 组是功能相关的云服务——现拆为两份独立报告。
  F 组见 `report-phase13-f-camera-gallery.md`。
- **结论速览**：
  - `com.oppo.ctautoregist` 是**唯一的硬性上报**：换卡/开关变化/开机时明文上报 IMEI+IMSI+ICCID+MAC+基站ID，
    这是工信部入网备案要求，**无用户开关**。
  - `com.coloros.bootreg` / `com.oplus.customize.coreapp` / `com.cmccslice.proxyapp` 均**零业务域名**。
  - `com.ted.number`（陌生号码识别）**自己不联网**，只提供 AIDL 服务，被 `blacklistapp` 调用。

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

## E5. `com.ted.number`（智能识别陌生号码）—— ⚠️ **该结论已被推翻，见第十五轮报告**

> 🔴 **更正（2026-11-06，第十五轮）**：本节下文说「它自己不联网」**是错的**。
> 实际它有 5 个 `tel-num-cn.heytapmobi.com` 端点，且 **phoneRec 会上传被查询的号码**。
> 详见 `report-phase15-h-sms-phone-weather.md` 第四节。
> 错因：上次只扫了 BuildConfig 常量，没扫 dex 里的完整 URL 字符串。

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


---

*本报告由原合并报告拆分而来，内容未改动。相关发现见 F 组报告：*
*`report-phase13-f-camera-gallery.md`*
