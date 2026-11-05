# 第八轮：差分隐私、模型文件、进程架构

- **日期**：2026-11-05
- **接上轮**：第七轮确认了 HTTPDNS 与端侧训练的存在
- **本文回答**：①24h 上报的是什么 ②差分隐私怎么保护（含 FedAvg 科普）③剩余三项待查

---

# 第一部分：每 24 小时上报的到底是什么

## 1.1 结论：**只有数量，四个整数**

`assets/biz/common/lr_train/fe_emb.py` 的 `get_fe_feature_info()`：

```python
@staticmethod
def get_fe_feature_info(model_name="lr"):
    ret = {
        "item_all_cnt": FeEmb._get_sql_data('fe_item_feature_embedding',
            f"select count(*) from fe_item_feature_embedding"),
        "user_cnt": FeEmb._get_sql_data('fe_user_feature_embedding',
            f"select count(*) from fe_user_feature_embedding"),
        "item_label_cnt": FeEmb._get_sql_data('fe_item_feature_embedding',
            f"select count(*) from fe_item_feature_embedding where label>-1"),
        "item_label1_cnt": FeEmb._get_sql_data('fe_item_feature_embedding',
            f"select count(*) from fe_item_feature_embedding where label=1"),
    }
    return ret
```

| 字段 | 含义 |
|---|---|
| `item_all_cnt` | 推荐项总曝光记录数 |
| `user_cnt` | 用户特征记录数 |
| `item_label_cnt` | 已标注样本数 |
| `item_label1_cnt` | 正样本数（点击/下载/付费） |

**上报代码（`train_lr.py:upload_local_samples`）：**

```python
def upload_local_samples(req):
    feature_info = FeEmb.get_fe_feature_info()
    py_tunnel.dcc_tunnel_send_v2("fe", "train", json.dumps({
        "type": "local_sample",
        "real_sample_info": feature_info      # ← 就是上面四个 count
    }))
```

定时器（`train_lr.py:init`）：
```python
upload_sameple_interval = moubleConfig.get("upload_sameple_interval", 86400)  # 默认 24h
BackgroundTaskManager.add_period_task(..., upload_local_samples, {}, upload_sameple_interval)
```

**→ 外发内容 = `{"item_all_cnt": N, "user_cnt": N, "item_label_cnt": N, "item_label1_cnt": N}`**

## 1.2 但本机存了完整样本

同一文件里，样本是写进本地 SQLite 的：

```python
# 用户特征
def write_sample_user_feature(req_id, user_feature_result):
    val = {
        'key':          req_id,
        'emb_list':     FeEmb.parse_sparse_feature_list(user_feature_result['feature_list']),
        'timestamp':    round(time.time() * 1000000),
    }
    FeEmb.write_sqllite_user([val])

# 物品特征
def write_sample_item_feature(req_id, item_feature_result):
    for one_item in item_feature_result:
        val = {
            'key': one_item['item_id'], 'req_id': req_id,
            'emb_list': ..., 'label': -1, 'timestamp': ...
        }
    FeEmb.write_sqllite_item(vals)
```

**`emb_list` 是什么？** `parse_sparse_feature_list()`：

```python
res.append(str(sparse_feature['sign']) + ":" + str(slot_id))
```

→ `"特征sign:slot_id"` 的稀疏表示。**是推荐系统内部的特征编码，不是原始内容。**

## 1.3 标签从哪来：你的真实行为

`update_label_when_event_received()` 从埋点事件回填标签：

```python
if event_group == '1003' and event_id == '902':
    # 曝光（opt_obj 解析出被曝光的 item）
    label = 0                       # 负样本

elif event_group == '2024' and event_id == '421':
    # 点击
    label = 1                       # 正样本

elif event_group == '10003' and event_id == '7000':
    # 列表下载
    label = 1

elif event_group == '10003' and event_id == '7002':
    # 详情下载
    label = 1

elif event_group == '2023' and event_id == '321':
    # 付费
    label = 1
```

| event_group | event_id | 含义 | label |
|---|---|---|---|
| 1003 | 902 | 曝光 | 0 |
| 2024 | 421 | 点击 | 1 |
| 10003 | 7000 | 列表下载 | 1 |
| 10003 | 7002 | 详情下载 | 1 |
| 2023 | 321 | 付费 | 1 |

**→ 你的点击 / 下载 / 付费行为在本机被记成训练样本（特征 + 标签），留在 `fe_item_feature_embedding` 表里。**

## 1.4 本地样本表的规模

