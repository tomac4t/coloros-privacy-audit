#!/usr/bin/env python3
"""把 report-phase13-e-f-camera-gallery.md 拆成 E 组（运营商/合规）和 F 组（相机/相册）两份独立报告。"""
import pathlib
import re

base = pathlib.Path(__file__).resolve().parent.parent
src = base / "report-phase13-e-f-camera-gallery.md"
text = src.read_text(encoding="utf-8")

lines = text.splitlines(keepends=True)

# 定位切分点
f_start = None
for i, ln in enumerate(lines):
    if ln.startswith("# 第二批｜F 组"):
        f_start = i
        break
if f_start is None:
    raise SystemExit("找不到 F 组切分点")

e_body = "".join(lines[f_start // 4:] ) if False else None  # placeholder
e_lines = lines[:f_start]
f_lines = lines[f_start:]

# E 组正文：从 "# 第一批｜E 组" 开始
e_start = None
for i, ln in enumerate(e_lines):
    if ln.startswith("# 第一批｜E 组"):
        e_start = i
        break
if e_start is None:
    raise SystemExit("找不到 E 组切分点")

e_core = "".join(e_lines[e_start:])

e_header = """# 第十三轮（E 组）：运营商 / 合规类系统组件

- **日期**：2026-11-06
- **拆分说明**：原报告 `report-phase13-e-f-camera-gallery.md` 把 E 组（运营商/合规）与 F 组（相机/相册）
  合并分析。两者性质完全不同——E 组是法定合规上报，F 组是功能相关的云服务——现拆为两份独立报告。
  F 组见 `report-phase13-f-camera-gallery.md`。
- **结论速览**：
  - `com.oppo.ctautoregist` 是**唯一的硬性上报**：换卡/开关变化/开机时明文上报 IMEI+IMSI+ICCID+MAC+基站ID，
    这是工信部入网备案要求，**无用户开关**。
  - `com.coloros.bootreg` / `com.oplus.customize.coreapp` / `com.cmccslice.proxyapp` 均**零业务域名**。
  - `com.ted.number`（陌生号码识别）**自己不联网**，只提供 AIDL 服务，被 `blacklistapp` 调用。

---

"""

e_tail = """
---

*本报告由原合并报告拆分而来，内容未改动。相关发现见 F 组报告：*
*`report-phase13-f-camera-gallery.md`*
"""

(base / "report-phase13-e-group-carrier-compliance.md").write_text(
    e_header + e_core + e_tail, encoding="utf-8"
)

# ---- F 组 ----
f_core = "".join(f_lines)

f_header = """# 第十三轮（F 组）：相机 / 相册

- **日期**：2026-11-06（v2 修订）
- **拆分说明**：原合并报告中的 E 组（运营商/合规）已拆出，见 `report-phase13-e-group-carrier-compliance.md`。
- **核心问题**：相册「文字识别服务」在哪、什么时候联网、有没有开关。

> ⚠️ **v2 修订要点**：v1 曾把两个云端 OCR 域名写成“后台定时上传”，**这是错的**。
> 复核确认：`aiscan.ocloud` 与 `airecognition-ocr-cn` 都只在**用户主动点「识别文字」**时触发；
> 相册后台扫描（OCR_SCAN）只做本地 OCR，不联网。详见文末「十二、修订与触发条件」。
> v2 新增「十三、退出选择盘点」——找到了真正的用户开关。

---

"""

f_tail = """
---

*本报告由原合并报告拆分而来。E 组（运营商/合规）见：*
*`report-phase13-e-group-carrier-compliance.md`*
"""

(base / "report-phase13-f-camera-gallery.md").write_text(
    f_header + f_core + f_tail, encoding="utf-8"
)

print("E:", len(e_header + e_core + e_tail), "chars")
print("F:", len(f_header + f_core + f_tail), "chars")
