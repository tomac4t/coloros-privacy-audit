# 第九轮：DAG 任务编排 / 事件清单 / native 加密

- **日期**：2026-11-05
- **接 phase6 的待办 3/4/5**
- 本文三部分：①云端可编程的边界 ②事件清单 ③native 密钥全部解开

---

# 第一部分：DAG 任务编排 —— 云端可编程的边界

## 1.1 结论先行

**服务端能给这台设备下发「任意 Python 脚本 + 任意 SQL」，按 DAG 顺序执行。**

不是「配置开关」，是**真正的远程代码执行**——只是脚本必须在 APK 内置的 `assets/` 里。

## 1.2 任务结构（`TaskInfo.java`）

```java
public abstract class TaskInfo {
    private long    appId;
    private String  cron;            // ★ cron 表达式（定时）
    private long    dagId;
    private int     frequency;
    private int     maxRetryTime;
    private long    scheduleTime;
    private String  script;          // ★★★ 脚本内容（服务端下发）
    private int     scriptType;      // ★ 1=SQL / 2=DSL / 3=Python
    private int     tagCloud;
    private long    taskId;
    protected int   taskType;        // 1=PULL_DATA / 2=TAG_SQL / 3=COMMON_SQL
    private int     priority;        // 1=MAX / 2=NORMAL / 3=MIN
    private TaskConstrains constrains;
    private List<Long> upstreamTasks;    // ★ DAG 前驱
    private List<Long> downstreamTasks;  // ★ DAG 后继
}
```

### scriptType 三种模式

| 值 | 常量 | 含义 |
|---|---|---|
| 1 | `SCRIPT_TYPE_SQL` | 执行 SQL |
| 2 | `SCRIPT_TYPE_DSL` | 执行 DSL（JSON 描述的数据拉取） |
| 3 | `SCRIPT_TYPE_PYTHON` | **执行 Python** |

### taskType 三种模式

| 值 | 常量 | 实现类 |
|---|---|---|
| 1 | `TASK_TYPE_PULL_DATA` | `PullDataDSLTaskInfo`（拉数据） |
| 2 | `TASK_TYPE_TAG_SQL` | `TagSqlTaskInfo`（打标签） |
| 3 | `TASK_TYPE_COMMON_SQL` | `CommonSqlTaskInfo`（通用 SQL） |

## 1.3 Python 任务的执行方式（最关键）

`PythonScriptModel`（`com/oplus/dcc/internal/work/script/`）：

```java
public final class PythonScriptModel {
    private final String module;   // ★ 模块名
    private final String func;     // ★ 函数名
    private final String param;    // ★ 参数（JSON 字符串）
}
```

对应 `pyvm_enter.py` 的入口：

```python
def main(p):
    params   = json.loads(p)
    module   = importlib.import_module(params['module'])   # ← 动态导入
    func     = getattr(module, params['func'])             # ← 动态取函数
    return func(params['param'])                           # ← 执行
```

**→ 服务端下发 `{scriptType:3, script:'{"module":"xxx","func":"yyy","param":"..."}'}`，
设备就执行 `xxx.yyy("...")`。**

### 能调用哪些 module？

`assets/pyvm/global/pyvm_global.py` 会 append sys.path，能导入的都在 `assets/` 下：

| 目录 | 能做什么 |
|---|---|
| `assets/20230719200305/biz/common/lr_train/` | 训练模型 |
| `assets/20230719200305/biz/common/predictor/` | 推理 |
| `assets/20230719200305/biz/common/feature/` | 特征工程 |
| `assets/dccpy/user_profile/` | 性别/年龄/偏好预测 |
| `assets/dccpy/user_profile_cn/` | 国内版 ETL |
| `assets/20230719200305/biz/scenes/*/` | 各类场景（主题推荐等） |

**边界：只能调 APK 里已存在的 module。但每个 module 内部能做什么，是开放式的。**

## 1.4 Python 能碰到的底层能力（`PyJavaProtocol.FuncName`）

```java
EmbeddingService,     // 调云端 embedding 服务
ObusTunnel,           // 写 OBUS 埋点
DccTunnel,            // 写 DCC 埋点（训练结果走这条）
MultProcess_DccTunnel,
LogTunnel,            // 写日志
S3Upload, S3Download, // ★ 上传/下载任意文件到对象存储
DccDownload, DccUpload, DccSend,
CubeFsUpload, CubeFsDownload,          // ★ CubeFS 对象存储
LocalFileSystemUpload, LocalFileSystemDownload,
MockCommunicator, Communicator, DccCommunicator,
UnzipFile, ZipFile
```