```python
sampleCache = Cache(maxsize=10000, ttl=7200, ...)     # 内存缓存 1 万条，2 小时
```

SQLite 表没有明显的行数上限，靠 `dataSetMinSize` / `dataSetMaxSize`（`TaskInfo`）控制参与训练的条数。

---

# 第二部分：差分隐私 / FedAvg / 模型文件

## 2.1 FedAvg 是什么

**FedAvg = Federated Averaging（联邦平均）**，联邦学习最基础的聚合算法。

```
┌──────────┐  ┌──────────┐  ┌──────────┐
│ 手机 A   │  │ 手机 B   │  │ 手机 C   │
│ 本地数据 │  │ 本地数据 │  │ 本地数据 │
└────┬─────┘  └────┬─────┘  └────┬─────┘
     │ 各训 1 轮   │             │
     ▼             ▼             ▼
   W_A            W_B           W_C          ← 只上传模型权重
     │             │             │
     └─────────────┼─────────────┘
                   ▼
          服务器：W_global = (W_A+W_B+W_C)/3
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
  手机 A        手机 B        手机 C        ← 下发全局模型，进入下一轮
```

**为什么用 FedAvg 而不是直接传梯度：**

| | 传梯度（FedSGD） | 传模型参数（FedAvg） |
|---|---|---|
| 上传量 | 每步都传 | 每轮传一次 |
| 隐私风险 | 梯度可能被反推出训练数据（gradient inversion） | 模型参数更难反推 |
| 网络依赖 | 需要持续在线 | 可以离线本地训多轮 |

## 2.2 "模型文件"是什么

就是神经网络/逻辑回归的**参数矩阵文件**。

具体到这台设备（`assets/dccpy/user_profile/models/`）：

```
gender_torch_model_v4.mnn      性别分类模型（MNN 格式，PyTorch 导出）
age_*.mnn                      年龄分段模型
test_StandardScaler_mean.txt   特征标准化参数（均值数组）
test_StandardScaler_std.txt    特征标准化参数（标准差数组）
applist_third_category_name_labelencoder_dic.pkl   类目编码表
launch_second_third_category_name_labelencoder_dic.pkl
category_id_name_all_new.pkl   类目 ID → 名称映射
```

`gender_torch_model_v4.mnn` 内部大致是：
```
layer1: weight[256×N] + bias[256]
layer2: weight[128×256] + bias[128]
output: weight[2×128]  + bias[2]       ← 二分类（男/女）
```

一个模型文件里可能有**几十万个 float**。这些数**本身不是你的明文数据**，但**是从包含你的数据算出来的**。

## 2.3 DP-SGD 怎么保护隐私

`dp_sgd.py` 的 `dpMaskModel()`：

```python
def dpMaskModel(self, model, modelBeforeTrain):
    # ① 计算本次训练让模型变了多少
    updateL2Norm = 0
    for i in range(len(model)):
        updateData = [x - y for x, y in zip(model[i], modelBeforeTrain[i])]
        updateL2Norm += sum(x**2 for x in updateData)
    updateL2Norm = sqrt(updateL2Norm)

    # ② 裁剪：变化幅度压到阈值以内
    clipFactor = min(1.0, self.__dpNormClip / updateL2Norm)
    updateData = [(x - y) * clipFactor for x, y in zip(data, dataBeforeTrain)]

    # ③ 加高斯噪声
    temp[j] = self.__gaussianSigma * random.gauss(0, 1)
    newData = x_before + updateData + noise
    update_model[i].write(newData)
```

**三个机制：**

### ① 裁剪（Clipping）
限制**任何单条记录**对模型的影响上限。

假设你的样本把某个权重推偏了 100，但 `dpNormClip = 1`，就只保留 1。这样别人无法判断“某个特定用户是否在训练集里”。

### ② 加噪（Noise）
给更新量加高斯噪声，σ 由隐私预算决定：

```python
def calculateSigma(self, clipNorm, eps, targetDelta):
    # 根据 (ε, δ) 反算出所需噪声强度
    alpha = sqrt(1 + s / 2) - sqrt(s / 2)
    return alpha * clipNorm / sqrt(2 * eps)
```

- **ε（`dpEps`）** 越小 → 噪声越大 → 越私密，但模型越不准
- **δ（`dpDelta`）** 是“保护失效的概率”，通常 1e-5

### ③ 敏感度控制
裁剪保证敏感度有界 → 加噪后的结果满足 (ε, δ)-差分隐私。

