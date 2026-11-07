# ColorOS 14 隐私审计（一加 8T）

对一加 8T（ColorOS 14）出厂系统应用做隐私安全审计：看有没有埋点、收集什么、发到哪儿，最终产出可用的 DNS 黑名单（AdGuard Home）。

---

## 一、研究进度总览

**基本研究已全部完成**（2026-11-05 ~ 2026-11-06），共 15 轮 + 5 次补挖，覆盖 345 个 APK 中的重点分组。

| 轮次 | 内容 | 报告 |
|---|---|---|
| 1 | 全量快扫（345 包） | [phase1](report-phase1-quickscan.md) |
| 2 | 埋点四件套精扫（statistics/nearx/olc/onetrace） | [phase2](report-phase2-telemetry-deepdive.md) |
| 3 | 短信/位置/相册数仓归属澄清 | [phase3](report-phase3-sms-location-album.md) |
| 4 | 找到捐赠方（quicksearchbox） | [phase4](report-phase4-donor-quicksearchbox.md) |
| 5 | 数据用途与去向 | [phase5](report-phase5-purpose-and-destination.md) |
| 6 | 剩余未挖面积盘点 | [phase6](report-phase6-remaining-surface.md) |
| 7 | HTTPDNS + 端侧训练 | [phase7](report-phase7-httpdns-and-training.md) |
| 8 | 差分隐私 + 模型文件 + 进程架构 | [phase8](report-phase8-dp-and-processes.md) |
| 9 | DAG 编排 + 事件清单 + native 加密 | [phase9](report-phase9-dag-events-native.md) |
| 9b | A 组剩余 4 包（logkit/crashbox/postman/nhs） | [phase9b](report-phase9b-a-group-remaining.md) |
| 10 | B 组 互联网服务（18 包） | [phase10](report-phase10-b-group-internet-services.md) |
| 11 | C 组 AI/感知（17 包） | [phase11](report-phase11-c-group-ai-perception.md) |
| 12 | D 组 手机管家/安全（10 包） | [phase12](report-phase12-d-group-security.md) |
| 13-E | E 组 运营商/合规 | [phase13-e](report-phase13-e-group-carrier-compliance.md) |
| 13-F | F 组 相机/相册（v3） | [phase13-f](report-phase13-f-camera-gallery.md) |
| 14-G | G 组 系统治理/诊断（8 包） | [phase14](report-phase14-g-group-system-governance.md) |
| 14b | G-2 定位 6 SDK + 融合算法深挖 | [phase14b](report-phase14b-location-dw-deepdive.md) |
| 15-H | H 组 短信/电话/联系人/天气/号码库（8 包） | [phase15](report-phase15-h-sms-phone-weather.md) |
| 15b | H-2 通讯录联系人是否触发号码识别 | [phase15b](report-phase15b-contacts-number-recognition.md) |

**术语表**：[`glossary.md`](glossary.md) —— DCS/DCC/CDO/dwd/dws/DUID/ONEID 等全部缩写。

**仍未完成**（需要真机/网络环境，静态分析做不了）：
- ⬜ 抓包验证（SNI 看真实域名）
- ⬜ 隐私政策正文比对（需抓 `muc.heytap.com`）

---

## 二、核心结论（按重要性）

### 🔴 1. 埋点四件套是统一入口，掐域名就够

`com.oplus.statistics.rom` + `nearx` + `olc` + `onetrace`，**140+ 个包**都引用它。
不需要逐 App 处理，拦掉主域名即可覆盖绝大部分采集。

**`com.oplus.statistics.rom` 不是简单上报器，而是自带 Python 运行时的端侧数据平台：**

```
本地数仓（15 张表，最多存 180 天）
  + 端侧机器学习（性别/年龄/偏好，MNN 模型 + LR/DNN 训练）
  + 云端可编排（DAG 任务 + Python 脚本 + 任意 SQL 读写）
  + 身份归一（DUID ↔ OUID ↔ SSOID ↔ ONEID）
  + 隐私计算（donate 接收 + 匿名标签池 + DP-SGD 代码）
```

**它采什么**（自己采，不靠别人）：
- 已装应用 + 安装时间 + 是否用过
- 前后台 Activity + URI 参数
- 设备指纹、WiFi SSID、内核日志
- 用私有 API `colorGetImei` 读 **IMEI**