**加 `DbConsumer` 的 `DB_SELECT` / `DB_INSERT` / `DB_UPDATE`（可执行任意 SQL）。**

→ 组合起来：**读任意本地表 → 算 → 打包 → 上传到对象存储**。这是完整的数据外流能力。

## 1.5 执行时机与约束（`TaskConstrains`）

```java
private boolean batteryNotLow;
private boolean charging;
private boolean deviceIdle;
private int     maxTemperature;
private int     networkType;   // 0=不要求 1=连网 2=不计费 3=非漫游 4=计费
private boolean storageNotLow;
```

配合 `cron` 表达式 + `DagInfo` 的 `effectTime` / `expireTime` 窗口。

**典型：夜间 + 充电 + 息屏 + WiFi。**

## 1.6 执行链

```
云端 dcc_124200_dag
  ↓ DagProto (protobuf)
DagLoadManager 解析
  ↓
DagInfo { dagId, effectTime, expireTime, tasks[] }
  ↓
DagWorker.doWork()  (androidx.work)
  ↓
v4/n DagWorkerDelegate.h()
  │ 检查 r3.c.d() → DCC 已初始化
  │ 检查 dagId >= 0
  │ 检查 currentTime 在 [effectTime, expireTime)
  │ 检查 tasks 非空
  ↓
m4/m.o(ctx).m(true, dagInfo)   → WorkManager 入队
  ↓
按 upstream/downstream 拓扑排序
  ↓
每个 task 按 scriptType 分派：
  ├─ SQL   → s4/w (TagSql) / CommonSqlTaskWorker
  ├─ DSL   → s4/j (PullDataDSL)
  └─ Python→ s4/k (PythonScript) → :train 进程 → CPython
```

## 1.7 ⚠️ 代码安全漏洞：SQL 字符串拼接

`s4/w.java:158`：

```java
final Cursor i02 = e4.c.j0().i0(this.f9002b, ((TagSqlTaskInfo) this.f9001a).getScript(), null);
```

`getScript()` 直接作为原始 SQL 传给 `rawQuery`，**没有任何白名单或参数化**。

**→ 服务端下发什么 SQL 就执行什么。** 理论上可以 `select * from sqlite_master`、`drop table`、甚至读其他表。

## 1.8 边界总结

| 能做 | 不能做 |
|---|---|
| 执行任意本地 SQL（读/写/删） | 不能安装新 APK |
| 执行 APK 内置的任意 Python 模块函数 | 不能加载任意远程 Python 代码（只能调已有 module） |
| 上传任意本地文件到 S3/CubeFS | 不能提权（依然是 App 权限） |
| 按 cron 定时 + 拓扑顺序执行 | 不能绕过 `TaskConstrains` 的充电/网络等限制 |
| 用 `checkSign` 校验签名后才跑 | — |

> **`checkSign` 在哪？** `libdcc_cipher.so` 里有 `_Z6verifyP7_JNIEnvP8_jobjectS2_Pc`（verify），
> 且 `.rodata` 有个 86 字符的字符集 `0123456987.=qwertyuiopasdfghjklzxcvbnm+-QWERTYUIOPASDFGHJKLZXCVBNM!@#$%^&*()`，
> 这是自定义签名字母表。DAG 任务是否走签名校验需进一步确认。

---

# 第二部分：事件清单

## 2.1 `s7/k0.java` —— 不是事件表，是"事件规则缓存"

`ConfigEventId.kt` 内部类名容易误解。实际内容：

```java
private final String f9137b = ... + "/event_rules/";        // 缓存目录
private final Map<String, i1> f9138c = new LinkedHashMap();

// appId 分派
if (TextUtils.equals("20200", appId)) { ... }
else if (TextUtils.equals("601", appId)) { update601Table... }
```

### 它处理的 5 类"表"

```java
if (u7.j2.i0("install") > 0)      { c0("install");      t0("install"); }
if (u7.j2.i0("launch") > 0)       { c0("launch");       t0("launch"); }
if (u7.j2.i0("pre_launch") > 0)   { c0("pre_launch");   t0("pre_launch"); }
if (u7.j2.i0("app_launch") > 0)   { c0("app_launch");   t0("app_launch"); }
if (u7.j2.i0("first_startup") > 0){ c0("first_startup");t0("first_startup"); }
```

