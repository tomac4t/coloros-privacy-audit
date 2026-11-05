# 第七轮：HTTPDNS 与端侧训练 —— 两个决定性问题

- **日期**：2026-11-05
- **问题**：①HTTPDNS 怎么做，屏蔽会不会回落到传统 DNS，黑名单还有没有用 ②端侧训练是否默认启用、能否关闭、输出什么、梯度会不会外传

---

# 第一部分：HTTPDNS

## 1.1 结论先行

| 问题 | 答案 |
|---|---|
| 用不用 HTTPDNS | **用，但只给 OkHttp 那一条 HTTP 通道用** |
| 屏蔽 HTTPDNS 会不会回落传统 DNS | **会。这是设计好的降级路径** |
| 黑名单还有用吗 | **有用**。主要上报走默认 DNS，HTTPDNS 只服务 OkHttp 子集 |
| ★ HTTPDNS 服务域名 | **`https://support.browser.heytapmobi.com`** 和 **`http://apisnd.heytapmobi.com`** |

> 这两个域名我**从代码里解出来了**（`c2/d.java` + `c2/e.java` + `c2/a.java` 的字节数组）：
> ```java
> // c2/a.java  字节数组藏域名后缀
> f944a = {111,112,112,111}         // "oppo"
> f945b = {109,111,98,105}         // "mobi"
> f946c = {104,101,121,116,97,112} // "heytap"
>
> // c2/d.java  HTTPDNS 主服务
> "https://support.browser." + "heytap" + "mobi.com"
>   = https://support.browser.heytapmobi.com
>
> // c2/e.java  备用 / 配置下发
> "http://apisnd.heytap" + "mobi" + ".com"
>   = http://apisnd.heytapmobi.com
> ```
> 路径常量在 `com/heytap/httpdns/serverHost/a.java`：
> `/httpdns/get`、`/getDNList`、`/getHttpDnsServerList`、`/v2/d`

## 1.2 实现结构

```
s6/b.java      OkHttpDns      ← 实现 okhttp3.Dns 接口
    a(hostname):
        List<h1.d> c10 = httpDns!!.lookup(hostname)   // HTTPDNS 查询
        if (list == null || list.isEmpty()) {
            return Dns.SYSTEM.lookup(hostname);        // ★★★ 回落系统 DNS
        }
        return list;
```

**对应源码（`s6/b.java:189-215`）：**

```java
@Override // okhttp3.f
public List<InetAddress> a(String hostname) {
    List<InetAddress> list = null;
    try {
        g gVar = this.f9046b;
        if (gVar != null) {
            List<h1.d> c10 = gVar.c(hostname);           // HTTPDNS lookup
            ArrayList arrayList = new ArrayList();
            for (h1.d it : c10) {
                InetAddress c11 = c(it, hostname);
                if (c11 != null) arrayList.add(c11);
            }
            list = v.X(arrayList);
        }
    } catch (Exception e10) { /* 打日志 */ }

    if (list == null || list.isEmpty()) {
        List<InetAddress> a10 = f.f7506a.a(hostname);     // ★ f.f7506a = Dns.SYSTEM
        return a10;
    }
    return list;
}
```

`okhttp3/f.java` 里的 `f7506a` 默认实现就是：
```java
InetAddress[] allByName = InetAddress.getAllByName(hostname);
```

→ **`InetAddress.getAllByName()` = 走系统 DNS = 走 AdGuard Home。**

## 1.3 但 HTTPDNS 不是全局的

**只有走 OkHttp 的请求会经过 `OkHttpDns`。** 证据：

```java
// t6/d.java:91
if (f9481c && f9482d) {
    aVar.e(new s6.b());     // 给 OkHttpClient 设置 dns = OkHttpDns
}
```

`f9481c = true`（硬编码）、`f9482d` = `f.f954b.a()` 初始化成功与否。

**而 statistics.rom 自己发上报请求用的是……**

