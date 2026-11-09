#!/usr/bin/env python3
"""
报警辅助（Alarm Assistance）短信 payload 解析 / 构造工具

背景：一加/OPPO ColorOS「SOS 紧急联络 → 位置共享 → 报警辅助」在拨打 110/120/119/122 时，
会把定位 + 周边 Wi-Fi 的 MAC 地址发给位置网，用于接处警中心定位。

网络通道走 disaster.coloros.com（ECIES 加密 JSON）；网络不可用或号码取不到时，
退化为向 1069030089933 发一条短信，内容是本工具解析的自定义二进制结构。

来源：com.oplus.sos.utils.g.n()  /  com.oplus.sos.utils.i2.a()

======================= 短信内容结构 =======================
外层是 7-bit 转义（GSM 03.38 风格），见 i2.a()：
    每 15 个“输出字节”前插一个 0x00 结束位，把原 8 位字节流按 7 位重新排列。

内层二进制（拼接后 131 字节）：

  [0:3]   魔数 06 0D 03
  [3:9]   RSA 加密块（PKCS#1 v1.5，1024 位）
            → 明文 117 字节：
              int16  紧急号码        （去掉区号，110/119/120/122）
              int16  区号（去首 0）   （如 010 → 10，无区号则 0）
              float64 latitude      （保留 6 位小数）
              float64 longitude     （保留 6 位小数）
              int64  时间戳位域     （低 14 位 = 拨号后经过的秒数，高位 = 拨号时刻 epoch/1000）
              uint8  标志位         （bit0-1: 上报渠道, bit2: 是否 120 呼叫）
              uint8  SIM 槽位       （1 或 2）
              uint8  Wi-Fi 数量     （最多 10）
              Wi-Fi 列表：每项 7 字节
                 6 字节 BSSID + 1 字节信号强度（RSSI，int8）

用法：
    python3 alarm_sms.py parse "<短信文本>"
    python3 alarm_sms.py decode-hex 060D03...
    python3 alarm_sms.py self-test
"""
from __future__ import annotations

import argparse
import struct
import sys

MAGIC = b"\x06\x0d\x03"
RSA_PLAIN_LEN = 117
RSA_BLOCK_LEN = 128
WIFI_ENTRY_LEN = 7
MAX_WIFI = 10


