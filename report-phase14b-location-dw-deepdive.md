# 第十四轮补（G-2）：网络定位 6 SDK + 融合算法 + 数字健康退出（v3）

- **日期**：2026-11-06
- **对象**：`com.oplus.location`（网络定位服务）、`com.coloros.digitalwellbeing`（数字健康）
- **样本**：`/tmp/g-apk/oplusloc.apk`、`/tmp/g-apk/dw.apk`
- **反编译**：`/tmp/gref/out_oplusloc/`、`/tmp/gref/out_dw/`
- **母报告**：`report-phase14-g-group-system-governance.md`

---

# 第一部分：数字健康能不能靠「关闭屏幕用时」停止上传？

## 1.1 结论

**能。关闭「屏幕用时」后，上传链路会被切断 —— 但切断点是「UI 不再请求」+「本地统计进程被停」，
而不是上传函数本身加了开关。**

⚠️ 具体分三件事说清楚：

| 问题 | 答案 |
|---|---|
| 关掉「屏幕用时」会上传吗？ | **不会**（UI 入口消失，统计服务被 stop） |
| 上传函数自己检查开关吗？ | **不检查**。`WellBeingProvider.call()` 只校验调用方权限 |
| 有残留风险吗？ | 有：如果别的系统组件（有 `OPPO_COMPONENT_SAFE` 权限）仍去 `call()` 它，**仍会上传** |

## 1.2 关闭按钮在哪

**路径**：健康/屏幕用时 App（`com.coloros.digitalwellbeing`）→ 首页 → 右上角设置 → **关闭屏幕用时**

弹窗文案（`res/values-zh-rCN/strings.xml`）：

```xml
<string name="close_screen_time_for_title">要关闭屏幕用时吗？</string>
<string name="close_app_tips">关闭后将清空历史数据、不再统计应用使用情况、使用限制不再生效，确认关闭？</string>
```

**「不再统计应用使用情况」= 你说的那个开关。**

## 1.3 关闭后代码做了什么（逐层）

```
关闭弹窗「关闭」
  └ g2.d.y(context, activity, id, dialog, which)      // MainModel
     ├ j.d(...) → new f(activity, id, null)            // 投递协程
     └ s2.c.k(context, false)                          // 埋点：close_app_button=0
        s2.a.c(context, "dynamic_statistics_app_switch", false)
```

协程 `f.invokeSuspend()` → 有密码校验则弹密码框，否则 `d.g(id)`：

```java
// g2/d.java:g()
public static final void g(int i10) {
    o(i10);                            // 关弹窗
    h1.c.f12760k.c().u();              // 清内存里的统计数据
    j.d(n1.f14979e, ...new a(null)...); // 投递下一个协程 → d.q()
}
```

`d.q()` 里做两件关键事：

```java
// g2/d.java:q() 简化
n(false);            // ←★ 写 dwb_open = false，并执行关服务逻辑
u(...);              // 把当前设置备份成 "dwb_close_data"（用于恢复）
```

```java
// g2/d.java:n(boolean)
public static final void n(boolean z10) {
    f12665b = z10;
    w2.d.B(d10, "dwb_open", z10);      // ←★ 持久化开关
    if (z10) { t(); return; }           // 开启：t()
    z0.a c10 = a1.c.c(d11);             // 关闭：取 appUsageTimeSwitch 处理器
    if (c10 != null) c10.a();
}
```

## 1.4 真正的切断点：`RefreshPersistStateService`

```java
// RefreshPersistStateService.h()
boolean z10 = w2.d.m(k(), "main_privacy_user_agree") && g2.d.i();   // g2.d.i() == dwb_open
...
if (!d(context)) {            // dwb_open == false
    log("startRefreshPersistState 2");
    f();                      // ←★ METHOD_PERSIST_STOP
    return;
}
```

```java
// RefreshPersistStateService.f()
getContentResolver().call("com.coloros.safecenter.AppUsageProvider", "METHOD_PERSIST_STOP", null, null);
```

**这就是关键**：`dwb_open = false` → 向 `com.coloros.safecenter`（手机管家）发 `METHOD_PERSIST_STOP`，
**停掉应用使用统计的持久化采集**。

同时 `SwitchRuleProcessor` 也会回 `APP_USAGE_TIME_SWITCH = false`：

```java
// a1/e.java:i()
boolean z10 = w2.d.m(k(), "main_privacy_user_agree") && g2.d.i();
return o(z10);   // OutEvent.eventCode = 10201, event = "APP_USAGE_TIME_SWITCH"
```

## 1.5 ⚠️ 但上传函数本身不检查开关

```java
// WellBeingProvider.call() —— 注意：全程没有 dwb_open 判断
@Override
public Bundle call(String str, String str2, Bundle bundle) {
    String callingPackage = getCallingPackage();
    t.a(context, callingPackage);            // ← 只校验调用方权限
    ...
    if (TextUtils.equals(str, METHOD_GET_APP_TYPE)) {   // ← 直接走
        Bundle bundle3 = new Bundle();
        bundle3.putStringArrayList(EXTRA_APP_TYPE_LIST, fetchGameTypeApp(context));
        return bundle3;
    }
```

