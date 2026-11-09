# RegService.apk 逆向审计（com.coloros.regservice）

审计对象：`/my_bigball/app/RegService/RegService.apk`（855,324 字节，SHA256 见下）
来源：**一加 8T / ColorOS 14** 系统 App（Tom 本机 `adb pull` 取得），
`/my_bigball` = 系统**可卸载但不显示在应用列表**的分区（my_* 分区即"运营商定制/可动态更新"分区）。

## 机型说明（重要）

- 本文所有结论均基于**一加 8T / ColorOS 14** 提取的 APK（Tom 本机 `adb pull`）
- v2ex 原帖（t/1255189）描述的是**网友在一加 ACE / ColorOS 15 上的现象**，非本文样本
- 一加 8T 上该组件**不一定被隐藏**，请先在自己机器上核实：
  ```bash
  adb shell pm path com.coloros.regservice
  adb shell "dumpsys package com.coloros.regservice | grep -E 'userId|enabled'"
  ```
- 两台机器的包是否完全一致、结论能否平移，本文不做假设

---

## 结论速览

这个 APK **就是网贴说的那个东西**，而且比网贴描述的更彻底：它是一套完整的**运营商终端管理 SDK（DM = Device Management）**，
由 **彩讯科技（Richinfo，cn.richinfo.dm.*）** 开发、**OPPO/一加签名**（CN=AndroidTeam, O=Oplus）、以系统 App 身份预装，
带**远程配置 + 远程动态代码下发**能力。

| 网贴说法 | 核实结果 |
|---|---|
| 包名 com.coloros.regservice | ✅ 确认 |
| 业务：中国移动终端设备管理、设备注册 | ✅ 确认，SDK 名 `DM`，走中移动 DM 协议，`dmkey=A100000357`（移动应用 key） |
| 上传域名 a.fxltsbl.com | ✅ 确认（+ `b.fxltsbl.com` 调试、`auc.fxltsbl.com` 授权中心） |
| 上传应用列表/使用时长/启动次数/分应用流量 | ✅ 确认，**全部应用**（`getInstalledPackages` 0x2005 全量，含系统应用） |
| 上传 Wi-Fi 列表、SIM/设备标识、基站/网络信息 | ✅ 确认，且**更多**：IMEI1/2、IMSI1/2、ICCID1/2、MEID、BT MAC、WLAN MAC、手机号、位置经纬度、蓝牙已配对设备、充电状态、传感器清单 |
| 存 cmcc_dm.db 上传到广州阿里云 | ✅ 数据库名确认（`cmcc_dm.db`）；**服务器 IP 落地在阿里云（见下）** |
| 「特殊隐藏名单 手机看不到」 | ⚠️ 部分成立：应用无 launcher activity（本来就不显示图标）；但**我没找到代码主动执行 `pm hide` 把自己加进隐藏名单的证据**，更可能是 ColorOS 在 ROM 侧对该包做的隐藏（需 ROM 侧核对） |

## 域名与基础设施

- `https://a.fxltsbl.com` —— 生产（`PublicConstance.BASE_URL_RELEASE`）
- `https://b.fxltsbl.com` —— 调试
- `https://auc.fxltsbl.com/AuthCenter/datareport` —— 拍照/认证上报
- 证书：`*.fxltsbl.com`，DigiCert DV（Encryption Everywhere DV TLS CA - G2），2025-11-18 ~ 2026-12-19
- DNS：`a.fxltsbl.com` / `b.fxltsbl.com` → `2409:8080:3824:f70d::1:8`（IPv6，中国移动段）+ 本机测试得 `117.134.71.39`（IPv4）
- 服务器 TLS 不支持安全重协商（`unsafe legacy renegotiation disabled`），老式 Java/旧客户端配置特征
- `fxltsbl` = "飞象联/风讯通" 类拼音缩写，与彩讯 DM 业务匹配

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
`WifiManager.getScanResults()` → `{bssid, ssid, rssi}` JSON 数组。**这是绕过正常 Android 权限模型做的**（扫描需要对系统应用的 NETWORK_SCAN 权限，本 APK 有 SIGNATURE 级权限背景）。

### 4. 基站/网络
cellId/lac/erafcn/band/rsrp/rsrq/sinr，4G/5G × 双卡；运营商码、网络类型、漫游状态、APN 状态、VoLTE/VoNR 开关。

### 5. 位置
`OppoDmykTelephonyManager.getLocationMsg()` 读 `LocationManager.getLastKnownLocation`（gps/network provider）。
**但注意：SDK 上层（`cn.richinfo.dm`）里没有调用 `getLocationMsg` 的地方** —— 有能力，但当前 SDK 4.0.7 未启用；**动态下发包里可能启用**。

