# 向 AdGuard 上报 `fxltsbl.com` —— 可直接提交的稿件

> 目标：把 `fxltsbl.com`（彩讯 Colyinfo DM 终端管理后端）加进 AdGuard 的反追踪/隐私列表。
> 本文件包含：提交地址、规则清单、两版报告正文（中文 / 英文）、以及提交前必须知道的三件事。
>
> **注意**：提交前请先看第 4 节「可能被拒的理由」。如果 AdGuard 拒了，不要意外，这不是材料不够，是列表政策不匹配。

---

## 1. 往哪儿提交

按优先级：

| # | 渠道 | 地址 | 适用 |
|---|---|---|---|
| 1 | **AdGuard Filters 上报工具**（官方唯一入口） | https://agrd.io/report | 主渠道，所有列表问题都走这里 |
| 2 | GitHub Issue（直接建） | https://github.com/AdguardTeam/AdGuardFilters/issues/new/choose | 上报工具进不去时的备选，需 GitHub 账号 |
| 3 | AdGuard DNS 支持 | https://adguard-dns.io/ | 只想让 AdGuard DNS 用户被保护，走这条 |

在 reporting tool 里：
- **Site / Service** 填 `fxltsbl.com`
- **Select a filter list** 选 **Spyware filter**（Tracking Protection 的实际文件路径是 `SpywareFilter/`）
- **Problem type** 选「Missing tracker / privacy-invasive request」

---

## 2. 规则清单（copy 到报告的「Suggested rules」框）

````
! Colyinfo (彩讯) DM terminal management backend — used by preinstalled
! com.coloros.regservice on OnePlus/OPPO ColorOS (mainland China builds, verified on OnePlus 8T / ColorOS 14)
||fxltsbl.com^
||a.fxltsbl.com^
||b.fxltsbl.com^
||auc.fxltsbl.com^
````

说明为什么这样写（这是 AdGuard 审核会关心的）：

- `||fxltsbl.com^` 已经覆盖全部子域，后面三条是冗余但不冲突（方便审核从日志里一眼对上）；
- **不要加 `$third-party`**。`SpywareFilter/sections/tracking_servers.txt` 的文件头写明 third-party 域名放这个文件、first-party 场景的子域放 `tracking_servers_firstparty.txt`；
  本场景是系统 App 直连自有应答域，无“第三方语境”可言，套 `$third-party` 反而可能不匹配；
- 参考文件里现成同类样本（Android 厂商遥测）：`||nmetrics.samsung.com^`、`||eu-stsdk.vivoglobal.com^`、`||umeng.com^`。

---

## 3. 报告正文

### 3.1 中文版（发 issue / 社区时用）

````markdown
### 域名
fxltsbl.com（含 a./b./auc. 子域）

### 归类
隐私追踪 / 遥测（非广告）—— 建议进 Spyware filter 的 tracking servers

### 背景

一加（OnePlus）8T / ColorOS 14 系统里预置了一个系统应用
`com.coloros.regservice`（APK 位于 `/my_bigball/app/RegService/RegService.apk`，
采用 OPPO 官方签名 `CN=AndroidTeam, O=Oplus`）。

该 APK 内含彩讯（Colyinfo / cn.richinfo.dm，SDK v4.0.7）的中移动 DM
（Device Management，终端管理）SDK，所有上报请求均发往 `*.fxltsbl.com`。

### 上报内容（静态逆向确认）

- 设备标识：IMEI1/2、IMSI1/2、ICCID1/2、MEID、WLAN MAC、蓝牙 MAC
- 完整已安装应用列表（含系统应用），以及每个应用的前台时长、启动次数、移动/WiFi 收发字节
- Wi-Fi 扫描列表（SSID / BSSID / RSSI）
- 基站信息（cellId / lac / RSRF / SINR，4G 与 5G × 双卡）
- 已配对蓝牙设备（名称 / UUID / MAC）
- 充电状态、传感器清单等设备指纹

### 接口清单

