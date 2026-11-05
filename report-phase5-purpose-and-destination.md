# 第五轮：捐赠的数据用来干什么，去了哪里

- **日期**：2026-11-05
- **接上轮**：全局搜索（`com.heytap.quicksearchbox`）把短信/相册/位置捐给 `com.oplus.statistics.rom`

---

## 一、先看结论

```
全局搜索读数据 ──捐──► statistics.rom 写本地数仓 ──批量──► OPPO 服务端 ──► 推荐/画像系统
                          │                                  │
                          │                                  └─ 反哺：给全局搜索下发推荐结果
                          │                                     （带 userprofile 标签）
                          └─ 按天滚动删除：3/7/15/30/60/90/180 天才清
```

**三个用途，都有代码证据**：

1. **拿推荐结果** —— 捐赠是「投名状」：我给你行为数据，你给我个性化推荐
   （`c5/` 包：`StoreRecommendationService` 应用商店推荐、`ThemeRecommendationService` 主题推荐）
2. **建用户画像标签** —— 服务端算好 `userprofile`（JSON），下发回来参与推荐排序
3. **DAU/留存/新用户统计** —— 纯运营指标，也是他们报表的基础

---

## 二、数据去了哪里

### 2.1 本地：先在手机上攒着

数据库文件（`u3/w.java` 的 `D()` / `E()`）：

```
/data/data/com.oplus.statistics.rom/databases/mt_doa_dw   ← 行为数仓（版本 5），z3/b.java
/data/data/com.oplus.statistics.rom/databases/mt_dw       ← 通用数仓（版本 8），d4/b.java
/data/misc/ostats/packet_files                            ← 打包待传
/data/oplus/kevent  +  /data/persist_log/DCS/kevent       ← 内核事件
```

`h4/l.java` 里做了版本映射：
```java
hashMap.put("mt_dw", 8);
hashMap.put("mt_doa_dw", 5);
```

### 2.2 保留策略（重要，说明数据不是"传完就删"）

`u3/w.java:19-40` 定义了**七档**保留期：

```java
private static int f9608f = 180;   // 180 天
private static int f9609g = 90;    // 90 天
private static int f9610h = 60;
private static int f9611i = 30;
private static int f9612j = 15;
private static int f9613k = 7;
private static int f9614l = 3;     // 3 天
```

`z()` 方法对每一档调用 `A(context, 档位天数, 表清单)`，`A()` 里：

```java
String[] strArr2 = { l0.a(i10, "yyyy-MM-dd") };   // 该档位的截止日期
List asList = Arrays.asList(this.f9618d);          // T1~T5 的 dwd 表
for (String str : strArr) {
    if (asList.contains(str)) {
        y(context, str, "s_4 <=?", strArr2);       // 按 s_4（dayno）删
    } else {
        y(context, str, "dayno <=?", strArr2);
    }
}
// y() 里每张表删完都 if (!K(context)) return;  ← K() = 库大小超过阈值就中止
```

**翻译**：数据按天分表（`dwd_doa_t1_inc_h` = 最近 3 天，`t2` = 7 天，……，`t4` = 60 天，
`t5` = 90 天，还有 180 天的档），**旧数据往下一档表滚，最老保留半年**。
而且**只要库还没超容量上限（`K()`）就会继续滚**，不是传完立刻清。

> 也就是说：你的短信/位置/相册摘要，在本机可能存了**最多 180 天**。

### 2.3 上传：两类通道

#### 通道 A：实时/准实时（JSON）

`m8/` 包，继承 `l8.e`（`BaseUploadData`）：

| 类 | 用途 | 路径码 |
|---|---|---|
| `m8.a` `BalanceCountUpload` | 配额/平衡计数 | `4005` → `/v1/stat/%sinstall` 附近 |
| `m8.b` `CommonOldUpload` | 旧版 V1 通道 | |
| `m8.f` `CommonV3Upload` | **V3 通道，主力** | `/v3_1/dcs/*` |
| `n8.f` `AppListUpload` | **应用清单** | `0`/`2010` |
| `n8.h` `DauUpload` | 日活 | `2011` |
| `n8.c` `AppEnterLaunchUpload` | 应用启动 | `6` `AppEnterLaunch` |

`l8/e.java:139` 的上传核心：

```java
String url = v.u(context, i10, str2, str3);     // i10 = 上面那些路径码
String resp = z7.f.a(url, body, true, false);   // POST
// 440 → 重新鉴权后重试一次
// 503 → "The net is blocking, please wait for a moment"，清空队列
```

