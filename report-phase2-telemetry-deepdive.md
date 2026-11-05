# 第二轮精扫：OPPO 埋点四件套（反编译分析）

- **日期**：2026-11-05
- **对象**：`com.oplus.statistics.rom` / `com.oplus.nearx`(内嵌于前者) / `com.oplus.olc` / `com.oplus.onetrace`
- **方法**：jadx 1.5.1 反编译 → 源码审计（未做动态调试）

| 包 | 版本 | 大小 | 反编译产出 |
|---|---|---|---|
| `com.oplus.statistics.rom` 数据基础服务 | 5.8.62.00 | 19 MB | 4936 个 java，35 MB |
| `com.oplus.olc` Olc | V14.0.18 | 3.2 MB | 1902 个 java，13 MB |
| `com.oplus.onetrace` OneTrace | 1.3.26 | 3.1 MB | 1186 个 java，9.9 MB |

> `nearx` 没有独立 APK，它是**编译进 `com.oplus.statistics.rom` 的库**（`com.oplus.nearx.track.*`），
> 同时也是独立的 AAR 给其他 App 用。

---

## 一句话结论

**`com.oplus.statistics.rom` 是一台完整的设备级埋点机器**：它用特权权限实时采集"应用启动/退出、
已安装应用清单、使用时长、网络/WiFi、位置、短信、相册元数据、内核日志"，以 duid/oneid 为设备主键
落进本地数仓，再按服务器下发的动态 URL 批量上传。`olc` 是日志采集器，`onetrace` 是性能/卡顿追踪，
两者都跑在系统特权下，数据汇到同一个出口。

**关于"退出"**：找到唯一的全局开关 `oplus_customize_cta_user_experience`（设置→用户体验改进计划）。
代码里明确只有 **0=关闭 才停**：`return i10 == 1;`
但**关掉后仍会保留部分采集**（见 §5.3），且这个开关只覆盖 statistics.rom，不覆盖 olc/onetrace。

---

## 二、`com.oplus.statistics.rom` 详细分析

### 2.1 权限：这是系统级特权应用

```
READ_PRIVILEGED_PHONE_STATE        ← 读 IMEI/IMSI 的关键权限
QUERY_ALL_PACKAGES                 ← 看全部已装应用
PACKAGE_USAGE_STATS                ← 应用使用时长
ACCESS_FINE_LOCATION / COARSE / BACKGROUND_LOCATION   ← 后台定位
WRITE_SETTINGS                     ← 改系统设置
RECEIVE_BOOT_COMPLETED             ← 开机自启
oplus.permission.RECEIVE_INSTALL_BACKGROUND  ← 后台安装事件
oplus.permission.safe.APP_MANAGER  ← 应用管理
```

`READ_PRIVILEGED_PHONE_STATE` 是 system/privileged 才给的权限，普通 App 拿不到。
这个包**确实会去读 IMEI**：

```java
// com/heytap/nearx/cloudconfig/device/DeviceInfo.java:531
Class<?> cls = Class.forName("android.telephony." + OS_NAME + "TelephonyManager");
Object invoke = cls.getMethod("colorGetImei", Integer.TYPE)
                  .invoke(cls.getMethod("getDefault", Context.class).invoke(cls, this.context), 0);
```

`colorGetImei` 是**高通/ColorOS 私有 API**，普通 `getImei()` 在 Android 10+ 已被封，
OPPO 用私有 API 绕过去了。读到的 IMEI 存在 `DeviceInfo(imei, duid, ouid, customClientId)` 里，
用于「测试机判定」（`isTestDevice`）：

```java
// com/oplus/nearx/track/internal/remoteconfig/DeviceInfo.java
final class DeviceInfo {
    private final String customClientId, duid, imei, ouid;
}
// RemoteConfigManager 用它决定要不要走测试分支：
"appId=[...] isTestDevice=[...] query appConfig success..."
```

> ⚠️ 也就是说：**IMEI 至少在配置拉取阶段被读取并参与逻辑判断**。
> 是否随埋点上报需要抓包确认（`DummyDataProto$Header` 有 DUID/ONEID/OUID/OSID 字段，**没有 IMEI 字段**，
> 所以大概率不上报，但本地读取是确定的）。