`t.a()` 只做一件事：

```java
// v2/t.java:c()
if (Binder.getCallingPid() == Process.myPid()
    || checkPermission(context, "oppo.permission.OPPO_COMPONENT_SAFE", str) == 0
    || checkPermission(context, "oplus.permission.OPLUS_COMPONENT_SAFE", str) == 0) {
    return;   // 放行
}
throw new SecurityException(callingPackage + " calling package is not permitted...");
```

**所以：任何持有 `OPPO_COMPONENT_SAFE` 系统权限的组件，即使你把屏幕用时关了，
只要它主动 `call("METHOD_GET_APP_TYPE")`，那套上传链路还是会跑。**

这不是理论风险 —— `METHOD_GET_APP_TYPE` 这个接口本来就是**给别的系统组件用的**
（自己进程内调用没必要走 ContentProvider.call）。

## 1.6 完整对照表

| 状态 | `dwb_open` | 统计进程 | UI 入口 | 上传（正常路径） | 上传（被系统组件 call） |
|---|---|---|---|---|---|
| 开启 | true | 运行 | 有 | ✅ 会 | ✅ 会 |
| **关闭** | **false** | **STOPPED** | **消失** | ❌ **不会** | ⚠️ **可能** |
| 未同意隐私政策 | false | — | 无 | ❌ | ⚠️ |

## 1.7 建议

1. **关掉「屏幕用时」是有意义的** —— 数据不再累积，正常入口也不会触发上传
2. **想要更彻底**：DNS 拦 `api.open.oppomobile.com`（不拦也不影响其他功能）
3. **验证方法**：

```bash
# 关掉后确认标志位
adb shell content query --uri content://com.coloros.digitalwellbeing.settings/key --where "key='dwb_open'"

# 观察上传（关掉后 3 天应该 0 条）
# AdGuard 里过滤 api.open.oppomobile.com
```

---

# 第二部分：网络定位服务（`com.oplus.location`）—— 到底是几个 SDK？

## 2.1 🔴 先纠正一个误解：**不是 3 个，官方自己也承认是 6 个**

你说「接三个 SDK 不太合理」——你看到的是**代码里能扫到的域名**，
但 APK 里自带的**隐私声明 HTML** 明确列了 **6 个第三方 SDK**。

文件：`assets/location_services_privacy_notice.html`
中文文案：`res/values-zh-rCN/strings.xml` → `privacy_notice__sdk1..6__gallery`

| # | SDK 名称 | 公司 | 收集的个人信息 | 我方获取 | 场景 |
|---|---|---|---|---|---|
| **1** | **腾讯定位 SDK** | 深圳市腾讯计算机系统 | **Wi-Fi列表、基站列表、蓝牙列表** | 位置信息 | 提供位置信息服务 |
| **2** | **NLP Vendor SDK** | 北京百度网讯科技 | **Wi-Fi列表、基站列表、蓝牙列表** | 位置信息 | 位置信息 + **离线定位** |
| **3** | **高德系统级网络定位服务** | 高德软件 | **Wi-Fi列表、基站列表、蓝牙列表** | 位置信息 | 提供位置信息服务 |
| **4** | **3D地图辅助定位** | 深圳市腾讯计算机系统 | **GPS位置信息** | 无 | 城市峡谷 3D 地图辅助 |
| **5** | **NtripClient** | **千寻位置网络** | **GPS位置信息** | 无 | **车道级导航**（差分数据） |
| **6** | **NtripClient** | 深圳市腾讯计算机系统 | **GPS位置信息** | 无 | 车道级导航（RTK） |

**原文摘录**（SDK 1）：

> SDK名称：腾讯定位SDK
> 第三方公司名称：深圳市腾讯计算机系统有限公司
> 第三方收集的个人信息：Wi-Fi列表、基站列表、蓝牙列表
> 我们从第三方获取的个人信息：位置信息
> 第三方调用的设备权限：网络权限，精确、粗略位置权限，后台定位权限
> 实现目的：提供位置信息，进一步优化、精确位置信息

**三方（腾讯/百度/高德）收集的东西一模一样，目的也一模一样。**

## 2.2 为什么会有三家？—— 代码里的真相（v3：存在融合）

> 🔴 **修正记录**：v1 写「随机分流」（错）→ v2 写「三家并行只取高德」（仍错）→ **v3 确认：三家结果全部参与
> `NlpFusionAlgo_v1.2` 算法融合**，最终上报的是融合结果，不是任何单一 SDK 的原始值。
> 之前误判的原因：只看了 `wb/i.q()` 的选择分支，没找到产出 type=32 的 `xb/i.java`（FusionProvider）。

### provider 类型编号

```java
// wb/k.java:c(int)
1  → xb.j  腾讯定位
2  → xb.b  百度 NLP
4  → xb.a  高德
64 → xb.e  百度离线
```

每个 provider 自己报类型：

```java
xb/j.c() → 1   // 腾讯
xb/b.c() → 2   // 百度
xb/a.c() → 4   // 高德
xb/e.c() → 64  // 百度离线
```

### 两套掩码，完全分开

