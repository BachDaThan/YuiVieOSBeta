#!/usr/bin/env python3
"""Kiểm thử bộ kiểm số liệu tài liệu P0.16 (scripts/check_doc_numbers.py).

1. Đơn vị: phân loại `unsafe` (khối/fn/impl/trait/extern/thuộc tính; bỏ chú
   thích và chuỗi), câu chuẩn đúng/lệch/kiểu cũ, đọc log `make test`, luật
   README (số check gắn với đúng một test, cấm "N test", số hiệu năng cần
   chú thích `số-đo`), dòng P0 của PLAN.
2. Đầu-cuối: chép tài liệu + `kernel-frame/src` của repo sang thư mục tạm, chạy
   với log thật (nếu đã `make test`) ⇒ xanh; sửa một số trong README hoặc thêm
   một khối `unsafe` ⇒ đỏ và nêu đúng chỗ.
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import check_doc_numbers as cd  # noqa: E402
from verify import strip_rust  # noqa: E402

checks = 0
failed = 0


def check(cond: bool, what: str) -> None:
    global checks, failed
    checks += 1
    if cond:
        print(f"  ok     {what}")
    else:
        failed += 1
        print(f"  FAIL   {what}")


def kinds(src: str) -> dict[str, int]:
    return {k: v for k, v in cd.classify_unsafe(strip_rust(src)).items() if v}


# ── 1. phân loại unsafe ──
check(kinds("fn f() { unsafe { g() } }") == {"block": 1}, "khối unsafe {}")
check(kinds("pub unsafe fn f() {}") == {"fn": 1}, "unsafe fn")
check(kinds('unsafe extern "C" fn f() {}') == {"fn": 1}, 'unsafe extern "C" fn tính là fn')
check(kinds("unsafe impl Send for X {}\nunsafe impl Sync for X {}") == {"impl": 2}, "unsafe impl ×2")
check(kinds("unsafe trait T {}") == {"trait": 1}, "unsafe trait")
check(kinds('unsafe extern "C" { fn x(); }') == {"extern": 1}, "khối unsafe extern")
check(kinds("#[unsafe(no_mangle)]\nfn f() {}") == {"attr": 1}, "thuộc tính #[unsafe(..)]")
check(kinds("// unsafe { x }\n/* unsafe fn */ fn f() {}") == {}, "chú thích không bị đếm")
check(kinds('fn f() { let s = "unsafe { x }"; }') == {}, "chuỗi không bị đếm")
check(kinds("let unsafe_ptr = 1; fn not_unsafe() {}") == {}, "tên chứa chữ unsafe không bị đếm")
check(kinds("unsafe\n    {\n x }") == {"block": 1}, "khối unsafe xuống dòng")

C = Counter(block=29, fn=5, impl=2)
canon = cd.canon_phrase(C)
check(canon == "29 khối `unsafe {}` + 5 `unsafe fn` + 2 `unsafe impl`", "câu chuẩn đúng dạng")
check(cd.check_unsafe_text(f"a {canon} b", "x.md", C) == [], "câu chuẩn khớp ⇒ không lỗi")
e = cd.check_unsafe_text("có 30 khối `unsafe {}` + 5 `unsafe fn` + 2 `unsafe impl`", "x.md", C)
check(len(e) == 1 and "x.md:1" in e[0] and "30 khối" in e[0], "câu chuẩn lệch số ⇒ lỗi có dòng")
e = cd.check_unsafe_text("dòng 1\nkernel-frame có 36 khối unsafe", "x.md", C)
check(len(e) == 1 and "x.md:2" in e[0], "câu kiểu cũ \"36 khối unsafe\" ⇒ lỗi")
e = cd.check_unsafe_text("unsafe ở 7 tệp. Tổng hiện tại: 29 khối.", "x.md", C)
check(len(e) == 1, "\"29 khối\" trên dòng nhắc unsafe nhưng không theo câu chuẩn ⇒ lỗi")
check(cd.check_unsafe_text("bảng có 36 khối màu", "x.md", C) == [], "dòng không nhắc unsafe ⇒ bỏ qua")

# ── 2. log make test ──
with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    (d / "test_a.log").write_text("  ok x\n\n\x1b[32m✓ test_a: 10 checks passed, 0 failed\x1b[0m\n", encoding="utf-8")
    (d / "test_capi.log").write_text("ok\n\n✓ test_capi: 3 checks passed, 0 failed\n", encoding="utf-8")
    (d / "test_b.log").write_text("\x1b[31m✗ test_b: 1 of 5 checks FAILED\x1b[0m\n", encoding="utf-8")
    (d / "test_c.log").write_text("bị ngắt giữa chừng\n", encoding="utf-8")
    counts, errs = cd.parse_logs(d)
    check(counts == {"test_a": 10, "test_capi": 3}, "đọc số check, bỏ mã màu ANSI")
    check(any("test_b" in x and "thất bại" in x for x in errs), "log có check thất bại ⇒ lỗi")
    check(any("test_c" in x for x in errs), "log thiếu dòng tổng ⇒ lỗi")
    check(cd.totals(counts) == (13, 10, 3), "tổng = C++17 + C11 (test_capi)")

# ── 3. luật README ──
cnt = {"test_hw": 290, "test_capi": 66, "test_x": 5}
R = cd.rule_readme
check(R("| a | `tests/test_hw.cpp` (290 check) |", cnt) == [], "số check khớp test ⇒ đạt")
e = R("| a | `tests/test_hw.cpp` (291 check) |", cnt)
check(len(e) == 1 and "291" in e[0] and "290" in e[0], "số check lệch ⇒ lỗi nêu cả hai số")
check(len(R("| a | `x/` (129 check) |", cnt)) == 1, "số check không gắn tệp test ⇒ lỗi")
check(len(R("| `tests/test_hw.cpp`, `tests/test_capi.c` (290 check) |", cnt)) == 1, "hai tệp test một số ⇒ lỗi")
check(len(R("| `tests/test_hw.cpp` (290 check, phần con 29 check) |", cnt)) == 1, "hai số check một dòng ⇒ lỗi")
check(len(R("| `tests/test_zz.cpp` (1 check) |", cnt)) == 1, "test không có trong log ⇒ lỗi")
check(R("| `tests/test_hw.cpp` (999 check) |", None) == [], "chưa có log ⇒ không so số check")
check(len(R("| ✅ 246 test | ime |", None)) == 1, "\"N test\" bị cấm cả khi chưa có log")
check(len(R("D-Bus avg 7.16 ms", None)) == 1, "số hiệu năng thiếu chú thích ⇒ lỗi")
check(len(R("đạt 120 MB/s và 30 FPS", None)) == 2, "MB/s, FPS ⇒ hai lỗi")
check(R("D-Bus avg 7.16 ms <!-- số-đo: máy X, 2026-11-16 -->", None) == [], "có chú thích số-đo ⇒ đạt")
check(len(R("x 7 ms <!-- số-đo: -->", None)) == 1, "chú thích số-đo rỗng ⇒ vẫn lỗi")
check(R("thử trong 60 giây, 100 % clean-room, 70 %/15 s", None) == [], "giây/% không phải số hiệu năng")
check(R("make test   # 361 kiểm thử (295 C++17 + 66 C11 ABI)", cnt) == [], "dòng tổng make test khớp")
check(len(R("make test   # 360 kiểm thử (294 C++17 + 66 C11 ABI)", cnt)) == 1, "dòng tổng make test lệch ⇒ lỗi")

# ── 4. dòng P0 + đầu-cuối ──
FILES = ["README.md", "docs/PLAN.md", "docs/BUILD.md", "docs/ARCHITECTURE.md", "docs/SECURITY.md", "Makefile"]


def make_copy(dst: pathlib.Path) -> None:
    for f in FILES:
        (dst / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / f, dst / f)
    shutil.copytree(ROOT / "kernel-frame/src", dst / "kernel-frame/src")


with tempfile.TemporaryDirectory() as td:
    d = pathlib.Path(td)
    make_copy(d)
    plan = d / "docs/PLAN.md"
    logs = d / "logs"
    logs.mkdir()
    (logs / "test_a.log").write_text("✓ test_a: 7 checks passed, 0 failed\n", encoding="utf-8")
    (logs / "test_capi.log").write_text("✓ test_capi: 2 checks passed, 0 failed\n", encoding="utf-8")
    e = cd.rule_p0(d, {"test_a": 7, "test_capi": 2})
    check(len(e) == 1 and "9 = 7 C++17 + 2 C11" in e[0], "dòng P0 lệch log ⇒ lỗi nêu số đúng")
    text = plan.read_text(encoding="utf-8")
    import re as _re
    text2 = _re.sub(r"nay \*\*\d+\*\* check = \d+ C\+\+17 \+ \d+ C11", "nay **9** check = 7 C++17 + 2 C11", text, 1)
    plan.write_text(text2, encoding="utf-8")
    check(cd.rule_p0(d, {"test_a": 7, "test_capi": 2}) == [], "dòng P0 khớp ⇒ đạt")
    # Makefile TESTS được đọc đúng và log thiếu test ⇒ lỗi.
    tests = cd.makefile_tests(d)
    check("test_hw" in tests and tests[-1] == "test_capi", "đọc danh sách TESTS từ Makefile")
    errs, _ = cd.run(d, logs)
    check(any("log make test thiếu" in x for x in errs), "log thiếu test của Makefile ⇒ lỗi")

real_logs = ROOT / "build/test-logs"
if real_logs.is_dir() and any(real_logs.glob("*.log")):
    with tempfile.TemporaryDirectory() as td:
        d = pathlib.Path(td)
        make_copy(d)
        errs, info = cd.run(d, real_logs)
        for x in errs:
            print(f"         {x}")
        check(errs == [], "repo thật + log make test thật ⇒ đạt")
        readme = d / "README.md"
        t = readme.read_text(encoding="utf-8")
        assert "`tests/test_hw.cpp` (" in t
        i = t.index("`tests/test_hw.cpp` (")
        j = t.index(" check", i)
        n = int(t[t.index("(", i) + 1:j])
        readme.write_text(t[:t.index("(", i) + 1] + str(n + 1) + t[j:], encoding="utf-8")
        errs, _ = cd.run(d, real_logs)
        check(len(errs) == 1 and "test_hw" in errs[0], "sửa 1 số check trong README ⇒ đỏ đúng một lỗi")
        readme.write_text(t, encoding="utf-8")
        boot = d / "kernel-frame/src/console.rs"
        boot.write_text(boot.read_text(encoding="utf-8") + "\nfn _p0_16() { unsafe { } }\n", encoding="utf-8")
        errs, _ = cd.run(d, real_logs)
        check(len(errs) >= 3 and all("30 khối" in x or "đếm được" in x for x in errs),
              "thêm 1 khối unsafe ⇒ mọi câu chuẩn trong tài liệu đỏ")
else:
    print("  (bỏ qua phần đầu-cuối với log thật: chưa chạy make test)")

print(f"\n{'✓' if failed == 0 else '✗'} test_check_doc_numbers: {checks - failed}/{checks} check đạt")
sys.exit(1 if failed else 0)
