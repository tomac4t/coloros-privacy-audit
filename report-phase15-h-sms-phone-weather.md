# 第十五轮（H 组）：短信 / 电话 / 联系人 / 天气 / 号码库

- **日期**：2026-11-06
- **对象**：8 个包
- **样本**：`/tmp/h-apk/`，反编译输出 `/tmp/hjadx/`
- **方法**：APK 权限 + dex 域名扫描 + jadx 反编译 + **jadx 失败项用 apktool 出 smali**

---

# 一、结论速览（先回答问题）

| Tom 的问题 | 答案 |
|---|---|
| **1. 短信、电话应用会不会上传信息（号码等）？** | ⚠️ **短信会上传号码。** 电话/来电界面**不上传**，但会**回调本地号码库服务**（`ted.number`）做识别 |
| **2. ted.number 会上传号码，还是离线号码库？** | 🔴 **两者都有。** 以前我说"它自己不联网"是**错的** —— 实际是**本地库先查，查不到就传号码上云** |
| **3. 天气会上传什么？符合隐私政策吗？** | ⚠️ **传经纬度 + 设备标识（vaid/brand）+ 定位来源**。WiFi/基站字段**全部留空**。基本符合，但有隐藏上报 |

---

# 二、短信应用（`com.android.mms`）—— 🔴 重点

## 2.1 它是什么

`com.android.mms` 不只是普通短信，里面打包了 **「智能短信 / 卡片短信」** 整套 SDK
（`SmartMessageInit`），底层是 **TeddyMobile（泰迪熊移动）** 的广告变现体系。

## 2.2 全部端点（从 `np/g.java:n()` 一次性初始化）

```java
// com/android/mms 里的 SmartMessageInit.initEnv()
gy.c.f33207a = "https://sms.ads.heytapmobi.com";              // ★ 短信广告主域
gy.c.f33208b = "http://www.teddymobile.cn";                    // TeddyMobile
gy.c.f33209c = "long.sms.heytapmobi.com";                      // 长链服务
gy.c.f33210d = "short.sms.heytapmobi.com";                     // 短链服务
gy.c.f33211e = "https://short.sms.heytapmobi.com";
gy.c.f33212f = "https://api.sms.heytapmobi.com/ads-activate";  // ★ 广告激活
gy.c.f33213g = "https://push1.teddymobile.cn";                 // 推送
gy.c.f33214h = "https://h-push1.teddymobile.cn";
gy.c.f33215i = "https://cl-data.ads.heytapmobi.com/upload/set12";  // ★ 广告数据上传
gy.c.f33216j = "http://store.oppomobile.com";
gy.c.f33220n = "map.qq.com";                                   // 短信里的地址卡片
gy.c.f33221o = "map.baidu.com";
gy.c.f33222p = "amap.com";
gy.c.f33223q = "gaode.com";
gy.c.f33224r = "map.sogou.com";
gy.c.f33225s = "http://commerce-ads.wanyol.com/api/k/g";        // ★ 电商广告
gy.c.f33226t = "https://sms.ads.heytapmobi.com/mo/api/mo/config";
gy.c.f33227u = "https://sms.ads.heytapmobi.com/mo/api/mo/nextandcard";  // ★ 下一条卡片
gy.c.f33228v = "https://data.sms.heytapmobi.com";               // ★ 数据上报
```

## 2.3 开关：`smart_message_cardview_switch`

```java
// dq/b.java
public static boolean c(Context context, boolean z11) {
    f28529c = z11 && f28527a;
    return sm.c.b(context.getContentResolver(),
                  "smart_message_cardview_switch", z11 ? 1 : 0);
}
```

初始化前的多重门禁：

```java
// np/g.java:l()
if (!r()) {
    log("initSmartSdk Fail, permission:" + k00.b.f38055h
        + ", enable:" + k00.b.f38049b + ", feature:" + wi.c.A
        + ", switch:" + dq.b.f28529c);
    return;
}
```

**四重门禁**：权限 + 功能启用 + 特性开关 + 用户设置。

还有一条：

```java
// dq/b.java:i()
if (wi.c.f53012o) {
    CtaDataBus.setNetworkAccessible(f28527a && h0.g() && com.oplus.mms.statement.g.j());
}
```

→ **必须用户同意隐私声明（`statement.g.j()`）才允许联网。**

## 2.4 关于"上传号码"

**结论：短信应用本身不上传短信内容。** 但有两类会上传：

