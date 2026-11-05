# 第四轮：谁是捐数据的人？—— 精确到代码路径

- **日期**：2026-11-05
- **起因**：Tom 问"位置和相册的信息是谁 Donate 的"，并给了 `dumpsys package` 结果
- **答案**：**全局搜索 `com.heytap.quicksearchbox`**。短信、相册是它自己读的；位置先用百度定位 SDK 取，再捐。

---

## 一、真机 `dumpsys` 结果解读

```
a041c68 com.oplus.statistics.rom/com.oplus.dcc.donate.DonateContentProvider filter 4d7f881
 Action: "android.intent.action.RECEIVE_DONATE_DATA"
```

**这条确认了两件事**：

1. Provider 只有一个实例，**在 `com.oplus.statistics.rom` 进程里**
2. **全系统只有这一个 Provider 声明了这个 action** —— 没有第二家接收方
   （如果有别的包也在收，这里会列出多个）

后面的 `[com.oplus.statistics.dcc.DonateContentProvider]:` 是 authority → provider 的映射，
以及 `[com.oplus.dcc.provider.TrackContentProvider]` 是另一个 provider（记录 trace，不是捐赠）。

---

## 二、全量扫描：到底有几个包在捐

我扫了 345 个 APK 的 **全部 dex + Manifest**（二进制字符串池，UTF-8 和 UTF-16 两种编码都查）：

| 包 | Manifest | dex |
|---|---|---|
| `com.oplus.statistics.rom` | ✅ 声明 provider | ✅ |
| **`com.heytap.quicksearchbox`** | — | ✅ `classes4.dex` 里同时有 `RECEIVE_DONATE_DATA` 和 `com.oplus.statistics.dcc.DonateContentProvider` |
| 其余 343 个 | ❌ | ❌ |

**只有全局搜索一个包在捐。** 小布助手、智慧数据增强那些我上轮猜的都不对 —— 它们有 READ_SMS 权限，
但**没有引用这个 Provider**，所以不捐。

---

## 三、全局搜索的捐赠代码（完整链路）

### 3.1 它把整个 DCC donate SDK 打包进了自己

`classes4.dex` 里有一整套：

```
com/oplus/dcc/donate/
    DccDonateDataApi                     ← 对外 API
    internal/config/  AlbumDonateConfig / SmsDonateConfig / Frequency / NetWorkType ...
    internal/biz/
        DonateContentProviderHelper      ← ★ 拼 URI 的地方
        DonateDataClientManager
        album/GalleryAlbumLoader         ← 相册读取
        album/GalleryOpenProviderHelper
        sms/loader/SmsLoader             ← ★ 短信读取
        sms/loader/MmsLoader             ← ★ 彩信读取
        sms/loader/SmsColumn / MmsColumn
        sms/SmsFilter
        location/LocationTransporter     ← ★ 位置写入
        check/{AlbumDonateCheck, FrequencyCheck, ChargingConstraintCheck, ScreenOffConstraintCheck, ...}
```

`Dcc_heytapRelease` 这个 build flavor 名字说明它是从 HeyTap 内部模块拿来的。

### 3.2 URI 拼法 —— 数字 = 表

`DonateContentProviderHelper.d()`：

```java
DonateDataType.ALBUM    → "1"    // → dwd_doa_t1_inc_h（相册表）
DonateDataType.SMS      → "2"    // → dwd_doa_t3_inc_h（短信表）
DonateDataType.LOCATION → "3"    // → dwd_doa_t2_inc_h（位置表）
```

和 statistics.rom 里的 `uriMatcher.addURI(authority, "1"/"2"/"3", ...)` 完全对应。

### 3.3 短信：**读真实短信库，含正文**

`SmsUri`（`SmsConst.kt`）：
```java
Uri.parse("content://sms/");
f16217b = Uri.parse("content://sms/inbox");   // ← 收件箱，实际用的就是它
Uri.parse("content://sms/sent");
Uri.parse("content://sms/draft");
Uri.parse("content://sms/outbox");
Uri.parse("content://sms/failed");
Uri.parse("content://sms/queued");
```

`SmsColumn`（`SmsConst.kt`）—— **要读哪几列**：
```java
{"_id", "thread_id", "type", "address", "body", "date", "read"}
                                    ↑↑↑↑↑↑↑↑
                               短信正文
```

`SmsLoader.b()` 实际查询：
```java
Cursor query = contentResolver.query(
    uri,                        // content://sms/inbox
    SmsColumn.a(),              // 上面那 7 列，含 body
    "_id > " + startId,         // 增量：只取上次 id 之后的新短信
    null,
    "_id ASC LIMIT " + limit);
```

`SmsLoader.a(Cursor)` 逐行构造 `SmsRecord(_id, thread_id, type, address, body, date, read)`。

**→ 是的，它会读短信正文。** 是增量读（只读新来的），不是每次全量扫。

