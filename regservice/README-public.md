# 一起系统级隐私审计：ColorOS 14 的 com.coloros.regservice

> 本文是一份面向公众的技术分析，依据仅为一个公开可分发的系统 APK 的静态逆向结果。
> 不含任何个人数据、设备标识、账号信息，也未接入或探测任何线上服务。

## 背景

社区反馈：部分一加机型（ColorOS 14，本文验证于 OnePlus 8T）中存在一个名为 `com.coloros.regservice` 的系统组件，
根据用户描述，它不在应用列表中显示，但可通过 ADB 查到，并且疑似在后台收集并上传大量设备与使用数据。

本文对该 APK 做静态逆向，逐条核对相关说法，并指出被忽略的风险点。

## 样本

| 项 | 值 |
|---|---|
| 包名 | `com.coloros.regservice` |
| 路径 | `/my_bigball/app/RegService/RegService.apk`（my_* 为运营商定制分区，设计上可卸载） |
| 大小 | 855,324 字节 |
| 签名 | `CN=AndroidTeam, O=Oplus, L=DongGuan`（OPPO 官方系统签名，SHA1withRSA） |
| 编译 | compileSdk 33，minColorOSApi 26，maxAndroidApi 34 |
| 版本 | SDK 4.0.7，协议 v2，构建 240605，commit ae1bc90 |

签名主体为 OPPO，说明这不是第三方侧载程序，而是随 ROM 预置的系统组件。

## 结论速览

相关说法基本属实，但实际能力比社区描述更完整：这是一套成熟的**运营商终端管理 SDK（DM, Device Management）**，
由**彩讯科技**（`cn.richinfo.dm.*`）开发、以 **OPPO 官方签名**随 ROM 预置，
除数据采集外还具备**服务端远程配置**与**远程下发并加载代码**的能力。

| 社区说法 | 核实结果 |
|---|---|
| 存在该组件且不在应用列表显示 | 属实：APK 无 launcher 入口 |
| 业务为中国移动终端管理/设备注册 | 属实：内置中移动 DM 协议，`dmkey=A100000357` |
| 上传域名 `a.fxltsbl.com` | 属实，另有调试域名 `b.` 与授权域名 `auc.` |
| 上传应用列表/使用时长/启动次数/分应用流量 | 属实，且覆盖全部已安装应用（含系统应用） |
| 上传 Wi-Fi 列表、SIM 与设备标识、基站信息 | 属实，且范围更大（详见下节） |
| 数据落地 `cmcc_dm.db` | 属实 |

## 域名与基础设施

- `https://a.fxltsbl.com` —— 生产（`PublicConstance.BASE_URL_RELEASE`）
- `https://b.fxltsbl.com` —— 调试
- `https://auc.fxltsbl.com/AuthCenter/datareport` —— 拍照/认证上报
- 证书：`*.fxltsbl.com`，DigiCert DV（Encryption Everywhere DV TLS CA - G2），2025-11-18 ~ 2026-12-19
- 域名注册与证书均为**单域名通配符 DV 证书**，未使用 EV/OV 增强验证
- 服务端 TLS 不支持安全重协商（`unsafe legacy renegotiation disabled`），属于较旧的 Java/客户端配置

## 接口清单（全部 `cn.richinfo.dm.net.UrlConstant`）

| 路径 | 用途 |
|---|---|
| `/sdkService?func=tsdk:postreglog` | 设备注册上报（50+ 字段，见 RegisterInfo） |
| `/sdkService?func=tsdk:posthblog` | 心跳（每次心跳把充电/蓝牙/网络/WiFi 列表一起带走） |
| `/sdkService?func=tsdk:postapplylog` | **应用使用数据**（应用名/包名/启动次数/前台时长/移动+WiFi 收发流量） |
| `/sdkService?func=tsdk:configlog` | 配置拉取日志 |
| `/TerminalConfigService/terminalConf?func=tsdk:termimalfullconfig` | **全量配置拉取**（所有采集开关、间隔、休眠时段由服务端决定） |
| `/TerminalConfigService/terminalConf?func=tsdk:checkupdate` | **SDK 动态包检查更新** |
| `/TerminalConfigService/auth?tsdk:sdkAuth` | 二次认证/拍照授权 |
| `/flowCollectService?func=tsdk:flowcollect` | 分时流量采集 |
| `/wifiInfo?` | **WiFi 扫描列表**（SSID/BSSID/信号强度） |
| `/network?` | 网络/基站信息 |
| `/batteryCharging?` | 充电状态 |
| `/bluetooth?func=tsdk:postBluetoothInfo` | **已配对蓝牙设备**（名称/UUID/MAC） |
| `/preInstalledApp?` | 预装应用列表 |
| `/internationalRoaming?` | 国际漫游 |
| `/errorDiagnosis?` / `/logReport?` | 异常日志、日志文件上传 |
| `/accept` | 通用接收 |
| `https://a.fxltsbl.com/getIpAddr` | 取出口 IP |

## 数据采集明细