### 2.2 上报路径（从 UrlConfig 直接读出）

```java
// c8/v.java  v(Context context, int type, String host, boolean z)
1001 → /v1/stat/%sclientStart     客户端启动
0    → /v1/stat/%sappList          ★ 已安装应用清单
1    → /v1/stat/%slaunch           ★ 应用启动
1003 → /v1/stat/%sAppLog
1004 → /v1/stat/%spageVisit
1005 → /v1/stat/%sException
2007 → /v1/stat/%sdynamic         动态配置
2008 → /v1/stat/%sstatic
2010 → /v1/stat/%sappList         （另一分支，走 dcs）
2011 → /v1/stat/%sdau
20061→ /v1/stat/%sdcs
2    → /v3_1/dcs/preLaunch
3    → /v3_1/dcs/osFirstLaunch
4    → /v3_1/dcs/preUninstall
5    → /v3_1/dcs/%sinstall
6    → /v3_1/dcs/appEnterLaunch
2006 → /v3_1/dcs
2012 → /v3_1/dcs/preAppList
4005 → /v3/dcs/balance
4007 → /v1/stat/%sinstall
4008 → /v1/stat/%sosLaunch
```

其中 `%s` 是**包名派生标识**（`s2.g.i()`），不是固定字符串。

### 2.3 服务器地址：三级来源，硬编码是可解的

```java
// com/heytap/nearx/cloudconfig/env/AreaEnv.java  —— 每段数组 XOR 0x11
private static final int[] https    = {121,101,101,97,98,43,62,62};   // "https://"
private static final int[] appconf  = {124,117,97,60,112,97,97,114,126,127,119}; // "mdp-appconf"
private static final int[] heytap   = {121,116,104,101,112,97};       // "heytap"
private static final int[] download = {117,126,102,127,125,126,112,117}; // "download"

cnUrl()        → https://mdp-appconf-cn.heytapdownload.com
configUrl()    → https://mdp-appconf.heytapdl.com
configUrl(%s)  → https://mdp-appconf-%s.heytapdl.com
```

> ⭐ **这是本次审计最有价值的发现**：
> **`mdp-appconf.heytapdl.com` / `mdp-appconf-cn.heytapdownload.com` 是所有埋点域名下发的入口。**
> 拿到配置之后，真实上报域名由服务器动态下发（`/api/dcc-conf/v1/get`），
> 所以**只屏蔽 cdo/epoch 不够，必须把 appconf 这一层也考虑进去**。

真实数据域名的三个来源（`c8/w.java` → `p8/q.java`）：

| 来源 | 代码 | 说明 |
|---|---|---|
| `Settings.System` | `com.oplus.dcs.data.url` / `tech.url` / `sample.url` / `storage.url` / `eap.url` | 系统属性，出厂预置或 OTA 写入 |
| `Settings.System` | `com.oplus.eap.release_host` | 同上 |
| 动态配置 | `/api/dcc-conf/v1/get` 返回 | 服务器可随时改 |

所以**真实域名不在 APK 里**，必须在真机上读：
```bash
adb shell settings get system com.oplus.dcs.data.url
adb shell settings get system com.oplus.dcs.tech.url
adb shell settings get system com.oplus.dcs.eap.url
adb shell settings get system com.oplus.eap.release_host
```

### 2.4 上报数据协议（Protobuf，字段已还原）

`DummyDataProto$Header`（每个数据包的包头）：
```
access, android_version, brand, carrier, channel, client_id, client_type,
custom_client_id, duid, model, oneid, osid, os_version, ota_version,
ouid, platform, post_time, region_code, region, region_mark,
rom_version, sdk_package_name, sdk_version, user_id
```

`DummyDataProto$DcsEvent`（事件体）：
```
app_id, app_package, app_version_code, app_version, boot_time_ns,
event_group, event_id, event_infos, sequence_number, wall_time_ns
```

`DummyDataProto$Body` / `Packet` / `FileInfo` / `WriterCheckpoint`
→ 说明它支持**离线队列 + 断点续传 + 文件分片上传**（不是简单的一条一条 POST）。

### 2.5 本地数仓：这是"设备画像"的证据

`u3/w.java` 里定义了要定期上传的表：