**它不采但接收**（通过 `DonateContentProvider`）：短信、位置、相册 —— 详见下方第 4 条。

### 🔴 2. 云端可下发任意 Python 和任意 SQL（第九轮最重磅）

`TaskInfo { script, scriptType }`，`scriptType = 3` 表示 Python：

```json
{"module": "lr_train.train_lr", "func": "train", "param": "..."}
```

→ `pyvm_enter.py` 用 `importlib.import_module()` + `getattr()` 执行。
配合 `DbConsumer` 的任意 SQL 读写 + `S3Upload`/`CubeFsUpload`，构成**完整数据外流能力**。

`s4/w.java:158` 直接 `rawQuery(getScript())`，**SQL 字符串拼接无任何防护**。

### 🔴 3. DNS 查询本身被上报

`t1/c.java` 实现 OkHttp `EventListener`，在 `DNS_END` 事件里：

```java
hVar.a(DNS_END, K(call), domainName, inetAddressList);
//                        ↑ 域名      ↑ 解析出的 IP
```

**你尝试访问的每个域名 + 解析 IP 都进埋点。拦截动作本身也是数据。**

### 🔴 4. 短信/相册/位置的真实读者是全局搜索，不是统计包

`com.oplus.statistics.rom` **没有** `READ_SMS`，全 dex 搜 `content://sms` 零命中 —— 它只是个仓库。

真正的读者是 **`com.heytap.quicksearchbox`（全局搜索）**，全 345 包里**只有它引用 DonateProvider**：

| 数据 | 来源 | 字段 |
|---|---|---|
| 短信 | `content://sms/inbox` | `{_id, thread_id, type, address, body, date, read}` —— **含正文** |
| 相册 | `content://com.open.gallery.smart.provider/searchInfo` | `{face_name, ocr, tags, address, lat/lng}` |
| 位置 | **百度定位 SDK 回调**（非系统 LocationManager） | 含 POI 名 + 位置描述 |

触发需要四个开关**同时**为真：`dccEnable && configEnable && userSettingEnable && personalEnable`。
最后一个是「个性化推荐」，**默认 true**。

### 🔴 5. 相册「文字识别」会上云，且国行开关拦不住

**它不在相册里**，是系统服务 `com.coloros.ocrservice`（SDK 由 `com.oplus.aiunit` 提供），相册只通过 AIDL 调用。

云端端点（Base64 混淆）：
```
https://aiscan.ocloud.heytapmobi.com/sceneocr/scan-web/v1/ocr_recognize
https://airecognition-ocr-cn.heytapmobi.com/ai_screen_recognition/api/v1/upload
```

上传：**JPEG 质量 100 + IMEI + 机型 + 语言**。

**国行永远"已联网"**：
```java
canAccessInternet() = isDomestic() || !isNeedApplyPrivacy(...)   // 国行短路为 true
```

所以相册设置里的「联网权限」**不控制** OCR 上传。

**六个入口的真相**（详见 phase13-f）：

| 入口 | 引擎 | 联网 |
|---|---|---|
| ① 照片页长按选字（拖拽框选→复制） | 本地 `ocr_ar` 模型 | ❌ |
| ② 照片页「识别文字」按钮 | 本地优先 | ⚠️ 模型缺失才退云端 |
| ③ 照片页「超级文本编辑」→ 识别文字 | **云端优先**（硬编码） | ✅ |
| ④ 扫一扫 / 取字 | **云端优先** | ✅ |
| ⑤ 后台文本搜索索引（OCR_SCAN） | 本地 | ❌ |
| ⑥ 编辑 → AI 证件照 | 云端（三道弹窗） | ✅ |

`album-idcard.heytapmobi.com` **不是身份证识别**，是「AI 证件照」的人像抠图服务（`/v2/idcard/getToken` + `/idCardAnalysis`），**不提取证件文字**。

### 🔴 6. 数字健康上传已安装应用列表 + TLS 校验被禁用