| 来源 | 上传什么 | 触发 |
|---|---|---|
| `sms.ads.heytapmobi.com` 等广告体系 | **广告曝光/点击/激活行为**（OAID 类） | 智能短信卡片展示时 |
| `api.sms.heytapmobi.com/ads-activate` | 广告激活事件 | 装了某广告主 App |
| `data.sms.heytapmobi.com` | 行为数据 | 定期 |

⚠️ **广告主域是 `*.ads.heytapmobi.com`，这是最大的隐私出口点。**
短信内容本身不上传，但**"你收到了哪个商户的短信、点了什么"**是上传的。

## 2.5 另外发现：内网测试地址

```
http://192.168.40.204:13011/statistics/getsynconfinfo?
http://192.168.40.204:13011/statistics/uploadlogInfo?
```

**内网 IP 打包进生产 APK** —— 这是调试遗留，虽然连不上但属于工程规范问题。

## 2.6 短信应用权限（挑最狠的）

```
READ_SMS / WRITE_SMS / RECEIVE_SMS / SEND_SMS     短信读写
READ_CONTACTS                                       通讯录
MANAGE_EXTERNAL_STORAGE                             全盘文件
RECORD_AUDIO / CAMERA                               录音/相机
ACCESS_FINE_LOCATION                                精确定位
READ_PRIVILEGED_PHONE_STATE                         特权电话状态
WRITE_SECURE_SETTINGS                               写系统安全设置
```

---

# 三、电话 / 来电 / 联系人 —— 🟢 干净

## 3.1 `com.android.incallui`（来电界面）

**业务域名：0 个。**
URL 里只有 `schemas.android.com`、`github.com/grpc-java` 的 issue 链接、`issuetracker.google.com`。

**结论：来电界面不联网。**

但它权限极高（`READ_CALL_LOG` / `WRITE_CALL_LOG` / `CAPTURE_AUDIO_OUTPUT` / `MANAGE_USERS` / `REBOOT`），
这是系统级通话 UI 的必需权限。

## 3.2 `com.android.phone`（电话服务）

**业务域名：0 个。**
URL 只有 `example.com/FAKE.png`（测试用）、`www.google.com`（常量）。

**结论：电话服务不联网。**

## 3.3 `com.android.contacts`（电话本）

业务域名里混进了**金融变现 SDK**：

```
configx.finzfin.com          finzfin = 深圳市分众? 类
epoch.finzfin.com
i-monetization.finzfin.com   ← 变现
gslb.finzfin.com
i-fin-test.wanyol.com        测试环境
epoch-test.wanyol.com
```

这批是 **「厚贝/钱包类」商业 SDK**（与之前 D 组发现碎屏险同源）。
⚠️ 电话本本身不传联系人，但挂了个广告/变现 SDK。

**建议**：`*.finzfin.com` 全部拦掉（对通讯录功能无影响）。

## 3.4 `com.android.providers.contacts`（联系人存储）

**业务域名：0 个。**
URL 只有 `schemas.android.com`。

**结论：联系人数据库本地存储，不上传。** ✅

## 3.5 `com.android.mms.service`（MMS 系统服务）

**业务域名：0 个。**
**结论：干净。**

---

# 四、🔴 `com.ted.number` —— **它会联网！我之前判错了**

## 4.1 更正说明

> 在 **E 组报告（第十三轮）** 里我写过：
> "`com.ted.number` **自己不联网**（全包扫描：没有任何 OkHttp/HttpURLConnection/网络调用代码）"
>
> **这是错的。** 这次扫 dex 字符串时发现了 4 个 `tel-num-cn.heytapmobi.com` 端点，
> 然后反编译确认了 `okhttp3.OkHttpClient` + `newCall().execute()` 真实调用。

**错因**：上次我只扫了 `BuildConfig` 常量就下结论，没扫 dex 里的完整 URL 字符串。

## 4.2 五个端点

```java
// d4/y.java + com/oplus/harassdetec/IncrementalUpdatePeriodJob.java
POST https://tel-num-cn.heytapmobi.com/v2/proxy/phoneRec      // ★ 号码识别（会上传号码！）
POST https://tel-num-cn.heytapmobi.com/v2/proxy/phoneMark     // 号码标记
POST https://tel-num-cn.heytapmobi.com/v2/proxy/phoneCorrect  // 号码纠错
POST https://tel-num-cn.heytapmobi.com/v3/proxy/phoneLib      // ★ 本地库增量下载
POST https://tel-num-cn.heytapmobi.com/v2/proxy/config        // 配置
```