加 `uninstall`（601 那个分支）。

| 事件名 | 含义 |
|---|---|
| `install` | 安装 |
| `uninstall` | 卸载 |
| `launch` | 启动 |
| `pre_launch` | 预启动 |
| `app_launch` | 应用启动 |
| `first_startup` | 首次开机 |

**这六个是「应用生命周期」维度的事件，不是全部事件。**

## 2.2 `t1/c.java` —— OkHttp 网络事件监听器

`EventFactoryStub.kt` 实现 `mc.l`（OkHttp EventListener），在**每一次 HTTP 请求**时触发：

```java
// 定义在 com/heytap/common/b.java
public enum b {
    CALL_START, CALL_END, CALL_FAILED,
    REQUEST_HEADER_START, REQUEST_HEADER_END,
    REQUEST_BODY_START,   REQUEST_BODY_END,   REQUEST_FAILED,
    DNS_START,            DNS_END,                    // ★★
    CONNECTION_START,     CONNECTION_END,     CONNECTION_FAILED,
    CONNECTION_ACQUIRED,  CONNECTION_RELEASED,
    SECURE_CONNECT_START, SECURE_CONNECT_END,
    RESPONSE_HEADER_START, RESPONSE_HEADER_END,
    RESPONSE_BODY_START,   RESPONSE_BODY_END, RESPONSE_FAILED
}
```

### 关键：`DNS_END` 会把域名和 IP 一起上报

```java
// t1/c.java:530
public void m(okhttp3.b call, String domainName, List<InetAddress> inetAddressList) {
    ...
    hVar.a(com.heytap.common.b.DNS_END, K(call), domainName, inetAddressList);
    //                                   ↑ call       ↑ 域名        ↑ 解析出的 IP 列表
}
```

```java
// t1/c.java:565
public void n(okhttp3.b call, String domainName) {
    hVar.a(com.heytap.common.b.DNS_START, K(call), domainName);
}
```

**→ 每一次 DNS 查询的「域名 + 解析结果 IP」都会进埋点！**

这意味着：

1. **你的 DNS 请求本身被上报了**（不管解析成功还是失败）
2. 就算 AdGuard 拦截了某个域名，**"你尝试访问它"这个事实仍然被上传**
3. 反过来，**服务端也能看到你的真实 DNS 解析行为**

> 这是一个**元隐私问题**：屏蔽动作本身成了数据。

### 具体上报字段（`t1/c.java`）

```java
"call"                 // 请求标识
"connection"           // 连接信息
"domainName"           // ★ 域名
"inetAddressList"      // ★ IP 列表
"inetSocketAddress"    // socket 地址
"ioe"                  // IOException 信息
"proxy"                // 代理信息
"request" / "response" // 请求/响应
"type"                 // HTTP / QUIC
```

## 2.3 完整事件清单（整合前几轮）

### 系统级（`/v1/stat/*`、`/v3_1/dcs/*`）

```
clientStart, appList, launch, install, unInstall, AppLog, pageVisit, Exception,
dynamic, static, dau, dcs, osLaunch, osdau, osFirstLaunch, appEnterLaunch,
preLaunch, preUninstall, preAppList, balance
```

### 应用生命周期（`s7/k0.java`）

```
install, uninstall, launch, pre_launch, app_launch, first_startup
```

### 网络事件（`com/heytap/common/b.java`，22 种）

```
CALL_START/END/FAILED
REQUEST_HEADER_START/END, REQUEST_BODY_START/END, REQUEST_FAILED
DNS_START, DNS_END                                    ← ★ 域名+IP
CONNECTION_START/END/FAILED/ACQUIRED/RELEASED
SECURE_CONNECT_START/END
RESPONSE_HEADER_START/END, RESPONSE_BODY_START/END, RESPONSE_FAILED
```

### 训练流程（`reporter/fed_reporter.py`）

```
train_flow / train_flow_*      → 训练流程事件
fe / train                     → type: train_result / local_sample
```

### 推荐行为（`fe_emb.py`，决定 label）

```
group 1003  event 902   曝光
group 2024  event 421   点击
group 10003 event 7000  列表下载
group 10003 event 7002  详情下载
group 2023  event 321   付费
```

### 位置/短信/相册（`DonateProvider`）

```
doa_t1 (相册), doa_t2 (位置), doa_t3 (短信)
```

---

# 第三部分：native 加密 —— 全部解开

## 3.1 `libdcc_cipher.so`（14 KB，aarch64，stripped）

