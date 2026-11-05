# 术语表与机制说明

> 读其他报告前的**前置文档**。所有缩写在这里一次性解释清楚，避免散落各篇。

---

## 一、系统与平台

| 缩写 | 全称 | 说明 |
|---|---|---|
| **DCS** | **D**ata **C**ollection **S**ervice | OPPO 埋点上报系统的总称。`com.oplus.dcs.*` 是这套系统的命名空间，`com.oplus.statistics.rom` 就是它的 ROM 版客户端 |
| **DCC** | **D**ata **C**loud **C**onfig | OPPO 的云端配置/云控平台。`com.oplus.dcc.*`。负责下发「采什么、采多少、发到哪、跑什么任务」 |
| **CDO** | **C**ustomer **D**ata **O**peration | OPPO 内部数据平台。`*.cdo.heytapmobi.com` 域名族是它的接口侧 |
| **DC** | **D**ata**C**enter / **D**ata**C**ollect | 数据落库收口。`*.dc.heytapmobi.com` |
| **mdp** | **M**obile **D**ata **P**latform | `mdp-appconf*.heytapdl.com` —— 移动数据平台的**配置下发**，是所有埋点域名分发的入口 |
| **olus** | — | 未确认，`com.oplus.osense` 相关 |

## 二、数据仓库

| 缩写 | 全称 | 说明 |
|---|---|---|
| **dwd** | **D**ata **W**arehouse **D**etail | 明细层（原始粒度，一行一个事件） |
| **dws** | **D**ata **W**arehouse **S**ummary | 汇总层（按天/按用户聚合） |
| **ads** | **A**pplication **D**ata **S**tore | 应用数据集市 —— ⚠️ 同名的「ads」在这里**不是广告**，而是数仓的第三层（直接供业务用）。但 OPPO 的 `ads_doa_t4_inc_d` 表同时被广告系统消费 |
| **dim** | **Dim**ension | 维度表（设备/应用/类目的静态属性） |
| **t1~t5** | tier 1~5 | 表的分层，对应不同保留天数（3/7/15/30/60/90/180） |
| **doa** | **D**ata **O**f **A**ction / 行为 | `doa` 前缀是行为数据（启动、页面、位置、短信…） |
| **os** | operating system | `os` 前缀是系统级数据（DAU、安装、卸载、应用清单） |

## 三、身份标识

| 缩写 | 说明 | 生成方 |
|---|---|---|
| **DUID** | Device Unique ID，设备唯一标识 | OPPO 生成（不是 IMEI） |
| **OUID** | OPPO User ID，账号体系内唯一 | OPPO 账号服务 |
| **SSOID** | Single Sign-On ID | account.oneplus.com |
| **ONEID** | 统一 ID，用于跨端/跨应用归一 | OPPO OneID 服务（`/oneid/v1/register`） |
| **OAID** | Open Anonymous Device Identifier，可重置的广告标识 | 移动安全联盟（MSA）标准 |
| **IMEI / IMSI / ICCID** | 硬件/运营商标识（非 OPPO 生成） | 设备/运营商 |

## 四、埋点框架

| 缩写 | 说明 |
|---|---|
| **nearx** | OPPO 埋点 SDK（`com.oplus.nearx`），编译进 statistics.rom |
| **olc** | **O**PPO **L**og **C**ollect，日志采集器（独立 APK `com.oplus.olc`） |
| **onetrace** | 性能/卡顿追踪（独立 APK `com.oplus.onetrace`） |
| **obus** | 运营埋点后台（`obus-*.dc.heytapmobi.com`），曝光/点击/转化 |
| **mdp-usertrace** | 用户行为轨迹 |
| **asdt** | 设备画像服务（`asdt-server*-*.allawnos.com`） |
| **adps** | 广告推送/画像（`adps-sys-cn.allawntech.com`） |

## 五、键机制

### 5.1 DCS 基础事件

**每次上报都附带的一整块设备指纹 JSON**，由 `DauRecorder`（`t1.java`）拼装：

```java
// 开关/环境
"switchUE"                       // 用户体验改进计划开关
"switchSP"                       // 系统稳定计划开关
"user_lang", "triggerType", "ota_version", "full_id", "clientTime"
"network", "resolution", "ramTotal", "romTotal", "romReserve"

// ★ Bootloader 状态（刷机检测）
"ro.boot.vbmeta.device_state"
"ro.boot.flash.locked"

// ★ 双卡运营商
"sim1Carrier", "sim2Carrier"

// ★★★ 最敏感（在 if (o8.i.d(context)) 保护下）
"imeis"     // 两张卡的 IMEI，用 \u0003 拼接
"imsis"     // 两张卡的 IMSI
"iccids"    // 两张卡的 ICCID（加密：o8.g.d("0YyB+?c@p2H&D5{^wkMRAaf]u*iI$>E3" + iccid)）
```

「基础事件」= 上面这坨 + `$app_id=21000`。所以它**不是心跳，是设备指纹随包走**。

### 5.2 DCC 动态配置拉取

从 `/api/dcc-conf/v1/get` 拿一份 JSON，客户端据此调整行为：

