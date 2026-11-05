# 第三轮：短信 / 位置 / 相册 数仓 —— 到底收了什么，谁在收

- **日期**：2026-11-05
- **起因**：Tom 问"会看我的短信吗"，并给了真机 adb 结果
- **结论先行**：**没有证据表明系统在自动读取短信内容**。
  短信表的存在目的是"**接收捐赠**"，不是"主动抓取"。位置/相册同理。

---

## 一、真机结果解读

| 查询 | 返回 | 含义 |
|---|---|---|
| `com.oplus.dcs.data.url` 等 5 个 + `eap.release_host` | **全 null** | ⚠️ 这是本机实况，见下方"为什么是 null" |
| `oplus_customize_cta_user_experience` | **0** | ✅ **用户体验改进计划是关闭的** |
| `oplus_customize_system_stable_plan_switch` | null | 稳定性计划：未设置（代码里 null 按"未开启"处理） |
| `oplus_customize_cta_update_service` | **1** | 更新服务开着 |
| `/data/misc/ostats/...` 等三个目录 | Permission denied | 正常：普通 shell 用户读不到 system 数据 |

### 为什么 `ds.*.url` 是 null？

代码里 `p8/q.java` 的读法是：

```java
public String d() {          // com.oplus.dcs.data.url
    if (TextUtils.isEmpty(f7913c)) {
        f7913c = y2.b.b(this.f7919a.getContentResolver(), "com.oplus.dcs.data.url", "");
    }
    return f7913c;
}
```

用 `Settings.System` 读的，key 不存在就返回 `""`。三种可能：

1. **域名根本没预置在这个 Settings key 里**（更可能）——代码里 `c8/v.java` 有兜底：
   ```java
   if (r7.g.y().t() == 3) {
       str = w.b();                 // UrlConfig.DATA_HOST
   } else if (TextUtils.isEmpty(str)) {
       str = z10 ? w.c() : r7.g.y().v();   // 兜底默认值 / 动态方案
   }
   if (TextUtils.isEmpty(str)) {
       str = w.b();                 // 还是空就用 DATA_HOST
   }
   ```
   也就是 **Settings 为空时走另一个来源**（`r7.g.y().v()` 来自 `UrlConfig` 的运行时赋值，
   由 Provider / 云端配置注入）。
2. **你关了用户体验改进计划（=0）后，配置拉取链被切断**，所以这些 key 从没被写入过。
   —— 这个解释跟你的 `user_experience=0` 正好对上。
3. 本机 ROM 里这套 DCS 已经降级，靠别的通道（`mdp-appconf*`）做。

> **结论**：静态分析到此确实到顶了。再往下必须抓包，看 `com.oplus.statistics.rom` 进程
> 实际建立过哪些 TLS 连接（域名在 SNI 里，即使里面有加密也能看到）。

---

## 二、短信：**它不会主动读你的短信**

### 2.1 确凿证据：连短信权限都没有

`com.oplus.statistics.rom` 的完整权限清单（aapt2 dump badging）：

```
READ_PRIVILEGED_PHONE_STATE   QUERY_ALL_PACKAGES       INTERNET
ACCESS_NETWORK_STATE          RECEIVE_BOOT_COMPLETED   USE_FINGERPRINT
oplus.permission.OPLUS_COMPONENT_SAFE                  com.oplus.permission.safe.SECURITY
com.oplus.permission.safe.APP_MANAGER                  oplus.permission.RECEIVE_INSTALL_BACKGROUND
SCHEDULE_EXACT_ALARM          PACKAGE_USAGE_STATS      WRITE_SETTINGS
ACCESS_COARSE_LOCATION        ACCESS_FINE_LOCATION     ACCESS_BACKGROUND_LOCATION
WAKE_LOCK                     FOREGROUND_SERVICE       REORDER_TASKS
```

**没有 `READ_SMS`，没有 `RECEIVE_SMS`，没有 `READ_CONTACTS`，没有 `READ_CALENDAR`，没有 `READ_CALL_LOG`。**

再扫一遍 dex 确认没有别的读取路径：

```bash
grep -rE "content://sms|Telephony\.Sms|READ_SMS|SMS_RECEIVED|SmsMessage|content://mms" \
     /tmp/jadx-out/statistics/sources   →  0 命中
```

**没有任何代码去读系统短信库。** 这一点是硬的。