报文结构（`c8/i.java`）：

```java
// JSON，两层
{
  "$brand": "...", "$model": "...", "$platform": 1,
  "$os_version": "...", "$rom_version": "...", "$android_version": "...",
  "$sdk_package_name": "com.oplus.statistics.rom",
  "$sdk_version": "5.8.62.00",
  "$channel": "OS", "$access": "...", "$region": "...", "$region_mark": "...",
  "$multi_user_id": ...,
  "$app_id": "21000",          // ★ 系统统计的 appId
  "$app_version": "5.8.62.00",
  "$cloud_config_product_version": "2.4.2.3",
  "$custom_head": { "os_properties": {...} },   // 见 os_properties
  "$app_version_code": "530806200",
  "$duid": "...",
  "$carrier": "...", "$post_time": "...",
  "$app_package": "com.oplus.statistics.rom"
}
```

`$app_id = "21000"` 是个很关键的标识：**所有厂商系统 App 的埋点，最终都归到 21000 这个 appId 下**。

#### 通道 B：数仓整表上传（Protobuf）

`DummyDataProto` 系列，支持**文件分片 + 断点续传 + 配额结算**：

```
DummyDataProto$Packet
    ├─ FILE_INFO            → 当前传的是哪个文件、哪个分片
    ├─ DCS_EVENTS           → 事件数组
    └─ WRITER_CHECKPOINT    → 断点（传失败了从哪续）
DummyDataProto$Body
    ├─ FILE_INFO
    ├─ DCS_EVENTS
    └─ BALANCE_MESSAGE      → 配额/流量结算
```

需要 `WRITER_CHECKPOINT` 说明它是**按文件流式上传**的，不是一条条 POST。
这也解释了 `mt_doa_dw` 这个 SQLite 库为什么会被整个打包。

### 2.4 到底发到哪个域名

**这是这一轮仍然没解开的地方**。原因：

- 业务域名不在 APK 里（前几轮已确认：`AreaEnv` 解出来的是 `mdp-appconf*.heytapdl.com` 配置入口）
- 真实域名由 `/api/dcc-conf/v1/get` 下发，或存在 `Settings.System com.oplus.dcs.*.url`
- 你机器上这 6 个 key **全是 null**

但从**扫描结果**可以给一个可信的候选集（`out/blocklist/01-telemetry-ads.txt` 里 cdo/dc 那组）：

```
*.cdo.heytapmobi.com        ← API 侧（api-cn.cdo / epoch-cn.cdo / gslb-cn.cdo / fupload-cn.cdo）
*.dc.heytapmobi.com         ← 数据侧（conf-cn.dc / dragate-cn.dc / obus-cn.dc / event.dc）
*.cdo.oppomobile.com        ← 旧域名，同上
*.dc.oppomobile.com
cubefs-norths3-cn.heytapmobi.com   ← 对象存储（olc 日志包）
```

**cdo = "CDO"，dc = "DataCenter/DataCollect"**，这两个是 OPPO 埋点体系的标准命名。

---

## 三、数据被用来干什么（重点）

### 3.1 用途一：推荐系统的输入（有直接代码证据）

`c5/` 包是「推荐服务」模块：

```
c5/a.java   IRecommendationService     ← 推荐服务接口
c5/k.java   RecommendationServiceFactory
c5/l.java   StoreRecommendationService      ← 应用商店推荐
c5/r.java   ThemeRecommendationService      ← 主题推荐（ID "10" → Theme，ID "2" → Store）
```

`c5/k.java:19`：
```java
aVar = "10".equals(str) ? new r(cVar)      // 10 = 主题推荐
     : "2".equals(str)  ? new l()           // 2  = 商店推荐
     : new r(cVar);                          // 默认主题
```

`c5/a.java` 里 `C0040a.b()` —— **推荐请求的报文**：

```java
jSONObject.put("uuid",        this.f978a);   // 设备 uuid
jSONObject.put("region",      this.f979b);   // 地区
jSONObject.put("brand",       this.f980c);   // 品牌
jSONObject.put("model",       this.f981d);   // 机型
jSONObject.put("tags",        new JSONArray(this.f982e));   // ★ 标签 ID 列表（int）
jSONObject.put("screens",     new JSONArray(this.f983f));   // ★ 屏幕特征
jSONObject.put("userprofile", this.f984g);   // ★ 用户画像 JSON
jSONObject.put("retrieveType",this.f985h);   // 召回类型
jSONObject.put("page_id",     this.f988k);   // 页面
jSONObject.put("scene_id",    this.f989l);   // 场景
jSONObject.put("scene",       this.f990m);   // 场景详情
```

