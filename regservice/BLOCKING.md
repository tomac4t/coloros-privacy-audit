# RegService 网络阻断方案（AdGuard / 防火墙 / 卸载）

> 目标包：`com.coloros.regservice`（uid 需实测，通常 10xxx）
> 域名：`a.fxltsbl.com`、`b.fxltsbl.com`、`auc.fxltsbl.com`，以及泛域名 `*.fxltsbl.com`
> 已知 IPv4：`117.134.71.39`；IPv6：`2409:8080:3824:f70d::1:8`

分三档，**建议按 1 → 2 → 3 叠加做**，单做 DNS 不够（它可能走 IP 直连，也可能已经被下发动态包）。

---

## 方案 1：AdGuard Home 域名屏蔽（最低成本，先做）

### 1.1 加规则

AdGuard Home → 过滤器 → DNS 黑名单 → 添加自定义列表，粘贴：

```
! RegService (CMCC DM SDK / 彩讯) - 2026-11-07
! 生产 / 调试 / 授权
||fxltsbl.com^
! 以下为冗余保险（父域已覆盖，但显式列出便于审计时看清意图）
||a.fxltsbl.com^
||b.fxltsbl.com^
||auc.fxltsbl.com^
```

`||fxltsbl.com^` 会连同所有子域一起拦（`@@` 白名单不受影响）。

### 1.2 用 AdGuard 自带的「查询日志」验证

1. 打开 AdGuard Home → 查询日志
2. 搜索框输入 `fxltsbl`
3. 如果手机在用、且该服务在采集 → 10 分钟内应该能看到命中
4. 命中后确认「处理方式」是 `已拦截`

⚠️ 如果**一直看不到查询**，说明它走 IP 直连或用了系统私有 DNS 绕过你的 AdGuard。

### 1.3 DNS-over-HTTPS / 私有 DNS 会绕过 DHCP 的 AdGuard

ColorOS 的「私人 DNS」如果被设成 `dns.alidns.com` 之类，就会跳过你的 AdGuard。
检查：设置 → 连接与共享 → 私人 DNS → 确认是**关闭**或指向你自己的 AdGuard。
（另一条路：在路由器层做透明 DNS 劫持，把 53/853 端口全导向 AdGuard。）

---

## 方案 2：按 App 断网（真正可靠，推荐）

### 2.1 方案 A：AdGuard for Android（应用防火墙模式）

AdGuard 安卓版（不是 AdGuard Home）有「应用管理」：
1. 设置 → 网络 → 应用管理 → 找到 **RegService**（AdGuard 里可能显示为 `com.coloros.regservice` 或「RegService」）
2. 勾选「仅 WiFi 可用」+ 取消「移动数据」→ 等于双向断网
3. 若列表里看不到，打开「显示系统应用」

### 2.2 方案 B：RethinkDNS（开源，可看实时连接，最透明）

1. 装 Rethink → 应用 → 找到 `com.coloros.regservice`
2. 关闭「WiFi」和「移动数据」两个开关
3. 打开「日志」页，可以实时看它尝试连了哪些 IP —— **这一步顺手就能验证它是否被下发过动态包**

### 2.3 方案 C：NetGuard（免 root，本地 VPN 模式）

同 AdGuard/Rethink：应用列表里找 `com.coloros.regservice`，勾掉「允许 WiFi 和移动数据」。
优点是轻、无账号；缺点是不能拦截已经建立的连接（要重启手机生效）。

### 2.4 方案 D：系统自带的「流量使用」限制（最保守，只能限后台）

设置 → 应用 → 特殊应用权限 → 流量使用情况 → `com.coloros.regservice` → 关闭「后台数据」、「漫游数据」。
⚠️ 这个**不能断 WiFi**，只能挡住移动数据后台，所以只能当辅助。

---

## 方案 3：卸载 / 禁用（最彻底）

`/my_bigball/` 是 ColorOS 的运营商定制分区，**意味着它被设计成可卸载**。

### 3.1 先查状态（不需要 root）

```bash
# 1. 确认包在哪个用户、是否已禁用、uid
adb shell pm list packages -f -u | grep regservice
adb shell "dumpsys package com.coloros.regservice | grep -E 'userId=|enabled=|installed=|hidden='"

# 2. 看它有没有在跑
adb shell "ps -A | grep regservice"

# 3. 看它是否已经在采集/下载动态包（关键）
adb shell "run-as com.coloros.regservice ls -l files/dynamic/ 2>/dev/null"
adb shell "run-as com.coloros.regservice ls -l databases/ 2>/dev/null"
```

### 3.2 卸载（对当前用户，重启后大概率不恢复，但 OTA 会）

```bash
adb shell pm uninstall --user 0 com.coloros.regservice
```

**验证**：
```bash
adb shell pm list packages --user 0 | grep regservice   # 应无输出
adb shell "ps -A | grep regservice"                     # 应无进程
```

**回滚**（万一影响功能，比如某些移动 SIM 的 VoLTE/注册异常）：
```bash
adb shell cmd package install-existing --user 0 com.coloros.regservice
```

### 3.3 不卸载，只禁用（更保险，可一键恢复）

```bash
adb shell pm disable-user --user 0 com.coloros.regservice
# 恢复：
adb shell pm enable com.coloros.regservice
```

### 3.4 最彻底：root 后从分区删掉