```java
// z7/n.java (OkHttpUtil)
private static p h() {
    p.a d10 = new p.a().d(new mc.g(5, 5L, TimeUnit.SECONDS));
    d10.a(v7.b.f10200a);        // ★ 只加了 GatewayUpdateInterceptor
    return d10.b();
}
```

**这里没有 `.dns(new s6.b())`！**

也就是说：**埋点上报走的 OkHttpClient 是系统默认 DNS，不是 HTTPDNS。**

## 1.4 那 HTTPDNS 到底给谁用

追踪 `t6/d` 的使用者：

```
s6/a.java  NetworkManager
    a(long, u6.a trackRequest):
        return f9044a ? new t6.d(...) : new t6.b(...)
```

`t6/d` 构造的是 **统计/埋点上报客户端**（`u6.a trackRequest` 参数）。
但它的 OkHttpClient（`t6/d.f9483e`）是静态字段，**只在这个类内部用**。

而 `t6/d` 的调用方……

```java
s6/b.java:102  u6.b a10 = s6.a.f9045b.a(-1L, f10.e(request.d())).a();
```

——是 OkHttpDns 自己的 DNS-over-HTTP 请求（去 HTTPDNS 服务器查 IP）。
**这是个自举：HTTPDNS 客户端自己也要发 HTTP 请求，那次请求用 t6.d（带 HTTPDNS 的 OkHttp）。**

所以结构是：

```
上报请求 (z7/n.java)  →  OkHttpClient（默认 DNS）  →  系统 DNS  →  AdGuard ✔ 可拦
                                                                    ↓
HTTPDNS 更新请求 (s6/b)  →  t6.d 的 OkHttpClient（带 OkHttpDns）
                                  ↓
                            先问 HTTPDNS 服务器拿 IP
                            ↓ 拿不到就回落系统 DNS
                                        ↓
                                    AdGuard 只能看到 HTTPDNS 服务器域名
```

## 1.5 HTTPDNS 服务地址在哪

`OkHttpDns` 初始化：
```java
b.C0127b q10 = new b.C0127b().q(new c());      // c = 自定义的 HTTP executor
b6.d dVar2 = b6.d.f807l;
g.b(dVar2.c(), q10.p(dVar2.h())...k(), new a());  // g.b = 初始化
```

**已确认的服务地址**（`com/heytap/httpdns/serverHost/a.java` → `c2/d.java` → `c2/e.java`）：

| 域名 | 用途 |
|---|---|
| **`https://support.browser.heytapmobi.com`** | ★ HTTPDNS 主服务（`/httpdns/get` `/getDNList` `/getHttpDnsServerList` `/v2/d`） |
| **`http://apisnd.heytapmobi.com`** | 备用 / 域名列表下发 |

**备用 IP 硬编码**（`c2/d.java:24`，当域名也解析不了时直接连）：
```
120.246.123.112, 106.3.18.112, 111.206.136.5,
120.238.145.15, 119.147.175.11, 157.148.79.10
```

**⚠️ AdGuard Home 拦不住 IP 直连。** 这 6 个 IP 需要单独在防火墙层处理。

另外还有几个相关的 HTTPDNS 域名（前面扫描里出现过）：
- `httpdns.ocloud.heytapmobi.com`
- `httpdns.push.heytapmobi.com` / `httpdns-euex-push.heytapmobile.com`
- `httpdns-push.heytapmobile.com`
- `ocloud-httpdns-cn.heytapmobi.com`
- `api.dns.oppomobile.com`

> **当前黑名单状态**：`support.browser.heytapmobi.com` 在 `02-caution.txt`（标为「浏览器」），
> `apisnd.heytapmobi.com` 在 `03-rest.txt`（未归类）。
> **这两个应该移到 `01-telemetry-ads.txt`，因为它们是埋点上报的 DNS 引导入口。**

## 1.6 对黑名单的实际影响