### 6. 蓝牙
`BluetoothAdapter.getDefaultAdapter().getBondedDevices()` 中 `isConnected()` 的设备 → 名称、第一个 UUID、MAC。

## ⚠️ 最高风险：远程动态代码执行（RAT 能力）

`service/DMService$b()`：

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
- 触发条件：`DMSDK.isDynamicReport()` && `SPUtils.getDynamicLoadSwitch() != "N"`；**开关由服务端 `terminalConf` 下发**（`sdkUpdate.isOpen=Y`）
- 这是完整 RAT 形态：**服务端（或任何能做中间人/接管 DNS 的人）+ MD5 碰撞/服务端被攻破 → 任意代码以系统权限运行**

## ⚠️ 其他风险点

1. **上报开关由服务端决定**（`a/z.java` 解析 `whitelistconfig`/`switchConfig`/`sleepSwitch`/`isOpen`），本地用户不可控。所谓"隐私开关"实际是服务端白名单。
2. **手机号明文采集**：`getPhoneNumber()` 读 `OplusOSTelephonyManager.getLine1NumberGemini`，但受 `Settings.Global["privacy_info_enabled_upload"]` 控制（默认 -1 走 Feature 判断）。若 `privacy_info_enabled_upload=1`（ROM/RomUpdateService 下发）就开启。
3. **WLAN MAC** (`getMacAddress`) 同样受 `isPrivacyInfoEnabledUpload()` 控制。
4. **远程静默改网络设置**：`set5G()` 可以写 `Settings.Global["preferred_network_mode<subId>"]` + 调 `TelephonyManager.setPreferredNetworkType()`，能把 5G 强制切 4G（`isSupportSilentSetFiveG` feature）。
5. **改 APN**：声明了 `WRITE_APN_SETTINGS`（代码里暂未直接找到，可能在动态包里）。
6. **OTA XML 注入**：`DMReceiver.updateSettingsGlobalForRomUpdate` 解析 ROM 里的 XML，把 `<setting key=X value=Y>` **直接写入 `Settings.Global`**（任意 key，可覆盖 privacy_info_enabled_upload 等）。
7. **保活**：`Utils.enableBackgroundService()` 调 `OplusActivityManager.addBackgroundRestrictedInfo("com.coloros.regservice", [...])` —— **主动申请加入后台限制豁免名单**；Manifest 有 `ForbidStop=true`，服务 `stopSelf()` 有 4 分钟倒计时保活。
8. **绕过用户可见路径**：`UTILS.isBootWizardCompleted()` 需要 `device_provisioned=1` 才初始化 → 首次开机向导前不采集（合规痕迹），**过完向导才开始**。
9. **三方入口**：`OppoDMReceiver` 监听 `cn.richinfo.dmyk.action.THIRD_REQUEST`，用 `com.dm.permission.THIRD_SEND` (signature) 保护 —— 其他**同为 OPPO 签名**的 App 可以让它执行事（远程控制入口）。
10. **弱加密**：AES 密钥硬编码在 `libaes-jni.so` 的 `.rodata`：`134e3265829ff82daf16e7b740a600b5`（MD5(密钥) 决定 AES key）。任何拿到 APK 的人都能解上报内容。
11. **签名 SHA1withRSA** —— 老签名算法，非 Android 9+ 推荐的 SHA256。

## 合规/法律视角

- 以系统 App 身份运行，声明 `READ_PRIVILEGED_PHONE_STATE`、`QUERY_ALL_PACKAGES`、`PACKAGE_USAGE_STATS`、`READ_NETWORK_USAGE_HISTORY`、`ACCESS_BACKGROUND_LOCATION`、`LOCAL_MAC_ADDRESS`、`WRITE_SECURE_SETTINGS` 等**普通应用申请不到的权限**。
- 按理属于《个人信息保护法》**敏感个人信息**：IMEI/IMSI/ICCID/位置/使用行为/精确画像，且**采集范围/频率/开关均不由用户控制**。
- 服务端能力（远程下发 + 远程 RAT）远超"终端管理"必要限度。

## 密码学实现（含解码工具）

### 算法

`cn.richinfo.dm.util.AesUtil`：

```java
Cipher cipher = Cipher.getInstance("AES/ECB/PKCS5Padding");
new SecretKeySpec(DigestUtils.md5(keyStr), "AES")
return Base64.encode(cipher.doFinal(payload));
```