**数学保证**：无论你是否在训练集里，输出分布的差异 ≤ e^ε。所以攻击者无法从模型推断你的存在。

## 2.4 ⚠️ 但当前配置 `do_dp: false`

`assets/20230719200305/fl_tasks.json`：

```json
{
  "loss": "weight_binary_cross_entropy",
  "do_dp": false,                                        ← ★★★
  "optim": "MNN.optim.SGD(model, 0.01, 0.9, 0.0005,MNN.optim.Regularization_Method.L1L2)",
  "stop_train_condition": " cur_auc > 0.78 and  cur_loss_avg < 4.0 "
}
```

**`do_dp: false` → 裁剪和加噪都不执行 → 模型更新是原始未加噪的权重差。**

这意味着：

- ✅ 服务端**有能力**做差分隐私（代码完整）
- ❌ **默认没开**
- ⚠️ 服务端可以随时下发新配置改成 `true`——但反过来，**现在这条链路是不受 DP 保护的**

> 这是一种常见的设计：基础设施建好，默认关闭（省钱/精度），需要时远程开启。
> 但从隐私角度看，**默认值就是实际状态**。

---

# 第三部分：你的隐私到底泄漏了什么

## 3.1 分级清单

### 🔴 确定外泄（无关开关，默认发生）

| 内容 | 载体 | 依据 |
|---|---|---|
| **性别推断** | tag 35 → `tag_long_duid_terminal` | `gender_predict.py` |
| **年龄段推断** | tag 36 | `age_predict.py` |
| **使用强度**（疯狂/重度/一般/轻度/极少） | `k_anonymity_tag_pool` id 33/34 | 资产文件 |
| **用户生命周期**（新手期/稳定期/熟练期） | id 17 | 资产文件 |
| **完整已装应用清单** | `dwd_os_applist_inc_d` | `j1.java:370` |
| 首次安装时间 / 最后更新时间 | 同上 | `j1.java:95-103` |
| **是否真的用过**（UsageStats 判断） | 同上 | `f8/c.java` |
| **前后台切换 + URI 参数** | `dwd_doa_t*_inc_h` | `t.java:749` |
| 设备指纹（型号/ROM/OTA/地区/语言/运营商） | `dim_device_info` | `e4/g.java` |
| **WiFi SSID** | 基础事件 | `y0/b.java:145` |
| **IMEI / IMSI / ICCID** | DCS 基础事件 | `t1.java` |
| Bootloader 解锁状态（是否刷机/root） | 基础事件 | `ro.boot.flash.locked` |
| 推荐/广告行为（曝光/点击/下载/付费） | `fe_item_feature_embedding` + 埋点 | `fe_emb.py` |

### 🟠 条件外泄（需要几个开关同时为真）

| 内容 | 条件 |
|---|---|
| **短信（号码 + 正文）** | 需全局搜索捐赠 + `dccEnable && configEnable && userSettingEnable && personalEnable` |
| **位置（到街道 + POI 名）** | 同上 |
| **相册 OCR / 人脸名 / 坐标** | 同上 |

详见 `report-phase4-donor-quicksearchbox.md`。

### 🟡 间接外泄

| 内容 | 条件 |
|---|---|
| 端侧训练出的**模型参数** | 云端下发训练任务；`do_dp=false` 时未加噪 |
| 样本量统计（4 个整数） | 每 24 小时，自动 |

### 🟢 确定不外泄

| 内容 | 原因 |
|---|---|
| 短信原始内容（statistics.rom 自己） | 没有 `READ_SMS` 权限 |
| **梯度** | `PyJavaProtocol.FuncName` 里没有任何梯度通道 |
| 样本特征明细（`emb_list`） | 只上报 `count(*)` |
| 相册照片本体 | 只读索引（face_name/ocr），不读图片 |

## 3.2 最严重的三条

1. **性别 / 年龄 / 使用强度 / 生命周期** —— 这是对"你是谁"的直接判定，**不可撤销、不可查看、不可删除**
2. **完整已装应用清单 + 是否真用过** —— 能推断你的职业、收入、兴趣爱好、健康状况（装了医疗 App？）
3. **IMEI / IMSI / ICCID** —— 硬件级唯一标识，跨设备、跨账号关联的锚点

**这三条都不受任何用户开关控制。**

---

# 第四部分：剩余三项待查结果

## 4.1 `b6/d.java` 的 `c()` / `h()` —— 不是 HTTPDNS 地址