```java
String[] TABLES = {
  "dwd_sdk_log_inc_h",        // SDK 日志
  "dwd_os_launch_inc_h",      // ★ 应用启动（带时长）
  "dwd_os_install_inc_h",     // ★ 应用安装（带安装来源 caller）
  "dwd_os_uninstall_inc_h",   // ★ 应用卸载
  "dwd_os_dau_inc_d",         // 日活
  "dwd_os_applist_inc_d",     // ★★ 应用清单（自装应用全量）
  "dws_os_user_active_info_all_d",  // ★★ 用户活跃画像（cbitmap 位图）
  "dwd_doa_t1..t5_inc_h",     // 行为明细
  "dws_doa_t4_inc_h",         // 行为汇总
  "ads_doa_t4_inc_d",         // 广告标签
  "dim_device_info"           // ★ 设备维度表
};
```

各表结构（`g4/*.java`，类名就是原 Kotlin 文件名）：

| 表 | 关键字段 | 隐私含义 |
|---|---|---|
| `dwd_os_applist_inc_d` (OsAppListTable) | pkg_name, app_name, app_version, event_time, **is_inner, first_install_time, last_update_time, enable_notice, original_package** | 全量已装应用 + 安装时间 + 是否系统应用 |
| `dwd_os_install_inc_h` (OsInstallTable) | pkg_name, app_name, app_version, channel, event_time, android_version, isreplace, issilent, **callerpackage, callername** | 安装来源（谁装的） |
| `dwd_os_uninstall_inc_h` (OsUninstallTable) | pkg_name, app_name, **is_inner**, event_time, **installcaller** | 卸载来源 |
| `dwd_os_launch_inc_h` (OsLaunchTable) | pkg_name, app_name, app_version, **pre_app_package**, is_inner, duration, session_id | ★ 前后台切换链 |
| `dwd_os_dau_inc_d` (OsDauTable) | network, sdk_version, client_ip, **root, event_time, resolution, ram_total, rom_total, rom_reserve, meids, iccids, imsis, switchue, user_lang** | ★★ **root 状态 + MEID/ICCID/IMSI 字段 + 屏幕分辨率 + 内存/存储** |
| `dws_os_user_active_info_all_d` (DwsOsUserActiveInfoAllTable) | duid, oneid, last_act_dayno, last2_act_dayno, init_act_dayno, **cbitmap_d, cbitmap_w, cbitmap_m** | 活跃日期位图（月/周/日）→ 用户活跃画像 |
| `dim_device_info` (DeviceInfoTable) | model, os_version, brand, rom_version, ota_version, region, region_mark, region_code, user_lang, carrier, android_version, duid, oneid | 设备指纹 |
| `dwd_doa_t1..t5_inc_h` (DwdActivityTable / DwsActivityTable) | **network, launched_from, window_mode, pre_activity, pre_activityLabel, activity, activityLabel, start_time, end_time, duration, session_id, event_info** | ★★ 页面级行为（哪个 Activity、从哪来、停留多久） |
| `dwd_doa_t2_inc_h` (LocationTable) | **latitude, longitude, countrycode, address, country, province, city, area, street** | ★★ 地理位置表（结构完整，写入路径待验证） |
| `dwd_doa_t3_inc_h` (SmsTable) | **number, content, status, client_time** | ★★★ **短信收发件人 + 正文** |
| `dwd_doa_t3_inc_h` 另一分支 | number, service_code, fromorear, sms_type | 短信分类 |
| 相册表 (AlbumTable) | media_id, dateTaken, date_modified, **face_name, address, tags, english_tags, ocr**, bucket_name, size, mime_type, duration, **longitude, latitude**, festival_name, memory_name | ★★★ **照片人脸名/OCR/地点标签** |
| `ads_browser_feature_inc_d` | pkg_name, s_pv, s_page_duration | 浏览器 PV/停留时长 |
| `dwd_os_new_users_inc_h` | network, dcc_version, event_time | 新设备 |
| Tag{String,Long,Double}DuidTable | tag_id, tag_value | ★ 服务器下发的用户标签 |