统一的请求头：

```java
.header("deviceId",   f.c(b8))     // ★ 设备 ID
.header("cipherInfo", f.a(b8))     // 加密信息
```

请求体是 **AES 加密后 Base64**（走 `d4.c.b(context, json)` → `f.b()`）。

## 4.3 🔴 核心：号码确实会上传

```java
// d4/y.java —— 组装请求体
JSONObject f(w wVar, Context context, String str, int[] iArr) {
    ...
    jSONObject2.put("areaCode",  wVar.a());       // 区号
    jSONObject2.put("contact",   wVar.b());       // 通话状态（振铃/接通）
    jSONObject2.put("recordTime", System.currentTimeMillis());
    jSONObject2.put("spList", new JSONArray(iArr));
    jSONObject3.put("header", jSONObject);
    jSONObject3.put("data",   jSONObject2);
}
```

`w wVar` 的第一个字段就是**被查询的号码本身**（`new w(requestData.getNumber(), ...)`）。

```java
// d4/y.java:g() —— 发起请求
Response execute = f7598f.newCall(new Request.Builder()
    .url("https://tel-num-cn.heytapmobi.com/v2/proxy/phoneRec")
    .post(RequestBody.create(json, b9))
    .header("deviceId", f.c(b8))
    .header("cipherInfo", f.a(b8))
    .build()).execute();
```

**也就是说：来电/去电/查号时，只要本地库没命中，号码就会上传到 `tel-num-cn.heytapmobi.com`。**

## 4.4 本地库 vs 云端：并行双查

```java
// d4/v.java:P() —— smali 还原
CompletableFuture localF  = CompletableFuture.supplyAsync(new d4.q(w), executor);   // → F() → N() 本地
CompletableFuture cloudF  = CompletableFuture.supplyAsync(new d4.r(w, z, iArr), executor); // → G() → O() 云端
CompletableFuture.allOf(cloudF, localF).get(timeout);
```

```java
// d4/v.java:N()  —— 本地
private static JSONObject N(w wVar) {
    log("本地库查询开始.");
    return d4.b.F(l.i(wVar.f(), wVar.g()));
}

// d4/v.java:O()  —— 云端
private static JSONObject O(w wVar, boolean z7, int[] iArr) {
    log("云端查询开始.");
    if (!z7) {                                   // ← ★ CTA 开关
        log("cta非true，禁止联网查询.");
        return null;
    }
    return y.g(wVar, wVar.f(), wVar.g(), iArr);
}
```

**本地和云端并行查，谁快用谁**（还各自带超时兜底）。

## 4.5 云端联网的开关

```java
// d4/v.java:O()
if (!z7) {
    log("cta非true，禁止联网查询.");
    return null;
}
```

`z7` 来自 `requestData.isAccessNetwork()`（调用方传入）。
上游 `p4/f.java:i()` 里：

```java
JSONObject P = v.r().P(wVar, timeout, requestData.isAccessNetwork(), ...);
```

而最终门禁在初始化阶段：

```java
// q4/b.java:b(boolean)
public void b(boolean z7) {
    log("NumberEngineManager", "init networkAccess=" + z7);
    o8.b(z7);
}
```

**结论**：有 `isAccessNetwork` 布尔开关，但是**由调用方（拦截/来电界面）传入**，
不是用户可见的独立开关。

## 4.6 用户能找到的开关

| 位置 | 作用 |
|---|---|
| **拨号/联系人 → 设置 → 智能识别陌生号码** | 总开关（`com.ted.number.ui.TedUpdateSettingActivity`） |
| 骚扰拦截 → 拦截规则设置 → 国家反诈中心 | 号码库比对（不同功能线） |

⚠️ **关掉"智能识别陌生号码"后**：
- 本地库查询也停（`Q(boolean)` → `g.m(z7)`）
- 云端查询也停

**这是目前唯一能彻底关掉号码上云的开关。**

## 4.7 号码库是离线的吗？

**混合模式**：

```java
// d4/v.java:K() —— 定时更新本地库
jobScheduler.schedule(new JobInfo.Builder(
    CommonStatusCodes.AUTHENTICATE_FAIL,
    new ComponentName(context, LocalDicUpdateJob.class))
    .setPeriodic(86400000L)      // 每 24 小时
    .build());

// 还有增量包升级
new JobInfo.Builder(1001, new ComponentName(context, SetIncrementalUpdatePeriodJob.class))
    .setMinimumLatency(currentTimeMillis)   // 每天固定时刻
```