# ---------------------------------------------------------------- 7-bit 转义
def unescape_7bit(data: bytes) -> bytes:
    """i2.a() 的逆运算：去掉每 15 字节的 0x00 分隔位，还原 7-bit 流"""
    out_bits = []
    for b in data:
        for i in range(7, -1, -1):
            out_bits.append((b >> i) & 1)
    # 每 16 个 bit 中最后 1 位是填充的 0
    payload_bits = []
    for i in range(0, len(out_bits), 16):
        payload_bits.extend(out_bits[i : i + 15])
    out = bytearray()
    for i in range(0, len(payload_bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | payload_bits[i + j]
        out.append(byte)
    return bytes(out)


def escape_7bit(data: bytes) -> bytes:
    """i2.a() 的正向实现（用于构造测试数据）"""
    bits = []
    for b in data:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
    out = bytearray()
    cur = 0
    cnt = 0
    for i, bit in enumerate(bits):
        if i % 15 == 0 and i > 0:
            # 补一个 0 结束位
            cur = (cur << 1) | 0
            cnt += 1
            if cnt == 8:
                out.append(cur)
                cur, cnt = 0, 0
        cur = (cur << 1) | bit
        cnt += 1
        if cnt == 8:
            out.append(cur)
            cur, cnt = 0, 0
    if cnt:
        out.append(cur << (8 - cnt))
    return bytes(out)


# ---------------------------------------------------------------- 位域解析
def parse_timestamp_field(v: int) -> tuple[int, int]:
    """低 14 位 = 拨号后经过秒数；高位 = 拨号时刻 epoch/1000"""
    elapsed = v & 0x3FFF
    dial_epoch_s = (v >> 14) & 0x7FFFFFFFFFF  # 剩下的位
    return dial_epoch_s, elapsed


def parse_plain(buf: bytes) -> dict:
    if len(buf) != RSA_PLAIN_LEN:
        raise ValueError(f"明文长度应为 {RSA_PLAIN_LEN}，实际 {len(buf)}")
    num, area = struct.unpack(">hh", buf[0:4])
    lat, lon = struct.unpack(">dd", buf[4:20])
    ts = struct.unpack(">q", buf[20:28])[0]
    flags = buf[28]
    sim = buf[29]
    n = buf[30]
    wifi = []
    off = 31
    for _ in range(min(n, MAX_WIFI)):
        mac = ":".join(f"{b:02x}" for b in buf[off : off + 6])
        rssi = struct.unpack(">b", buf[off + 6 : off + 7])[0]
        wifi.append({"bssid": mac, "rssi": rssi})
        off += WIFI_ENTRY_LEN
    dial_epoch, elapsed = parse_timestamp_field(ts)
    return {
        "emergencyNumber": num,
        "areaCode": area,
        "latitude": round(lat, 6),
        "longitude": round(lon, 6),
        "dialEpochSeconds": dial_epoch,
        "elapsedSeconds": elapsed,
        "flagsRaw": flags,
        "flagBit0_1_channel": flags & 0x03,
        "flagBit2_isAmbulance": bool((flags >> 2) & 1),
        "simSlot": sim,
        "wifiCount": n,
        "wifi": wifi,
        "trailingBytes": len(buf) - off,
    }


def parse_message(raw: bytes) -> dict:
    """输入：短信正文的原始字节（已按 7-bit 解压，或在文本模式下先转回字节）"""
    if len(raw) < 131:
        raise ValueError(f"长度不足：{len(raw)} < 131")
    if raw[:3] != MAGIC:
        raise ValueError(f"魔数不匹配：{raw[:3].hex()} (期望 060d03)")
    rsa_ct = raw[3 : 3 + RSA_BLOCK_LEN]
    return {
        "magic": raw[:3].hex(),
        "rsaCiphertextLen": len(rsa_ct),
        "rsaCiphertextHex": rsa_ct.hex(),
        "note": "RSA 段需要用设备内置公钥解密，本工具只做结构解析",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="报警辅助短信 payload 解析")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("parse", help="解析短信文本（自动 7-bit 还原）")
    p1.add_argument("text", help="短信正文")
    p1.add_argument("--bytes", action="store_true", help="输入是 latin-1 原始字节")

    p2 = sub.add_parser("decode-hex", help="解析十六进制")
    p2.add_argument("hex")

    p3 = sub.add_parser("parse-plain", help="解析已解密的 117 字节明文（hex）")
    p3.add_argument("hex")

    sub.add_parser("self-test", help="构造一条样例短信并解析回来")

    a = ap.parse_args()

    if a.cmd == "parse":
        data = a.text.encode("latin-1") if a.bytes else a.text.encode("utf-8")
        print(unescape_7bit(data).hex())

    elif a.cmd == "decode-hex":
        raw = bytes.fromhex(a.hex.replace(" ", ""))
        for k, v in parse_message(raw).items():
            print(f"{k:20s} {v}")

    elif a.cmd == "parse-plain":
        buf = bytes.fromhex(a.hex.replace(" ", ""))
        for k, v in parse_plain(buf).items():
            print(f"{k:24s} {v}")

    elif a.cmd == "self-test":
        plain = bytearray(RSA_PLAIN_LEN)
        struct.pack_into(">hh", plain, 0, 110, 571)  # 110, 杭州 0571
        struct.pack_into(">dd", plain, 4, 30.274084, 120.155070)
        ts = ((1759876543 << 14) | 42) & 0x7FFFFFFFFFFF
        struct.pack_into(">q", plain, 20, ts)
        plain[28] = 0b00000101  # channel=1, ambulance=1
        plain[29] = 1
        plain[30] = 2
        off = 31
        for mac, rssi in [(b"\x00\x11\x22\x33\x44\x55", -48), (b"\xaa\xbb\xcc\xdd\xee\xff", -71)]:
            plain[off : off + 6] = mac
            struct.pack_into(">b", plain, off + 6, rssi)
            off += WIFI_ENTRY_LEN
        print("明文(117B) hex:")
        print(plain.hex())
        print("\n解析回来:")
        for k, v in parse_plain(bytes(plain)).items():
            print(f"  {k:24s} {v}")

        msg = MAGIC + b"\x00" * RSA_BLOCK_LEN
        enc = escape_7bit(msg)
        dec = unescape_7bit(enc)
        print(f"\n7-bit 往返: {'OK' if dec == msg else 'FAIL'}  ({len(msg)}B → {len(enc)}B)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