```java
// wb/j.java
private int f18626a = 599;   // locationProviderMask —— 定位用
private int f18627b = 4;     // geocodeProviderMask  —— 逆地理用 ★ 只有高德

public int c() { return f18627b; }   // 逆地理掩码
public int g() { return f18626a; }   // 定位掩码
```

| 用途 | 掩码 | 启用 |
|---|---|---|
| **定位** | `599` = `0b10_0101_0111` | 腾讯(1) + 百度(2) + 高德(4) + 16 + 百度离线(64) + 512 |
| **逆地理** | `4` | **只有高德** |

### 🔴 三家并行：谁都不闲着

```java
// wb/i.java:发起请求
for (xb.d dVar3 : this.E.i()) {      // ← 遍历所有已注册 provider
    this.f18612p++;                   // 并发计数 +1
    dVar3.q(this.f18611o, l11);       // ← 每个都发
}
log("request code:", reqCode, "provider count:", this.f18612p);
```

**三家同时收到请求，同时采集 WiFi/BLE/基站，同时上传。没有“随机挑一家”这回事。**

### 🔴🔴 结果不是丢弃，而是**全部喂进融合算法**

这是我前两版最大的失误。真实链路是：

```
三家 provider 并行请求
  xb/j (腾讯 type=1)   xb/b (百度 type=2)   xb/a (高德 type=4)
        ↓ 各自返回 Location
┌───────────────────────────────────────────────────┐
│ NlpLocFilterMgr (vb/d.w) —— 归一化，不丢弃          │
│   AMAP_FUSION    → 精度>200 ? AMAP_CELL : AMAP_WIFI │
│   TENCENT_FUSION → TENCENT_WIFI / CELL / BT_HIGHPREC│
│   BAIDU_FUSION   → 精度>100 ? BAIDU_CELL : BAIDU_WIFI│
└───────────────────────────────────────────────────┘
        ↓ 塞进 vb/c.f18144h : List<Pair<provider, Location>>
┌───────────────────────────────────────────────────┐
│ NlpFusionMgr (vb/c.g) —— ★ 真正的融合算法           │
│   算法标识：NlpFusionAlgo_v1.2                      │
└───────────────────────────────────────────────────┘
        ↓ 产出 provider="network" 的融合位置
┌───────────────────────────────────────────────────┐
│ FusionProvider (xb/i)                               │
│   new wb.h(..., 32).sendToTarget()  ← 只有它产 32   │
└───────────────────────────────────────────────────┘
        ↓
wb/i.q()  type==32 分支优先级最高 → 上报融合结果
```

**关键点：type=32 这个“融合结果”是 `xb/i.java`（FusionProvider）生成的，
它在 `q()` 里的优先级高于高德原始结果（type=4）。**

### 融合算法 `vb/c.java:g()` 全文还原

```java
public Location g() {
    // ① 有高精度结果 → 直接用，不融合
    Location h10 = h(list);                    // 找 provider 含 "HIGHPRECISION"
    if (h10 != null) { log("report high precision location"); return h10; }

    // ② 有缓存 GNSS → 直接用
    if (list.get(0).second.getProvider().equals("CACHED_GNSS")) {
        log("report CACHED_GNSS"); return list.get(0).second;
    }

    int size = list.size();
    if (size >= 3) {
        // ③ 三家都在 → 两两配对算距离，选最一致的一对
        b pair = d(list);
        if (pair != null) location = i(pair.c(), pair.d());
    } else if (size == 2) {
        location = i(list.get(0).second, list.get(1).second);
    } else if (size == 1) {
        location = list.get(0).second;
    }
    list.clear();
    return location;
}
```

#### ③ 两两家距离筛选（`d()`）—— 剔除离群值

```java
private b d(List<Pair<String,Location>> list) {
    if (list.size() < 3) return null;
    // 任意两家两两配对，算距离
    for (i = 0; i < size-1; i++)
        for (j = i+1; j < size; j++)
            pairs.add(new b(j(loc_i, loc_j), loc_i, loc_j));
    if (pairs.size() < 3) return null;
    // 选距离最小（位置最一致）的那一对
    b best = pairs.get(0);
    for (k = 1; k < pairs.size(); k++)
        if (pairs.get(k).a(best)) best = pairs.get(k);
    return best;
}
```

**三家之中，位置最接近的两家被选中融合，第三家（离群值）被排除。**
这是典型的“三取二一致”容错策略。

#### 融合公式（`i()` → `f()` / `e()`）

```java
private Location f(List<a> list) {          // a = (置信度等级, Location)
    int la = list.get(0).a();
    int lb = list.get(1).a();
    if (Math.abs(la - lb) >= 2) {
        log("report confident location");
        return la > lb ? new Location(locA) : new Location(locB);  // 差距大 → 取高的
    }
    log("report average location");
    return e(locA, locB);                                       // 差距小 → 取平均
}

private Location e(Location a, Location b) {
    Location r = new Location(a);
    r.setLatitude((a.getLatitude()  + b.getLatitude())  / 2.0);   // 中点
    r.setLongitude((a.getLongitude() + b.getLongitude()) / 2.0);
    r.setAccuracy((a.getAccuracy() + b.getAccuracy()) / 2.0f);    // 精度取平均
    r.setProvider(a.provider + "_" + b.provider + "_AVG_FUSION");
    return r;
}
```