`com.coloros.digitalwellbeing`：
- 上传**已安装应用包名列表**到 `api.open.oppomobile.com/security/app-summarys/type`（每批 50 个）
- **重大安全缺陷**：`s1/a.java` 的 `C0230a` TrustManager
  ```java
  cert.verify(cert.getPublicKey());   // 自签恒真
  } catch (Throwable ignored) { }     // 异常全吞
  ```
  → **TLS 校验形同虚设，可被 MITM**

关掉「屏幕用时」可停正常路径上传，但上传函数本身**没有开关检查**（`WellBeingProvider.call()` 只校验 `OPPO_COMPONENT_SAFE` 权限）。

### 🔴 7. 网络定位：6 个 SDK，三家并行 + 算法融合

**不是 3 个，是 6 个**（APK 自带隐私声明 HTML 明确列出）：

| # | SDK | 收集 |
|---|---|---|
| 1 | 腾讯定位 SDK | WiFi/基站/蓝牙列表 |
| 2 | 百度 NLP Vendor SDK | 同上 + 离线定位 |
| 3 | 高德系统级网络定位 | 同上 |
| 4 | 腾讯 3D 地图辅助定位 | GPS |
| 5 | 千寻位置 NtripClient | GPS（RTK 车道级） |
| 6 | 腾讯 NtripClient RTK | GPS |

**架构：三家并行上报 → 结果全部进融合算法 → 上报融合结果**

```java
// wb/j.java
locationProviderMask = 599;   // 1(腾讯)|2(百度)|4(高德)|16|64(百度离线)|512
geocodeProviderMask  = 4;     // 逆地理只有高德
```

融合算法 `NlpFusionAlgo_v1.2`（`vb/c.g()`）：
1. 有 HIGHPRECISION → 直接用
2. 有缓存 GNSS → 直接用
3. **3 家都在 → 两两算距离，选最一致的 2 家**
4. 置信度差 **≥2** → 取高的；**<2** → 坐标取中点
5. 置信度是**动态学习**的（`vb/a.f()`，按历史精度打分）

腾讯上传字段（`lbs.map.qq.com/loc`）：
```
wifis[{mac,rssi,ts}] / cells[{mcc,mnc,lac,cellid,rss}] / bles[{mac,major,minor,rssi,time}] / wlan{mac,rssi,ssid}
```

**`wlan.ssid` 常常是「张三家的网」「XX公司-5G」这类带身份的信息。**

### 🔴 8. `com.ted.number` 会联网（推翻早期结论）

**本地库查不到就把号码上传到 `tel-num-cn.heytapmobi.com/v2/proxy/phoneRec`。**

5 个端点：
```
/v2/proxy/phoneRec      ← 号码识别（上传号码）
/v2/proxy/phoneMark     ← 号码标记
/v2/proxy/phoneCorrect  ← 号码纠错
/v3/proxy/phoneLib      ← 本地库增量下载
/v2/proxy/config        ← 配置
```

**混合模式，不是纯离线**：本地库每天增量下载（`LocalDicUpdateJob`，86400000ms），查不到走云端。

**两个独立开关**：

| 开关 | 默认 | 作用 |
|---|---|---|
| `NUMBERRECOGNITION_SWITCH`（Global） | **1（开）** | 总开关，含本地库 |
| `KEY_ONLINE_RECOGNIZE_SWITCH` / `UpdateStrangers` | **0（关）** | **云端查询** |

→ **出厂状态下云端查询默认关闭**，要用户手动开启「联网识别」。

**通讯录联系人也拦不住（电话侧）**：`OplusTedQuery` 只查本地黄页库，没有通讯录短路。
通讯录命中只在 `OplusCall.java:165` 把 `isYellowPageNumber = false`，**只影响是否显示黄页名**。

短信侧不触发，但靠的是**黑/白名单**判断，不是通讯录。

### 🟠 9. 短信打包了整套广告变现体系

`com.android.mms` 里 18 个端点（`np/g.java:initEnv()`）：
```
sms.ads.heytapmobi.com                    ← 短信广告主域
api.sms.heytapmobi.com/ads-activate       ← 广告激活
cl-data.ads.heytapmobi.com/upload/set12   ← 广告数据上传
data.sms.heytapmobi.com                   ← 数据上报
commerce-ads.wanyol.com/api/k/g           ← 电商广告
push1.teddymobile.cn                      ← TeddyMobile
```