| 场景 | AdGuard 能否拦 |
|---|---|
| 埋点上报（`/v1/stat/*`、`/v3_1/dcs/*`）走 `z7/n.java` 的 OkHttp | ✅ **能**（默认 DNS） |
| 走 `t6.d` 的统计客户端 | ❌ 不能（HTTPDNS） |
| HTTPDNS 自身的更新请求 | ⚠️ 只能看到 HTTPDNS 服务器域名 |
| 其他模块（`u5/z.java` HttpURLConnectionUtils 等） | ✅ 大概率能（要逐个确认） |

**结论：你的黑名单仍然有效，而且大概率能拦住主要上报。**
但要注意两点：

1. **HTTPDNS 服务器本身也要加黑名单**（`httpdns.*.heytapmobi.com` 那几个），否则它会一直帮你解析真实域名
2. **会不会「HTTPDNS 拿到了 IP 就不经过 DNS」** —— 会。所以如果某个模块用了 `t6.d`，那条链路 AdGuard 看不见

## 1.7 一个额外发现：GatewayUpdateInterceptor

```java
// v7/b.java
public r a(i.a chain) {
    d dVar = f10201b;
    if (dVar == null) return chain.b(chain.a());
    r b10 = chain.b(dVar.b(chain));     // ★ 改写请求
    dVar.a(b10);                        // 观察响应
    return b10;
}
```

`v7/c.java` 注册的是 `v7.a(new a())`，而 `v7/a` 绑定 `GatewayUpdateHandler`，从云控 `CloudCtlProductList` 读 `productId + version`。

**→ 这是「网关热切换」：服务端可以下发新的网关地址，客户端拦截器实时改写请求的目标。**
所以即使你把域名拉黑，服务端也可能改成别的域名。

---

# 第二部分：端侧训练

## 2.1 结论先行

| 问题 | 答案 |
|---|---|
| 训练代码存在 | ✅ 完整（`train_lr.py` 51KB + `train_dnn.py` 52KB + `dp_sgd.py`） |
| 默认启用吗 | **代码层面是「64 位设备就加载模块」，但真正训练要等云端下发任务** |
| 能否关闭 | **用户层面不能**。只能靠断网/拦域名 |
| 训练会输出什么 | **模型权重文件（`.mnn` / `.snapshot`）+ 训练指标 fragment** |
| 梯度会不会传出去 | **不上传梯度**。上传的是「模型参数」+「AUC/accuracy 统计」+「样本数」 |

## 2.2 启用条件的完整链路

```
StatisticsApplication
    └─ j2/g.java:64 注册模块列表
         ├─ DcsModule
         ├─ EapModule
         ├─ DataModule
         ├─ AwarenessModule
         ├─ InferModule        ← 端侧推理
         └─ TrainModule        ← ★ 端侧训练
              └─ TrainModule.c()  (初始化回调)
                   if (f.i()) {        // ★★★ w3/f.i() = 设备是否支持 arm64-v8a
                       b1.c(Runnable -> TrainModule.l(this))
                   }
```

**关键源码（`TrainModule.java`）：**

```java
@Override // m2.d
protected void c() {
    super.c();
    if (f.i()) {                          // f = w3.f
        b1.c(new Runnable() { ... this$0.k(); ... });
    }
}
```

**`w3/f.i()` 的实现：**

```java
public static boolean i() {
    String[] strArr = Build.SUPPORTED_64_BIT_ABIS;
    if (strArr == null || strArr.length <= 0) return false;
    for (String str : strArr) {
        if ("arm64-v8a".equals(str.toLowerCase(Locale.ENGLISH))) return true;
    }
    return false;
}
```

**→ 只要你的手机是 64 位（一加 8T 一定是），训练模块就会初始化。没有用户开关。**

至于「会不会真的开始训练」—— 需要云端下发 `TaskInfo`：

```java
// com.oplus.dcc.ml.train.config.TaskInfo
private final String taskId;
private final String appPackage;
private final String appId;
private final List<String> regions;      // 按地区下发
private final List<String> models;       // 按机型下发
private final List<String> osVersions;   // 按系统版本下发
private final int dataSetMinSize;        // ★ 样本量下限
private final int dataSetMaxSize;        // ★ 样本量上限
private final long expireTime;
private final long selectTimeout;
private final String ext;                // ★ 扩展参数（模型超参与训练配置）
```

