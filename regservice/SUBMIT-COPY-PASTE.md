# 提交给 AdGuard 的现成文本（直接复制粘贴用）

这个文件只放三段可直接粘贴的内容，不含解释。解释见 `REPORT-TO-ADGUARD.md`。

---

## ① 规则（粘到「Suggested rules」框）

```
||fxltsbl.com^
||a.fxltsbl.com^
||b.fxltsbl.com^
||auc.fxltsbl.com^
```

---

## ② 英文正文（GitHub issue 用这个，AdGuard 团队看英文）

````markdown
### Any additional information

I'm reporting a **privacy-invasive telemetry endpoint shipped in stock firmware**,
not a website tracker. It was found by static analysis of a preinstalled system app,
so there is no straightforward way to capture it from a browser.

**Target:** `fxltsbl.com` and all subdomains (`a.`, `b.`, `auc.`)

**App:** `com.coloros.regservice`
`/my_bigball/app/RegService/RegService.apk` — 855,324 bytes
SHA256 `8c68675c0f6c0a367bd2d4db28d924a0efdf6dfb76bee880cd83aa4d6845381e`
Signed with OPPO's platform certificate: `CN=AndroidTeam, O=Oplus, L=DongGuan`

This app ships on OnePlus devices running ColorOS (mainland China builds; verified on OnePlus 8T / ColorOS 14).
It has no launcher entry, so users cannot see or manage it from Settings.
It embeds Colyinfo's `cn.richinfo.dm` SDK v4.0.7 (China Mobile Device Management).

### What it sends to `*.fxltsbl.com`

- IMEI1/2, IMSI1/2, ICCID1/2, MEID, WLAN MAC, Bluetooth MAC
- Full installed-app list including system apps, plus per-app foreground time,
  launch count (read reflectively from the hidden `UsageStats.mLaunchCount` field),
  and mobile/Wi-Fi RX+TX byte counters
- Wi-Fi scan results (SSID, BSSID, RSSI)
- Cell info: cellId, lac, RSRP, RSRQ, SINR for 4G and 5G, both SIM slots
- Paired Bluetooth devices: name, UUID, MAC
- Charging state, and a device-fingerprint string enumerating available sensors

### Endpoints

| Path | Purpose |
| --- | --- |
| `/sdkService?func=tsdk:postreglog` | device registration, 50+ fields |
| `/sdkService?func=tsdk:postapplylog` | per-app usage data |
| `/sdkService?func=tsdk:posthblog` | heartbeat (also flushes charge/BT/network/Wi-Fi data) |
| `/TerminalConfigService/terminalConf` | pulls full remote config and checks for SDK updates |
| `/wifiInfo?` | Wi-Fi scan list |
| `/bluetooth?func=tsdk:postBluetoothInfo` | paired Bluetooth devices |
| `/flowCollectService?func=tsdk:flowcollect` | per-period traffic |
| `/preInstalledApp?` | preinstalled app list |

### Why this should be blocked

1. **Collection switches, intervals and "sleep" windows are dictated by the vendor
   backend** via `/TerminalConfigService/terminalConf`. There is no user-facing control;
   what looks like a privacy toggle is a server-side whitelist.
2. The scope — per-app usage detail, surrounding Wi-Fi, paired Bluetooth, cell data —
   goes well past what "device management" requires.
3. The SDK can **download and load code at runtime**: it fetches a `patch.jar` from a
   server-provided URL and loads `cn.richinfo.dmpatch.business.DMController` through
   `DexClassLoader`, validated by MD5 only (no signature check).
4. The app has no launcher entry, so ordinary users have no way to notice it.

### On the "carrier compliance" objection

Device registration (IMEI/IMSI/ICCID) plausibly has a regulatory basis in China.
Everything else listed above does not: per-app usage detail, Wi-Fi scan lists,
paired Bluetooth devices, and remote code delivery are not required for registration.

### Suggested rules

```
||fxltsbl.com^
||a.fxltsbl.com^
||b.fxltsbl.com^
||auc.fxltsbl.com^
```

Happy to provide the decompiled file paths for any specific claim so it can be verified
against the same APK.
````

---

## ③ 中文正文（发 V2EX / 酷安 / 少数派用）

````markdown
### 背景

一加 8T / ColorOS 14 国行系统里预置了一个不在应用列表显示的系统组件
`com.coloros.regservice`，路径 `/my_bigball/app/RegService/RegService.apk`，
用的是 OPPO 官方平台签名（`CN=AndroidTeam, O=Oplus`）。

这个包里嵌了彩讯（`cn.richinfo.dm`，SDK v4.0.7）的中国移动 DM
（Device Management，终端管理）SDK，所有上报请求都发往 `*.fxltsbl.com`。

### 它采什么

- 设备标识：IMEI1/2、IMSI1/2、ICCID1/2、MEID、WLAN MAC、蓝牙 MAC
- 完整已安装应用列表（含系统应用），以及每个应用的前台时长、启动次数、
  移动/WiFi 收发字节
- Wi-Fi 扫描列表（SSID / BSSID / RSSI）
- 基站信息（cellId / lac / RSRP / SINR，4G 与 5G × 双卡）
- 已配对蓝牙设备（名称 / UUID / MAC）
- 充电状态，以及逐项探测设备传感器的指纹串

### 三个值得注意的点

1. **开关不在你手里**。采集范围、频率、休眠时段全部由服务端
   `/TerminalConfigService/terminalConf` 下发，手机上那个"隐私开关"其实是服务端白名单。
2. **它能远程加载代码**。服务端可以下发 `patch.jar`，客户端用 `DexClassLoader`
   加载 `cn.richinfo.dmpatch.business.DMController` 顶替原有逻辑，**只校验 MD5，不验签名**。
3. **脱敏不彻底**。上报内容用 AES/ECB 加密，但密钥以明文常量写在
   `libaes-jni.so` 的 `.rodata` 里；日志上传连加密都没有，文件名里直接拼 IMEI。

### 怎么处理

优先级：彻底卸载 > 按应用断网 > DNS 屏蔽域名。

```
||fxltsbl.com^
```

（纯 DNS 拦截足够挡住解析，但要防 IP 直连，最稳还是在系统层按 uid 断这个应用的网。）

### 我不是唯一一家

已经给 AdGuard 提交了规则请求，希望进 Spyware filter。
如果能进公共列表，比每个人各自配规则要有意义得多。
````
