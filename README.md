# ColorOS 14 隐私审计（一加 8T）

对一加 8T（ColorOS 14）出厂系统应用做隐私安全审计：看有没有埋点、收集什么、发到哪儿，
最终产出可用的 DNS 黑名单（AdGuard Home）。

## 当前状态

- ✅ **第一轮：全量快扫完成**（2026-11-05）→ 见 [`report-phase1-quickscan.md`](report-phase1-quickscan.md)
- ✅ **第二轮：埋点四件套精扫完成**（2026-11-05）→ 见 [`report-phase2-telemetry-deepdive.md`](report-phase2-telemetry-deepdive.md)
- ✅ **第三轮：短信/位置/相册数仓归属澄清**（2026-11-05）→ 见 [`report-phase3-sms-location-album.md`](report-phase3-sms-location-album.md)
- ✅ **第四轮：找到捐赠方**（2026-11-05）→ 见 [`report-phase4-donor-quicksearchbox.md`](report-phase4-donor-quicksearchbox.md)
- ✅ **第五轮：数据用途与去向**（2026-11-05）→ 见 [`report-phase5-purpose-and-destination.md`](report-phase5-purpose-and-destination.md)
- ✅ **第六轮：剩余未挖面积盘点**（2026-11-05）→ 见 [`report-phase6-remaining-surface.md`](report-phase6-remaining-surface.md)
- ✅ **第七轮：HTTPDNS + 端侧训练**（2026-11-05）→ 见 [`report-phase7-httpdns-and-training.md`](report-phase7-httpdns-and-training.md)
- ✅ **第八轮：差分隐私 + 模型文件 + 进程架构**（2026-11-05）→ 见 [`report-phase8-dp-and-processes.md`](report-phase8-dp-and-processes.md)
- ✅ **第九轮：DAG 编排 + 事件清单 + native 加密**（2026-11-05）→ 见 [`report-phase9-dag-events-native.md`](report-phase9-dag-events-native.md)
- 📖 **术语表**：[`glossary.md`](glossary.md) —— DCS/DCC/CDO/dwd/dws/DUID/ONEID 等全部缩写
- ⬜ 抓包验证（SNI 看真实域名）
- ⬜ 隐私政策条文对照

## 🚨 第九轮的重磅发现

### 1. 云端可编程：能下发任意 Python 和任意 SQL

`TaskInfo { script, scriptType }`，`scriptType` 3 = **Python**：
```json
{"module": "lr_train.train_lr", "func": "train", "param": "..."}
```
→ `pyvm_enter.py` 用 `importlib.import_module()` + `getattr()` 执行。
加上 `DbConsumer` 的任意 SQL 读写 + `S3Upload`/`CubeFsUpload` → **完整的数据外流能力**。

`s4/w.java:158` 直接 `rawQuery(getScript())`，**SQL 字符串拼接无任何防护**。

### 2. ⚠️ DNS 查询本身被上报

`t1/c.java` 实现 OkHttp EventListener，`DNS_END` 事件：
```java
hVar.a(DNS_END, K(call), domainName, inetAddressList);
//                        ↑ 域名      ↑ 解析出的 IP
```
**→ 你尝试访问的每个域名 + 解析 IP 都进埋点。拦截动作本身也是数据。**

### 3. native 加密全部解开

**RSA-1024 公钥**（`.rodata+0x1124`，每 4 字节 int32 +0x38 后取低8位）：
```
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDSKXcrn/ZitSsMO8tIVieDy2K62V9cv+dGEF53nT3jDgGe2OugVEoWpLyNqiNqUlFtc5K8eKiQIQTZyGzP4fz87FSRilF/sv61cpROa1fnrzvfl+eG9hVzYXTpPt9vdAgRyWxTlwU+Xcqm/Xch9uNh9scaN6b7T2VumgZjGNK6FQIDAQAB
```

| 密钥 | 值 |
|---|---|
| DCC AES key | `Hml.5Fe=DatdYTUp` |
| DCC AES iv | `yUo.6Fe=Dytd` |
| TapConnect AES key | **`Hml.8Fe=DatdYThp`**（注意是 8） |
| APP_KEY | `iT4VvYW1DfAc6LdqJw0hA1` |
| APP_SECRET | `uJTKTRol5N9YolkiCPqlI5` |
| 签名字母表 | `0123456987.=qwerty...`（86 字符自定义） |

**两个 .so 是同一套代码，密钥差一个字符（5 vs 8）。native 没有更高安全级别。**
olc 的 `a9/r.java` host 仍解不开（非标准封装，可能构建时改写）。

## 24h 上报的是什么？—— **四个整数，不是样本**