开关 `smart_message_cardview_switch` + 四重门禁。
**短信内容本身不上传**，上传的是「你看了哪个广告、点了什么」。

### 🟠 10. 隐私计算：代码完整但**默认没开**

| 项 | 状态 |
|---|---|
| DP-SGD 代码 | ✅ 完整（裁剪 + 高斯加噪 + σ 反推） |
| **当前配置** | ❌ `fl_tasks.json` 里 **`do_dp: false`** |
| FedAvg | 各端本地训，只传模型权重 |
| 传梯度吗 | ❌ 无通道 |
| 24h 上报内容 | **四个整数**（`item_all_cnt` / `user_cnt` / `item_label_cnt` / `item_label1_cnt`），不是样本明细 |

### 🟠 11. native 加密全部解开，没有更高安全级别

| 密钥 | 值 |
|---|---|
| DCC AES key | `Hml.5Fe=DatdYTUp` |
| DCC AES iv | `yUo.6Fe=Dytd` |
| TapConnect AES key | `Hml.8Fe=DatdYThp`（注意是 8） |
| APP_KEY | `iT4VvYW1DfAc6LdqJw0hA1` |
| APP_SECRET | `uJTKTRol5N9YolkiCPqlI5` |

RSA-1024 公钥在 `.rodata+0x1124`（每 4 字节 int32 +0x38 后取低 8 位）。
**两个 .so 是同一套代码，密钥只差一个字符（5 vs 8）。**

### 🟢 12. 干净的组件

| 包 | 说明 |
|---|---|
| `com.oneplus.camera` 等 3 包 | **零业务域名**（37 个 ns.adobe.com 全是 XMP 命名空间） |
| `com.oplus.nhs` | **连 INTERNET 权限都没有**，纯本地 GNSS 统计 |
| `com.android.incallui` / `com.android.phone` | **零业务域名** |
| `com.android.providers.contacts` | **零业务域名**，纯本地存储 |
| `com.oplus.exsystemservice` | 只有 Google 广告 SDK 的死常量 |
| `com.qualcomm.location` / `com.android.location.fused` | 零域名 |
| `com.heytap.vip` / `accessory` | 0 个上报域名 |

### 🟡 13. 权限惊人但零联网的

| 包 | 危险权限 | 联网 |
|---|---|---|
| `com.oplus.athena` | REBOOT / MANAGE_USERS / SET_PROCESS_LIMIT | ❌ 零 |
| `com.oplus.battery` | KILL_UID / FORCE_STOP_PACKAGES / DEVICE_POWER | ❌ 零 |

> 💡 排查技巧：`strings` 扫到 623 个 `okhttp` 命中，逐个看全是
> `import okhttp3.internal.ws.RealWebSocket` 这类常量类 import，**不是真联网**。

### 🔴 14. `postmanservice` = OPPO 售后远程诊断通道

ASDT（After-Sales Diagnostic Tool），12 个服务器地址硬编码：
```
生产（国内）https://asdt-server5-cn.allawntech.com     ★
海外：fr / sg / in / us 各一
```

PC 下发 `start_catch_log` → `OlcHelper.sendLogCatch()` → 系统 Olc 抓日志 → 上传。
所有指令需**签名验证**（`protocol/common/BaseSignProtocol`）。

权限：`FORCE_STOP_PACKAGES` / `DELETE_PACKAGES` / `MANAGE_APP_OPS_MODES` / `REBOOT` / `WRITE_EMBEDDED_SUBSCRIPTIONS` …

**合法售后功能，但一旦签名密钥泄露 = 远程控制通道。**

---

## 三、域名与黑名单

### 快速拿结果

**✅ 推荐：直接用 `final/` 目录**（按隐私敏感度 + 副作用双维度重新分组）

```
out/blocklist/final/10-tier-a-privacy.txt   # ★★★ 35 条，直接启用，副作用极小
out/blocklist/final/11-tier-b-optional.txt  # 13 条，看需求（AI证件照/售后/问卷）
out/blocklist/final/12-tier-c-caution.txt   # 全注释，功能相关，自己判断
out/blocklist/final/13-never-block.txt      # 全注释，“为什么不该拦”
out/blocklist/final/14-verify-first.txt     # 全注释，需真机查 Settings
out/blocklist/final/README.md               # ★ 决策说明，每个域名注明“拦了会怎样”
```