> **⚠️ 重要修正（见 `report-phase3-sms-location-album.md`）**：
> `SmsTable` / `LocationTable` / `AlbumTable` 这三张表的**写入唯一入口**是
> `DonateContentProvider`（`com.oplus.dcc.donate`，`exported=true` + `android:permission="oplus.permission.OPLUS_COMPONENT_SAFE"`）。
> **`com.oplus.statistics.rom` 自己没有 `READ_SMS` / `READ_CONTACTS` 权限，
> 全 dex 搜 `content://sms` / `Telephony.Sms` / `SmsMessage` 零命中** —— 它不主动读短信。
> 它只是「数据捐赠」的**接收方 + 上传方**，真正采集的是持有 `OPLUS_COMPONENT_SAFE` 的其他系统应用。

### 2.6 应用清单采集：`AppListRecorder`（`j1.java`，920 行）

```java
// j1.java:370
List<PackageInfo> installedPackages = packageManager.getInstalledPackages(0);
for (PackageInfo packageInfo : installedPackages) {
    appPackageInfo.setIsSystemApp(1 或 0);          // 是否系统应用
    appPackageInfo.setIsAppHasUi(1 或 0);           // 是否有界面（过滤掉纯后台）
}
// j1.java:95-103
aVar.D(packageName);           // 包名（可脱敏 p8.c0.l()）
aVar.F(versionCode);
aVar.G(versionName);
aVar.w(firstInstallTime);      // ★ 首次安装时间
aVar.A(lastUpdateTime);        // ★ 最后更新时间
```

再结合 `f8/c.java`（`AppListRecorderHelper`）：

```java
// 用 UsageStatsManager 判断"装过但没用过"
Map<String, UsageStats> map = queryUsageStats(INTERVAL_DAILY/3, 0, now);
if (usageStats.getTotalTimeVisible() > 0) status = 2;  // 用过
else status = 1;                                        // 装了没用
```

→ **最终上报的是「哪些 App 装了、什么时候装的、有没有真的用」**。
这是判断"是否刷机/是否装了竞品/是否测机"的典型特征。

上报频率限制：`j1.java:500` 附近 `lastUploadAppListTime`，43200000 ms = **12 小时一次**。

### 2.7 前后台行为采集：`ActRecorder`（`t.java`，920 行）

来源是系统广播 `onActivityEnter` / `onActivityExit`（携带 `AppEnterInfo` / `AppExitInfo`），
**不是**无障碍（Accessibility）也不是屏幕内容：

```java
// q8/m.java:67
AppEnterInfo info = intent.getParcelableExtra("onActivityEnter");
t.N(context).P(info);

// t.java:860  P()
g0Var.s(pkgName);                      // 包名
g0Var.t(activityLabel);                // 应用名
g0Var.r(activityClass);                // Activity 类名
g0Var.w(isColdLaunch ? 1 : 0);         // 是否冷启动
g0Var.D(packageName);
g0Var.B(sessionId);
g0Var.C(startTime);
// t.java:624  X() —— 如果 ActChecker 判定可解析
X(json, appEnterInfo):
    遍历 AppEnterInfo 的 Bundle 所有 key
    把所有 Parcelable / Serializable / 基本类型 → 转成 JSON
    json.put("uri", appEnterInfo.getUri())   // ★ 页面 URI（可能含参数！）
```

> ⚠️ **`uri` 这一项风险最大**：如果某个 App 的 Activity 是通过 `intent://...?query=` 打开的，
> 这里会把**整个 URI 连同查询参数**写进 `event_info`。
> 社交媒体跳转、支付回调、搜索词，理论上都可能被带出去。
> 触发条件是 `ActChecker` 返回 true —— 白名单来自服务器下发的 `AppActWhiteList`（`ActWhiteListProto`）。

### 2.8 全局开关：只有一个，且是"反方向"的

```java
// w7/p0.java:172
public static boolean h(Context context) {
    int i10 = Settings.System.getInt(cr, "oplus_customize_cta_user_experience");  // 默认 -1
    return i10 == 1;
}
```

开关变量：**`oplus_customize_cta_user_experience`**（设置 → 关于手机 → 用户体验改进计划）
另一个：**`oplus_customize_system_stable_plan_switch`**（系统稳定性改进计划）
第三个：**`oplus_customize_cta_update_service`**（更新服务）