**过滤**（`SmsFilter.a()`）：
```java
// 只保留 status == "READ" 或 "UNREAD" 的
// 再用 PhoneNumberUtil.b(number) 过滤号码
```
`PhoneNumberUtil.b()` 应该是「是否为普通手机号」判断（可能过滤掉 1069 之类的服务短号）。

**它自己的权限表**（`aapt2 dump badging` 确认）：
```
READ_SMS          ← 读短信
READ_CONTACTS     ← 读通讯录
READ_CALENDAR     ← 读日历
READ_MEDIA_IMAGES / VIDEO / AUDIO
ACCESS_FINE_LOCATION / COARSE
PACKAGE_USAGE_STATS
READ_LOGS
oplus.permission.OPLUS_COMPONENT_SAFE
oppo.permission.OPPO_COMPONENT_SAFE
```

### 3.4 相册：**不读 MediaStore，走相册 App 的私有 provider**

`GalleryOpenProviderHelper`：

```java
Uri f16170a = Uri.parse("content://com.open.gallery.smart.provider");

String[] f16171b = {
    "_id", "media_id", "_data", "dateTaken", "date_modified",
    "face_name",            // ★ 人脸识别结果
    "address",              // ★ 地点
    "tags", "english_tags", // ★ 标签
    "ocr",                  // ★★ 图片里的文字
    "bucket_name", "bucket_id",
    "_display_name", "title", "_size",
    "media_type", "mime_type", "duration",
    "longitude", "latitude",   // ★ 拍摄坐标
    "festival_name", "memory_name", "tagflags"
};

// 实际查询
Uri uri = f16170a.buildUpon().appendEncodedPath("searchInfo").build();
Bundle extras = new Bundle();
extras.putString("limit", ...);
extras.putString("selection", ...);
extras.putStringArray("selectionArgs", ...);
extras.putString("order", ...);
ContentProviderClient c = resolver.acquireUnstableContentProviderClient(uri);
Cursor cursor = c.query(uri, f16171b, extras);   // 走 Bundle 传参
```

**关键**：它不是自己扫照片，而是**问相册 App**（`com.coloros.gallery3d` 暴露的
`com.open.gallery.smart.provider`）要「智能搜索结果」。
也就是说 **OCR 文本、人脸名，是相册 App 已经算好的结果，全局搜索只是转发**。

`GalleryOpenProviderHelper` 上有 `@RequiresApi(api = 26)`，用 `acquireUnstableContentProviderClient`
（不稳定客户端，说明它能容忍对方进程挂掉）。

### 3.5 位置：**用百度定位 SDK 自己取**

`LocationTransporter.a(double lat, double lng, long time)` → 写入 `dwd_doa_t2_inc_h`。

谁调它？`DonateDataClientManager:166`：
```java
public static void a(DonateDataClientManager t, double d2, double d3, long j2) {
    new LocationTransporter(t.f16093a).a(d2, d3, j2);
}
```

而上游是这一条链：

```
com.heytap.quicksearchbox.common.location.LocationManager      ← 用百度 SDK
  └─ BDLocationListener.b(BDLocation location)   // 百度定位回调
        lat  = location.getLatitude()
        lng  = location.getLongitude()
        country/province/city/cityNumber/district/
        address = location.getLocationDescribe()   // ★ 位置描述（"在XX路附近"）
        adCode, poiName = location.getPoiList().get(0).getName()  // ★ POI 名
        locTimeMillis
        ↓ 存进 MMKV（MMKVKey.LOCATION_INFO）
```

**注意**：用的是 **百度地图 SDK（`com.baidu.location`）**，不是系统 LocationManager。
所以位置数据先经百度，再捐给 OPPO，**至少两个第三方**。

Google 的 `SystemLocationManager` 也在包里（走 `Geocoder` 反查地址），但捐赠这条链用的是百度。

---

## 四、触发条件：四个开关必须同时为真

`DccSmsManager.a()` / `DccAlbumManager.a()`：

```java
// 短信：canDonate = dccEnable && configEnable && userSettingEnable && personalEnable
boolean dccEnable        = DccDonateConfig.getDccEnable();            // 云端开关
boolean configEnable     = config.getSmsDonateConfig().getEnable();   // 云端配置里 SMS 捐赠子开关
boolean userSettingEnable= DCCSpManager.l().p();                      // 用户设置里的"体验计划"
boolean personalEnable   = SearchSettingSpManager.e().d(
                             DockSettingSpManager.SHOW_SEARCH_PERSONALIZED_RECOMMENDATION, true);
                             // ★ 默认 true！「个性化推荐」开关
```

日志里会打出：
```
canDonate:dccEnable=..., configEnable=..., userSettingEnable=..., personalEnable=...
```

**→ 你要关的地方是：全局搜索 → 设置 → 个性化推荐 / 或设置里「用户体验改进计划」。**
两者任一关掉，短信和相册就不捐了。