### 2.2 那短信表是干嘛的？——"数据捐赠"接收器

`SmsTable`（`c4/k.java` → 表名 `dwd_doa_t3_inc_h`）：

```java
CREATE TABLE IF NOT EXISTS dwd_doa_t3_inc_h (
    _id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT,        // 号码
    content TEXT,       // 正文
    status TEXT,        // 状态
    client_time TEXT,
    duid TEXT, oneid TEXT, hour TEXT, dayno TEXT
);
```

**字段名和结构是完整短信摘要。** 但关键在**谁往里写**：

`p3/m.java`（`SmsDataManager.kt`）只做两件事：
- `g(Uri, ContentValues...)` → **接收写入**
- `h(Uri)` → 查询（只有 `devQueryAll` 调试命令能读回，需过 `com.oplus.dcc.safe.auth` 校验）

而这个类**唯一的调用方**是：

```java
// com/oplus/dcc/donate/DonateContentProvider.java:102
if (match == 2) {
    return m.c(getContext()).g(uri, contentValuesArr);   // match=2 → SmsDataManager
}
```

Manifest 里它的声明：

```xml
<provider
    android:name="com.oplus.dcc.donate.DonateContentProvider"
    android:authorities="com.oplus.statistics.dcc.DonateContentProvider"
    android:permission="oplus.permission.OPLUS_COMPONENT_SAFE"
    android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.RECEIVE_DONATE_DATA" />
```

**翻译成人话**：这是一个**开放的收件箱**。别的系统应用（拿到 OPLUS_COMPONENT_SAFE 权限的）
可以主动把"我看到的短信"、"我拿到的位置"、"我知道的照片信息"**投递**进来，
statistics.rom 只负责存表和上传，它自己不去读。

> ⚠️ 但这个设计本身有隐私风险，且**比"自己读"更难审计**：
> 真正读短信的是那些持有 `OPLUS_COMPONENT_SAFE` 权限的应用（比如手机管家、信息、安全中心等）。
> 想知道短信有没有被捐，得去查别的包。**这是一条待办线索。**

### 2.2.1 捐赠方排查结果（2026-11-05 补测）

全量扫了 345 个 APK 的 Manifest：

- **持有 `OPLUS_COMPONENT_SAFE` 的：166 个包**（几乎是所有系统应用）
- **同时有 `READ_SMS` 的：14 个包**

| 同时具备「READ_SMS + 捐赠权限 + 其他敏感权限」的包 | 说明 |
|---|---|
| `com.android.mms` 信息 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.android.mms.service` 信息服务 | READ_SMS |
| `com.heytap.quicksearchbox` 全局搜索 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.heytap.speechassist` 小布助手 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.nearme.instant.platform` 快应用 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.oplus.metis` 智慧决策 | READ_SMS + 位置 |
| `com.oplus.pantanal.ums` 智慧建议 | READ_SMS + 位置 + 相册 |
| `com.coloros.sceneservice` 智慧数据增强 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.oplus.deepthinker` 智慧能力 | READ_SMS + 位置 |
| `com.oplus.securitypermission` 权限管理 | READ_SMS |
| `com.android.phone` 电话服务 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.android.contacts` 电话本 | READ_SMS + 相册 + 通讯录 |
| `com.android.bluetooth` 蓝牙 | READ_SMS + 位置 + 相册 + 通讯录 |
| `com.oplus.account` 账号中心 | READ_SMS + 相册 |

> **重点**：`com.heytap.speechassist`（小布助手）、`com.coloros.sceneservice`（智慧数据增强）、
> `com.heytap.quicksearchbox`（全局搜索）这三个都同时拥有「读短信 + 位置 + 相册 + 通讯录 + 捐赠权限」，
> 而且都是会主动分析用户内容的应用。**如果短信被捐，最可能从这三个之一出去。**
> 这是下一轮精扫的优先目标。

另外一个直接可验证的指标：`dwd_doa_t3_inc_h` 是 SMS 表、`dwd_doa_t2_inc_h` 是 Location 表，
如果真机上有这两个表的行数非零，就说明捐赠确实发生了。需要用 root 或 `run-as` 查（普通 shell 读不到）。

### 2.3 数据会不会被加密再存？

会被"混淆"：`c4/f.java:40`