> **AdGuard 里只加载 `final/` 下的 10 和 11**，老文件留作参考。

**历史文件（可追溯，不建议直接加载）**：

```
out/blocklist/01-telemetry-ads.txt          # 195 条，A+B+C 组汇总（混了功能域名）
out/blocklist/02-caution.txt                # 186 条，功能相关，屏蔽会掉功能
out/blocklist/00-wildcard-tier-a.txt        # 通配版 ||domain^
out/blocklist/04-httpdns-fallback-ips.txt   # ★ HTTPDNS 备用 IP（DNS 拦不住，需防火墙）
out/blocklist/05-manual-additions.txt       # 手补（XOR 编码的静态扫描抓不到）
out/blocklist/06-b-group-additions.txt      # B 组 39 条
out/blocklist/07-c-group-additions.txt      # C 组（AI画像/OCR/翻译）
out/blocklist/08-d-group-additions.txt      # D 组（碎屏险/密码本）
out/blocklist/09-e-f-group-additions.txt    # ★ E/F 组（相册 OCR + 入网备案）
```

### 域名主战场

| 域族 | 用途 |
|---|---|
| `*.cdo.heytapmobi.com` / `*.dc.*` | 统计流水（实时 JSON） |
| `epoch.*` | 合并上报表 |
| `*.ads.heytapmobi.com` / `adx.*` | 广告投放 / 程序化竞价 |
| `bot-*` / `nearx.*` | AI 助手 / 场景推荐 / 用户画像 |
| `*.ocloud.heytapmobi.com` | OCloud 服务（OCR / AI 修复 / 分享） |
| `asdt*` | 售后诊断 |
| `mdp-appconf*.heytapdl.com` | **埋点配置下发总入口** |

### HTTPDNS：黑名单**仍然有效**

| 项目 | 结论 |
|---|---|
| 埋点上报走 HTTPDNS 吗 | **不走**。`z7/n.java` 的 OkHttpClient 没装 HTTPDNS，走默认 DNS |
| 抹掉 HTTPDNS 会回落吗 | **会**。`s6/b.java:211` 有 `Dns.SYSTEM.lookup(hostname)` 兜底 |
| HTTPDNS 服务域名 | `support.browser.heytapmobi.com`（主）+ `apisnd.heytapmobi.com`（备） |
| 备用 IP（需防火墙） | `120.246.123.112` / `106.3.18.112` / `111.206.136.5` / `120.238.145.15` / `119.147.175.11` / `157.148.79.10` |

---

## 四、用户能关到什么程度

### 4.1 唯一的全局开关

`oplus_customize_cta_user_experience`（设置 → 关于手机 → 用户体验改进计划）
代码里 `return i10 == 1;` —— **只有明确设成 1 才算开**。

**关掉后仍继续跑的**：应用清单、前后台 Activity（含 URI 参数）、设备指纹、WiFi SSID。
只有内核日志和部分 DCS 事件会停。

### 4.2 各功能开关一览

| 目标 | 操作 | 效果 |
|---|---|---|
| 号码不上云 | 拨号/联系人 → 设置 → 关闭「智能识别陌生号码」 | 完全停止（含本地库） |
| 只关云端识别 | `UpdateStrangers = 0`（默认就是 0） | 保留本地库 |
| 智能短信卡片 | 信息 → 设置 → 关闭卡片视图 | 不显示广告卡片，普通短信正常 |
| 相册 OCR | **关不掉**，只能 DNS 拦 | 降级本地 |
| 屏幕用时 | 健康 App → 设置 → 关闭 | 停上传（正常路径） |
| 广告个性化 | 设置 → 隐私 → 广告与隐私 → 关闭 | 至少拿回 OAID 控制权 |

### 4.3 「关掉就真停了吗」的答案

**大部分不是。** 详见下方「结论的局限」。

---

## 五、方法论与经验（后续维护必读）

### 5.1 三次踩过的坑

