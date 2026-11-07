# 第十五轮补（H-2）：通讯录联系人会不会触发号码识别？

- **日期**：2026-11-06
- **问题**：当来电/短信的号码**已在通讯录里**，还会触发「智能识别陌生号码」的云端查询吗？
- **母报告**：`report-phase15-h-sms-phone-weather.md`

---

# 一、结论

| 场景 | 是否触发 `ted.number` 查询 | 是否会上传号码 |
|---|---|---|
| **电话：通讯录里的联系人** | ⚠️ **会触发**（无通讯录短路） | ⚠️ 取决于本地库 |
| **电话：陌生号码** | ✅ 触发 | ✅ 本地未命中就上传 |
| **短信：通讯录里的联系人** | ❌ **不触发** | ❌ 不上传 |
| **短信：陌生号码** | ✅ 触发 | ✅ 跟随 ted.number 策略 |

**核心差异：短信侧有通讯录/白名单判断，电话侧没有。**

---

# 二、电话侧（`com.android.incallui`）—— 无通讯录短路

## 2.1 调用链

```
OplusCall / OplusContactsInfoManager (j4/i.java)
  → 只有 location / whitelist 判断，没有 isInContacts 判断
  → y8.a.a().startQueryInfo(...)          // y8.c 接口
  → NumberInterfaceInvoker.startQueryInfo
  → OplusTedQuery.e(context, number, number, type, listener, slot)
  → tedquery.d.a().e(...)
  → 跨进程（gRPC / icdf）→ com.ted.number
```

## 2.2 🔴 关键：查询前只查本地黄页库，不查通讯录

```java
// com/android/incallui/number_recognition/tedquery/a.java:e()
public final void e(Context context, String str, String str2, int i10, b.a aVar, int i11) {
    h.k("OplusYellowPageQuery", " startQueryInfo number = " + h.l(str) + " type = " + i10);
    y8.b bVar = new y8.b();
    bVar.f17078a = str;
    bVar.f17079b = str2;
    bVar.f17089l = i11;
    d(context, str, i10, i11);          // 初始化
    if (c(bVar)) {                       // c() = 查本地黄页库（i(bVar)）
        bVar.f17088k = 3;
        aVar.a(bVar);
    } else {
        // 本地没查到 → 走云端 consumer
        if (!OPLUS_VERSION_EXP || OplusPhoneUtils.isNumberRecognitionEnable()) {
            Bundle bundle = new Bundle();
            bundle.putString("query_param", "QueryOmojiInfo");
            a(bVar, bundle, aVar);       // → gRPC → ted.number
        }
    }
    b();
}
```

```java
// OplusTedQuery.java:c()  —— 本地黄页库查询
protected boolean c(y8.b bVar) {
    Log.d("OplusTedQuery", "getYellowPageInfoFromLocalDB number = " + h.l(this.f5366e));
    return i(bVar);        // ← 本地库
}
```

**`c()` 只查「本地黄页标记库」，完全没有查通讯录。**

## 2.3 通讯录信息是在结果显示阶段才用的

```java
// m4/c.java:s() —— 判断"要不要显示黄页名"
public static boolean s(ContactCacheEntry e, String str, Context ctx) {
    if (e.isYellowPageNumber) return true;              // 已经是黄页号
    String loc = e.location;
    if (!TextUtils.isEmpty(e.yellowPageInfo.f17080c)) { // 有黄页名
        ...
        if (g.y(str)) {                                  // ← isFamilyOrCornetGroupNumber：短号判断，非通讯录
            e.isYellowPageNumber = false;
            return false;
        }
        e.isYellowPageNumber = true;
    }
}
```

```java
// OplusCall.java:165-170  —— 拿到通讯录 person_id 后
long j10 = contactCacheEntry.person_id;
if (j10 != -1) {                          // ← 有通讯录命中
    contactCacheEntry2.person_id = j10;
    contactCacheEntry2.contactType = contactCacheEntry.contactType;
    contactCacheEntry2.isYellowPageNumber = false;   // ← 只是「不显示黄页名」
    ...
}
```

**通讯录命中只影响「是否显示黄页名」，不影响「是否发起查询」。**

## 2.4 所以流程是