| 路径 | 用途 |
|---|---|
| `/sdkService?func=tsdk:postreglog` | 设备注册（50+ 字段） |
| `/sdkService?func=tsdk:postapplylog` | 应用使用数据 |
| `/sdkService?func=tsdk:posthblog` | 心跳（每次连带充电/蓝牙/网络/WiFi 列表） |
| `/TerminalConfigService/terminalConf?...` | 拉取全量配置 / 检查 SDK 更新 |
| `/wifiInfo?` | Wi-Fi 扫描列表 |
| `/bluetooth?func=tsdk:postBluetoothInfo` | 已配对蓝牙设备 |
| `/flowCollectService?func=tsdk:flowcollect` | 分时流量 |
| `/preInstalledApp?` | 预装应用列表 |

### 为什么应被拦截

1. 采集开关、采集频率、休眠时段**全部由服务端 `/TerminalConfigService/terminalConf` 下发**，终端用户无法控制；
2. 采集范围远超“终端管理”必要限度（应用使用明细 + Wi-Fi 周边 + 蓝牙配对 + 基站）；
3. 该 SDK 具备**从服务端下发并 `DexClassLoader` 加载代码**的能力（`patch.jar`，仅 MD5 校验），对隐私风险进一步放大；
4. 应用无 launcher 入口，用户无法在设置里感知其存在。

### 建议规则

（见第 2 节）
````

### 3.2 English version（AdGuard 团队主要看英文）

````markdown
### Domain
fxltsbl.com (incl. a./b./auc.)

### Category
Privacy-invasive telemetry (not advertising) — Spyware filter, tracking servers section

### Context

ColorOS 14 (OnePlus, mainland China builds) ships a preinstalled system app
`com.coloros.regservice` (`/my_bigball/app/RegService/RegService.apk`), signed with
OPPO's official platform certificate (`CN=AndroidTeam, O=Oplus`).

The APK embeds Colyinfo's (`cn.richinfo.dm`, SDK v4.0.7) China Mobile Device Management
(DM) SDK. All telemetry is sent to `*.fxltsbl.com`.

### Collected and uploaded (confirmed by static analysis)

- Device identifiers: IMEI1/2, IMSI1/2, ICCID1/2, MEID, WLAN MAC, BT MAC
- Full installed-app list (including system apps) plus per-app foreground time,
  launch count, and mobile/Wi-Fi RX/TX bytes
- Wi-Fi scan results (SSID / BSSID / RSSI)
- Cell info (cellId / lac / RSRP / SINR, 4G and 5G, both SIM slots)
- Paired Bluetooth devices (name / UUID / MAC)
- Charging state and a device-fingerprint string enumerating available sensors

### Endpoints

`/sdkService?func=tsdk:postreglog` (registration),
`/sdkService?func=tsdk:postapplylog` (app usage),
`/sdkService?func=tsdk:posthblog` (heartbeat),
`/TerminalConfigService/terminalConf` (remote config + SDK update check),
`/wifiInfo`, `/bluetooth`, `/flowCollectService`, `/preInstalledApp`.

### Why it should be blocked

1. Collection switches, intervals and sleep windows are **dictated by the vendor
   backend** via `terminalConf`; the end user has no control.
2. The scope (per-app usage detail, surrounding Wi-Fi, paired Bluetooth, cell data)
   clearly exceeds what "device management" requires.
3. The SDK can **download and load code at runtime** (`patch.jar` via `DexClassLoader`,
   MD5-checked only), which amplifies the privacy risk considerably.
4. The app has no launcher entry, so ordinary users cannot see or manage it.

### Suggested rules

```
||fxltsbl.com^
||a.fxltsbl.com^
||b.fxltsbl.com^
||auc.fxltsbl.com^
```
````


---

## 4. ⚠️ 可能被拒的理由（提前想好对策）

按 AdGuard 公开的 filter policy：

1. **「Rules for a specific site will only be added if there is sufficient traffic」**

   —— 这条主要针对网站规则。但审核员可能拿它卡你这个“小众到无法统计流量”的域。
   **对策**：强调这不是网站，是**预置在数百万台出厂设备上的遥测端点**，覆盖面不由访问量反映。