`fe_emb.py:get_fe_feature_info()` 只返回 `count(*)`：
```json
{"item_all_cnt": N, "user_cnt": N, "item_label_cnt": N, "item_label1_cnt": N}
```
本机 SQLite（`fe_user/item_feature_embedding`）存的是完整特征 + 标签，**但明细不上传**。

## 差分隐私现状

| 项 | 状态 |
|---|---|
| DP-SGD 代码 | ✅ 完整（`dp_sgd.py`：裁剪 + 高斯加噪 + σ 反推） |
| **当前配置** | ❌ **`fl_tasks.json` 里 `do_dp: false`** |
| FedAvg | 各端本地训、只传模型权重、服务器取平均 |
| 模型文件 | `.mnn` / `.snapshot`，几十万个 float 的参数矩阵 |
| 传梯度吗 | ❌ 无通道 |

## 进程架构

| 进程 | Service |
|---|---|
| 主 | 统计/数仓/上传 |
| `:train` | `RemoteTrainService`（exported=false） |
| `:infer` | `RemoteInferService` |
| `:worker` | `DccRemoteWorkerService`（DAG） |

训练的 `DccTunnel` 最终走主进程埋点通道 → **默认 DNS → AdGuard 可拦**。

## ✅ 两个关键问题已答复（第七轮）

### HTTPDNS：黑名单**仍然有效**

| 项目 | 结论 |
|---|---|
| 用不用 HTTPDNS | 用了，但**只给 OkHttp 那一条通道** |
| 埋点上报走哪 | `z7/n.java` 的 OkHttpClient —— **没装 HTTPDNS，走默认 DNS** |
| 抹掉 HTTPDNS 会回落吗 | **会**。`s6/b.java:211` 明确写了 `Dns.SYSTEM.lookup(hostname)` 兜底 |
| HTTPDNS 服务域名 | **`support.browser.heytapmobi.com`**（主）+ **`apisnd.heytapmobi.com`**（备） |
| 备用 IP（需防火墙拦） | `120.246.123.112` / `106.3.18.112` / `111.206.136.5` / `120.238.145.15` / `119.147.175.11` / `157.148.79.10` |

已加入黑名单 `01-telemetry-ads.txt`（现在 140 条，新增 9 条 HTTPDNS）。
IP 清单单独放在 `out/blocklist/04-httpdns-fallback-ips.txt`。

### 端侧训练：**默认加载，但需云端下发任务**

| 项目 | 结论 |
|---|---|
| 启用条件 | `TrainModule.c()` 只检查 **`arm64-v8a`**。没有用户开关 |
| 能否关闭 | ❌ 用户层面不能。只能断网/拦域名 |
| 训练时机 | 云端下发 `TaskInfo`（按 region/model/osVersion 定向）+ 充电/电量/温度/息屏/网络约束 |
| 输出什么 | 模型权重 + 混淆矩阵(TP/TN/FP/FN) + loss/acc/AUC + 样本数 |
| 传梯度吗 | ❌ **不传梯度**。传的是模型参数 |
| ⚠️ 差分隐私 | **`fl_tasks.json` 里 `do_dp: false`** —— 默认**不加噪** |
| 额外上报 | 每 24 小时报一次样本信息（即使不训练） |

## 这个包到底是什么

不是「埋点上报器」，而是一个**自带 Python 运行时的设备端数据平台**：

```
本地数仓（15 张表，最多存 180 天）
  + 端侧机器学习（性别/年龄/偏好，MNN 模型 + LR/DNN 训练代码）
  + 云端可编排（DAG 任务 + Python 脚本 + 任意 SQL 读写）
  + 身份归一（DUID ↔ OUID ↔ SSOID ↔ ONEID）
  + 隐私计算（donate 接收 + 匿名标签池 + DP-SGD 代码）
```

注：代码里到处是 `anonymity_tag_pool` / `DP-SGD` / `k_anonymity`。这套设计的意图是
**「数据不出设备，只出标签」**。但标签本身就是对用户的判定（性别/年龄/使用强度/生命周期），
而且**不可撤销、不可查看、不可删除**。

## ⚠️ 最重要的一条

`com.oplus.statistics.rom` 里的真实上报域名**不在 APK 里**，由 `mdp-appconf*.heytapdl.com` 动态下发。
静态扫描只能看到代码，**必须真机读**：

```bash
adb shell settings get system com.oplus.dcs.data.url
adb shell settings get system com.oplus.dcs.tech.url
adb shell settings get system com.oplus.dcs.eap.url
adb shell settings get system com.oplus.eap.release_host
```