### 导出符号

```
JNI_OnLoad
_Z22rsa_public_key_encryptP7_JNIEnvP11_jbyteArray
_Z22rsa_public_key_decryptP7_JNIEnvP11_jbyteArray
_Z11aes_encryptP7_JNIEnvPhiS1_iS1_i
_Z11aes_encryptP7_JNIEnvPhiS1_iP11_jbyteArray
_Z11aes_decryptP7_JNIEnvPhiS1_iP11_jbyteArray
_Z6verifyP7_JNIEnvP8_jobjectS2_Pc
_Z14get_public_keyP7_JNIEnv
_Z7get_uidP7_JNIEnvP8_jobjectP8_jstring
```

### 注册的 Java 类

```
com/oplus/dcc/cipher/RSAUtil
com/oplus/dcc/cipher/CipherAlgoNative
com/oplus/dcc/cipher/AESUtil
```

### ★ 硬编码的 RSA-1024 公钥（已完整还原）

`get_public_key()` 从 `.rodata + 0x1124` 读 **864 字节**，每 4 字节的 int32 **+0x38** 后截断低 8 位，得到 216 字节 Base64：

```
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDSKXcrn/ZitSsMO8tIVieDy2K62V9cv+dGEF53nT3jDgGe2OugVEoWpLyNqiNqUlFtc5K8eKiQIQTZyGzP4fz87FSRilF/sv61cpROa1fnrzvfl+eG9hVzYXTpPt9vdAgRyWxTlwU+Xcqm/Xch9uNh9scaN6b7T2VumgZjGNK6FQIDAQAB
```

openssl 验证：

```
Public-Key: (1024 bit)
Modulus:
    00:d2:29:77:2b:9f:f6:62:b5:2b:0c:3b:cb:48:56:
    27:83:cb:62:ba:d9:5f:5c:bf:e7:46:10:5e:77:9d:
    3d:e3:0e:01:9e:d8:eb:a0:54:4a:16:a4:bc:8d:aa:
    23:6a:52:51:6d:73:92:bc:78:a8:90:21:04:d9:c8:
    ...
Exponent: 65537 (0x10001)
```

**混淆方式**：每个 int32 的低 8 位是 `ASCII + 0x38`，其余 24 位是填充。
（`movi v0.4h, #0x38` → `xtn → add → xtn` 就是这个变换）

### ★ 硬编码的 AES 密钥（`.data` 段明文）

| 偏移 | 值 | 用途 |
|---|---|---|
| `0x3046` | `Hml.5Fe=DatdYTUp` | DCC AES key（`DccCipher.F_KEY`） |
| `0x3057` | `iT4VvYW1DfAc6LdqJw0hA1` | TapConnect APP_KEY（`TapConst.RELEASE_APP_KEY`） |
| `0x307f` | `yUo.6Fe=Dytd` | AES IV（`DccCipher.F_IV`） |
| `0x308c` | `uJTKTRol5N9YolkiCPqlI5` | TapConnect APP_SECRET（`TapConst.RELEASE_APP_SECRET`） |

### 自定义签名字母表（`.rodata + 0x1d2`）

```
0123456987.=qwertyuiopasdfghjklzxcvbnm+-QWERTYUIOPASDFGHJKLZXCVBNM!@#$%^&*()
```

86 个字符，顺序被打乱（注意 `0123456987` 不是 `0123456789`）。
这是 `checkSign` / `verify` 用的编码表。

## 3.2 `libheytap_tapconnect_cipher.so`（14 KB）

同结构，但**密钥不同**：

| 偏移 | 值 | 用途 |
|---|---|---|
| `.data+0x0ae` | `Hml.8Fe=DatdYThp` | TapConnect AES key（注意是 **8** 不是 5） |
| `.data+0x0bf` | `iT4VvYW1DfAc6LdqJw0hA1` | 同上 APP_KEY |
| `.data+0x0d6` | `Hml.8Fe=DatdYThp` | IV |
| `.data+0x0e7` | `uJTKTRol5N9YolkiCPqlI5` | APP_SECRET |

其他字符串：

```
CIPHER_KEY
MCS2.0_CIPHER_ALGO        ← MCS 2.0 加密算法标识
com/heytap/connect/cipher/CipherAlgoNative
com/heytap/connect/cipher/RSAUtil
com/heytap/connect/cipher/AESUtil
```

**→ 两个 .so 是同一套代码的两份，密钥差一个字符（`5` vs `8`）。**