**两种策略**：
- 置信度差 **≥ 2** → 取置信度高的那家（不平均）
- 置信度差 **< 2** → 坐标取中点（真·平均融合）

#### 还有个直接规则：WiFi 胜 基站

```java
// vb/c.java:250
if (provider1.contains("WIFI") && provider2.contains("CELL")) return location1;
if (provider1.contains("CELL") && provider2.contains("WIFI")) return location2;
```

### 置信度是**动态学习**出来的

```java
// vb/a.java:f()  getSDKConfidenceList
public static List<Pair<Integer,Integer>> f() {
    List<Pair> out = new ArrayList();
    if (f18124i.size() >= 2 && (c = c(f18124i)) > 0) out.add(new Pair(1, c));  // 腾讯
    if (f18122g.size() >= 2 && (c = c(f18122g)) > 0) out.add(new Pair(4, c));  // 高德
    if (f18123h.size() >= 2 && (c = c(f18123h)) > 0) out.add(new Pair(2, c));  // 百度
    return out;   // 之后按置信度排序
}
```

三家各自的历史定位精度被记录、打分（`c(list)`），得分高的在融合时权重更大。
**这是在线学习，不是写死的优先级。**

### 那 `q()` 里的 `"resultProviderType do not match"` 是什么？

```java
// wb/i.smali 还原
if (type == 64)       offline  = loc;
else if (type == 32)  fused    = loc;   // ← 融合结果，优先级最高
else if (type == 4)   standard = loc;   // ← 高德原始结果
else                  log("resultProviderType do not match");   // 腾讯1/百度2 的【原始】结果
```

**这里的“丢弃”是指“原始结果不参与最终选择”——因为它们已经通过融合被用掉了。**
不是白传，是“传了→参与融合→融合结果胜出”。

### ✅ v3 定论

| 问题 | 答案 |
|---|---|
| 三家都发请求吗？ | ✅ 是 |
| 存在融合吗？ | ✅ **存在**，`NlpFusionAlgo_v1.2`（`vb/c.g()`） |
| 融合策略 | 3 家 → 两两算距离选最一致的 2 家 → 置信度差 ≥2 取高的 / <2 取中点 |
| 腾讯/百度白传吗？ | ❌ **不白传**，参与融合计算 |
| 最终上报 | type=32 融合结果（`provider="network"`） |
| 优先级 | HIGHPRECISION > 缓存GNSS > **融合(32)** > 高德(4) > 百度离线(64) |
| 设计合理吗 | ✅ **技术上合理**（交叉校验 + 离群剔除 + 动态置信度） |
| 代价 | ❌ 隐私上要三家全量 WiFi/BLE |

---

## 2.3 三家分别上传什么（逐字段拆解）

### 🔴 腾讯 —— 最详细，字段全扒出来了

```java
// o0/u0.java:e(z0) —— 组装请求体
JSONObject:
  "wifis" : [ {mac, rssi, ts}, ... ]          // ★ 扫描到的所有 WiFi
  "cells" : [ {mcc, mnc, lac, cellid, rss}, ... ]  // ★ 基站
  "bles"  : [ {mac, major, minor, rssi, time}, ... ] // ★ BLE 信标
  "wlan"  : {mac, rssi, ssid}                // ★ 当前连接的 WiFi（含名字！）
```

```java
// o0/u0.java:c(z0) —— 端点
String url = "https://lbs.map.qq.com/loc?c=1&mars=10&obs=1";
byte[] body = encrypt(e10.getBytes("GBK"));    // GBK 编码 + 自定义加密
```

**字段敏感度**：

| 字段 | 内容 | 风险 |
|---|---|---|
| `wlan.ssid` | **WiFi 名称**（常是「张三家的网」「XX公司-5G」） | 🔴 可识别身份/场所 |
| `wlan.mac` | 路由器 BSSID | 🔴 WiFi 地理库精确定位 |
| `wifis[]` | 周围所有 WiFi 的 MAC + 信号 | 🔴 定位精度 ~10m |
| `cells[]` | MCC/MNC/LAC/CellID | 🟡 基站级定位 ~500m |
| `bles[]` | 所有 BLE 信标 MAC + major/minor | 🔴 商场/机场室内定位 |

其他腾讯端点（全部编译进同一 SDK）：

```
https://analytics.map.qq.com/?sf           // 行为埋点（D_CH_ID=fc_sdk, D_FC_SRC=209）
https://analytics.map.qq.com/?wf4          // WiFi 上报埋点
https://analytics.map.qq.com/tr?utr       // 上报
https://rttgpsreport.map.qq.com/report?type=sdk&key=5e1fe70424035ee83066ac22b24f31dc
                                            // ★ RTK/GPS 原始数据上报（GpsNaviPro）
https://rgeorest.map.qq.com/               // 逆地理
https://nlp.map.qq.com/?sf                 // NLP 结果
https://cs.map.qq.com/key                  // 取密钥
https://lbs6.map.qq.com/k
https://lbs-trpc.map.qq.com/k
https://mt.map.qq.com/key
https://flpst.map.qq.com/u
https://regionlbs.map.qq.com/
https://testdatalbs.sparta.html5.qq.com/tr  // 测试环境（打包进去了！）
https://lstest.map.qq.com/nlpdr?sf          // 测试环境
```