```java
public final Context c() {
    Context context = f797b;
    if (context == null) v("context");
    return context;
}

public final String h() {
    String str = f799d;
    if (str == null) v("region");
    return str;
}
```

`c()` 返回 **Context**，`h()` 返回 **region 字符串**。

`OkHttpDns` 的初始化（`s6/b.java:168`）：

```java
b.C0127b q10 = new b.C0127b()
    .q(new c())          // HttpDns 的 HTTP 请求器
    .p(dVar2.h())        // ← 这里传的是 region，不是域名
    .l(...)              // 环境
    .o(...)              // 日志级别
    .n(dVar)             // 日志
    .k();                // build
g.b(dVar2.c(), q10, new a());   // dVar2.c() = Context
```

**`b6.d` 只是「运行环境配置」，域名不在这里。**

真正域名在 `c2/d.java` / `c2/e.java`（已解出，见第七轮）。

## 4.2 `u5/z.java` —— **不用 HTTPDNS**

```java
// u5/z.java:83
java.net.URL r5 = new java.net.URL(r3);
java.net.URLConnection r3 = r5.openConnection();     // ← 系统默认 handler
java.net.HttpURLConnection r3 = (java.net.HttpURLConnection) r3;
r3.setRequestMethod("POST");
r3.setRequestProperty("Content-Type", "application/json;charset=UTF-8");
```

`new URL(str)` → `openConnection()` → `JDK 默认 URLStreamHandler` → `InetAddress.getAllByName()` → **系统 DNS**。

它 `import com.heytap.httpdns.dnsList.AddressInfo` 只是因为借用了常量名 `COLUMN_TIMESTAMP` 当参数 key：

```java
hashMap.put(AddressInfo.COLUMN_TIMESTAMP, String.valueOf(currentTimeMillis));
```

**结论：`u5/z.java` 的所有请求 AdGuard 都能看到。**

`u5/b0.java` 的 `compiled from` 是 `JsonUtils.kt`，纯 JSON 工具，跟网络无关。

### 但发现第三个 HTTPDNS 域名（当前不生效）

`u5/n.java:111`（`DomainManager.i()`）：

