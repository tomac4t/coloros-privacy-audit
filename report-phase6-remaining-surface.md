# 第六轮：`com.oplus.statistics.rom` 还有哪些没挖的

- **日期**：2026-11-05
- **目的**：盘点这个包剩余的未探索区域，按「信息价值 / 挖掘成本」排序
- **本轮已完成**：Python 机器学习环境（最重磅）、OneID、资产清单

---

## 一、本轮新挖到的内容（已挖掘部分）

### 1.1 ★★★ 端侧 Python + MNN 跑的性别/年龄/偏好预测

**这是整个审计里最重磅的发现。**

APK 里有 `lib/arm64-v8a/libcpythonapp.so`（316 KB）+ `libpycomponent.so`，
配合 `assets/pyvm/sys/`（544 个 Python 标准库文件）和 `assets/dccpy/`，
构成了一个**完整的嵌入式 CPython 运行时**。

Java 侧入口：`com.oplus.dcc.py.DccPythonVm`，桥接层：
```
assets/pyvm/global/pyvm_enter.py    ← 所有 Python 调用的统一入口
    main(p): params = json.loads(p)
             module = importlib.import_module(params['module'])
             func = getattr(module, params['func'])
             return func(params['param'])
```

**能力开放**（`pyvm_java_call.py` + `DbConsumer.java`）：

| 调用 | 作用 |
|---|---|
| `DB_SELECT` | 执行任意 SQL 查询（`{"sql_statements": "...", "db_name": "mt_dw"}`） |
| `DB_INSERT` | 执行任意 SQL 插入 |
| `DB_UPDATE` | 执行任意 SQL 更新 |

也就是说 **Python 脚本对本地数仓有完整读写权限**。

#### 三个预测脚本

`assets/dccpy/user_profile/`：

| 脚本 | tag_id | 输出 | 模型 |
|---|---|---|---|
| `gender_predict.py` | **35** | 性别 | `gender_torch_model_v4.mnn`（MNN 格式） |
| `age_predict.py` | **36** | 年龄段 | `.mnn` |
| `user_cate_pref_predict.py` | 动态（查 `cate_name_tag_id_map_prod.txt`） | 类目偏好 | 规则/查表 |

#### 输入从哪来（`my_utils/utils.py: get_input_data()`）

```sql
-- 应用使用时长（按 app×day 聚合）
select duid, app_package as pack_name, app_name,
       sum(duration) as start_duration, count(*) as start_times, dayno
from dwd_os_launch_inc_h
where dayno >= date('now','-7 days') and is_inner=0
group by app_name, app_package, dayno, duid

-- 已安装应用清单
select duid, app_package, app_name, dayno
from dwd_os_applist_inc_d
where dayno = (select max(dayno) from dwd_os_applist_inc_d) and is_inner=0

-- 应用类目字典
select pkg_name, first_category_id, second_category_id, third_category_id
from dim_app_category
```

**→ 用「你装了什么 App + 用了多久 + 这些 App 属于什么类目」推断性别、年龄、消费偏好。**

#### 特征工程（从 `gender_predict.py` 提取）

```
applist_third_category_name_label         已装应用的类目编码
launch_second_third_category_name_label   启动应用的类目编码
top3_start_times_third_category_name            前三高频类目（次数）
top3_start_duration_third_category              前三时长类目（时长）
top3_start_times_third_category_name_workday    工作日前三（次数）
top3_start_duration_third_category_name_workday 工作日前三（时长）
top3_start_duration_third_category_weekend      周末前三（时长）
top3_start_times_third_category_weekend         周末前三（次数）
+ get_weekday_app_launch_statis()               按星期几的启动统计
+ get_agg_features()                            mean/max/min/sum/std/count/nunique
```

#### 输出：写回本地标签表

```python
# my_utils/utils.py: db_insert()
insert into tag_long_duid_terminal(dayno, hour, duid, tag_id, tag_value)
values("{today}", "00", "{duid}", "{tag_id}", "{tag_value}")
# db_name = "mt_dw"
```

推到最末：
```python
tag_id = 35 (性别) / 36 (年龄段)  →  tag_value = 模型 output argmax
data = {"tag_id": tag_id, "tag_value": pred, "tag_type": "int"}
```