**下发流程：**
```
云端 -> dcc_124200_trainingTaskCondition (ServerTrainTaskList)
     -> dcc_124200_trainingTimeCondition (ServerTrainStrategy.trainingTimeCondition)
     -> f5/c.java: X(taskInfo) 检查授权
        if (com.oplus.dcc.safe.auth.e.a(ctx, appId).d(d.TRAIN))  // ★ 需要 TRAIN 授权
     -> RemoteTrainService (独立进程)
     -> Python: lr_train/train_lr.py  或  train_dnn.py
```

**训练时机的约束条件（`TrainingTimeCondition`）：**
```java
startCondition.getTime()             // 时间段
startCondition.getCharging()         // 是否充电
startCondition.getBattery()          // 电量阈值
startCondition.getTemperature()      // 温度上限
startCondition.getScreenOffDelay()   // 息屏多久后开始
startCondition.getNetworksList()     // 允许的网络类型
startCondition.getStorage()          // 存储下限
startCondition.getRegionsList()      // 地区白名单
startCondition.getModelsList()       // 机型白名单
startCondition.getOsVersionsList()   // 系统版本白名单
```

**典型的「夜间充电 + WiFi + 息屏」模式。**

## 2.3 训练会输出什么

`train_lr.py` 的训练收尾（第 1130-1160 行）：

```python
fragment = { ... }
fragment_json = json.dumps(fragment)
# ★ 上传模型
py_communicator.send("BACK_MODEL_MESSAGE", fragment_json, local_data.is_test)

# ★ 上传埋点
msg = json.dumps({
    "type": "train_result",
    "req_str": local_data._req_json,
    "fragment": fragment_json,
    "train_cost": cost_log,                     # 各阶段耗时
    "real_sample_cnt": online_train_dataset.__len__(),   # ★ 真实样本数
    "feature_info": feature_info,
})
py_tunnel.dcc_tunnel_send("fe", "train", msg)
```

**`fragment` 里是什么？** 看 metrics：

```python
metrics = {
    "train": {"acc_fragment": ..., "loss_fragment": ..., 
              "tp_fragment": [...], "tn_fragment": [...],
              "fp_fragment": [...], "fn_fragment": [...]},
    "test":  { 同上 },
    "auc_fragment": auc.auc_calculate(labels, scores),
}
```

**→ 上传的是：混淆矩阵（TP/TN/FP/FN）+ loss + accuracy + AUC + 样本数。**

外加模型文件本身：
```python
py_communicator.send("BACK_MODEL_MESSAGE", fragment_json, ...)
```

`BACK_MODEL_MESSAGE` 走的是 `DccSend` → `CommonComponentsController.sendData(type, data)`。

## 2.4 梯度会不会传出去

**不会。** 依据：

1. **代码里没有任何「上传梯度」的路径**。`dp_sgd.py` 的 `dpMaskModel()` 只做本地操作：
   ```python
   # 1. 算更新量的 L2 范数
   updateL2Norm = sqrt(sum((x-y)^2))
   # 2. 裁剪
   clipFactor = min(1.0, dpNormClip / updateL2Norm)
   # 3. 加高斯噪声
   temp[j] = self.__gaussianSigma * random.gauss(0, 1)
   # 4. 写回模型文件
   update_model[i].write(newData)
   ```
   全部在本地，**输出是 `update_model`（模型文件），不是梯度**。

2. **联邦学习的结果是「模型参数」，不是梯度**。这是 FedAvg 的典型做法。

3. **但是**：`reporter/fed_reporter.py` 会上报训练流程事件到 obus：
   ```python
   py_tunnel.dcc_tunnel_send("train_flow", "train_flow_", jsonData)
   ```

## 2.5 ⚠️ 但 `do_dp = false`

**这是最关键的发现。**

`assets/20230719200305/fl_tasks.json`：