```java
public String i() {
    if (f9699d == 1) {
        return g1.a("`||x{2''lkk%`||xlf{%kf&\u007fifqgd&kge");   // XOR 0x08
    }
    DomainConfig cfg = f9697b;
    if (cfg != null && cfg.getHttpDns() != null) return cfg.getHttpDns();
    return "";
}
```

解码：

```python
"`||x{2''lkk%`||xlf{%kf&\x7fifqgd&kge" XOR 0x08
  = https://dcc-httpdns-cn.wanyol.com
```

**为什么当前不生效**（追到底了）：

```
u5/n.f9699d = cVar.getEnv()
  → n2/a.java:182  getEnv() = v5.c.f10184a.b() ? <DevTools> : cVar
    → v5/c.java:29-45  b() 检查：
        f10185b != null        ✓（有 Application）
        && n2.b.b()            ← devTools 开关
        && Class.forName("com.oplus.dcc.devtools.DevToolsImpl") 存在
      → n2/b.b() 读 n2.b.f6683c.get("devTools")
        → j2/c.java:620  hashMap.put("devTools", Boolean.FALSE);   ← ★ 硬编码 FALSE
```

**`devTools` 在正常启动路径被硬编码为 `FALSE`** → `b()` 返回 false → 不走 DevTools 分支 → `getEnv()` 返回 0 → `f9699d != 1` → **用 `DomainConfig.getHttpDns()`（云端下发），不用那个硬编码域名**。

> 所以 `dcc-httpdns-cn.wanyol.com` 是 dev/debug 分支的死代码。
> **已加入黑名单作为兜底**（`01-telemetry-ads.txt` 末尾）。

## 4.3 `RemoteTrainService` 的进程与权限

从 Manifest 直接读：

```xml
<service
    android:name="com.oplus.dcc.ml.train.multiprocess.RemoteTrainService"
    android:exported="false"
    android:process=":train" />
```

### 完整进程表

| 进程 | Service | 职责 |
|---|---|---|
| 主进程 `com.oplus.statistics.rom` | — | 统计、数仓、上传 |
| **`:train`** | `RemoteTrainService` | **端侧训练** |
| `:infer` | `RemoteInferService` | 端侧推理 |
| `:worker` | `DccRemoteWorkerService` | DAG 任务编排 |
| `(:xxx)` | `com.oplus.dcc.alive.FService` | 保活（`foregroundServiceType=0x2`） |

### 服务定义极简

```java
public final class RemoteTrainService extends ProcessService {
}
```

逻辑全在 `com/oplus/base/process/ProcessService.java`，通过 AIDL（`l2.b`）与主进程通信。

### 权限

- `exported="false"` —— 外部应用不能 bind
- 整个包持有 `com.oplus.permission.safe.PERSISTENT`（常驻不被杀）
- `oplus.permission.OPLUS_COMPONENT_SAFE`（系统级）

### 完整调用链

```
主进程 com.oplus.statistics.rom
  │ AIDL (l2.b)
  ▼
:train 进程 (RemoteTrainService extends ProcessService)
  │ StarfireLiteSdk / MlEngine.init(EngineConfig)
  ▼
CPython (lib/arm64-v8a/libcpythonapp.so)
  │ pyvm_enter.main({module, func, param})
  ▼
assets/20230719200305/biz/common/lr_train/train_lr.py (或 train_dnn.py)
  │ get_input_data() → DB_SELECT (读 mt_dw)
  │ MNN 训练
  │ assert/embedding 写回 fe_user/item_feature_embedding
  ▼
py_tunnel.dcc_tunnel_send("fe","train", msg)
  │ cpythonapp.call_java_func("DccTunnel", ...)
  ▼
PyFuncCallAdapter.DccTunnel → CommonComponentsController.onTrack(...)
  │ x4/b.java  EngineTrackProxy.onTrack()
  ▼
j7/h.java  OplusTrack.g()
  │ s9/h.b(Runnable → k7/e.c(ctx, aVar))   // CommonAgent
  ▼
m7/l.java  ProxyRecorder
  │ 先探测：t9/h.a() → m7/j.m()
  │         content://com.oplus.statistics.provider/support
  ├─可用─► m7/j.java ContentProviderRecorder
  │         insert("content://com.oplus.statistics.provider/track_event", values)
  │           ▼
  │         DcsContentProvider.insert()      ← 同包，进程内
  │           ▼
  │         u.h().w(msgType, intent)         ← DcsWorker
  │           ▼
  │         Handler → 各记录器 → 数仓
  │
  └─不可用─► m7/o.java ServiceRecorder
             Intent → ComponentName("com.nea_rme.statistics.rom",
                                    "com.nearme.statistics.rom.service.ReceiverService")
             （Base64 解码出的旧包名，same-process fallback）

         ↓ 最终都汇入主进程数仓

主进程 → OkHttp (z7/n.java) → 默认 DNS → AdGuard 可见
```

## 4.4 ⚠️ 修正：DccTunnel **不直连网络**

上一轮（第七轮）写「DccTunnel 最终走埋点通道、默认 DNS」，容易误解成「DccTunnel 直连网络」。
实际不是——**DccTunnel 全程是本地 IPC，不出网。**

### 4.4.1 两个 fallback 分支

`m7/l.java`（`ProxyRecorder`）在第一次写入前会探测：

```java
private void b(Context context) {
    if (this.f6381a != null) return;
    if (t9.h.a(context)) {          // → m7/j.m()
        this.f6381a = new j();      // ContentProviderRecorder
    } else {
        this.f6381a = new o();      // ServiceRecorder
    }
}
```

探测方式（`m7/j.java:152`）：往 `content://com.oplus.statistics.provider/support` 插一条空数据。

| 分支 | 类 | 通道 |
|---|---|---|
| 可用 | `m7/j.java` ContentProviderRecorder | `content://com.oplus.statistics.provider/track_event` |
| 不可用 | `m7/o.java` ServiceRecorder | `Intent` → `com.nearme.statistics.rom.service.ReceiverService`（旧包名，Base64 解码） |

**两条路都是本地 IPC，没有域名，没有 socket。**

### 4.4.2 Provider 端做了什么

`com/oplus/statistics/rom/service/DcsContentProvider.java`：

```java
static {
    uriMatcher.addURI("com.oplus.statistics.provider", "track_event", 1);
    uriMatcher.addURI("com.oplus.statistics.provider", "white_list",  2);
    uriMatcher.addURI("com.oplus.statistics.provider", "support",     3);
    uriMatcher.addURI("com.oplus.statistics.provider", "query_event", 4);
}

private void e(final ContentValues contentValues) {
    Intent intent = new Intent();
    contentValues.keySet().forEach(k -> intent.putExtra(k, cv.getAsString(k)));
    intent.putExtra(KEY_APP_ID, ...);
    intent.putExtra(KEY_BOOLEAN_IS_ANONYMOUS, ...);
    Integer dataType = contentValues.getAsInteger(KEY_INT_DATA_TYPE);
    u.h().w(dataType != null ? m9.a.a(dataType, 0) : 0, intent);   // ← 丢给 DcsWorker
}
```

Manifest：
```xml
<provider
    android:name="com.oplus.statistics.rom.service.DcsContentProvider"
    android:authorities="com.oplus.statistics.provider"
    android:exported="true" />        ← 注意：没有 permission 保护
```

> 这个 provider **没有权限限制**，任何应用都可以往里面写埋点事件。
> 但与 DonateProvider 不同，它的数据源受 `$app_id` 限制，不能直接捐敏感数据。

### 4.4.3 真正的出网域名

数据进了 `DcsWorker` → 各记录器 → 数仓，然后和普通埋点一起批量上传，入口是同一套：

| 域名 | 作用 |
|---|---|
| `api-cn.cdo.heytapmobi.com` / `api-gl.cdo.heytapmobi.com` | CDO 接口 |
| `api.cdo.oppomobile.com` | 同上（旧域名） |
| `epoch-cn.cdo.heytapmobi.com` 及 `epoch-{gl,id,in,my,ph,th,tw,vn}.*` | epoch 统计流水 |
| `epoch.cdo.oppomobile.com` / `*epoch.oppomobile.com` | 旧域名 |
| `fupload-cn.cdo.heytapmobi.com` | 文件分片上传 |
| `gslb-cn.cdo.heytapmobi.com` / `gslb-gl.cdo.heytapmobi.com` | GSLB |
| `conf-cn.dc.heytapmobi.com` | 配置 |
| `event.dc.heytapmobi.com` / `event.dc.oppomobile.com` | 事件 |
| `dragate-cn.dc.heytapmobi.com` | 数据网关 |
| `mdp-usertrace-cn.heytapmobi.com` | 用户轨迹 |
| `ums-telemetry-cn.heytapmobi.com` | 遥测 |

**共 77 个上报类域名**（完整清单见 `out/hosts-clean.json`），全部已在 `out/blocklist/01-telemetry-ads.txt` 中。

### 4.4.4 结论修正

| 说法 | 准确性 |
|---|---|
| 「DccTunnel 走埋点通道」 | ✅ 对 |
| 「DccTunnel 直连网络/直连域名」 | ❌ **错**，全程本地 IPC |
| 「训练数据最终走默认 DNS 出网」 | ✅ 对（汇入数仓后批量上传） |
| 「AdGuard 能拦」 | ✅ 对，拦的是数仓上传域名 |

---

# 五、结论汇总

| 问题 | 答案 |
|---|---|
| 24h 上报的是数量还是内容 | **数量**，4 个 `count(*)` 整数 |
| 本地存了什么 | 完整特征样本（稀疏编码 + 标签），但不上传明细 |
| 差分隐私怎么保护 | 裁剪 + 加噪，数学上保证 (ε,δ)-DP |
| ⚠️ 当前开着吗 | **没开**（`do_dp: false`） |
| FedAvg 是什么 | 联邦平均，各端本地训练、只上传模型权重、服务器取平均 |
| 模型文件是什么 | 神经网络参数矩阵（.mnn / .snapshot），几十万个 float |
| 传梯度吗 | **不传**，无通道 |
| 到底泄漏了什么 | 性别/年龄/使用强度/生命周期/已装应用/URI/IMEI/SSID — **都确定外泄** |
| statistics.rom 进程架构 | 主 + `:train` + `:infer` + `:worker` + 保活 |
| 训练上报能被拦吗 | **能**，DccTunnel 是本地 IPC（不出网）→ 汇入数仓 → 由埋点域名出网 |
| DccTunnel 直连域名 | **没有**。全程 ContentProvider/Intent IPC |
| 训练数据真实出口 | `*.cdo.heytapmobi.com` / `*.dc.heytapmobi.com` / `*.oppomobile.com`（77 个上报类域名） |

---

# 六、黑名单更新记录

本轮新增（手动）：

```
dcc-httpdns-cn.wanyol.com  # ★HTTPDNS | devTools 分支硬编码，release 不生效，兜底屏蔽
```

文件：`out/blocklist/01-telemetry-ads.txt`（末尾附注）
另有独立清单：`out/blocklist/05-manual-additions.txt`

**当前 Tier A 总数：141 条**（脚本产出 140 + 手动 1）