| # | 坑 | 教训 |
|---|---|---|
| 1 | 看到「上传函数」就断定"会自动上传" | **必须追到调用方入口**，看有没有定时器/JobScheduler |
| 2 | 说"没有开关"，实际有三层 | **要查 UI 资源 + 存储键**（`res/xml/*.xml` 的 `android:key`），不能只看判断函数 |
| 3 | 说 `ted.number` "不联网" | **必须扫 dex 里的完整 URL 字符串**，不能只扫 `BuildConfig` 常量 |

### 5.2 判断"是否联网"的正确姿势

1. **扫 dex 完整 URL**：`strings classes*.dex | grep -oE "https?://[^\\s]+"`
2. **警惕常量类误报**：`import okhttp3.internal.ws.RealWebSocket` 这类不算联网
3. **追到最内层引擎选择**：如 `ocrWithPriority`（云）vs `ocr`（本地），中间层的 `z=true` 只是意图
4. **查 APK 自带隐私声明 HTML**：`assets/*privacy*.html` 是最权威的 SDK 清单来源
   （定位服务代码只扫到 3 家，官方声明列了 6 个）

### 5.3 工具链

```bash
# 单包体检（权限 + 域名 + URL）
python3 scripts/g_apk_survey.py <apk> <name>

# 批量分组
python3 scripts/g_survey_all.py  /tmp/g-apk    # G 组
python3 scripts/h_survey_all.py  /tmp/h-apk    # H 组
python3 scripts/a_survey_all.py  /tmp/a-apk    # A 组剩余

# 反编译
~/.openclaw/workspace/tools/jadx/bin/jadx -d out -j 4 --no-res app.apk
bash scripts/decompile_g.sh /tmp/g-apk /tmp/gref

# ⚠️ jadx 失败的用 apktool 出 smali
java -jar ~/.openclaw/workspace/tools/apktool.jar d -f app.apk -o smali/
```

### 5.4 jadx 已知失败点

| 方法 | 处理 |
|---|---|
| `wb/i.q()`（定位结果选择） | 必须 smali 还原 |
| `d4/v.P()`（号码查询主流程） | 必须 smali 还原 |
| `Xg0.a()`（AI 证件照预裁剪） | 未解 |

### 5.5 其他坑

- **zip 解压中文乱码**：zip 文件名 UTF-8 但未设 GP-Bit 11，`unzip` 会按 GBK 解。用 Python `zipfile`。
- **`cd x && cat >> memory/xx.md`** 会失败，先 `cd` 到 workspace 根。
- **`@Metadata(d1=...)` 长行**会撑爆 grep 输出，用 `python3 -c` 精确切片。
- **exec preflight**：`python3 - <<EOF` heredoc 或 `cd x && python3 y.py` 会被拒，必须先写到 .py 文件。
- **APK 文件名格式**：`中文名_包名.apk`，匹配用 `f.endswith("_" + pkg + ".apk")`。
- **大包 jadx 耗时**：相册 189MB → 4.6 万文件约 10 分钟，用 `nohup` 后台跑。

---

## 六、重要限制与待验证

### ⚠️ 最重要的一条：真实上报域名不在 APK 里

`com.oplus.statistics.rom` 的上报域名由 `mdp-appconf*.heytapdl.com` **动态下发**。
静态扫描只能看到代码，必须真机读：

```bash
adb shell settings get system com.oplus.dcs.data.url
adb shell settings get system com.oplus.dcs.tech.url
adb shell settings get system com.oplus.dcs.eap.url
adb shell settings get system com.oplus.eap.release_host
adb shell settings get system com.oplus.eap.cloud_storage_release_host_v3
```

**真机实测（2026-11-05）**：6 个 key **全为 null**，`oplus_customize_cta_user_experience = 0`（开关已关）。

### 其他待验证项（按包）

| 包 | 待验证 |
|---|---|
| 相册 | `ocr_ar` 本地模型是否始终可用（`adb logcat -s VersionUtils \| grep ocrStaticSupport`） |
| 数字健康 | `C0230a` TrustManager 是否真用于生产连接 |
| 耗电监控 | 实际上传域名（运行时下发） |
| 定位 | 三家 SDK 谁实际请求最多 |
| crashbox | `com.oplus.eap.release_host` 实际值 |
| 天气 | 界面 App 包名（system/app 预装，不在备份里） |