2. **`fxltsbl.com` 是自有应答域，不是 CNAME 伪装**
   —— 不会进 cname-trackers 仓库，走 Spyware filter 常规规则即可。别往 cname 那边提。

3. **审核可能要求“可复现”**
   —— 他们没有国行一加手机。**对策**：把 APK 的 SHA256 + 签名主体 + 反编译关键文件路径一起给出，
   任何人都能下载官方 OTA 提取同一 APK 复现。
   注意：**不要上传 APK 本体或反编译产物到 issue 里**，只贴哈希与文件路径。

4. **可能被要求走「regional filter（Chinese）」**
   —— 本场景确实是国行 ROM 专属。如果被这么建议，就顺着改成 Chinese filter 的规则。
   国内用户基数大，未必是坏事。

5. **反方论点要预先回应**：
   - “这是运营商合规要求，属于法律必需的设备注册”
     → 注册（IMEI/IMSI/ICCID）确实有法规基础；**但应用使用明细、Wi-Fi 扫描列表、蓝牙配对设备、通往服务端的远程代码加载，都超出该必要限度**。这句话一定要写进报告，否则容易被一句“运营商要求”打回。

---

## 5. 提交前自检清单

- [ ] 报告里没有你自己的 IMEI / 手机号 / 真实 SIM 信息
- [ ] 没有上传 APK 本体、反编译源码、`cmcc_dm.db` 或任何设备数据
- [ ] 域名写的是 `fxltsbl.com`（父域），不是只有 `a.fxltsbl.com`
- [ ] 选了 Spyware filter，不是 Base filter
- [ ] 规则没加 `$third-party`
- [ ] 附上了「超必要限度」的论证段落（第 4 节第 5 条）
- [ ] 留了可复现路径（SHA256 + 签名主体 + APK 内部路径），但没贴文件内容

### APK 哈希（可复现锚点）

```
SHA256  8c68675c0f6c0a367bd2d4db28d924a0efdf6dfb76bee880cd83aa4d6845381e
大小    855,324 字节
路径    /my_bigball/app/RegService/RegService.apk
签名    CN=AndroidTeam, O=Oplus
特性    SDK 4.0.7 / 协议 v2 / 构建 240605 / commit ae1bc90
```

这个哈希只锁定了“我们分析的是哪个包”，不暴露任何设备信息，可以放心贴。

---

## 6. 如果被拒，还有哪些地方能提

- **EasyPrivacy**（uBlock Origin 默认启用）：https://github.com/easylist/easylist/issues
- **AdGuard Home 用户自己的黑名单**（已完成，见 `BLOCKING.md`）
- **NextDNS / ControlD 的 community 列表**
- **中国区过滤器**（AdGuard Chinese filter）：https://github.com/AdguardTeam/AdguardFilters/tree/master/ChineseFilter
- 国内社区：V2EX、酷安、少数派 —— 曝光度有时比进列表更有用

---

## 附：可直接引用的技术事实（带出处）

| 事实 | 出处（反编译路径） |
|---|---|
| 上报域名 | `cn/richinfo/dm/constance/PublicConstance.java` |
| 接口清单 | `cn/richinfo/dm/net/UrlConstant.java` |
| 注册字段 50+ | `cn/richinfo/dm/bean/RegisterInfo.java` |
| 应用使用采集 | `cn/richinfo/dm/a/C0009b.java` |
| Wi-Fi 扫描 | `cn/richinfo/dm/a/Q.java` + `com/dmyk/android/telephony/OppoDmykTelephonyManager.getWifiList()` |
| 蓝牙配对设备 | 同上 `getBluetoothInfo()` |
| 动态代码加载 | `cn/richinfo/dm/service/DMService.java`（`DexClassLoader` + `cn.richinfo.dmpatch.business.DMController`） |
| 服务端下发的开关 | `cn/richinfo/dm/a/z.java` |
| 数据库文件 | `cn/richinfo/dm/db/DbOpenHelper.java`（`cmcc_dm.db`） |