```json
{
  "loss": "weight_binary_cross_entropy",
  "do_dp": false,          ← ★★★ 差分隐私默认关闭
  "optim": "MNN.optim.SGD(model, 0.01, 0.9, 0.0005,...)",
  "stop_train_condition": " cur_auc > 0.78 and  cur_loss_avg < 4.0 ",
  "cur_train_weight": [
    {"value_resolver": "4", "value_resolver_condition": "round_idx < 10"},
    {"value_resolver": "5", "value_resolver_condition": "round_idx < 20"},
    {"value_resolver": "5", "value_resolver_condition": "True"}
  ],
  "pre_train_select_condition": "True",
  "pre_train_good_enough": "  train['auc_fragment']>0.85 ",
  "dyn_lr": [...]
}
```

**`do_dp: false`** —— 差分隐私**默认关闭**。
所以 `dp_sgd.py` 虽然写了，但按当前配置**不执行**。模型更新是**未加噪的原始权重差**。

这意味着：如果需要，服务端**可以**下发更新的 `fl_tasks.json` 把 `do_dp` 改成 `true`。
但当前默认是不加噪。

## 2.6 「样本数」也被上传

```python
def upload_local_samples(req):
    feature_info = FeEmb.get_fe_feature_info()
    py_tunnel.dcc_tunnel_send_v2("fe", "train", json.dumps({
        "type": "local_sample",
        "real_sample_info": feature_info        # ★ 真实样本信息
    }))
```

而且这个任务是**定时的**：
```python
upload_sameple_interval = moubleConfig.get("upload_sameple_interval", 86400)  # 默认 24 小时
BackgroundTaskManager.add_period_task(..., upload_local_samples, {}, upload_sameple_interval)
```

**→ 即使不训练，也会每 24 小时上报一次「我这条链路有多少样本」。**

## 2.7 能否关闭

| 手段 | 有效性 |
|---|---|
| 用户设置开关 | ❌ **没有**。`TrainModule.c()` 里只有 `f.i()`（64 位检查） |
| 关闭「用户体验改进计划」 | ❓ 未验证。`TrainModule.c()` 没检查 `p0.h()` |
| 断网 / 拦域名 | ✅ 有效（但要拦住下发任务的域名和上报域名） |
| 卸载/冻结 `com.oplus.statistics.rom` | ✅ 有效，但会连带停掉其他统计 |

**代码里 TrainModule 的启动条件只有一个：`arm64-v8a`。没有任何用户可达的开关。**

## 2.8 训练任务实际有没有跑？

需要真机确认。看日志关键字：
```bash
adb logcat -s TrainModule RemoteTrainService DccTrainService train_flow
```

Python 侧日志关键字（`pylog_i`）：
```
=====train_lr begin
=====train upload args beg, fragment:
=====train_lr end, total_cost:...
train_result
```

如果 24 小时内没出现这些，说明云端没给这台设备下发训练任务。

---

# 三、两个问题的合并结论

## HTTPDNS
- **黑名单有效**，因为主要上报路径（`z7/n.java`）走默认 DNS
- 需要额外拦住 `httpdns.*.heytapmobi.com` 等 HTTPDNS 服务域名
- 但 `GatewayUpdateInterceptor` 可以让服务端随时换网关，这是黑名单的长期弱点

## 端侧训练
- **64 位设备默认加载模块**，无用户开关
- 但**真正训练要云端下发任务**（按 region/model/osVersion 定向）
- 输出：模型权重 + 混淆矩阵 + loss/acc/AUC + 样本数
- **不上传梯度**
- ⚠️ **`do_dp: false`** —— 差分隐私默认关闭，模型更新是未加噪的
- 每 24 小时上报一次样本信息（即使不训练）

---

# 四、剩余待查

1. `b6/d.java` 的 `c()` / `h()` —— HTTPDNS 服务器的真实地址
2. `u5/z.java`（HttpURLConnectionUtils）、`u5/b0` 等其他 HTTP 通道是否也用 HTTPDNS
3. `RemoteTrainService` 到底在哪个进程，权限如何
4. 真机验证训练是否真的触发