> ⚠️ 注意：**测试域名 `testdatalbs.sparta.html5.qq.com` 和 `lstest.map.qq.com` 被编译进生产包**，
> 由 `q1.f15221i` 标志切换。这属于 SDK 打包不干净。

### 高德

```java
// com/amap/location/adiu/net/a.java —— 设备标识上报
String url = "https://adiu.amap.com/ws/device/adius?channel=<ch>&div=<div>&sign=<签名>";
JSONObject body:
  "tid"  : ""          // 空
  "diu"  : <设备ID>     // ★ 高德设备唯一标识
  "diu2" : <设备ID2>
  "diu3" : ""
```

```java
// xb/a.java —— 初始化，productName 固定 "opposdk"
AmapConfig amapConfig = new AmapConfig();
amapConfig.productName = AmapConfig.PRODUCT_OPPO;   // = "opposdk"
amapConfig.needReverseGeo = true;
amapConfig.reverseGeoToAddress = true;
```

**高德上报内容**（`AmapFPS` 类）：

```java
// com/amap/android/location/AmapFPS.java
public List<CellInfo> cellInfoList;
public CellLocation cellLocation;
public WifiInfo mainWifi;
public List<NeighboringCellInfo> neighboringCellList;
public String networkOperator;
public List<ScanResult> wifiList;      // ★ 完整 WiFi 扫描结果
```

其他端点：

```
https://rgeo-aloc.amap.com/geo/r?       // 逆地理
https://rgeo-aloc.amap.com/rgeo/r?q=1&type=0
http://cgicol.amap.com/dataPipeline/uploadData     // ★ 数据回传（生产也是 http！）
http://aps.testing.amap.com/dataPipeline/uploadData // ★ 测试环境（http）
https://offline.aps.amap.com/LoadOfflineData/repeatData?
http://aps.oversea.amap.com/APS/r?      // 海外
```

**高德内嵌 key（明文）**：

```xml
<authentication version="2.2">
  <key key="eJwVwbkNACAMBLCaYSLlIM-1ScFSiN0RNgb0g1PHge4yLkqUpTR9SSQg1WG16R457wMMKgrm"
       username="AutoNavi" />
</authentication>
```

→ `cgicol.amap.com/dataPipeline/uploadData` 走 **http 明文**，是个实实在在的降级点。

### 百度

```
https://loc.map.baidu.com/sdk.php                              // 主定位
https://loc.map.baidu.com/cfgs/loc/commcfgs                    // 配置
http://blg.map.baidu.com/cfgs/loc/commcfgs_ly                  // 配置（http）
https://newclient.map.baidu.com/client/opennlp/service         // NLP
https://daup.map.baidu.com/ofloc/offdis/grid                   // ★ 离线定位网格上报
https://daup.map.baidu.com/ofloc/offdis/data                   // ★ 离线定位数据上报
https://blg.map.baidu.com/ofloc/offdis/stat                    // 离线统计
http://blg.map.baidu.com/ofloc/offdis/data                     // （http）
http://blg.map.baidu.com/ofloc/offdis/grid                     // （http）
```

百度隐私政策链接（自己声明的）：
`https://newclient.map.baidu.com/client/mecppartner/privacy/nlpprivacy`

### 千寻位置（Ntrip / RTK）

```java
// com/oplus/location/precise/QESdkHelper.java:173
PP_eDGNSSEnums.LocationStatus r = mEDGNSSManager.enablePPENtripStream(
    "100.100.100.100", "model", "test", "test", 8002L, true, false, true);
```

**这里有点意思**：host 硬编码 `100.100.100.100`（一个内网/测试 IP），账号 `test/test`，
端口 8002 —— 这明显是**测试配置遗留**。实际生产环境走 DGNSS 配置下发。

千寻的定位是什么：**RTK 差分数据服务**，服务于「车道级导航」。
它需要收到你的精确 GPS 坐标（GGA 报文）才能返回差分改正数。

## 2.4 触发条件（什么时候真的上传）

```
任意 App 请求定位
  → framework 走 NetworkLocationProvider
    → NetworkLocationService（com.oplus.location）
      → wb.i（主控制器）
        → wb.k.ProviderManager.h(type)
          → 三家并行发请求（腾讯1 + 百度2 + 高德4）
            → xb.j（腾讯）/ xb.b（百度）/ xb.a（高德）
              → 采集 WiFi/BLE/基站 → 加密 → POST
```

| 条件 | 行为 |
|---|---|
| 定位总开关关闭 | ❌ 不上报 |
| App 只给了「大致位置」 | ⚠️ 仍可能走网络定位（本来就是粗定位） |
| 有 GPS 且有信号 | 一般不用网络定位 |
| 室内 / 地下 / 首定位（TTFF） | ✅ **必触发** |
| 高精度导航（车道级） | ✅ 触发 RTK（千寻/腾讯） |

**关键：这不是某个 App 的行为，是系统定位服务本身。你打开任何一个需要定位的 App，都可能触发。**