#### 本地标签池 `assets/k_anonymity_tag_pool.json`（26 个标签，全部枚举出）

| id | 类型 | 取值 | 推断含义 |
|---|---|---|---|
| 6 | text | `V12.1` | 系统版本 |
| 8 | text | `CPH2113_11_F.55` 等 10 个 | 固件版本 |
| 9 | text | `12` | Android 版本 |
| 10 | text | `51010`,`51001`… | 渠道/区域码 |
| 11 | int | `7` | 平台/地区 |
| 12 | text | `CPH2113`,`CPH2043`… | 机型 |
| 13 | int | 106,107,225… | 运存档位？ |
| 14 | int | 0,45,46,3,1… | **兴趣标签 ID** |
| **17** | text | **`新手期` / `稳定期` / `熟练期`** | ★ 用户生命周期 |
| 18–23 | int/double | 86,174,100… / 781,1082749,257330… | 使用量、流量、时长等统计量 |
| 24–26 | int | `1`/`0` | 布尔标记 |
| 27–32 | int | `0` | 占位 |
| **33** | text | **`疯狂` / `重度` / `一般` / `轻度` / `极少`** | ★ 使用强度分级 |
| **34** | text | **`轻度` / `极少` / `一般` / `重度` / `疯狂`** | ★ 另一套强度分级（顺序不同） |

> id 33 和 34 是**同一组词但顺序不同**，说明是两个不同的分类维度（比如「游戏强度」vs「视频强度」），
> 或者一个是「激活时」一个是「近期」。这两条是最直白的「用户分级」证据。

### 1.2 OneID 注册/更新：又一个外部身份接口

`com/oplus/statistics/rom/oneid/`：

```java
ONEID_REGISTER_INTERFACE = "/oneid/v1/register"   // 首次注册
ONEID_UPDATE_INTERFACE   = "/oneid/v1/update"     // 后续更新
```

请求参数（`OneidService.java:185-239`）：

```java
"$ssoid"      account.oneplus.com 的账号 SSO ID（AccountSdkManager.getSsoid()）
"duid"        设备唯一ID
"ouid"        OPPO 用户ID
"model"       机型
"oneid"       已有的 oneid（有则走 update，无则走 register）
```

签名方式（`OneidHttpConnection.signUrl()`）：
```java
"region"    = 区域标记
"appKey"    = BuildConfig.DCC_ACCESS_KEY   // "LEtKjVyigNISFjgokNZzGTuahOcTRRAp"
"timestamp" = 当前毫秒
"sign"      = sign(ACCESS_KEY, timestamp, params, SECRET_KEY)
```

时间约束（`adjustOneIdConfig`）：
```java
intervalTime    ∈ [720, 10080]   分钟  (12 小时 ~ 7 天)
ssoidCircleTime ∈ [30, 10080]    分钟
```

**→ 这条链路把「设备ID（DUID）」和「账号ID（OUID/SSOID）」绑定在一起，
即使用户没登录，也能在登录后把匿名行为归并到账号。**
Host 存在 `OneidKvStoreHelper.ONE_ID_HOST_NAME_CLOUD = "one_id_hostName_cloud"`，由云端下发。

### 1.3 资产清单（705 个文件，之前完全没看）

```
assets/
├── 20230719200305/biz/          122 个  ← 2023-07-19 构建的业务 Python 模块
│   ├── common/feature/          特征工程：feature.py / feature_sequence.py / feature_statistics.py
│   ├── common/lr_train/         ★ 本地训练：train_dnn.py(52KB) / train_lr.py(51KB) / dp_sgd.py
│   ├── common/predictor/        ★ 推理：inference_rec_rec_mnn.py / inference_rec_mnn_lr_v2.py
│   ├── common/modelCenter/      模型管理
│   └── common/fedSelector/      ★ 联邦学习选择器（目录存在但文件为 0 字节）
├── dccpy/user_profile/          ★ 性别/年龄/偏好预测（见上）
├── dccpy/user_profile_cn|in|sgp/  分区域版本
├── dccpy/user_profile_cn/
│   ├── dws_doa_t4_inc_h.py      数仓 ETL（t3 → t4 汇总）
│   └── ads_browser_feature_inc_d.py  ★ 浏览器特征提取（PV/停留）
├── config/10_ID/prod/           FeatureRetrieval / PackageManager3 / PackageManager 配置
├── cloudctl_config.json         云控配置清单（9 个配置项）
├── dcs_cloud_config.json        DCS 配置清单（3 个 product，9 个配置项）
├── k_anonymity_tag_pool.json    ★ 26 条本地标签枚举（见上）
└── appWhiteList.json            6 个应用的签名白名单（主题商店/软件商店系）
```