端点 `https://tel-num-cn.heytapmobi.com/v3/proxy/phoneLib` 就是**下载本地号码库**。

**所以是**：
- **有本地离线库**（每天增量下载）
- **查不到时走云端**（upload 号码）
- **不是纯离线**

---

# 五、天气应用 —— 只有一个包

## 5.1 「两个天气」是什么

你印象里的两个，实际是：

| 名字 | 包名 | 在不在样本里 |
|---|---|---|
| **天气服务**（后台服务） | `com.coloros.weather.service` | ✅ 在 |
| **天气**（界面 App） | 系统内置，**不在 app_backup 里** | ❌ |

**只有服务端软件包被备份到了。** 界面 App 是 system/app 下的预装，
需要 `adb pull /system/app/Weather*` 才能拿到。

## 5.2 天气服务干什么

```
com.oplus.weather
 ├ location/          ← 定位 → 城市名
 │   ├ LocationSdkCallback
 │   └ calibration/   ← 位置校准
 ├ datasource/        ← 天气数据
 ├ provider/          ← ContentProvider（给桌面小组件、锁屏用）
 ├ external/          ← ExternalWeatherWidgetService / KeyguardService
 └ updateweatherpoint/← 天气刷新点
```

## 5.3 🔴 上传什么（`LocationDataSource.addReportParams`）

```java
// com/oplus/weather/datasource/service/LocationDataSource.java:58-90
private void addReportParams(double d10, double d11) {
    this.mParams.put("longitude", String.valueOf(d10));   // ★ 经度
    this.mParams.put("latitude",  String.valueOf(d11));   // ★ 纬度
    this.mParams.put("language",  q.b());

    // ↓↓↓ 下面全是【空字符串】！！！
    this.mParams.put(MCC,  "");
    this.mParams.put(MNC,  "");
    this.mParams.put(LAC,  "");
    this.mParams.put(CID,  "");
    this.mParams.put(SSID, "");        // ← WiFi 名：空
    this.mParams.put(BSSID,"");        // ← WiFi MAC：空
    this.mParams.put(SID,  "");
    this.mParams.put(NID,  "");
    this.mParams.put(BID,  "");
    this.mParams.put(UDID, "");
    this.mParams.put("oaid",  "");
    this.mParams.put("imei",  "");

    // ↓↓↓ 这些是真值
    this.mParams.put(TS,     r.c(System.currentTimeMillis()));
    this.mParams.put(SOURCE, str);                 // 定位来源（google/amap/...）
    this.mParams.put("vaid", getNonNullString(a10)); // ★ VAID（虚拟广告 ID）
    this.mParams.put(BRAND,  SystemProp.getBrand().toLowerCase());  // ★ 品牌
    this.mParams.put(TODAY_LOCATE_CNT, y.h(c11));  // ★ 今日定位次数
    this.mParams.put(ACTIVATION_TIMESTAMP, y.e(c11)); // ★ 激活时间戳
    this.mParams.put(PLACE_DETAIL_LEVEL, str2);    // 街道级开关状态
}
```

## 5.4 逐字段隐私评估

| 字段 | 值 | 评估 |
|---|---|---|
| `longitude` / `latitude` | **真实经纬度** | 🔴 位置 |
| `vaid` | **真值** | 🟠 虚拟设备 ID |
| `BRAND` | `oppo` | 🟢 低 |
| `TODAY_LOCATE_CNT` | **真值** | 🟡 行为频率 |
| `ACTIVATION_TIMESTAMP` | **真值** | 🟡 设备激活时间 |
| `SOURCE` | 定位来源 | 🟠 可推断用了哪家 SDK |
| `PLACE_DETAIL_LEVEL` | 街道级开关 | 🟡 |
| `SSID` / `BSSID` | **空** | 🟢 未采集（好） |
| `MCC/MNC/LAC/CID` | **空** | 🟢 未采集（好） |
| `oaid` / `imei` / `UDID` | **空** | 🟢 未采集（好） |

## 5.5 符合隐私政策吗？

**基本符合，但有几个灰点**：