## 2.5 逆地理（Reverse Geocode）—— 什么时候用？

> 你问「逆编码是什么时候会用到」，这得先区分清楚它跟定位是**两条完全独立的链路**。

### 是什么

| 名称 | 方向 | 例子 |
|---|---|---|
| **地理编码**（Geocode / GC） | 地址 → 坐标 | “杭州市西湖区文三路 100 号” → 30.28, 120.13 |
| **逆地理编码**（Reverse Geocode / RGC） | 坐标 → 地址 | 30.28, 120.13 → “浙江省杭州市西湖区文三路…” |

**注意：逆地理不是定位。** 定位是「算出你在哪」，逆地理是「把你已经知道的坐标翻译成人类可读的地址」。

### 触发时机（只有 App 调 Geocoder 才触发）

```java
// rb/b.java:onGetFromLocation —— 这就是 framework 的 Geocoder.getFromLocation()
public String onGetFromLocation(double lat, double lon, int maxResults,
                                GeocoderParams params, List<Address> out) {
    if (!ic.b.h()) return null;                     // 没开机向导就不做
    log("RGC request", "%.2f:%.2f");
    bc.a aVar = new bc.a();
    aVar.p(lat).r(lon).u(maxResults).o(params).n(out);
    this.f16990a.z(aVar);                           // → wb.g.k() → 高德
    return aVar.j();
}
```

调用方：**Android framework 的 `Geocoder` API**。

```java
// 任意 App 调这个就会过来：
new Geocoder(context).getFromLocation(lat, lon, 1);   // ← 逆地理
new Geocoder(context).getFromLocationName("西湖", 1);  // ← 地理编码
```

**典型场景**：

| 场景 | 说明 |
|---|---|
| 相册「地图相册」 | 显示「拍摄于 杭州市西湖区」 |
| 照片详情看地址 | 同相册 |
| 天气 App 显示当前城市 | 定位后转城市名 |
| 外卖/打车显示「当前位置」 | 显示“XX 大厦”而不是坐标 |
| 部分 App 的拍照/打卡地点标注 | — |

**这些场景里，坐标系是已经拿到的，只是要翻译成文字。**

### 逆地理用的是哪家？—— **只有高德**

```java
// wb/j.java
private int f18627b = 4;                 // geocodeProviderMask = 4 = 高德
public int c() { return this.f18627b; }

// wb/g.java:s() 选逆地理 provider
int i10 = -1;
if ((this.f18576b.c() & 1) > 0)      i10 = 1;   // 腾讯 key
else if ((this.f18576b.c() & 2) > 0) i10 = 2;   // 百度 key
else if ((this.f18576b.c() & 4) > 0) i10 = 4;   // 高德 key

if (i10 >= 0) this.f18584j = this.f18591q.e(i10);
if (this.f18584j == null) this.f18584j = this.f18591q.e(4);   // ★ 兜底也是高德
```

**两个结论**：
1. 逆地理 **默认走高德**（`f18627b = 4`）
2. `h(int)` 里的 `nextInt()` 随机，**只在这三家逆地理 key 全都无法匹配时才会执行** —— 基本碰不到

### 逆地理会上传什么

```java
// xb/a.java:91
str = this.f19034h.reverseGeocode(aVar.c(), aVar.f(), aVar.i(), aVar.d(), aVar.a());
```

请求体是：**经度 + 纬度 + 语言 + 最大结果数**。

**⚠️ 它只发坐标，不发 WiFi/BLE 列表。** WiFi/BLE 是「定位」阶段传的。

```xml
<!-- 高德逆地理请求（f3/b.java:524） -->
<ReverseGeoRQ xmlns="http://rgeo.amap.com/wps/2014" version="2.24"
              street-address-lookup="full">
  <authentication version="2.2">
    <key key="eJwVwbkNACAMBLCaYSLlIM-1ScFSiN0RNgb0g1PHge4yLkqUpTR9SSQg1WG16R457wMMKgrm"
         username="AutoNavi" />
  </authentication>
  <point><latitude>%f</latitude><longitude>%f</longitude></point>
</ReverseGeoRQ>
```

端点：`https://rgeo-aloc.amap.com/rgeo/r?q=1&type=0`

### ⚠️ 隐私影响分析

| 对比 | 定位 | 逆地理 |
|---|---|---|
| 触发 | 任意 App 请求定位 | **任意 App 请求 Geocoder** |
| 发给谁 | 腾讯+百度+高德（三家） | **只有高德** |
| 发什么 | WiFi列表 + 基站 + BLE | **只有经纬度** |
| 频率 | 室内/冷启动高频 | 只在需要显示地址时 |

**逆地理反而比定位“干净”** —— 它不传 WiFi，只传你**已经知道的坐标**。

但有个隐含影响：**高德能把你每次逆地理的坐标串起来，画出轨迹**。
如果你的相册带 GPS 照片很多，又频繁看地址，高德就能知道你去过哪些地方。

### 拦不拦？