### 1. 设备注册（`bean/RegisterInfo.java`，`getConfigRegisterMsg`）
50+ 字段，**每个字段受服务端配置 `cfgCheck()` 白名单控制**（默认全采）：
`sdkVersion, imei1, imei2, brand, model, firmwareVer, systemVer, cpu, rom, ram, type, iccid1/2, imsi1/2, mac, cellId, lac, channel, dataCard, masterStatus, sendTime, soltQuantity, dataCard2, soltNetwork1/2, cellId2, lac2, inType, verify, phoneNumber1/2, status5g1/2, currentRam, currentRom, networkMode5g1/2, smsSwitch5g1/2, vonrSwitch1/2, software700M, hardware700M, softwareSA, hardwareSA, netCard, voiceCard, tempValue1/2, carrierAggregation, foreignRoaming, voNRPlus, R16_5G1/2, bluetoothMac`

`verify` 字段是**设备指纹串**（`VerifyUtil.getVerifyInfo`）：`imei_..`、`imsi_..`、`mac_..`、`brand_`、`model_`、`version_`、`totalRam_`、`SDFreeSpace_`、`cpu_`、`screen_W*H`、`SimSerialNumber_`、`romSpace_`、`battery_`、`<传感器名>:Y/N||...`（加速度计/陀螺仪/磁力计/气压计/温湿度/计步/心率类等逐个探测）。

### 2. 应用使用数据（`a/C0009b.java` + `bean/a.java`）
- `PackageManager.getInstalledPackages(8197)` = `GET_META_DATA|GET_PERMISSIONS|GET_SIGNATURES`，**全量应用（含系统应用）**
- `UsageStatsManager.queryAndAggregateUsageStats(0, now)`：前台时长、首次使用时间
- 反射读 `UsageStats.mLaunchCount`：**启动次数**（这是被 Google 隐藏的字段）
- `NetworkStatsManager` 按 UID 统计：移动收发、WiFi 收发
- 每 7 天一个采集周期，落 `cmcc_dm.db` 的 `app_info_<时间戳>` 表，名前格式 `pkg|应用名|启动次数|使用秒|移动收|移动发|uid|安装flags|WiFi收|WiFi发`

### 3. WiFi 列表（`a/Q.java` + `OppoDmykTelephonyManager.getWifiList`）
`WifiManager.getScanResults()` → `{bssid, ssid, rssi}` JSON 数组。
扫描周边 Wi-Fi 在 Android 上属于受严格管控的能力（需 `NETWORK_SCAN` 等特权权限），本 APK 借助系统身份拿到了该权限。

### 4. 基站/网络
cellId/lac/erafcn/band/rsrp/rsrq/sinr，4G/5G × 双卡；运营商码、网络类型、漫游状态、APN 状态、VoLTE/VoNR 开关。

### 5. 位置
`OppoDmykTelephonyManager.getLocationMsg()` 读 `LocationManager.getLastKnownLocation`（gps/network provider）。
**但注意：SDK 上层（`cn.richinfo.dm`）里没有调用 `getLocationMsg` 的地方** —— 有能力，但当前 SDK 4.0.7 未启用；**动态下发包里可能启用**。

### 6. 蓝牙
`BluetoothAdapter.getDefaultAdapter().getBondedDevices()` 中 `isConnected()` 的设备 → 名称、第一个 UUID、MAC。

## 最高风险项：服务端可下发并加载代码

`service/DMService.b()` 中的核心逻辑：

```java
new DexClassLoader(patch.jar, getCacheDir(), null, classLoader)
    .loadClass("cn.richinfo.dmpatch.business.DMController")
    .getMethod("getInstance", Context.class).invoke(null, this);
```

- 服务端通过 `?func=tsdk:checkupdate` 下发 `{version, versionName, filePath, md5, size, feature}`
- **`filePath` 是服务端给的任意 URL**，用 `HttpURLConnection` 直接下载到 `files/dynamic/patch.jar`
- 只有 **MD5 校验**（`MD5.fileMD5`，无签名、无证书链）
- 要求 `version` 以 `DMConfig.SDK_VERSION`（`4.0.7`）开头
- 加载后替换整个 `DMController`（`DMFuncImpl` 接口：13 个采集回调）
- 触发条件：`DMSDK.isDynamicReport()` && `SPUtils.getDynamicLoadSwitch() != "N"`；开关由服务端 `terminalConf` 下发（`sdkUpdate.isOpen=Y`）
- 只要服务端被攻破、或其通信被中间人接管，攻击者即可向设备下发任意代码，并以系统应用权限运行。

## 其他风险点