```bash
adb root && adb remount          # 或 Magisk 里选中 /my_bigball
adb shell "mount -o rw,remount /my_bigball"
adb shell "mv /my_bigball/app/RegService /data/local/tmp/RegService.bak"
adb reboot
```

⚠️ **不要直接删**，先 `mv` 到别处，方便恢复。OTA 升级会重新刷回这个分区，所以需要 Magisk 模块做 overlay 才能永久保持。

---

## 方案 4：RouterOS / OpenWrt 层统一拦（多设备、防重装）

如果你在路由器上做 DNS，AdGuard Home 那套直接生效。
如果要兜 IP 直连，在 OpenWrt 上：

```sh
# 屏蔽已知 IP（示例，实际以 DNS 解析结果为准）
nft add rule inet fw4 output ip daddr 117.134.71.39 drop
nft add rule inet fw4 output ip6 daddr 2409:8080:3824:f70d::1:8 drop
```

但更稳的是**按域名解析出的地址动态建 ipset**（dnsmasq 的 `ipset=` 选项 + nft 规则），细节略。

---

## 验证清单（做完逐条打勾）

- [ ] AdGuard Home 查询日志里 `fxltsbl.com` 显示「已拦截」
- [ ] AdGuard/Rethink 里 `com.coloros.regservice` 显示为「已阻断」且有连接记录
- [ ] `adb shell "run-as com.coloros.regservice ls files/dynamic/"` 返回空或目录不存在（说明没有下发过动态包）
- [ ] 卸载/禁用后 `adb shell "ps -A | grep regservice"` 无输出，且重启后仍无
- [ ] 插移动 SIM 验证 VoLTE / 5G / 短信正常（怕影响运营商功能的话，先选 3.3 禁用而不是卸载）
- [ ] 三天后再查一次查询日志，确认无 `fxltsbl` 记录

## 需要复核的风险

1. **禁用后运营商功能是否异常**：这个 App 挂着 `com.dm.permission.THIRD_SEND`，可能有其他系统 App（如设置里的「移动网络」）调用它。禁用前先备份 `dumpsys package` 输出。
2. **动态包可能已存在**：如果 `files/dynamic/patch.jar` 已经在了，光断网不够（下一次开机它会加载）。得先删掉那个文件再断网，或者直接卸载。
3. **优先级**：**卸载 > 断网 > DNS 屏蔽**。如果你能接受卸载，就别折腾前两层。

---

# 附：把本地采集库拉下来分析

⚠️ `cmcc_dm.db` 在 `/data/data/<pkg>/databases/`，是**应用私有目录**，`adb pull` 直接拉不到（Permission denied）。下面按条件从易到难排。

## 方案 A：`run-as`（先试，最快）

```bash
PKG=com.coloros.regservice

# 1) 先确认是否允许 run-as（系统签名应用经常被禁）
adb shell run-as $PKG id

# 2) 能跑就流式导出（adb exec-out 做二进制透传，不会破坏字节）
adb exec-out "run-as $PKG cat databases/cmcc_dm.db" > cmcc_dm.db

# 3) WAL 模式务必连带导出，否则丢最新一批数据
adb exec-out "run-as $PKG cat databases/cmcc_dm.db-wal" > cmcc_dm.db-wal

# 4) 验证
head -c 15 cmcc_dm.db      # 应输出 SQLite format 3
```

## 方案 B：root（最稳）

```bash
adb shell su -c "ls -l /data/data/$PKG/databases/"
adb exec-out "su -c 'cat /data/data/$PKG/databases/cmcc_dm.db'" > cmcc_dm.db
```

## 方案 C：userdebug 系统

```bash
adb root && adb wait-for-device
adb exec-out "cat /data/data/$PKG/databases/cmcc_dm.db" > cmcc_dm.db
```

## 方案 D：不拉库，只看 logcat（不 root、不碰文件）

这个 SDK 的 `Utils.VERBOSE_DEBUG` 是**编译期常量 `true`**，所以大量日志默认就写在 logcat 里（tag 是中文）：

```bash
adb logcat -v time | grep -E "RegService|richinfo|应用采集|自注册|Wifi采集|流量采集"
# 或一次性 dump 后翻
adb logcat -d > logcat.txt
grep -nE "应用采集|自注册|Wifi采集" logcat.txt
```

优点：免 root、不碰私有目录。缺点：只有摘要，没有完整明细。

## 方案 E：网络侧（最不侵入）

手机 HTTP(S) 代理指向电脑上的 mitmproxy，只看 `host + 路径 + 请求体大小 + 频率` 就足够定性。
要还原明文，把 body 存成文件后：

```bash
python3 tools/dm_decode.py decrypt --file body.b64 --json
```

## 配套脚本（推荐）

`tools/pull_db.sh` 会把 A/B/C 三条自动降级跑一遍，并直接生成报告：

```bash
bash tools/pull_db.sh ./regservice_data
```

## 拿到库之后

```bash
python3 tools/dm_decode.py db cmcc_dm.db --out db-report.md
```

报告会按采集周期展开成「包名 / 应用名 / 启动次数 / 前台时长 / 移动与 WiFi 流量」，
并自动标注银行、支付、医疗、IM、VPN、交友等敏感类别。

## 安全提醒

这是你的真实使用记录。建议：

1. 分析完就删：`shred -u cmcc_dm.db*`
2. 不要提交到任何 git 仓库
3. 发帖贴证据时用 `tools/test_db.py` 里的合成数据，别贴真表