```
来电 → 号码
  ├ 查本地黄页库（命中 → 直接用，不上云）
  └ 未命中 → gRPC → ted.number
       ├ 查 ted.number 本地标记库
       └ 仍未命中 → 云端 phoneRec（★ 号码上传）
```

**通讯录联系人一样走这条路。** 只要"张三 138xxxx"没有出现在本地黄页库里，
就会触发查询（是否上云取决于 `isAccessNetwork`）。

## 2.5 ⚠️ 但有个缓解因素

`m4/c.java:s()` 里：

```java
if (!TextUtils.isEmpty(e.yellowPageInfo.f17080c)) {   // 只有「有黄页名」时才继续判断
```

如果通讯录联系人早期就填充了 `name`，UI 层可能根本不需要黄页结果 ——
但这是**显示层优化，不是查询层拦截**。

**结论：查询照发，只是结果可能不被使用。**

---

# 三、短信侧（`com.android.mms`）—— 有判断，但是黑名单不是通讯录

## 3.1 调用链

```
收到短信 → CustomReceiveSmsMessageAction.getBlockInfoWrapper()
  → 黑名单/白名单判断
  → gl.d.f(str) → isNAFCNumberSync
  → OStitch('key_nafc_identify') → NAFCIdentify
  → INumberService.queryNumberInfo / queryNumberInfoAsync
  → com.ted.number
```

## 3.2 关键判断代码

```java
// com/oplus/mms/datamodel/action/CustomReceiveSmsMessageAction.java:107
private static g.a getBlockInfoWrapper(Context ctx, String str, boolean z11, ...) {
    if (!p.g(context)) {
        return new g.a(z11 ? 16 : 0);
    }
    if (z11) {
        if (!or.f.p(str) && !or.f.k(context, str)) {
            return new g.a(16);
        }
    } else {
        if (z12) {
            return or.g.i(context, str, str2, z13, true, i11, r0Var);
        }
        if (!or.f.p(str) && !or.f.k(context, str) && gl.d.f(str)) {
            return new g.a(20);         // ← 20 = 需要号码识别
        }
    }
    return new g.a(0);
}
```

两个函数：

| 函数 | 含义 | 出处 |
|---|---|---|
| `or.f.p(str)` | 判断是否**特殊号码**（运营商服务号等） | 硬编码规则 |
| `or.f.k(ctx, str)` | 查 **`com.coloros.provider.BlackListProvider`** 的 **白名单**（`bl_list` / `kw_list` 同区） | `isInWhiteList` |

```java
// or/f.java:k()
public static boolean k(Context context, String str) {
    boolean z11 = ((Boolean) newFixedThreadPool.submit(new b(context, str))
                      .get(3000L, TimeUnit.MILLISECONDS)).booleanValue();
    yj.c.b("BlackListUtil", "isInWhiteList isWhite = " + z11);   // ← 白名单
    return z11;
}
```

**⚠️ 这不是通讯录！** 是「黑/白名单提供者」。

## 3.3 那通讯录会不会被间接包含？

`content://com.coloros.provider.BlackListProvider` 的数据来源在
`com.coloros.safecenter`（骚扰拦截）侧，通常是：
- 用户手动加入的黑/白名单
- 联系人是否自动加入白名单 —— **这取决于骚扰拦截的设置**

如果骚扰拦截里开了「联系人不拦截」，那联系人算法上会进白名单，
`or.f.k()` 返回 true → **不触发号码识别**。

**所以短信侧是「可能」不查联系人，取决于骚扰拦截配置，不是硬编码。**

## 3.4 还有一层：`gl.d.f(str)`

```java
// gl/d.java
public static final boolean f(String str) {
    // OStitch 调用 key_nafc_identify → is_nafc_number_sync
}
```

这层没有通讯录判断，只是转发到 `NAFCIdentify.isNAFCNumberSync(str)`。

## 3.5 短信侧的额外发现

```java
// NAFCIdentify.java:226
public static final boolean isNAFCIdentifyOff() { ... }
```

有一个**总开关** `isNAFCIdentifyOff`，如果为 true 整条链路跳过。

---

# 四、汇总对比