### 结论的局限

- ✅ 可以说"这个包里有这些域名"
- ❌ 不能说"运行时一定请求"（可能是死代码 / 备用地址 / 测试环境）
- ❌ 不能说"关掉开关就真不上报"（静态看不清运行时行为）

---

## 七、样本与复现

### 样本

- 原始包：`/home/admin/Downloads/app_backup.zip`（3.1 GB）
- 解压位置：`/tmp/app_backup/`（4.9 GB，345 个 APK，**重启会清空**）
- 索引：`out/apk-index.json`

```bash
# 解压（务必用 Python，别用 unzip）
python3 - <<'EOF'
import zipfile, os
dst = "/tmp/app_backup"; os.makedirs(dst, exist_ok=True)
z = zipfile.ZipFile("/home/admin/Downloads/app_backup.zip")
for i in z.infolist():
    if i.filename.endswith(".apk"):
        with i.open() as s, open(os.path.join(dst, i.filename.split("/")[-1]), "wb") as o:
            while (c := s.read(1 << 20)): o.write(c)
EOF
```

### 反编译产物（重启后需重建）

| 目录 | 内容 |
|---|---|
| `/tmp/jadx-out/` | 60+ 包（B/C/D 组等） |
| `/tmp/gref/out_*` | G 组 8 包 |
| `/tmp/hjadx/` | H 组（sms/weather/incallui/tednumber） |
| `/tmp/ajadx/` | A 组 4 包 |
| `/tmp/locsmali/` | 定位 smali（`wb/i.smali` 关键） |
| `/tmp/hsmali/` | ted.number smali |

### 复现脚本

```bash
python3 scripts/scan_apk.py       # 快扫（约 25 分钟 / 4 核）
python3 scripts/aggregate.py      # 域名聚合
python3 scripts/refine.py         # 主机名清洗 + 厂商判定
python3 scripts/build_blocklist.py
python3 scripts/build_profiles.py
python3 scripts/mine_privacy.py   # 约 15 分钟
```

---

## 八、目录结构

```
README.md                      本文（入口 + 全局结论 + 方法论）
scope-proposal.md              研究范围论证（签名分组、排除规则）
glossary.md                    术语表
report-phase1~15*.md           各轮详细报告
out/
  apk-index.json               345 包的签名者/体积/entry 数
  hosts-clean.json             分类清洗后的域名
  profiles.json                每包画像
  privacy-toggles.json         隐私政策 URL + 开关 key
  scan/<pkg>.json              每包原始扫描结果
  blocklist/                   各轮历史输出（01-09）
  blocklist/final/             ★ 最终版（10-14 + 决策说明）
scripts/
  scan_apk.py / aggregate.py / refine.py / build_blocklist.py
  build_profiles.py / mine_privacy.py / extract_text.py / build_index.py
  g_apk_survey.py              单包体检（通用）
  g_survey_all.py              批量 G 组
  h_survey_all.py              批量 H 组
  a_survey_all.py              批量 A 组剩余
  decompile_g.sh               批量反编译
  split_phase13.py             合并报告拆分
  build_final_blocklist.py     ★ 生成 final/ 最终黑名单（含来源校验）
```

---

## 九、历史版本说明

| 文件 | 状态 |
|---|---|
| `report-phase13-e-f-camera-gallery.md` | ⚠️ **已拆分为 E/F 两份，仅作历史版本追溯** |

拆分后：
- E 组 → `report-phase13-e-group-carrier-compliance.md`
- F 组 → `report-phase13-f-camera-gallery.md`（v3，已修正 v1 的多处错误，附录 A 有完整修正记录）

**F 组的三次修正**（教训价值高）：
1. v1：把「用户主动点识别」写成「默认/定时自动上传」—— 错
2. v2：修正为「仅主动触发」，但每写完就补丁，文档前后矛盾
3. v3：整体重写为系统性版本，附录 A 列出 7 条错误逐条对照

**G-2 定位的三次修正**：
1. v1：「随机分流」—— 错
2. v2：「三家并行只取高德」—— 仍错
3. v3：**三家并行 → 结果全部融合**（漏看 `xb/i.java` 生成 type=32）