| 目标 | 做法 |
|---|---|
| 拦逆地理 | DNS 拦 `rgeo-aloc.amap.com` → 地图相册不显示地名，天气 App 显示“未知位置” |
| **只想防 WiFi 外传** | **不用拦逆地理**，拦 `lbs.map.qq.com` 就够了 |
| 保留功能 | 不拦，知道“坐标会发给高德”就行 |

**结论：拦逆地理性价比低（只漏坐标、只给一家），拦定位的 WiFi 上报性价比高。**

---

## 2.6 「接三家」到底合不合理？我的判断

### 厂商的官方理由（从代码能推出来的）

1. **可用性冗余**：一家挂了还有别家。网络定位是「兜底」，不能因为腾讯限流就定位失败
2. **覆盖差异**：三家在国内的 WiFi/基站库覆盖有差异，某些区域 A 准、某些区域 B 准
3. **冗余设计**：高德返回异常时其他两家兜底（但实现上没做成本优化）
4. **离线能力**：百度提供离线定位（`OFLOCOFFDIS`），无网也能粗定位
5. **RTK 必须两家**：千寻 + 腾讯各有所长（千寻是专业差分服务商，腾讯是互联网方案）

### 但这套设计的问题

| 问题 | 说明 |
|---|---|
| 🔴 **三倍的数据暴露面** | 同一个 WiFi 列表要发给三家公司，任一家泄露就等于全泄露 |
| 🔴 **隐私政策含糊** | 政策只说「Wi-Fi列表、基站列表、蓝牙列表」，没说你**同时**发给三家 |
| 🟠 **降级到 http** | 高德 `cgicol.amap.com`、百度 `blg.map.baidu.com` 都有 http 明文端点 |
| 🟠 **测试域名进生产** | 腾讯 `testdatalbs.sparta.html5.qq.com`、高德 `aps.testing.amap.com` |
| 🟠 **明文 key** | 高德 RTK key 硬编码在 XML 里 |
| 🟠 **测试账号残留** | 千寻 `100.100.100.100` + `test/test` |

**我的看法**：
- **融合设计本身是合理的** —— 三家交叉校验 + 距离筛选 + 置信度加权，室内定位确实更准
- **但隐私代价高** —— 算法上的收益，是拿「三方全量 WiFi/BLE 上传」换来的
- **三倍暴露是真问题** —— 用户以为「位置信息给我自己用」，实际是三家地图公司都拿到了
- **合规上站不住** —— 隐私政策列了 6 个 SDK 但没强调「三家并行」，普通用户不会意识到

## 2.7 你要怎么处理

### 方案 A：关闭系统定位总开关（最彻底）

```
设置 → 位置信息 → 关闭
```
代价：所有定位功能失效。**日常不可行。**

### 方案 B：DNS 拦掉全部三家（推荐给「只要本地定位」的人）

```
# 腾讯
lbs.map.qq.com
lbs6.map.qq.com
lbs-trpc.map.qq.com
cs.map.qq.com
mt.map.qq.com
analytics.map.qq.com
rgeorest.map.qq.com
nlp.map.qq.com
rttgpsreport.map.qq.com
flpst.map.qq.com
regionlbs.map.qq.com

# 百度
loc.map.baidu.com
newclient.map.baidu.com
daup.map.baidu.com
blg.map.baidu.com

# 高德
adiu.amap.com
rgeo-aloc.amap.com
aps.amap.com
offline.aps.amap.com
cgicol.amap.com
```

**代价**：室内/无 GPS 场景定位变慢或失败；导航冷启动变慢。
**但 GPS 有信号时仍能定位**（纯 GPS，不上报 WiFi）。

### 方案 C：只拦最敏感的（折中）

```
lbs.map.qq.com           # 唯一上传 ssid + bles 的端点
adiu.amap.com            # 高德设备 ID
daup.map.baidu.com       # 百度离线数据
```

保留 `loc.map.baidu.com`、`rgeo-aloc.amap.com` 等逆地理，功能基本不受影响。

### 方案 D：什么都不做，但知道自己在被谁看到

至少知道：**你的 WiFi 名 + 周围蓝牙设备，会发给腾讯、百度、高德三家。**

---

# 第三部分：交叉发现（顺手查到的）

## 3.1 数字健康的 TLS 缺陷（补充说明）

母报告已经写了 `s1/a.java` 的 `C0230a` TrustManager。这里补一条判断：

```java
class C0230a implements X509TrustManager {
    private void a(X509Certificate[] chain, String authType) throws CertificateException {
        if (chain == null) return;              // 空链放行
        for (X509Certificate c : chain) {
            try {
                c.checkValidity();
                c.verify(c.getPublicKey());     // 自签恒真
            } catch (Throwable ignored) { }     // 全吞
        }
    }
    public void checkServerTrusted(...) { a(...); }   // 永不抛
}
```

**这段代码如果被用于实际连接，等价于 `TrustManager` 全放行。**
从 `h(trustManager)` 的用法看，它至少构造过 `SSLContext.getInstance("SSL")`。
是否真的挂到 OkHttp 上，需要抓包或动态 hook 确认 —— 但**代码存在本身就该报给厂商**。

## 3.2 定位服务里也有明文 key

```xml
<!-- 高德 RTK -->
<key key="eJwVwbkNACAMBLCaYSLlIM-1ScFSiN0RNgb0g1PHge4yLkqUpTR9SSQg1WG16R457wMMKgrm" username="AutoNavi" />
```