| 检查项 | 电话（incallui） | 短信（mms） |
|---|---|---|
| 查询前判通讯录 | ❌ **没有** | ⚠️ 间接（走白名单） |
| 查询前判黑名单 | ❌ | ✅ `BlackListProvider` |
| 查询前判特殊号码 | ❌ | ✅ `or.f.p()` |
| 是否必然触发云端 | 本地库未命中即触发 | 同上，但被白名单挡住 |
| 通讯录命中影响 | 只影响「是否显示黄页名」 | — |

---

# 五、结论与建议

## 5.1 直接回答

**当号码是通讯录联系人时：**

- **电话**：✅ **仍会触发「智能识别陌生号码」查询**。通讯录命中不阻止查询。
  是否上传号码取决于 `ted.number` 本地库是否命中。
- **短信**：⚠️ **可能不触发**，但**不是因为通讯录**，而是因为
  「白名单/特殊号码」判断。取决于骚扰拦截是否把联系人自动加白。

## 5.2 防御建议

| 目标 | 操作 |
|---|---|
| 彻底不查/不上传 | 拨号/联系人 → 设置 → 关闭「智能识别陌生号码」<br>（`NUMBERRECOGNITION_SWITCH`） |
| 只关云端、留本地 | 关闭 `KEY_ONLINE_RECOGNIZE_SWITCH` / `UpdateStrangers`<br>（Android T 之前叫 `UpdateStrangers`） |
| 短信侧额外加固 | 骚扰拦截 → 设置 → 开启「联系人不拦截」 |

## 5.3 两个开关的区别（重要）

```java
// PreferenceUtils.java
public static boolean isNumberRecognitionSwitchOn(Context c) {
    return Settings.Global.getInt(c.getContentResolver(), NUMBERRECOGNITION_SWITCH, 1) == 1;
}

public static boolean isOnlineRecognizeSwitchOn(Context c) {
    if (OsUtil.isAndroidT()) {
        return PropertySharedPreferenceUtil.getBoolean(c, KEY_ONLINE_RECOGNIZE_SWITCH, false);
    }
    return Settings.System.getInt(c.getContentResolver(), "UpdateStrangers", 0) == 1;
}
```

```java
// TedNumberApplication / BootBroadcastReceiver
q4.b.f10718a.b(isOnlineRecognizeSwitchOn(ctx) && isNumberRecognitionSwitchOn(ctx));
```

**最终 `networkAccess = 在线识别开关 AND 号码识别开关`**：

| 开关 | 默认 | 作用 |
|---|---|---|
| `NUMBERRECOGNITION_SWITCH`（Global，默认 **1**） | 开 | 总开关，含本地库 |
| `KEY_ONLINE_RECOGNIZE_SWITCH` / `UpdateStrangers`（SP，默认 **false**） | 关 | **云端查询** |

⚠️ **注意默认值**：`UpdateStrangers` 默认 0 = **云端查询默认关闭**。
也就是说，**出厂状态下号码可能不上云**，要靠用户手动开启「联网识别」。

## 5.4 验证命令

```bash
# 当前开关状态
adb shell settings get global NUMBERRECOGNITION_SWITCH
adb shell settings get system UpdateStrangers

# 观察是否真的查了（电话）
adb logcat -s OplusYellowPageQuery I Harass_Detect | grep -E "startQueryInfo|云端查询开始|本地库查询开始|cta非true"

# 观察短信侧
adb logcat -s NAFCIdentify BlackListUtil | grep -E "queryNumberInfo|isInWhiteList"
```

**预期**：如果 `UpdateStrangers = 0`，日志会打印 `cta非true，禁止联网查询`。

---

# 六、待验证

| # | 项目 | 方法 |
|---|---|---|
| 1 | 通讯录联系人来电时，日志是否出现 `startQueryInfo` | 真机打给联系人（需另一台手机） |
| 2 | 「联系人不拦截」默认是否开启 | 骚扰拦截设置截图 |
| 3 | `UpdateStrangers` 在 ColorOS 14 的实际默认值 | `adb shell settings get system UpdateStrangers` |
| 4 | ~~`m4/c.s()` 的 `g.y(str)` 是否查通讯录~~ | ✅ **已确认：不是通讯录**，是 `isFamilyOrCornetGroupNumber` 短号判断（首位 6、长度 3-6 等规则） |

---

**报告完成时间**：2026-11-06