**真机实测（2026-11-05）**：上述 6 个 key **全为 null**，
`oplus_customize_cta_user_experience = 0`（开关已关）。
→ 静态分析到此到顶，**下一步必须抓包看 SNI**。详见 phase3 报告。

## 短信会被看吗？—— 会，但不是我以为的那个包

`com.oplus.statistics.rom` **没有** `READ_SMS`，全 dex 搜 `content://sms` 零命中 —— 它只是仓库。
真正的读者是：**`com.heytap.quicksearchbox`（全局搜索）**，全 345 个包里**只有它一个**引用 DonateProvider。

- 短信：`content://sms/inbox`，列 `{_id, thread_id, type, address, body, date, read}`（**含正文**），
  增量读（`_id > lastId`），过滤 READ/UNREAD + 合法号码
- 相册：不读原始照片，问相册 App 要 `content://com.open.gallery.smart.provider/searchInfo`，
  拿 `{face_name, ocr, tags, address, lat/lng, ...}` —— OCR/人脸名是相册算好的
- 位置：**百度定位 SDK** 回调（不是系统 LocationManager），含 POI 名 + 位置描述

触发需四个开关全为真：`dccEnable && configEnable && userSettingEnable && personalEnable`
（最后一个是「个性化推荐」，**默认 true**）。

## 数据用途与去向（第五轮）

**三个用途，都有代码证据**：
1. **推荐系统输入** —— `c5/` 包（`StoreRecommendationService` / `ThemeRecommendationService`），
   请求体带 `tags`(int 标签) + `userprofile`(JSON) + `scene_id` + `page_id`
2. **用户画像** —— `com.oplus.dcc.ml.infer` 包，端侧轻量推理；`Tag{String,Long,Double}DuidTable` 存服务器下发标签
3. **DAU/留存/新用户统计** —— 但也有 `ads_doa_t4_inc_d` 表（`ads_` 前缀），说明**荐选和广告共用同一套行为数据**

**去向**：`*.cdo.heytapmobi.com` / `*.dc.*`（实时 JSON）→ 数据库 `mt_doa_dw`(v5) / `mt_dw`(v8)
→ Protobuf 分片上传 + 断点续传（`DummyDataProto$WriterCheckpoint`）。
`$app_id = "21000"` 是所有系统 App 埋点的统一标识。

**保留期**：本机最多 **180 天**（`u3/w.java:19-40` 七档：180/90/60/30/15/7/3 天，表按天滚动删，受容量阈值保护）

**PreciseControlRule**：服务端可对每个 appId+eventId 配采样比例和间隔（降本手段，也能远程调采集强度）

## 关掉开关能停多少？

唯一的开关是 `oplus_customize_cta_user_experience`（设置→关于手机→用户体验改进计划）。
代码里 `return i10 == 1;` —— 只有明确设成 1 才算开。
**但关掉后仍继续跑的**：应用清单、前后台 Activity 记录（含 URI 参数）、设备指纹、WiFi SSID。
只有内核日志（关即删文件）和部分 DCS 事件会停。
短信/位置/相册数仓本身不受开关控制，但那是**捐赠接收**，不是主动采集（见 phase3）。

## 快速拿结果

**黑名单（直接用这个）**：
```
out/blocklist/01-telemetry-ads.txt          # 141 条，埋点/广告/画像/埋点配置/★HTTPDNS
out/blocklist/02-caution.txt                # 185 条，功能相关，屏蔽会掉功能
out/blocklist/00-wildcard-tier-a.txt        # 通配版 ||domain^
out/blocklist/04-httpdns-fallback-ips.txt   # ★ HTTPDNS 备用 IP（DNS 层拦不住，需防火墙）
out/blocklist/05-manual-additions.txt       # 手补域名（XOR 编码的静态扫描抓不到）
```

## 样本

- 原始包：`/home/admin/Downloads/app_backup.zip`（3.1 GB）
- 解压位置：`/tmp/app_backup/`（4.9 GB，345 个 APK，重启会清空）
- 索引：`out/apk-index.json`

> ⚠️ zip 内文件名是 UTF-8 但没设 GP-Bit 11 标志，用 `unzip` 会按 GBK 解码成乱码。
> 必须用 Python `zipfile` 解（脚本见 `scripts/`，或参考下方命令）。

## ⚠️ 结论的局限

**本轮只做静态扫描，没有反编译。** 所以：

- ✅ 可以说："这个包里出现了这些域名"
- ❌ 不能说："这个包运行时一定请求这些域名"（可能是死代码 / 备用地址 / 测试环境）
- ❌ 不能说："关掉开关就真的不上报了"（只找到 key，没验证读取点和实际行为）