调用点：
```java
// q8/i.java:77  —— 应用创建时
if (!p0.g(ctx) || !p0.h(ctx)) return null;   // g()=更新服务开关, h()=用户体验开关
StatisticsApplication.c(...)                  // 两个都开才继续

// recorder/s2.java:295  —— 内核日志
if (!w7.p0.h(this.mContext)) {
    "UserExperienceToggle OFF，delete all matched files!"   // ★ 关了就删文件
    f(fileArr); return;
}
```

### 2.9 ⚠️ 关掉开关后**仍然继续**的事

| 项目 | 是否受 `user_experience` 开关控制 | 证据 |
|---|---|---|
| 应用清单上传 `appList` | ❌ 不受控 | `j1.o0()` 里只检查 `K()`(是否初始化) 和频率，没有开关检查 |
| 预置应用清单 `preAppList` | ❌ 不受控 | 走 `PreInstallAppInfoBean` → `n8/w.java` |
| 前后台 Activity 记录 | ❌ 不受控 | `t.java` 没有开关判断 |
| 短信 / 位置 / 相册 数据仓 | ❌ 不受控 | 表结构 + `DonateContentProvider` 都无开关 |
| DCC 动态配置拉取 | ❌ 不受控 | `q8/i.java` 里 `dcc_enabled` 是**另一个独立开关**，默认 `true` |
| 内核日志上传 | ✅ 受控 | `s2.java:295` 关即删文件 |
| DCS 基础事件 | ✅ 受控 | 走 `p0.h()` 判断 |

> **这就是"是否允许退出"的真实答案：不能完全退出。**
> 用户体验改进计划关掉，能停掉内核日志和部分 DCS 事件，但**应用清单、前后台记录、
> 位置/短信/相册数仓、以及配置拉取都还在跑**。

### 2.9 补遗：`DauRecorder` 的基础事件含 IMEI/IMSI/ICCID

> 本节于 2026-11-05 17:00 补充。此前（§2.1）结论是「IMEI 仅用于测试机判定」，**这个判断不完整**。

`com/oplus/statistics/rom/business/recorder/t1.java` 是 `DauRecorder`（日活记录器），
它拼出来的就是每次上报都带的「DCS 基础事件」：

```java
// 开关/环境
"switchUE", "switchSP", "user_lang", "triggerType",
"ota_version", "full_id", "clientTime",
"network", "resolution", "ramTotal", "romTotal", "romReserve",

// ★ Bootloader 状态（刷机/root 检测）
"ro.boot.vbmeta.device_state",
"ro.boot.flash.locked",

// ★ 双卡运营商
"sim1Carrier", "sim2Carrier",

// ★★★ 最敏感（在 if (o8.i.d(context)) 保护下）
"imeis",   // 两张卡的 IMEI，用 \u0003 拼接
"imsis",   // 两张卡的 IMSI
"iccids",  // 两张卡的 ICCID，加密：o8.g.d("0YyB+?c@p2H&D5{^wkMRAaf]u*iI$>E3" + iccid)
```

**结论修正**：IMEI 不只是「测试机判定」，**它会随 DCS 基础事件一起上报**。
这解释了为什么这个包需要 `READ_PRIVILEGED_PHONE_STATE`。
同时它还在采集 `ro.boot.flash.locked` / `ro.boot.vbmeta.device_state`（是否解 BL 锁 / 是否 root）。

### 2.10 ★★★ 端侧 Python + MNN：性别/年龄/偏好预测

`assets/` 里有 705 个文件，包含**完整 CPython 运行时**（`libcpythonapp.so`）+ MNN 推理引擎。

`assets/dccpy/user_profile/` 三个预测脚本：

| 脚本 | tag_id | 输出 |
|---|---|---|
| `gender_predict.py` | **35** | 性别 |
| `age_predict.py` | **36** | 年龄段 |
| `user_cate_pref_predict.py` | 动态 | 类目偏好 |