- 模式：**AES/ECB/PKCS5Padding**（ECB 无 IV，相同明文出相同密文，不具备语义安全）
- 密钥：`DigestUtils.md5(keyStr)` —— 注意这里取的是 MD5 的**32 位小写 hex 字符串的 ASCII 字节**（32 字节），不是 16 字节原始摘要
- 编码：Base64（无换行）
- 两条路径：
  - `EncryptJsonRequest` → 直接 `AES(json)`
  - `GZIPJsonRequest` → 先 gzip 再 `AES(gzip(json))`，解密后需 gunzip

### 密钥来源：`libaes-jni.so` 反汇编

`AesUtil.keyFromJNI()` 是 native 方法，实现在 `lib/arm64-v8a/libaes-jni.so`（仅 5,808 字节）。
用 capstone 反汇编 `.text`（140 字节）后可完整还原逻辑：

```asm
; Java_cn_richinfo_dm_util_AesUtil_keyFromJNI   @ 0x53c
053c  stp  x29, x30, [sp, #-0x10]!
0540  mov  x29, sp
0544  sub  sp, sp, #0x20
0548  adrp x8, #0
054c  add  x8, x8, #0x588        ; x8 = .rodata 起始
0550  stur x0, [x29, #-8]        ; 存 JNIEnv*
0554  str  x1, [sp, #0x10]       ; 存 jobject
0558  ldur x0, [x29, #-8]        ; x0 = JNIEnv*
055c  ldr  x0, [x0]               ; x0 = *JNIEnv  -> functions 表
0560  ldr  x0, [x0, #0x538]       ; JNIEnv->NewStringUTF
0564  ldur x1, [x29, #-8]        ; x1 = JNIEnv*（准备调 Real_JNI_OnLoad 的回调路径）
0568  str  x0, [sp, #8]
056c  mov  x0, x1
0570  mov  x1, x8                 ; x1 = .rodata 常量指针
0574  ldr  x8, [sp, #8]
0578  blr  x8                     ; return NewStringUTF(env, ".rodata 常量")
057c  mov  sp, x29
0580  ldp  x29, x30, [sp], #0x10
0584  ret
```

关键点：

- 整个函数**只有一条数据引用**：`.rodata @ 0x588`
- `.rodata` 内容：`134e3265829ff82daf16e7b740a600b5\0`（32 字节 ASCII）
- 没有异或、没有解密、没有任何混淆 —— JNI 层“加密”实际就是**把一个硬编码字符串返回给 Java**
- 早期版本常见的 `relax_jni_onload`（`0x524`）也只是对 `NULL` 做判断的桩代码

因此：

```
keyStr  = "134e3265829ff82daf16e7b740a600b5"
AES key = MD5(keyStr) 的 hex 字符串的 ASCII = "d65cd40966e8d6534cf39b5ecb590064"
```

### 连带影响

同一密钥用于**上行全部明文 JSON**与（服务端返回体暂未加密，直接 `new JSONObject(bytes)`）。也就是说：

- 任何拿到这个 APK 的人都能解密抓到或从数据库导出的上报内容
- 抓包拿到 base64 body → 一条命令还原明文，包括 IMEI/IMSI/ICCID/应用使用明细

### 解码工具

`tools/dm_decode.py`（本目录），依赖 `pycryptodome`：

```bash
# 解密单个上报 body
python3 tools/dm_decode.py decrypt --file body.b64
python3 tools/dm_decode.py decrypt --file body.b64 --json     # 自动识别 gzip 并美化

# 加密（自测/构造回放样本）
python3 tools/dm_decode.py encrypt '{"imei1":"..."}'

# 计算 URL 签名 token = MD5(imei1 + timestr 后 8 位)
python3 tools/dm_decode.py token 860000000000000 1759876543210

# 分析从设备 pull 下来的 cmcc_dm.db，输出 Markdown 报告
python3 tools/dm_decode.py db cmcc_dm.db --out db-report.md

# 扫描拉下来的整个应用数据目录，自动识别并解密所有密文文件
python3 tools/dm_decode.py scan ./regservice_data
```

自测：`python3 tools/selftest.py`，覆盖 AES 往返、gzip 路径、URL token 三组断言。

### URL 层签名（非加密，仅防重放）

`BusinessUtils.getUrlParamsV1/V2`：

```
&appkey=A100000357&timestr=<毫秒时间戳>&imei=<imei1>&version=v2&token=<MD5(imei1 + timestr[-8:])>
```

- `token` 只是 `MD5(imei1 + 时间戳后 8 位)`，**密钥即 IMEI 本身**
- 没有 HMAC、没有服务端密钥，因此**任何人都能伪造合法请求**
- 服务端返回体不加密：`new JSONObject(new String(networkResponse.data))`

### 日志文件上传连加密都没有