| 配置类 | 作用 |
|---|---|
| `GlobalConfigEntity` | 全局开关 |
| `SDKConfig` | 上报间隔 / 批量大小 / 重试次数 |
| `EventRuleEntity` | 哪个事件要采、采哪些字段 |
| `EventBlackEntity` | **哪些事件不采** |
| `PreciseControlRuleProto` | **采样比例**（见 5.3） |
| `DcsDynamicUrlData001Entity` | **真实上报域名** |
| `ActWhiteListProto` | 哪些 App 的 Activity 允许采 URI 参数 |
| `PackageDictionaryEntity` | 包名脱敏映射表 |
| `SpecialAppListEntity` | 特殊应用清单 |

**关键**：这套机制让 OPPO **不更新系统就能改**「发什么 / 发多少 / 发到哪 / 跑什么任务」。

`assets/dcs_cloud_config.json` 里列了三个 product：
```
compass_dcs              业务配置（BUSINESS_CONF_KEY / BUSINESS_CONF_DCS /
                         APP_LAUNCH_WHITE_LIST / APP_ACT_WHITE_LIST）
obus_package_dictionary  包名字典（PACKAGE_DICTIONARY / _V2 / APPID_DICTIONARY）
50351                    动态 URL（dcs_dynamic_url_data_001）
```

`assets/cloudctl_config.json` 里是另一个 product `dcc_124200`（124200 也是 Python 任务里见过的 id）：
```
dcc_globalConfig                  全局配置
dcc_dimension_table_transmission_v2  维度表
dcc_124200_dag                    ★ DAG 任务编排
dcc_124200_inferenceUpdateCondition  ★ 推理模型更新策略
dcc_124200_inferenceResourceCondition  推理资源更新
dcc_124200_inferenceCondition      推理策略
dcc_124200_anonymityTagPool        ★ 匿名标签池
dcc_124200_trainingTimeCondition   ★ 训练时间条件
dcc_124200_trainingTaskCondition   ★ 训练任务列表
```

### 5.3 PreciseControl 采样（"精确控制"）

```protobuf
PreciseControlRule {
  app_id             = 1
  event_group        = 2
  event_id           = 3
  operator           = 4
  type               = 5
  proportion         = 6     // 0-100
  sampling_intervals = 7
}
```

客户端实现（`i8/v0.java:114`）：

```java
public final boolean l(final int proportion) {
    if (proportion < 0 || proportion > 100) return true;   // 配错 = 全采
    int nextInt = new Random().nextInt(101);               // 0..100
    return nextInt < proportion;                           // 小于比例才保留
}
```

**翻译**：服务端说「这个 appId 的这个事件只采 30%」，客户端就随机扔掉 70%。
这是**降本手段**，但也意味着**你的数据样本量由服务端决定，且随时可变**。

### 5.4 Donate（数据捐赠）

```
App A 读到数据 → 通过 DonateContentProvider → 写进 com.oplus.statistics.rom 的数仓 → 上传
```

Provider 定义：
```xml
<provider
    android:name="com.oplus.dcc.donate.DonateContentProvider"
    android:authorities="com.oplus.statistics.dcc.DonateContentProvider"
    android:permission="oplus.permission.OPLUS_COMPONENT_SAFE"
    android:exported="true">
    <intent-filter>
        <action android:name="android.intent.action.RECEIVE_DONATE_DATA" />
```

URI 路径码 = 表：
```
/1 → dwd_doa_t1_inc_h   相册（face_name / ocr / tags / 经纬度）
/2 → dwd_doa_t3_inc_h   短信（number / content / status）
/3 → dwd_doa_t2_inc_h   位置（lat / lng / 到街道的地址）
```

**全 345 个包里，只有 `com.heytap.quicksearchbox`（全局搜索）在捐。**

### 5.5 端侧机器学习

APK 内嵌完整 CPython（`libcpythonapp.so`）+ MNN 推理引擎。

| 脚本 | tag_id | 输出 |
|---|---|---|
| `gender_predict.py` | **35** | 性别 |
| `age_predict.py` | **36** | 年龄段 |
| `user_cate_pref_predict.py` | 动态 | 类目偏好 |

输入：`dwd_os_launch_inc_h`（用了什么 App、多久）+ `dwd_os_applist_inc_d`（装了什么）
+ `dim_app_category`（App 类目）→ 特征工程 → MNN 模型 → 写 `tag_long_duid_terminal`

Python 对本地库有**完整读写权限**（`DbConsumer` 暴露 `DB_SELECT`/`DB_INSERT`/`DB_UPDATE`）。

---

## 六、域名族速查

| 域名 | 用途 |
|---|---|
| `mdp-appconf*.heytapdl.com` | ★ 配置下发总入口（所有埋点域名的源头） |
| `*.cdo.heytapmobi.com` | 业务 API（api-cn / epoch-cn / gslb-cn / fupload-cn） |
| `*.dc.heytapmobi.com` | 数据采集（conf / dragate / obus / event） |
| `*.cdo.oppomobile.com` / `*.dc.oppomobile.com` | 旧域名，与上面同构 |
| `adx.ads.*` / `stg-data.ads.*` / `ssp-adx` | 广告程序化竞价 |
| `bot-*.heytapmobi.com` | AI 助手（小布/Breeno） |
| `asdt*` / `adps*` | 设备画像 |
| `cubefs-norths3-cn.heytapmobi.com` | 对象存储（olc 日志包） |
| `muc.heytap.com` | 协议文档（隐私政策原文在这） |