1. **上报开关由服务端决定**（`a/z.java` 解析 `whitelistconfig`/`switchConfig`/`sleepSwitch`/`isOpen`），本地用户不可控。用户可见的「隐私开关」并非实际生效口径。
2. **手机号采集**：`getPhoneNumber()` 读 `OplusOSTelephonyManager.getLine1NumberGemini`，但受 `Settings.Global["privacy_info_enabled_upload"]` 控制（默认 -1 走编译期 Feature 判断）。若该值为 1（可由 ROM 更新服务下发）则开启。
3. **WLAN MAC**（`getMacAddress`）同样受上述开关控制。
4. **远程调整网络设置**：`set5G()` 会写入 `Settings.Global["preferred_network_mode<subId>"]` 并调用 `TelephonyManager.setPreferredNetworkType()`，可改变终端的网络制式偏好（需机型 Feature 支持）。
5. **APN 写入能力**：声明了 `WRITE_APN_SETTINGS`，当前代码路径未直接找到使用点，但权限已具备。
6. **OTA XML 注入**：`DMReceiver.updateSettingsGlobalForRomUpdate` 解析 ROM 中的 XML，把 `<setting key=X value=Y>` 直接写入 `Settings.Global`（可写任意 key）。
7. **保活策略**：`Utils.enableBackgroundService()` 调用 `OplusActivityManager.addBackgroundRestrictedInfo("com.coloros.regservice", [...])` 主动加入后台限制豁免；Manifest 中 `ForbidStop=true`，服务 `stopSelf()` 前有 4 分钟倒计时。
8. **启动时机**：`isBootWizardCompleted()` 要求 `device_provisioned=1` 才初始化，即在首次开机向导完成前不工作。
9. **跨应用入口**：`OppoDMReceiver` 监听 `cn.richinfo.dmyk.action.THIRD_REQUEST`，由 `com.dm.permission.THIRD_SEND`（signature 级）保护，同签名的其他 OPPO 应用可向其发送指令。
10. **加密强度**：AES 密钥以明文常量存放在 `libaes-jni.so` 的 `.rodata`，JNI 不做任何密钥派生保护，拿到 APK 即可解密全部上报内容。
11. **签名算法**：SHA1withRSA，属已被 Android 新版本弃用的弱算法。

## 合规视角

- 以系统应用身份运行，声明了 `READ_PRIVILEGED_PHONE_STATE`、`QUERY_ALL_PACKAGES`、`PACKAGE_USAGE_STATS`、`READ_NETWORK_USAGE_HISTORY`、`ACCESS_BACKGROUND_LOCATION`、`LOCAL_MAC_ADDRESS`、`WRITE_SECURE_SETTINGS` 等普通应用无法获得的权限。
- 采集内容涉及 IMEI/IMSI/ICCID、应用使用行为等，在《个人信息保护法》框架下通常被认定为敏感个人信息或可组合识别到个人的信息。
- 采集范围、频率与开关均由服务端下发，终端用户缺少知情与选择手段。
- 服务端具备下发并加载代码的能力，其必要性超出「终端管理」的一般范畴，值得监管与用户关注。

## 复现与自查

以下命令仅用于在自己的设备上确认组件状态，不涉及任何数据上传。

```bash
# 确认包是否存在、位于哪个分区
adb shell pm path com.coloros.regservice

# 查看它申请到的权限（能看出权限级别的异常）
adb shell dumpsys package com.coloros.regservice | grep -A40 "requested permissions"

# 是否在运行
adb shell ps -A | grep regservice

# 是否存在已下发的动态包（关键：判断远程代码是否已被激活）
adb shell run-as com.coloros.regservice ls -l files/dynamic/

# 本地采集库是否存在
adb shell run-as com.coloros.regservice ls -l databases/
```

## 缓解建议

优先级从高到低：彻底卸载 > 按应用断网 > DNS 域名屏蔽。
详细操作步骤见同目录 `BLOCKING.md`。

要点：
1. `||fxltsbl.com^` 加入 DNS 黑名单，只能挡住域名解析；
2. 更可靠的是在系统层按 uid 阻断该应用的网络（AdGuard / RethinkDNS / NetGuard 均可）；
3. `/my_bigball/` 分区意味着可用 `pm uninstall --user 0 com.coloros.regservice` 对当前用户卸载；
4. 若 `files/dynamic/patch.jar` 已存在，仅断网无效，须先删除该文件或直接卸载。

## 分析方法

- `apktool` 2.9.3 反编译资源与 smali
- `jadx` 1.5.1 反编译为 Java 源码（182 个类）
- `capstone` 反汇编 `libaes-jni.so`（AArch64）
- 域名信息来自公开 DNS / 证书链查询

## 附：逐项核对结论

| 社区说法 | 核对结果 |
|---|---|
| 存在 `com.coloros.regservice` | 属实 |
| 业务为中国移动终端设备管理 | 属实：内置中移动 DM 协议，`dmkey=A100000357` |
| 上传域名 `a.fxltsbl.com` | 属实，另有 `b.`（调试）与 `auc.`（授权） |
| 上传应用列表、使用时长、启动次数、分应用流量 | 属实，且覆盖全部已安装应用（含系统应用） |
| 上传 Wi-Fi 列表、SIM/设备标识、基站信息 | 属实，此外还包含蓝牙配对设备、充电状态、传感器清单等 |
| 数据落地 `cmcc_dm.db` | 属实 |
| 在应用列表中不可见 | 部分属实：该 APK 无 launcher 入口，本就不显示图标；未在代码中发现主动隐藏自身的逻辑 |