✅ **符合的部分**
- 只传经纬度，不传 WiFi/基站
- OAID/IMEI 明确留空（说明做过合规改造）
- 有 `PLACE_DETAIL_LEVEL` 开关（街道级定位可控）

⚠️ **灰点**
1. **`vaid` 仍在上传** —— 虽然是"虚拟"ID，但可用于跨会话关联
2. **`TODAY_LOCATE_CNT` / `ACTIVATION_TIMESTAMP`** —— 这两个是**行为统计**，
   隐私政策里通常写"设备信息"，但具体到"今天定位了几次"可能超出必要范围
3. **`SOURCE` 字段泄露定位来源** —— 能推断出你用的是高德/Google/百度

## 5.6 天气服务的隐私声明

`com/oplus/weather/service/privacy/PrivacyStatementActivity` 存在，
HTML 在 `assets/` 里（与本 APK 同款形态）。

## 5.7 另一个发现

```java
// fa/k.java:48
weatherTipsResult.setDetailLink(
    "https://weather.com/zh-CN/weather/tenday/l/085466a63dc1be5f8a7c1f8c8851b337d59091c464d9a4e3");
```

天气详情页的"查看更多"会跳转到 **weather.com（The Weather Company）**。
⚠️ 这是**第三方网站**，跳过去后有自己的 Cookie/追踪，但不属于 OPPO 的上传。

---

# 六、总结表

| 包 | 业务域名 | 会上传号码/联系人？ | 定性 |
|---|---|---|---|
| `com.android.mms` | 30+（含短信广告体系） | ❌ 短信内容不上传<br>⚠️ 广告行为上传 | 🟠 有变现 SDK |
| `com.android.mms.service` | 0 | ❌ | 🟢 干净 |
| `com.android.incallui` | 0 | ❌ | 🟢 干净 |
| `com.android.phone` | 0 | ❌ | 🟢 干净 |
| `com.android.contacts` | 金融 SDK 7 个 | ❌ 联系人不上传 | 🟠 挂了变现 SDK |
| `com.android.providers.contacts` | 0 | ❌ | 🟢 干净 |
| **`com.ted.number`** | **1（5 个端点）** | 🔴 **会！号码上云** | 🔴 重点 |
| `com.coloros.weather.service` | 0（运行时拼） | ❌ | 🟡 传经纬度+vaid |

---

# 七、建议

## 7.1 拦截优先级

| 优先级 | 域名 | 影响 |
|---|---|---|
| 🔴 高 | `tel-num-cn.heytapmobi.com` | 陌生号码识别失效（改纯本地） |
| 🟠 中 | `sms.ads.heytapmobi.com`<br>`*.ads.heytapmobi.com` | 智能短信卡片不显示（普通短信正常） |
| 🟠 中 | `*.finzfin.com` | 通讯录里的变现 SDK | 
| 🟡 低 | `api.sms.heytapmobi.com` | 同上 |

## 7.2 用户可操作的开关

| 目标 | 操作 |
|---|---|
| **号码不上云** | 拨号/联系人 → 设置 → 关闭「智能识别陌生号码」 |
| **智能短信卡片关掉** | 信息 → 设置 → 关闭「智能短信/卡片视图」（`smart_message_cardview_switch`） |
| 天气位置 | 天气 → 设置 → 关闭「街道级定位」 |

## 7.3 验证命令

```bash
# 1. 确认 ted.number 是否真的联网（实测）
adb logcat -s Harass_Detect | grep -E "云端查询开始|本地库查询开始|cta非true"

# 2. 看智能短信是否启用
adb shell settings get global smart_message_cardview_switch

# 3. 看号码库更新任务
adb shell dumpsys jobscheduler | grep -A5 "LocalDicUpdateJob"

# 4. 天气上报（观察是否只在刷新天气时）
# AdGuard 过滤 weather
```

---

# 八、待验证

| # | 项目 | 方法 |
|---|---|---|
| 1 | `ted.number` 云端查询**实际频率**（每次来电？还是只首次） | logcat + AdGuard 3 天 |
| 2 | `smart_message_cardview_switch` 国行默认值 | 真机 `settings get global` |
| 3 | 天气界面 App（非服务）的包名和独立域名 | `adb shell pm list packages \| grep weather` |
| 4 | `com.android.contacts` 的 finzfin SDK 是否真被调用 | 抓包观察 3 天 |
| 5 | `192.168.40.204:13011` 是否还有别的包在用 | 全样本 grep |

---

**报告完成时间**：2026-11-06
