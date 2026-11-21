#!/usr/bin/env python3
"""Sinh tests/data/frombytes_vectors.txt cho P2.22: `FromBytes` tự viết.

Bản tham chiếu Python, viết độc lập với `kernel-cap/src/frombytes.rs`
(`check_exact`/`check_prefix`, chạy bằng `cargo test` trên host) và với
`kernel-frame/src/frombytes.rs` (phép ép con trỏ thật, chạy lúc boot trong QEMU
trên cả ba kiến trúc). Cả hai bản Rust đọc cùng tệp vector này.

Quy tắc (đổi thì phải đổi cả ba bản + vector):
  1. Kích thước kiểu = 0 ⇒ `zero_sized` (không có trong vector: mọi kiểu ở đây
     đều > 0; kiểm riêng bằng test đơn vị).
  2. Độ dài trước: len < size ⇒ `too_short`; chế độ `exact` và len > size ⇒
     `length_mismatch`; chế độ `prefix` nhận len ≥ size (phần dư trả lại).
  3. Rồi căn chỉnh: địa chỉ đầu % align ≠ 0 ⇒ `misaligned`.
  4. Còn lại ⇒ `ok`.

Địa chỉ đầu = (gốc đệm, căn 16) + `lệch`, nên `lệch % align` quyết định căn
chỉnh. Kích thước/căn chỉnh của từng kiểu (đích 64 bit: x86_64, aarch64,
riscv64) ghi ở dòng `type`; bản Rust kiểm `size_of`/`align_of` khớp dòng đó —
struct bị thêm đệm hay đổi trường sẽ làm test đỏ.

  python3 scripts/gen_frombytes_vectors.py          # ghi tệp
  python3 scripts/gen_frombytes_vectors.py --check  # CI: tệp có lỗi thời không
"""
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "data", "frombytes_vectors.txt")
BUF = 64  # đệm thử trong nhân: 64 byte, căn 16

# tên, size, align — khớp kernel-cap/src/frombytes.rs
TYPES = [
    ("u8", 1, 1),
    ("u16", 2, 2),
    ("u32", 4, 4),
    ("u64", 8, 8),
    ("le32", 4, 1),
    ("u32x3", 12, 4),   # [u32; 3]
    ("demo_header", 16, 8),  # { magic: Le32, version: Le16, flags: Le16, length: u64 }
    ("le_record", 8, 1),     # { a: Le16, b: Le32, c: Le16 }
]
OFFSETS = [0, 1, 3, 4, 8]
MODES = ["exact", "prefix"]


def expect(size, align, mode, length, off):
    if size == 0:
        return "zero_sized"
    if length < size:
        return "too_short"
    if mode == "exact" and length > size:
        return "length_mismatch"
    if off % align != 0:
        return "misaligned"
    return "ok"


def cases():
    out = []
    for name, size, align in TYPES:
        lens = sorted({0, max(size - 1, 0), size, size + 3})
        for mode in MODES:
            for length in lens:
                for off in OFFSETS:
                    if off + length > BUF:
                        continue
                    out.append((name, mode, length, off, expect(size, align, mode, length, off)))
    return out


def render():
    lines = [
        "# frombytes_vectors.txt — sinh bởi scripts/gen_frombytes_vectors.py (P2.22). Đừng sửa tay.",
        "# type <kiểu> <size> <align>",
        "# <kiểu> <exact|prefix> <độ-dài> <lệch> <ok|too_short|length_mismatch|misaligned>",
    ]
    for name, size, align in TYPES:
        lines.append("type %s %d %d" % (name, size, align))
    cs = cases()
    for c in cs:
        lines.append("%s %s %d %d %s" % c)
    return "\n".join(lines) + "\n", cs


def main():
    text, cs = render()
    kinds = {}
    for c in cs:
        kinds[c[4]] = kinds.get(c[4], 0) + 1
    summary = ", ".join("%s %d" % (k, kinds[k]) for k in sorted(kinds))
    if "--check" in sys.argv:
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur != text:
            print("frombytes_vectors.txt lỗi thời: chạy scripts/gen_frombytes_vectors.py", file=sys.stderr)
            return 1
        print("frombytes_vectors.txt khớp (%d ca: %s)" % (len(cs), summary))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(text)
    print("đã ghi %s (%d ca: %s)" % (os.path.relpath(OUT), len(cs), summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