`lib/`：
```
libcpythonapp.so       316 KB   Python 运行时
libdcc_cipher.so        14 KB   DCC 加密（native 实现）
libheytap_tapconnect_cipher.so 14 KB   连接 SDK 加密
libmmkv.so             716 KB   腾讯 MMKV 存储
libpycomponent.so      227 KB   Python 桥
libsqlite3x.so        1.9 MB    带扩展的 SQLite
```

---

## 二、还没挖的部分（按价值排序）

### P0 —— 高价值，建议继续

| # | 什么 | 为什么值得挖 | 成本 |
|---|---|---|---|
| **1** | `assets/20230719200305/biz/common/lr_train/`（`train_dnn.py` 52KB + `train_lr.py` 51KB + `dp_sgd.py`） | **本地训练**。`dp_sgd.py` = Different Privacy SGD，说明他们打算在设备上做**差分隐私训练**。如果真跑，意味着模型会带着你的数据特征更新并上传 | 中（读 Python） |
| **2** | `biz/common/fedSelector/trainer_selector.py`（0 字节）+ `modelCenter/` | 目录叫 fed（federated），文件却是空的 —— 是**未启用的联邦学习**还是**被剥离的**？值得确认 | 低 |
| **3** | `biz/common/predictor/inference_rec_mnn.py`（18KB） | 推荐模型的端侧推理。看输入特征和输出是推荐 item 还是 tag | 中 |
| **4** | `dccpy/user_profile_cn/ads_browser_feature_inc_d.py` | 浏览器特征提取的**具体指标定义**，直接对应 `ads_` 前缀表 | 低 |
| **5** | `com/oplus/dcc/internal/work/`（`DagWorker` / `DagProto` / `CommonSqlTaskWorker`） | **DAG 任务编排**：服务端能下发「任务图」，让设备按顺序跑 Python/SQL/上传。这是「可编程设备」的证据 | 中 |
| **6** | `com/oplus/dcc/ml/train/`（`TrainConfigManager` / `ServerTrainStrategy`） | 训练策略也由云端下发（`dcc_124200_trainingTimeCondition` / `dcc_124200_trainingTaskCondition`） | 中 |
| **7** | `com/oplus/statistics/rom/oneid/` 剩余部分 + `AccountSdkManager` | SSOID 怎么取的、绑定了哪些账号 | 低 |
| **8** | `libdcc_cipher.so` / `libheytap_tapconnect_cipher.so`（各 14KB） | **native 层加密**。之前解不开的 `a9/r.java` host 可能就在这里 | 中（IDA/objdump） |

### P1 —— 中等价值

| # | 什么 | 说明 |
|---|---|---|
| 9 | `com/oplus/dcc/awareness/`（`AwarenessTask` / `AwarenessTaskDao`） | 「场景感知任务」——检测你在干什么（开车/睡觉/运动？） |
| 10 | `com/oplus/dcc/safe/auth/`（`AppWhiteList` / `AppAuthManager` / `ServiceAuthManager`） | 哪些 App 有权限调用 DCC 接口。这决定了「谁能拿到数据」 |
| 11 | `com/oplus/dcc/internal/dimensioninfo/`（`DimensionInfoTable`） | 维度表 = 用户/设备的画像维度定义 |
| 12 | `c1/b.java` `DnsCombineLogic`（938 行）+ `z0/d.java` `HttpDnsDao` | **HTTPDNS 实现** —— 说明域名可能不走系统 DNS，**AdGuard Home 可能拦不住** ⚠️ |
| 13 | `a8/f0.java` `UploadAgent`（924 行） | 上传总调度，可能有重试/降级/多域名策略 |
| 14 | `com/oplus/dcc/cloudctl/`（`CloudCtlManager` 930 行） | 云控核心 |
| 15 | `w5/d.java` `TrackApi`（1099 行） | 对外埋点 API，看其他 App 怎么接入 |
| 16 | `t1/c.java` `EventFactoryStub`（794 行）+ `s7/k0.java` `ConfigEventId`（400 行） | **事件 ID 配置表**——能列出所有采集的事件类型 |
| 17 | `h0/c.java` `DbInjector`（565 行） | 数据库注入，可能是运行时动态建表 |
| 18 | `com/oplus/dcc/py/RemoteInferService` | Python 推理跑在独立进程（`multiprocess/`），看 IPC 怎么传数据 |