## 3.3 Java 侧对应类

`com/oplus/dcc/cipher/DccCipher.java`：

```java
private static final String F_IV  = "yUo.6Fe=Dytd";
private static final String F_KEY = "Hml.5Fe=DatdYTUp";
```

`com/heytap/connect/TapConst.java`：

```java
public static final String RELEASE_APP_KEY    = "iT4VvYW1DfAc6LdqJw0hA1";
public static final String RELEASE_APP_SECRET = "uJTKTRol5N9YolkiCPqlI5";
```

**→ native 和 Java 层使用的是同一套硬编码密钥，没有"藏得更深"。**

## 3.4 对之前解不开问题的意义

### olc 的 `a9/r.java` host（XOR 0x08 → Base64 → AES/GCM）

用了 `DccCipher` 的 key/iv 试过，**仍然解不开**。原因：

- 那串东西 XOR 0x08 后不是合法 Base64 密文结构
- 216 字节的长度对不上 GCM 的 tag 要求
- 可能是**构建时由 flavor 改写**，或**这部分代码在 release 是死代码**

### 但 native 层的确解出了有价值的东西

| 解出 | 价值 |
|---|---|
| RSA-1024 公钥 | 用于加密「授权证书」/「设备绑定」，只能加密不能解密 |
| 4 个 AES 密钥 | 本地数据加密（DccCipher）、TapConnect 通信加密 |
| 签名字母表 | 能还原 `checkSign` 的算法 |

### 一个重要判断

**这些密钥全是硬编码在 APK 里的**，意味着：

1. **本地数据加密可逆**（任何人拿到 APK 都能解）
2. **但传输层的密钥只有公钥在设备上**，私钥在服务器 → **抓包拿到的密文，没有私钥解不开**
3. `checkSign` 用过打乱的 86 字符表，但**表在 APK 里** → 同样可逆推

---

# 四、三部分结论汇总

## 4.1 DAG 任务编排

| 能力 | 说明 |
|---|---|
| 远程下发 SQL | ✅ 任意 SQL，字符串拼接无防护 |
| 远程下发 Python | ✅ 只能调 APK 内置 module，但 module 内部能力开放 |
| 数据外流 | ✅ 通过 S3Upload / CubeFsUpload |
| 执行时机 | cron + 充电/网络/息屏/温度/存储约束 |
| 拓扑控制 | upstream / downstream 依赖 |
| 签名校验 | `checkSign` + 自定义字母表（表在 APK 里，可逆） |

## 4.2 事件清单

**7 大类**：

1. 系统埋点（21 种 `/v1/stat/*` + `/v3_1/dcs/*`）
2. 应用生命周期（6 种）
3. **网络事件（22 种，含 `DNS_START/DNS_END` 上报域名+IP）**
4. 训练流程
5. 推荐行为（5 种 label）
6. 捐赠数据（3 类表）
7. 端侧推理/训练结果

**最值得注意**：`DNS_END` 会把「你访问了哪个域名 + 解析出什么 IP」一起上报。
**即使 AdGuard 拦住了，拦截动作本身也是数据。**

## 4.3 native 加密

| 项 | 结果 |
|---|---|
| RSA-1024 公钥 | ✅ 已完整还原（+0x38 混淆） |
| DCC AES key/iv | ✅ `Hml.5Fe=DatdYTUp` / `yUo.6Fe=Dytd` |
| TapConnect AES key | ✅ `Hml.8Fe=DatdYThp`（差一个字符） |
| APP_KEY / SECRET | ✅ `iT4VvYW1DfAc6LdqJw0hA1` / `uJTKTRol5N9YolkiCPqlI5` |
| 签名字母表 | ✅ 86 字符自定义表 |
| olc 那串 host | ❌ 仍解不开（非标准封装） |

**结论**：native 层没有"更高的安全等级"，只是把 Java 层硬编码的字符串搬到了 .so 里。
**唯一真正不可逆的是 RSA 私钥（在服务器）。**

---

# 五、对黑名单的影响

**没有新增域名**（DAG/Python/native 都不直接出网，最终都走埋点通道）。

但有一个重要的补充认知：

> **`DNS_END` 事件会上报"你尝试解析的所有域名 + IP"。**
> 这意味着 AdGuard 的拦截日志，**OPPO 服务端也有一份（通过埋点）。**
> 删掉 AdGuard 日志没用，因为拦截动作已经被上报了。

这条值得单独记一笔，见下方「新增建议」。