**约束条件**（`BaseDonateConstraint`）—— 捐赠不是随时跑，要满足：
```
frequency    执行频率
networkType  网络类型（可能只允许 WiFi）
charging     是否要求充电中
electricity  电量阈值
temperature  温度上限
screenOff    是否要求息屏
availMem     可用内存下限
```
`DccManager` 里还有个逻辑：相册频率如果 ≤60 秒会被强制改成 3600 秒（**1 小时一次**）。

---

## 五、对你上一个问题的修正

| 之前说的 | 实际情况 |
|---|---|
| "有三张表，可能是别的 App 捐的" | ✅ 对，但**只有一个 App**：全局搜索 |
| "小布助手/智慧数据增强/全局搜索 三个都可疑" | ❌ 只有**全局搜索**真在捐，另两个只是有权限 |
| "statistics.rom 不看短信" | ✅ 仍然正确，它没 READ_SMS |

---

## 六、所以真实的数据流是这样

```
┌─────────────────────────────────────────────────────────────┐
│  com.heytap.quicksearchbox（全局搜索）                        │
│                                                              │
│  ① 短信：content://sms/inbox                                 │
│     → 列 {_id, thread_id, type, address, body, date, read}   │
│     → 过滤：status∈{READ,UNREAD} + 合法号码                    │
│                                                              │
│  ② 相册：content://com.open.gallery.smart.provider/searchInfo│
│     → 列 {face_name, ocr, tags, address, lat/lng, ...}       │
│     （OCR/人脸名是相册 App 算的，搜索只是转发）                  │
│                                                              │
│  ③ 位置：百度定位 SDK 回调                                     │
│     → {lat, lng, country, province, city, district,          │
│        address描述, adCode, POI名, 时间}                     │
│                                                              │
│  触发：dccEnable && configEnable && userSetting && 个性化推荐   │
│  约束：频率/充电/WiFi/息屏/电量/温度/内存                        │
└────────────────────────┬────────────────────────────────────┘
                         │ content://com.oplus.statistics.dcc.DonateContentProvider/2
                         │ /1 /3  + query param method
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  com.oplus.statistics.rom（数据基础服务）                     │
│  DonateContentProvider → SmsDataManager / AlbumDataManager / │
│                          LocationDataManager                 │
│  → 写 dwd_doa_t3_inc_h / t1 / t2（AES-GCM 加密 number/content）│
│  → 到点批量上传（/v1/stat/* 或 /v3_1/dcs/*）                    │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、立刻可做的验证

### 7.1 看全局搜索现在到底捐没捐

```bash
# 看它的日志（需要能读 logcat，一般连 USB 就能看自己的应用日志）
adb logcat -s DccSmsManager DccAlbumManager DccManager SmsLoader GalleryOpenProviderHelper
```

如果看到 `canDonate:dccEnable=..., userSettingEnable=false, personalEnable=false` → 没捐。
如果四个全是 true → **正在捐**。

### 7.2 关掉捐赠

两条路，任一即可：
1. **全局搜索 → 设置 → 关闭"个性化推荐"**（对应 `SHOW_SEARCH_PERSONALIZED_RECOMMENDATION`）
2. 关闭系统「用户体验改进计划」（对应 `DCCSpManager.l().p()`，你已经是 0 了）

通过 adb 直接读当前值：
```bash
# 看个性化推荐开关（key 名在 DockSettingSpManager 里，SP 文件名待确认）
adb shell run-as com.heytap.quicksearchbox ls shared_prefs/
```

### 7.3 确认有没有真捐出去

```bash
# 需要 root
adb shell su -c "ls /data/data/com.oplus.statistics.rom/databases/"
adb shell su -c "sqlite3 <db> 'select count(*) from dwd_doa_t3_inc_h'"   # 短信表行数
adb shell su -c "sqlite3 <db> 'select count(*) from dwd_doa_t1_inc_h'"   # 相册表行数
adb shell su -c "sqlite3 <db> 'select count(*) from dwd_doa_t2_inc_h'"   # 位置表行数
```

行数 > 0 = 真的捐了。这张表是加密的，但行数可以看出规模。

---

## 八、结论

**是的，你的短信会被读 —— 但读者不是 statistics.rom，是全局搜索（`com.heytap.quicksearchbox`），
而且只读收件箱里「新来的、已读/未读的、合法号码的」那部分，字段含正文。**

**相册**：不读原始照片，读相册 App 已经算好的「智能搜索索引」（人脸名/OCR/标签/坐标）。

**位置**：百度定位 SDK 取，含 POI 名和位置描述，精度高于单纯经纬度。

**这几条都受「个性化推荐」和「用户体验改进计划」两个开关控制**，关掉任一个就停。
但你现在的状态需要确认 `personalEnable` 是不是 true（它默认是 **true**）。