**→ 这就是闭环**：你捐的短信/相册/位置 → 服务端算成 `tags`（int 标签）和 `userprofile`（JSON）
→ 下次请求推荐时带回 OPPO 服务器 → 服务器返回个性化内容。

### 3.2 用途二：反哺回来做个性化

`a5/o0.java:668`：

```java
for (UserProfile userProfile : com.oplus.dcc.ml.infer.config.h.f2588c.a(this.f337c).c()) {
    hashMap.put(userProfile.getId(), userProfile.getValues());
}
```

包名 `com.oplus.dcc.ml.infer` —— **DCC + Machine Learning + Inference**。
说明设备端也跑一些轻量推理（标签生成 / 场景判定），不是全部扔云端。

### 3.3 用途三：DAU / 新用户 / 留存统计

上传的报表类型（表名自带含义）：

```
dwd_os_dau_inc_d                 日活
dwd_os_new_users_inc_h           新设备（首次激活）
dwd_os_install_inc_h             安装（带 caller，能算渠道）
dwd_os_uninstall_inc_h           卸载（带 installcaller，能算留存）
dwd_os_launch_inc_h              启动
dwd_os_applist_inc_d             应用清单
dws_os_user_active_info_all_d    活跃画像（cbitmap 位图，按日/周/月）
ads_doa_t4_inc_d                 广告标签（"ads" 前缀 = 广告侧消费）
```

**`ads_doa_t4_inc_d` 这个表名值得注意**：前缀 `ads_` 说明**同一套行为数据在广告系统里也被用**。
配合 `adx.ads.heytapmobi.com`（程序化竞价）、`stg-data.ads.heytapmobi.com`（广告数据回传），
可以推断：**行为数据是推荐和广告共用的底座**。

### 3.4 用途四：精准控制（"Precise Control"）—— 反过来的：控制采集

`i8/j.java` `PreciseControlStrategy`，配合 `PreciseControlRuleProto`：

```protobuf
PreciseControlRule {
  app_id             = 1
  event_group        = 2
  event_id           = 3
  operator           = 4
  type               = 5
  proportion         = 6      // 采样比例
  sampling_intervals = 7      // 采样间隔
}
```

服务端可以给**每个 appId + eventId 单独配置**「采样多少比例、间隔多久」。
这是**降本手段**（数据太多传不完就采样），但也意味着**服务端能远程调整你的采集强度**。

---

## 四、谁在看这些数据

| 接收方 | 域名族 | 用途 |
|---|---|---|
| OPPO 统计平台 | `*.cdo.heytapmobi.com` / `*.dc.*` | 数仓落地 |
| OPPO 推荐系统 | 同上（`c5/` 走同一套） | tags / userprofile |
| OPPO 广告系统 | `adx.ads.*` / `stg-data.ads.*` / `ssp-adx` | 广告定向 |
| OPPO 云存储 | `cubefs-norths3-cn.heytapmobi.com` | olc 日志包 |
| 百度 | 定位 SDK | **位置数据第一次流出** |

---

## 五、按你的目标，能确认的三件事

1. **数据不是用完就删**：本机最多存 180 天（7 档滚动删除，且受容量阈值保护）
2. **数据同时喂给推荐 + 广告**：`ads_doa_t4_inc_d` 表名 + ads 域名组
3. **服务端能远程调节采集强度**：`PreciseControlRule` 可下发采样比例/间隔

## 六、仍然没解开的

- 真实上报域名（需抓包 / root 读 `Settings.System`）
- 服务端返回的 `userprofile` 具体有哪些标签（需抓包看响应体）
- `dwd_doa_t4/t5` 的完整字段（jadx 对这几张表的 `CREATE TABLE` 反编译不完整，
  只确认了表名和 `s_4`/`dayno` 删除字段）

## 七、下一步

```bash
# 1. 抓包看真实域名（最关键）
sudo tcpdump -i any -n -s 0 'tcp port 443' -w coloros.pcap

# 2. 看推荐请求（如果 App 里能进设置→个性化推荐页，抓这个接口）
#    找 scene_id / page_id / userprofile 字段

# 3. root 后看数仓实际规模
adb shell su -c "ls -l /data/data/com.oplus.statistics.rom/databases/"
adb shell su -c "du -h /data/data/com.oplus.statistics.rom/databases/mt_doa_dw"
```