`a/C0019l.java` 上传 `.DMLog` 目录时使用 `multipart/form-data` 明文 POST，
文件名还直接拼了 `imei1-时间戳-原名`。也就是说，**日志文件内容 + IMEI 同时以明文出现在 URL query 与 multipart 头里**。

### 小结

这套加密的实际效果：**只防随手看，不防任何有意的分析**。密钥在包里、算法是 ECB、签名用 IMEI、日志明文传。



## 复现与自查

以下命令仅用于在自己的设备上确认组件状态，不涉及任何数据上传。

```bash
# 确认包在系统中
adb shell pm path com.coloros.regservice
adb shell "dumpsys package com.coloros.regservice | grep -E 'requested permissions|granted'"

# 检查系统是否把它隐藏了
adb shell "pm list packages -f | grep regservice"
adb shell "pm list packages -d -u | grep regservice"
adb shell "dumpsys package com.coloros.regservice | grep -i hidden"

# 数据库与动态包
adb shell "run-as com.coloros.regservice ls -l /data/data/com.coloros.regservice/databases/"
adb shell "run-as com.coloros.regservice ls -l /data/data/com.coloros.regservice/files/dynamic/"
adb shell "run-as com.coloros.regservice cat /data/data/com.coloros.regservice/shared_prefs/*.xml" | grep -iE 'patch|dynamic|switch|open'

# 观测网络（不用抓包，看流量即可）
adb shell "dumpsys netstats | grep -B2 -A2 uid=1000[0-9][0-9]"

# 不用 root 也能判断：DNS 日志/AdGuard 里看 fxltsbl.com
```

## 缓解建议（从简单到彻底）

详细配置与验证步骤见 **[`BLOCKING.md`](BLOCKING.md)**（AdGuard / RethinkDNS / NetGuard / pm uninstall 四档）。要点：

1. **DNS 层**：AdGuard Home 加 `||fxltsbl.com^`，能拦住域名解析
2. **按应用断网**（推荐，覆盖 IP 直连）：AdGuard 安卓版 / RethinkDNS / NetGuard 里把 `com.coloros.regservice` 双向禁用
3. **卸载**：`my_bigball` 分区意味着可卸载，`adb shell pm uninstall --user 0 com.coloros.regservice`；回滚用 `cmd package install-existing`
4. **顺序提醒**：先查 `files/dynamic/patch.jar` 是否存在 —— 若已存在，光断网无效，必须删除或卸载

## 上报 AdGuard：`REPORT-TO-ADGUARD.md`

整理成可直接提交的稿件，包含：

- **提交渠道**：https://agrd.io/report（AdGuard 官方唯一入口）→ 选 Spyware filter
- **规则**：`||fxltsbl.com^` 为主，不带 `$third-party`
- **中英文两版正文**（AdGuard 团队主要看英文）
- **预判驳回理由** + 应对方式（重点：流量门槛、中国区 filter、反方“运营商合规”论点）
- **提交前自检清单**：不贴 IMEI、不传 APK、只给哈希与路径
- **备选渠道**：EasyPrivacy、Chinese filter、NextDNS、国内社区

需要直接粘的话，用 [`SUBMIT-COPY-PASTE.md`](SUBMIT-COPY-PASTE.md)：里面只有三段——规则、英文正文、中文正文，无解释无废话。

## 证据链与文件位置

```
projects/coloros-privacy-audit/regservice/
├── SHA256SUMS                  原包校验（原包 RegService.apk 在 ~/Downloads，仓库内不存）
├── README.md                   本文（内部完整版）
├── README-public.md            对外版（已剔除可操作的敏感细节）
├── BLOCKING.md                 网络阻断 / 卸载 / 验证清单
├── REPORT-TO-ADGUARD.md         上报 AdGuard 的稿件（含驳回预判与对策）
├── SUBMIT-COPY-PASTE.md        纯粘贴版：规则 + 英文正文 + 中文正文
├── tools/
│   ├── dm_decode.py            AES 解码 + cmcc_dm.db 分析
│   ├── selftest.py             算法自测（AES/GZIP/token 三组断言）
│   ├── test_db.py              合成数据库分析测试（不接触真实数据）
│   └── pull_db.sh              拉库脚本（run-as → su → adb root 逐级降级）
```

> ⚠️ **2026-11-09 清理**：`raw/`、`apktool/`、`jadx/` 已删除（可重建）。
> 保留的关键副本在 `../sos/evidence/`：`regservice-raw/`（classes.dex + libaes-jni.so）
> 与 `regres-handout/`（解码后 Manifest、strings/public 资源）。重建命令见 `../sos/evidence/README.md`。