```java
public void b(ContentValues contentValues) {
    String[] e10 = e();
    for (String str : e10) {
        if (contentValues.containsKey(str)) {
            contentValues.put(str, com.oplus.dcc.utils.a.e(contentValues.getAsString(str)));
        }
    }
}
// SmsTable.e() → {"number", "content"}
```

`com.oplus.dcc.utils.a.e()` 是 DCC 的加密封装（`DCC/AESUtil`，AES/GCM，key 固定为
`Hml.5Fe=DatdYTup` / iv `yUo.6Fe=Dyd` —— 见 `DccCipher.java`）。

**号码和正文是加密后才落库的。** 好的一面：本地文件里不是明文。
坏的一面：**key 是硬编码的，等于"可逆混淆"，不是真加密**。

---

## 三、位置：表结构完整，但采集方不在这个包

`LocationTable`（`c4/e.java` → 表名 `dwd_doa_t2_inc_h`）：

```java
CREATE TABLE ... (
    client_time TEXT,
    latitude DOUBLE, longitude DOUBLE,     // 精确坐标
    countrycode, address, country, province, city, area, street,
    duid, oneid, hour, dayno
);
```

**能精确到街道地址。**

### 但这张表也一样——只收不采

`p3/l.java`（`LocationDataManager.kt`）：

```java
public int d(Uri uri, ContentValues... values) {    // ← 写入入口
    if (!TextUtils.isEmpty(method))  return -1;
    for (ContentValues cv : values)
        a4.h.k0().l0(context, cv);                  // 插入 dwd_doa_t2_inc_h
}
public Cursor e(Uri uri) {                          // ← 读取，仅 devQueryAll + 鉴权
    if (n.a("devQueryAll", method) && com.oplus.dcc.safe.auth.c.b(context)) ...
}
```

`a4.h.l0(...)`（LocationDaoHelper）的**唯一调用方**就是 `p3/l.java`，
而 `p3/l.java` 只被 `DonateContentProvider` 的 match=3 分支调用。

**它没有申请定位权限去自己取？** 等等——它申请了：
```
ACCESS_FINE_LOCATION / ACCESS_COARSE_LOCATION / ACCESS_BACKGROUND_LOCATION
```

但我在整个 4936 个类里搜 `LocationManager` / `getLastKnownLocation` / `LocationListener` /
`GpsStatus`，**只有 androidx 的兼容库命中，业务代码零命中**。

> **结论**：这三个定位权限是**为捐赠链路准备的**（或者纯粹是历史遗留的声明），
> 代码里没有主动定位的实现。位置数据同样靠别的 App 捐赠。

---

## 四、相册：收了"照片理解结果"，不是照片本身

`AlbumTable`（`c4/a.java` → 表名 `dwd_doa_t1_inc_h`）：

```java
CREATE TABLE ... (
    media_id INTEGER,
    dateTaken TEXT, date_modified TEXT,
    face_name TEXT,          // ★ 人脸识别的"人名"
    address TEXT,            // ★ 拍摄/识别地点
    tags TEXT, english_tags TEXT,   // ★ 图片标签
    ocr TEXT,                // ★★ 图片里的文字（OCR 结果）
    bucket_name TEXT, size INTEGER, media_type INTEGER, mime_type TEXT,
    duration INTEGER, longitude DOUBLE, latitude DOUBLE,
    festival_name TEXT, memory_name TEXT,   // 节日、回忆相册名
    tagflags TEXT, duid, oneid, hour, dayno
);
```

**这是"相册理解画像"**：每张照片 → 谁、在哪、什么内容、上面有什么字、属于哪个回忆相册。

同样，`a4.b.l0()`（AlbumDaoHelper）唯一调用方是 `p3/a.java`（AlbumDataManager），
而 `p3/a.java` 只被 `DonateContentProvider` 的 match=1 分支调用。

> 也就是说：**相册的人脸名 / OCR 文本 / 地点标签，是从别处（相册 App、AI 服务）捐进来的**，
> statistics.rom 自己不扫描照片。

---

## 五、这个包真正自己采的，只有这些

前面澄清了"收"≠"采"。真正由 `com.oplus.statistics.rom` **自己动手**采集的是：