输入 SQL（`my_utils/utils.py: get_input_data()`）：
```sql
-- 应用使用时长
select duid, app_package, app_name, sum(duration) as start_duration,
       count(*) as start_times, dayno
from dwd_os_launch_inc_h
where dayno >= date('now','-7 days') and is_inner=0

-- 已装应用
select duid, app_package, app_name, dayno from dwd_os_applist_inc_d
where dayno = (select max(dayno) from dwd_os_applist_inc_d) and is_inner=0

-- App 类目字典
select pkg_name, first_category_id, second_category_id, third_category_id
from dim_app_category
```

**→ 用「装了什么 App + 用了多久 + App 类目」推断性别、年龄、消费偏好。**

输出写回本地标签表（`db_insert()`）：
```sql
insert into tag_long_duid_terminal(dayno, hour, duid, tag_id, tag_value)
values("{today}", "00", "{duid}", "{tag_id}", "{tag_value}")
```

Python 通过 `DbConsumer`（`com/oplus/dcc/py/`）对本地库有**完整读写权限**：
`DB_SELECT` / `DB_INSERT` / `DB_UPDATE`，可执行任意 SQL。

本地标签池 `assets/k_anonymity_tag_pool.json` 里 26 个标签，其中最直白的：
```
id=17  新手期 / 稳定期 / 熟练期       ← 用户生命周期
id=33  疯狂 / 重度 / 一般 / 轻度 / 极少  ← 使用强度
id=34  轻度 / 极少 / 一般 / 重度 / 疯狂  ← 另一套强度分级
```

详细分析见 [`report-phase6-remaining-surface.md`](report-phase6-remaining-surface.md)。
术语与机制说明见 [`glossary.md`](glossary.md)。

---

## 三、`com.oplus.olc`（Olc）分析

**定位：系统日志采集器 + 上传器。**

### 3.1 权限（比统计还狠）

```
com.oplus.permission.safe.LOG        ← OPPO 私有，日志读取
com.oplus.permission.safe.PERSISTENT ← 常驻不被杀
com.tencent.mm.permission.MOVE_XLOG  ← ★ 微信的 XLog 日志目录读写权限
READ_PRIVILEGED_PHONE_STATE
REBOOT                               ← 可以重启设备
INTERACT_ACROSS_USERS
SYSTEM_ALERT_WINDOW
```

> `com.tencent.mm.permission.MOVE_XLOG` 很反常：**OPPO 系统应用申请了读写微信日志的权限**。
> 这说明它能把微信的私有日志一起打包带走。

### 3.2 44 个采集任务（`logcollection/task/`）

| 类别 | 任务 |
|---|---|
| 系统日志 | `AndroidLogTask`(logcat)、`KernelLogTask`、`MainLogTask`、`SystemLogTask`、`EventsLogTask`、`RadioLogTask` |
| 通信 | `ModemLogTask`、`BtHciLogTask`、`BtSsrdumpLogTask`、`WifiLogTask`、`NWatchCallLogTask` |
| 音频/视频 | `AudioLogTask`、**`AudioPcmDumpLogTask`（PCM 原始音频）**、`VideoLogTask`、`CameraLogTask` |
| 性能 | `SysTraceLogTask`、`UtraceLogTask`、`HprofLogTask`（堆转储）、`MemLeakLogTask`、`FreezeLogTask` |
| 定位 | `GpsLogTask` |
| 其他 | `TcpdumpLogTask`（**抓包**）、`TouchpanelLogTask`、`LauncherLogTask`、`OBrainLogTask`、`OneTraceLogTask`、`QualityProtectLogTask`、`AdspLogTask`、`QcomMinidumpLogTask` 等 |

**最值得注意的三个**：

1. **`AudioPcmDumpLogTask`** — 导出原始 PCM 音频数据
2. **`TcpdumpLogTask`** —— 抓网络包
3. **`HprofLogTask`** —— Java 堆转储（内存里的所有对象，可能含 token/密码）

### 3.3 上报出口

Olc 本身不含 URL（`grep https://` 只命中 google 的 issue tracker），
上传走的是 **OPPO 云存储 SDK**（`com.cloud.sdk.cloudstorage`）→ `OCloudSyncAgent`：

```java
// y8/m.java:278
OCloudSyncAgent.INSTANCE.init(
    new OCloudSdkOptions.Builder(context, host)   // host 来自 r.c(context)
        .setRegionMark(...)
        .setDeviceIdCallback(deviceIdCallback)    // 设备 ID
        .setStatisticsDispatcher(...)
);
```