### P2 —— 低价值 / 补充

- `q7/*.java`：所有 Bean 类，能拿到完整的字段清单
- `c8/i.java` `JsonProvider`：JSON 拼装，可以确认每个上报字段
- `s7/q0.java` `ConfigGlobal`（739 行）
- `com/oplus/nearx/cloudconfig/` 剩余部分
- `com/heytap/connect/`（TapConnect 连接 SDK）

---

## 三、⚠️ 一个影响黑名单结论的重大发现

**`c1/b.java` 是 `DnsCombineLogic`（938 行），`z0/c.java` 是 `HttpDnsCore`（486 行），
`z0/d.java` 是 `HttpDnsDao`（582 行）。**

这套 HTTPDNS 意味着：
- 上报域名**不经过系统 DNS 解析**
- 客户端直接连 HTTPDNS 服务拿到 IP，再用 IP + SNI 建连
- **AdGuard Home 只能看到最初那次 HTTPDNS 请求，看不到后续的真实域名**

→ **这是黑名单方案的一个根本性漏洞。** 需要确认：
1. HTTPDNS 服务本身的域名（这个拦了才有效）
2. 是否有「HTTPDNS 失败就回落系统 DNS」的降级逻辑

这条我建议**优先级提到 P0 第一位**，因为它直接决定了你整套黑名单有没有用。

---

## 四、建议的挖掘顺序

```
第 1 步（必做）：HTTPDNS 实现 —— 验证黑名单是否有效
    c1/b.java DnsCombineLogic
    z0/c.java HttpDnsCore
    z0/d.java HttpDnsDao
    a1/b.java AllnetDnsSub
    → 找 HTTPDNS 服务地址 + 降级策略

第 2 步：端侧训练是否真的启用
    biz/common/lr_train/train_dnn.py
    biz/common/lr_train/dp_sgd.py
    biz/common/fedSelector/
    com/oplus/dcc/ml/train/
    → 判断「你的数据会不会训练出模型并上传」

第 3 步：DAG 任务编排 —— 服务端能让你执行什么
    com/oplus/dcc/internal/work/DagWorker
    DagProto
    → 判断「云端可编程」的边界

第 4 步：事件清单 —— 到底采了什么
    s7/k0.java ConfigEventId
    t1/c.java EventFactoryStub
    → 补齐事件的完整列表

第 5 步：native 加密
    libdcc_cipher.so
    → 解出之前解不开的 host
```

---

## 五、结论

`com.oplus.statistics.rom` 不只是一个「埋点上报器」，它实际上是：

```
一个自带 Python 运行时的设备端数据平台
  ├─ 本地数仓（15 张表，最多存 180 天）
  ├─ 端侧机器学习（性别/年龄/偏好推理，MNN 模型 + LR/DNN 训练代码）
  ├─ 云端可编排（DAG 任务 + Python 脚本 + 任意 SQL 读写）
  ├─ 身份归一（DUID ↔ OUID ↔ SSOID ↔ ONEID）
  └─ 隐私计算（donate 接收 + 匿名标签池 + DP-SGD 代码）
```

**「隐私计算」这个命名很讲究** —— 代码里到处是 `anonymity_tag_pool`、`DP-SGD`、
`k_anonymity`（k-匿名）。这套设计的意思是：
**数据不出设备，只出标签**。但标签本身就是对用户的判定（性别/年龄/使用强度/生命周期），
而这套判定是**不可撤销、不可查看、不可删除**的。