所有需要反编译/抓包才能确认的结论，报告里都标了「待验证」。

## 目录结构

```
scope-proposal.md              研究范围论证（签名分组、排除规则、候选清单）
report-phase1-quickscan.md     第一轮快扫报告（345 包全量）
report-phase2-telemetry-deepdive.md  第二轮精扫报告（埋点四件套反编译）
out/
  apk-index.json               345 包的签名者/体积/entry 数
  hosts-clean.json             分类清洗后的域名（vendor 568 / thirdparty 8067）
  profiles.json                每包画像
  privacy-toggles.json         隐私政策 URL + 开关 key
  scan/<pkg>.json              每包原始扫描结果
  blocklist/                   黑名单输出
  text/                        文本提取缓存
scripts/
  scan_apk.py                  快扫主程序（需 /tmp/app_backup 就位）
  aggregate.py                 域名聚合
  refine.py                    主机名清洗 + 厂商域名判定
  build_blocklist.py           黑名单分级
  build_profiles.py            每包画像
  mine_privacy.py              隐私政策 + 开关 key 挖掘
  extract_text.py              文本提取（调试用，很慢）
```

## 复现

```bash
# 1. 解压（务必用 Python，别用 unzip）
python3 - <<'EOF'
import zipfile, os
dst = "/tmp/app_backup"; os.makedirs(dst, exist_ok=True)
z = zipfile.ZipFile("/home/admin/Downloads/app_backup.zip")
for i in z.infolist():
    if i.filename.endswith(".apk"):
        with z.open(i) as s, open(os.path.join(dst, i.filename.split("/")[-1]), "wb") as o:
            while (c := s.read(1 << 20)): o.write(c)
EOF

# 2. 建索引 + 快扫（约 25 分钟 / 4 核）
python3 /tmp/idx2.py                   # 或参考 scripts 下 apk-index 生成逻辑
python3 scripts/scan_apk.py

# 3. 聚合 + 清洗 + 出黑名单
python3 scripts/aggregate.py
python3 scripts/refine.py
python3 scripts/build_blocklist.py
python3 scripts/build_profiles.py
python3 scripts/mine_privacy.py        # 约 15 分钟
```

## 关键结论速览

1. **埋点高度集中**：`com.oplus.statistics.rom` + `nearx` + `olc` + `onetrace` 是统一入口，
   140+ 个包都引它 → 掐域名就够，不用逐 App 处理
2. **上报路径**：`/v1/stat/*` 和 `/v3_1/dcs/*`，含 `appList`（已装应用列表）、`install`、`dau` 等
3. **域名主战场**：`*.cdo.heytapmobi.com` / `epoch.*` / `*.ads.*` / `bot-*` / `asdt*`
4. **异常发现**：OPPO 系统 App 里混了**百度定位**（浏览器/搜索/小布助手/信息），
   浏览器和快应用里还有**华为 HMS**（说明是移植来的）
5. **AOSP 组件被改过**：settings/systemui/mms/contacts/phone/downloads 全挂了 OPPO 埋点
6. **开关存在但不等于有效**：85 个包有开关 key，但关掉后是否真停发，需要反编译或抓包验证

## 第二轮精扫结论（已反编译验证）

1. **`com.oplus.statistics.rom` 是设备级埋点机器**：
   - 特权权限：`READ_PRIVILEGED_PHONE_STATE`、`QUERY_ALL_PACKAGES`、`PACKAGE_USAGE_STATS`、后台定位
   - 用 ColorOS 私有 API `colorGetImei` 读 **IMEI**（普通 App 拿不到）
   - 自己采的：**已装应用+安装时间+是否用过**、**前后台 Activity+URI 参数**、**设备指纹**、**WiFi SSID**、**内核日志**
   - 只存不采的：短信/位置/相册（靠 `DonateContentProvider` 接收，见 phase3 报告）
2. **`mdp-appconf*.heytapdl.com` 是埋点配置下发总入口** → 真实上报域名不在 APK 里
3. **`olc` 权限比统计还狠**：申请了 **微信 XLog 日志读取权限**（`com.tencent.mm.permission.MOVE_XLOG`），
   44 个采集任务含 **PCM 原始音频 / tcpdump 抓包 / hprof 堆转储**
4. **`onetrace` 不联网**，通过 AIDL 交给 statistics.rom 上传；采集含**应用切换序列+位置+按 UID 流量**
5. **开关是单向的**：关掉 `oplus_customize_cta_user_experience` 只停内核日志和部分 DCS 事件，
   **应用清单/前后台/短信/位置/相册数仓照常跑**