host 来源 `a9/r.java`（**AES 加密的硬编码**）：

```java
public static String f503a = ">FzK~XX[\\f'@x=]zcaFD^aYC=B:PD>\u007fOB@Rc_zmEiJ'^DG;DEgx{YL<`COC:[Y[Y";
public static String f504b = "noa'#X#^`;i\\fbK~lECj[p;:JJLff<\u007fKrPLb\\rea9z>\u007f@1=iNXca9>11KAAbrJ^B";
// 解密：XOR 0x08 → Base64 → AES/GCM + key "Hml.5Fe=DatdYTUp" iv "yUo.6Fe=Dyd"
```

实测这串解出来的**不是合法 Base64/AES-GCM 密文**（可能是构建时按 flavor 改写，或这层只是混淆占位）。
最终要用运行时 `adb shell settings get ...` 或内存 dump 拿到。

补充线索（`g4/a.java`）：Olc 里还埋了 `cubefs-norths3-cn.heytapmobi.com`（OPPO 自建对象存储）。

---

## 四、`com.oplus.onetrace`（OneTrace）分析

**定位：系统性能/卡顿追踪，数据比统计细得多。**

### 4.1 结构

- 177 个 `com.oplus.onetrace.*` 类，全部位于 `trace/nano/`
- proto 定义类型（`*Metrics`），每个都是一个 `GeneratedMessageLite`

### 4.2 采集的指标（部分）

```
ActivitySwitchMetrics    前后台切换          AppSwitchMetrics     应用切换(含 enter/exit 包名)
AppJankEventMetrics      卡顿                ApplicationMemoryUsageMetrics  内存占用
GpsInfo                  ★ 位置              WifiInfo / WifiP2PInfo          WiFi 信息
TrafficInfo / TrafficThroughputInfo / UidTrafficDiffInfo   ★ 按 UID 的流量
CameraIdMetric / CameraReportMetrics / CameraSensorMetrics 相机
AudioStreamMetrics / AudioRecordStreamMetrics / AudioVolumeMetrics  音频
BatteryMetrics / ThermalMetrics   电池/温度
CpuFreqInfoMetric / CpuLoadMetrics / CpuTaskProfilerMetrics CPU
Dim 维度型：FixedIntervalHistogramDrawer / FrequencyTable
```

关键点 —— **`AppSwitchMetrics` 有 `enterPackageName` / `exitPackageName`**，也就是**应用切换序列**。

### 4.3 权限

```
ACCESS_FINE_LOCATION / ACCESS_COARSE_LOCATION   ← 为何一个性能追踪要位置？
READ_PHONE_STATE
CAMERA_OPEN_CLOSE_LISTENER
MANAGE_USERS / INTERACT_ACROSS_USERS
BATTERY_STATS
oplus.permission.safe.LOG
oplus.permission.safe.APP_MANAGER
```

### 4.4 数据出口

OneTrace 自己**不联网**（`grep https://` 无结果），通过 AIDL 服务 `IOplusTraceService`
把数据交给别的进程（很可能是 `com.oplus.statistics.rom` 或 `com.oplus.nhs`），
由下游统一上传 → **所以屏蔽 statistics.rom 的域名同时会掐掉 OneTrace 的数据出口**。

---

## 五、四者关系图

```
┌─────────────────────────────────────────────────────────────┐
│ 数据采集层                                                   │
│                                                             │
│  com.oplus.onetrace ──AIDL──┐  (性能/卡顿/位置/流量)          │
│  com.oplus.olc ─────────────┤  (日志/PCM/tcpdump/hprof)      │
│                              ↓                              │
│  com.oplus.statistics.rom  ←── 统一采集 + 落盘 + 上传         │
│    ├ AppListRecorder      已装应用/安装来源/是否用过          │
│    ├ ActRecorder          前后台切换 + URI 参数               │
│    ├ KernelDataRecorder   /data/oplus/kevent                 │
│    ├ SmsDataManager       短信表（可通过 DonateProvider 写入） │
│    ├ Location/Album 表    位置/相册人脸OCR                    │
│    └ DeviceInfoTable      设备指纹                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
        ┌─────────────────────┴──────────────────────┐
        ↓                                            ↓
  mdp-appconf*.heytapdl.com                   OPPO 云存储 SDK
  （动态配置下发，决定真实上报域名）            （olc 日志包）
        ↓
  /api/dcc-conf/v1/get  →  真实 hosts（Settings.System 预置）
        ↓
  /v1/stat/*  /v3_1/dcs/*  →  数据落地
```

---

## 六、对黑名单的影响（行动项）

### 6.1 必须补上的域名

| 域名 | 为什么要加 | 风险 |
|---|---|---|
| `mdp-appconf.heytapdl.com` | **埋点配置下发总入口**，掐了能拿到"断粮"效果 | 中：可能影响主题/商店配置，需实测 |
| `mdp-appconf-cn.heytapdownload.com` | 同上（国内） | 中 |
| `cubefs-norths3-cn.heytapmobi.com` | Olc 日志包对象存储 | 低 |

### 6.2 上一轮报告需要修正的地方

1. **`01-telemetry-ads.txt` 里的 `rest-cn-feedback` / `static-cn-feedback`**：
   这俩是**用户主动提交反馈**才用的，不是自动埋点 —— 建议移到 caution 层
2. **上一轮说"关掉开关就停"要改成**：`user_experience` 开关只对部分采集有效，
   应用清单 / 前后台 / 短信等数据仓不受其控制
3. **域名黑名单的局限**：真实上报域名由 `mdp-appconf*` 动态下发，
   静态扫描看不到。**必须靠真机 `settings get` 或抓包补全**

---

## 七、待验证（需要真机）

```bash
# 1) 读出真实上报域名（最关键）
adb shell settings get system com.oplus.dcs.data.url
adb shell settings get system com.oplus.dcs.tech.url
adb shell settings get system com.oplus.dcs.sample.url
adb shell settings get system com.oplus.dcs.storage.url
adb shell settings get system com.oplus.dcs.eap.url
adb shell settings get system com.oplus.eap.release_host

# 2) 读开关当前值
adb shell settings get system oplus_customize_cta_user_experience
adb shell settings get system oplus_customize_system_stable_plan_switch
adb shell settings get system oplus_customize_cta_update_service

# 3) 看本地数仓文件名（验证有没有真在写）
adb shell ls -l /data/misc/ostats/packet_files
adb shell ls -l /data/oplus/kevent
adb shell ls -l /data/persist_log/DCS/kevent

# 4) 关掉开关后对比（实验设计）
adb shell settings put system oplus_customize_cta_user_experience 0
# 然后跑 adb shell dumpsys 或者抓包，对比 /v1/stat/appList 是否还在发
```

---

## 八、复现命令

```bash
# 反编译（每个 2-6 分钟，4 核）
JADX=~/.openclaw/workspace/tools/jadx/bin/jadx
$JADX -d /tmp/jadx-out/statistics --no-res \
  "/tmp/app_backup/数据基础服务_com.oplus.statistics.rom.apk"
$JADX -d /tmp/jadx-out/Olc --no-res "/tmp/app_backup/Olc_com.oplus.olc.apk"
$JADX -d /tmp/jadx-out/OneTrace --no-res "/tmp/app_backup/OneTrace_com.oplus.onetrace.apk"

# 权限表
aapt2 dump badging "$APK" | grep -E "^package:|uses-permission"

# 关键字定位
grep -rn "oplus_customize_cta_user_experience" /tmp/jadx-out/statistics/sources
grep -rn "/v1/stat/\|/v3_1/dcs/" /tmp/jadx-out/statistics/sources/c8/
grep -rn "CREATE TABLE" /tmp/jadx-out/statistics/sources/c4/ /tmp/jadx-out/statistics/sources/g4/
```

## 九、审计局限

- 未做动态调试，`SmsTable` / `LocationTable` / `AlbumTable` 的**写入方**未完全验证
  （表结构 + 上传清单里有，但写入是否在出厂固件里被禁用，需真机确认）
- 加密的 `f503a/f504b`（Olc 上传 host）未能解开，需运行时获取
- AdGuard 只能拦域名，**拦不住已经发到 CDN/云存储的数据**
- 服务器下发配置可随时改，静态分析的黑名单是**时间点快照**
