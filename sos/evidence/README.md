# evidence/ — 保留的关键证据副本

完整反编译产物（jadx `sources/`、apktool `smali*/`）已于 2026-11-09 清理，
**可随时从 APK 重新生成**，命令见下。这里只留报告里直接引用、重建成本高的部分。

## 内容

- `sos-handout/values-zh-rCN/`、`sos-handout/xml/` —— SOS.apk 的 apktool 资源子集：
  用户协议文案（`strings.xml`）、`network_config_for_test.xml` 等首选项 XML。
- `regres-handout/` —— RegService.apk 的 apktool 资源子集：`AndroidManifest.xml`（解码后）、
  `res/values/{strings,public}.xml`、drawable 图标。
- `regservice-raw/` —— RegService.apk 解包后的原始 `classes.dex`（824 KB）与 `lib/*/libaes-jni.so`。
  ⚠️ `classes.dex` 是唯一无法从别处重建的证据（原 APK `RegService.apk` 不在仓库里，
  SHA256 `8c68675c…5381e`）。做 JNI / dex 字节级复核时用它。

## 重建完整反编译

```bash
cd ~/.openclaw/workspace/projects/coloros-privacy-audit/sos
~/.openclaw/workspace/tools/jadx/bin/jadx -d jadx/sources --no-res SOS.apk
java -jar ~/.openclaw/workspace/tools/apktool.jar d -f -o apktool SOS.apk

# RegService：需先从手机 adb pull /my_bigball/app/RegService/RegService.apk，
# 并校验 SHA256 与 ../regservice/SHA256SUMS 一致后再解包
```