| 数据 | 证据 | 是否受开关控制 |
|---|---|---|
| **已安装应用清单**（包名/版本/首装时间/是否用过） | `j1.java:370` `getInstalledPackages(0)` | ❌ 不受控 |
| **应用启动/卸载事件**（含安装来源 caller） | `dwd_os_install_inc_h` 等表 | ❌ 不受控 |
| **前后台切换**（包名/Activity/停留时长/URI 参数） | `t.java` + 系统广播 `onActivityEnter` | ❌ 不受控 |
| **设备指纹**（型号/ROM/OTA/地区/语言/运营商） | `e4/g.java` r0() → `dim_device_info` | ❌ 不受控 |
| **WiFi SSID**（连接的网络名） | `y0/b.java:145` `getConnectionInfo().getSSID()` | ❌ 不受控 |
| **IMEI**（经 `colorGetImei` 私有 API） | `cloudconfig/device/DeviceInfo.java:531` | 仅用于测试机判定 |
| 内核日志 | `s2.java:295` `/data/oplus/kevent` | ✅ 关了会删文件 |

**短信 / 位置 / 相册 / 通讯录 / 通话记录 —— 它自己一律不碰。**
这几张表是"接收捐赠"的空壳，而且这个 shell 用户读不到（Permission denied 是正常的）。

---

## 六、真正该担心的三件事（比短信更实在）

1. **前后台 URI 参数**（`t.java:749` `jSONObject.put("uri", ...)`）
   如果你从某个 App 点链接跳到另一个 App，`intent://...?q=搜索词` 这种，
   整个 URI 会被写进 `event_info` 上传。**这个比短信更容易泄露"你在干什么"。**

2. **已装应用清单 + 使用时长**
   第三方 App 拿不到 `QUERY_ALL_PACKAGES` + `PACKAGE_USAGE_STATS`，
   这个系统应用能，而且**关掉开关也不停**。

3. **谁在往 DonateProvider 里捐数据**
   持有 `oplus.permission.OPLUS_COMPONENT_SAFE` 的应用。
   如果要查短信有没有真的被捐，得审计这些包：
   ```bash
   adb shell dumpsys package com.oplus.statistics.rom | grep -A2 DonateContentProvider
   # 或在全部 APK 里搜 OPLUS_COMPONENT_SAFE 的持有者
   ```

---

## 七、下一步（修正后的建议）

### 你现在的状态

开关 = 0（已关），所以：
- ✅ 内核日志不再采、文件已删
- ✅ 部分 DCS 事件停发
- ❌ **应用清单 / 前后台 / 设备指纹 / WiFi SSID 还在跑**
- ❓ 配置拉取链看起来没激活（ds.*.url 全 null 可能就是这个原因）

### 建议动作（按优先级）

**A. 抓包（最高优先级，一天能出结论）**

```bash
# 方法一：电脑侧 tcpdump（不需 root，不需装证书）
sudo tcpdump -i any -n -s 0 'tcp port 443' -w coloros.pcap
# 跑 1-2 小时，正常使用手机（开关可以来回切）

# 方法二：AdGuard Home 看日志（最直接）
# 把 statistics.rom 的 UID 对应查询按域名聚合
```

TLS 内容解不开，但 **SNI 里就是域名**——这直接就是最终黑名单，
而且能看出“开关关着的时候还发不发”。

**B. 验证“关了开关还发不发”**

```bash
adb shell settings put system oplus_customize_cta_user_experience 1   # 开
# 等 1 小时，抓包
adb shell settings put system oplus_customize_cta_user_experience 0   # 关
# 再等 1 小时，抓包，对比
```

注意代码里应用清单的上报间隔是 **12 小时**（`43200000` ms），所以观察窗口要足够长。

**C. 查捐赠是否真实发生（需要 root）**

```bash
adb shell su -c "ls -l /data/data/com.oplus.statistics.rom/databases/"
adb shell su -c "sqlite3 /data/data/com.oplus.statistics.rom/databases/xxx.db \
  'select count(*) from dwd_doa_t3_inc_h;'"   # SMS 表
adb shell su -c "sqlite3 ... 'select count(*) from dwd_doa_t2_inc_h;'"   # Location 表
```

如果行数是 0，就说明捐赠链路在你这台上根本没被使用。

**D. 黑名单现在就能用的部分**

`out/blocklist/01-telemetry-ads.txt`（131 条）不受上面这些不确定性影响，
可以先上，观察功能是否正常。重点是先不要拦 `02-caution.txt` 里的推送/云服务/商店。