```java
// 千寻测试配置
enablePPENtripStream("100.100.100.100", "model", "test", "test", 8002L, ...)
```

---

# 四、结论汇总

| 问题 | 结论 |
|---|---|
| **数字健康关掉屏幕用时能停上传吗** | ✅ 能（正常路径），但上传函数本身无开关，被系统组件 call 仍会传 |
| **定位服务有几个 SDK** | 🔴 **6 个**（腾讯定位、百度NLP、高德、腾讯3D、千寻RTK、腾讯RTK），不是 3 个 |
| **为什么接这么多** | 覆盖差异 + 离线 + RTK；核心是**三家交叉校验做融合**（`NlpFusionAlgo_v1.2`） |
| **会上传什么** | WiFi 列表（含 **SSID 名字**）、基站列表、**BLE 信标**、GPS 原始数据 |
| **发到哪** | 腾讯 `lbs.map.qq.com` / 百度 `loc.map.baidu.com` / 高德 `adiu.amap.com` 等 30+ 端点 |
| **最大风险** | 同一份 WiFi 数据发给三家；部分端点走 http 明文 |
| **存在融合吗？** | ✅ **存在**。三家结果归一化后全部进入 `vb/c.g()` 融合 |
| **融合策略** | 3 家 → 两两算距离选最一致的 2 家 → 置信度差 ≥2 取高的 / <2 取坐标中点 |
| **最终上报谁？** | type=32 融合结果（provider=`network`），优先于任何单一 SDK |
| **百度离线（64）什么时候用？** | 仅在没有在线结果时（`Offline location won't report when online location exist.`） |
| **逆地理什么时候触发？** | 任意 App 调 `Geocoder.getFromLocation()`（地图相册、天气、外卖…），**只传经纬度给高德一家** |

---

**报告时间**：2026-11-06
**样本**：`/tmp/g-apk/oplusloc.apk`、`/tmp/g-apk/dw.apk`

---

# 附录 B：融合算法的验证路径（可复现）

## B.1 我前两版为什么判错

| 版本 | 结论 | 错在哪 |
|---|---|---|
| v1 | 「随机分流」 | 只看到 `wb/k.h()` 里的 `nextInt()`，但那只用于逆地理保底 |
| v2 | 「三家并行，只取高德」 | 只追了 `wb/i.q()` 的选择分支，看到 `"resultProviderType do not match"` 就收工 |
| **v3** | **三家结果融合** | 找到产出 `type=32` 的 `xb/i.java`（FusionProvider） |

**教训**：`q()` 是「从已有结果里挑」，但**结果列表里已经有融合产物**。
必须先问「这个 type=32 是谁生成的」，而不是假设只有三个 SDK 各产一个。

## B.2 关键文件索引

```
xb/j.java         腾讯 provider，c() 返回 1
xb/b.java         百度 provider，c() 返回 2
xb/a.java         高德 provider，c() 返回 4
xb/e.java         百度离线，c() 返回 64
xb/i.java         ★ FusionProvider，产出 type=32
vb/d.java         NlpLocFilterMgr，归一化 *_FUSION → *_WIFI/*_CELL
vb/c.java         ★ NlpFusionMgr，融合算法主体（g() / d() / f() / e() / i()）
vb/a.java         NlpCacheMgr，置信度学习（f() getSDKConfidenceList）
wb/k.java         ProviderManager，provider 创建与掩码过滤
wb/j.java         配置：f18626a=599（定位掩码），f18627b=4（逆地理掩码）
wb/g.java         地理编码/逆地理管理器
wb/i.java         ★ 主控制器，q() 最终选择（需 smali 还原）
```

## B.3 `q()` 的反编译问题

`wb/i.q()` jadx 直接报 `UnsupportedOperationException`，必须用 apktool：

```bash
java -jar ~/.openclaw/workspace/tools/apktool.jar d -f \
     /tmp/g-apk/oplusloc.apk -o /tmp/locsmali/sm
grep -n "\.method private q()V" -A180 /tmp/locsmali/sm/smali/wb/i.smali
```

## B.4 融合算法的可观测证据

如果要在真机上验证融合确实发生：

```bash
# 1. 看是否有 AVG_FUSION 后缀的 provider
adb logcat -s NlpFusionMgr | grep -E "report (average|confident) location|AVG_FUSION"

# 2. 看三家是否都有结果进来
adb logcat -s NlpLocFilterMgr | grep "updateFusionLocType"

# 3. 看最终选中的类型
adb logcat -s i | grep -E "PROVIDER_LOC_FUSION|Set standardLocation|request providers left"

# 4. 看置信度学习
adb logcat -s NlpCacheMgr | grep "getSDKConfidenceList"
```

预期日志顺序：
```
request location: 1 / 2 / 4          ← 三家都发
updateFusionLocType: TENCENT_WIFI    ← 归一化
updateFusionLocType: AMAP_WIFI
updateFusionLocType: BAIDU_WIFI
report average location              ← 融合（或 report confident location）
chooseAndReportLocation: PROVIDER_LOC_FUSION
```
