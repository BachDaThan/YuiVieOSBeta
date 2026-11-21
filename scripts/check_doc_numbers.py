#!/usr/bin/env python3
"""P0.16 — số liệu trong tài liệu phải khớp mã.

Ba luật:

1. **`unsafe` trong `kernel-frame` đếm theo loại.** Mỗi từ khoá `unsafe` (đã bỏ
   chú thích/chuỗi) được xếp vào: khối `unsafe {}`, `unsafe fn` (kể cả
   `unsafe extern "C" fn`), `unsafe impl`, `unsafe trait`, `unsafe extern {}`,
   thuộc tính `#[unsafe(...)]`. Tài liệu chỉ được nêu số bằng **câu chuẩn**
   ``N khối `unsafe {}` + M `unsafe fn` + K `unsafe impl` `` — câu chuẩn nào lệch
   số đếm thật ⇒ đỏ; câu kiểu cũ "N khối unsafe" (không rõ đếm gì) trong các tệp
   được kiểm ⇒ đỏ. Loại lạ (không thuộc ba loại trên) ⇒ đỏ cho tới khi có
   người thêm vào câu chuẩn.
2. **Số check ở dòng P0 của PLAN §0** (``nay **N** check = X C++17 + Y C11``)
   phải bằng tổng các dòng ``✓ …: N checks passed, 0 failed`` trong log của
   `make test` (`build/test-logs/*.log`). Chưa có log (chưa chạy `make test`,
   ví dụ job tĩnh của CI) ⇒ bỏ qua, có in ra.
3. **README không chứa số chưa kiểm được** (khớp P7.15):
   - mỗi ``N check`` phải nằm trên dòng nêu đúng MỘT tệp `tests/test_*.c[pp]`
     và bằng số check của test đó trong log; ``N test`` (không kiểm được từ
     `make test`) bị cấm;
   - ``make test  # N kiểm thử (X C++17 + Y C11 ABI)`` phải khớp log;
   - số hiệu năng (ms, µs, ns, MB/s, GB/s, tok/s, FPS) chỉ được có trên dòng
     mang chú thích ``<!-- số-đo: <nguồn> -->`` (máy + người đo + ngày/commit).

Dùng: ``python3 scripts/check_doc_numbers.py [--logs DIR]``; thoát 0 khi đạt.
Kiểm thử: ``scripts/test_check_doc_numbers.py``.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from verify import strip_rust  # noqa: E402  (verify.py có `if __name__ == "__main__"`)

KINDS = ("block", "fn", "impl", "trait", "extern", "attr", "other")
CANON_KINDS = ("block", "fn", "impl")  # ba loại có trong câu chuẩn
CANON_RE = re.compile(r"(\d+) khối `unsafe \{\}` \+ (\d+) `unsafe fn` \+ (\d+) `unsafe impl`")
# Câu kiểu cũ trên dòng có nhắc `unsafe`: "36 khối unsafe", "Tổng: 29 khối" …
LOOSE_RE = re.compile(r"(?<![\w.])(\d+) khối\b")
# Tệp được kiểm luật 1: toàn bộ các tệp này + dòng P2.1 của PLAN.
UNSAFE_DOCS = ("README.md", "docs/BUILD.md", "docs/ARCHITECTURE.md", "docs/SECURITY.md",
               "kernel-frame/README.md")
PLAN_UNSAFE_ROWS = ("| P2.1 |",)

PASS_RE = re.compile(r"✓ ([^:]+): (\d+) checks passed, 0 failed")
FAIL_RE = re.compile(r"✗ ([^:]+): (\d+) of (\d+) checks FAILED")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
P0_RE = re.compile(r"nay \*\*(\d+)\*\* check = (\d+) C\+\+17 \+ (\d+) C11")
README_TOTAL_RE = re.compile(r"make test\s+#\s*(\d+) kiểm thử \((\d+) C\+\+17 \+ (\d+) C11")
CHECK_RE = re.compile(r"(?<![\w.])(\d+) check\b")
TEST_WORD_RE = re.compile(r"(?<![\w.])(\d+) test\b")
TEST_FILE_RE = re.compile(r"tests/(test_\w+)\.(?:cpp|c)\b")
PERF_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?\s?(?:ms|µs|us|ns|MB/s|GB/s|tok/s|FPS|fps)\b")
MEASURED_TAG = re.compile(r"<!--\s*số-đo:\s*\S[^>]*-->")
C11_TEST = "test_capi"


# ------------------------------------------------------------------ luật 1 --
def classify_unsafe(clean: str) -> Counter:
    """Đếm `unsafe` theo loại trong mã Rust đã bỏ chú thích/chuỗi."""
    c: Counter = Counter()
    for m in re.finditer(r"\bunsafe\b", clean):
        rest = clean[m.end():].lstrip()
        before = clean[: m.start()].rstrip()
        if rest.startswith("{"):
            c["block"] += 1
        elif re.match(r"fn\b", rest) or re.match(r"extern\b[^{;]*?\bfn\b", rest):
            c["fn"] += 1
        elif re.match(r"impl\b", rest):
            c["impl"] += 1
        elif re.match(r"trait\b", rest):
            c["trait"] += 1
        elif re.match(r"extern\b", rest):
            c["extern"] += 1
        elif rest.startswith("(") and before.endswith("["):
            c["attr"] += 1
        else:
            c["other"] += 1
    return c


def count_frame_unsafe(frame_src: pathlib.Path) -> Counter:
    total: Counter = Counter()
    for path in sorted(frame_src.rglob("*.rs")):
        total += classify_unsafe(strip_rust(path.read_text(encoding="utf-8")))
    return total


def canon_phrase(c: Counter) -> str:
    return f"{c['block']} khối `unsafe {{}}` + {c['fn']} `unsafe fn` + {c['impl']} `unsafe impl`"


def check_unsafe_text(text: str, where: str, c: Counter) -> list[str]:
    """Lỗi của luật 1 trên một đoạn văn bản."""
    errs = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for m in CANON_RE.finditer(line):
            got = tuple(int(x) for x in m.groups())
            want = tuple(c[k] for k in CANON_KINDS)
            if got != want:
                errs.append(f"{where}:{line_no}: ghi \"{m.group(0)}\" nhưng đếm được \"{canon_phrase(c)}\"")
        if "unsafe" not in line:
            continue
        spans = [m.span() for m in CANON_RE.finditer(line)]
        for m in LOOSE_RE.finditer(line):
            if any(a <= m.start() < b for a, b in spans):
                continue
            errs.append(f"{where}:{line_no}: \"{m.group(0)}\" không nói rõ đếm gì — "
                        f"dùng câu chuẩn \"{canon_phrase(c)}\"")
    return errs


def rule_unsafe(root: pathlib.Path) -> tuple[list[str], str]:
    c = count_frame_unsafe(root / "kernel-frame/src")
    errs = []
    odd = {k: c[k] for k in KINDS if k not in CANON_KINDS and c[k]}
    if odd:
        errs.append(f"kernel-frame có unsafe loại ngoài câu chuẩn {odd} — cập nhật câu chuẩn và tài liệu")
    for rel in UNSAFE_DOCS:
        p = root / rel
        if p.is_file():
            errs += check_unsafe_text(p.read_text(encoding="utf-8"), rel, c)
    plan = root / "docs/PLAN.md"
    if plan.is_file():
        lines = plan.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines, 1):
            if line.startswith(PLAN_UNSAFE_ROWS):
                errs += [e.replace("docs/PLAN.md:1:", f"docs/PLAN.md:{i}:")
                         for e in check_unsafe_text(line, "docs/PLAN.md", c)]
    return errs, canon_phrase(c)


# ------------------------------------------------------------------ luật 2 --
def parse_logs(logs: pathlib.Path) -> tuple[dict[str, int], list[str]]:
    """{tên test (theo tên tệp log): số check}, lỗi (log thiếu dòng tổng/thất bại)."""
    counts: dict[str, int] = {}
    errs: list[str] = []
    for p in sorted(logs.glob("*.log")):
        text = ANSI_RE.sub("", p.read_text(encoding="utf-8", errors="replace"))
        passed = PASS_RE.findall(text)
        if FAIL_RE.search(text):
            errs.append(f"{p.name}: có check thất bại")
        elif len(passed) != 1:
            errs.append(f"{p.name}: cần đúng một dòng \"✓ …: N checks passed, 0 failed\", có {len(passed)}")
        else:
            counts[p.stem] = int(passed[0][1])
    return counts, errs


def makefile_tests(root: pathlib.Path) -> list[str]:
    mk = (root / "Makefile").read_text(encoding="utf-8")
    m = re.search(r"^TESTS\s*:=((?:.*\\\n)*.*)$", mk, re.M)
    if not m:
        return []
    return m.group(1).replace("\\\n", " ").split() + [C11_TEST]


def totals(counts: dict[str, int]) -> tuple[int, int, int]:
    c11 = counts.get(C11_TEST, 0)
    total = sum(counts.values())
    return total, total - c11, c11


def rule_p0(root: pathlib.Path, counts: dict[str, int]) -> list[str]:
    plan = (root / "docs/PLAN.md").read_text(encoding="utf-8")
    row = next((l for l in plan.splitlines() if l.startswith("| **P0** |")), None)
    if row is None:
        return ["docs/PLAN.md: không thấy dòng \"| **P0** |\" ở bảng trạng thái"]
    m = P0_RE.search(row)
    if not m:
        return ["docs/PLAN.md dòng P0: không thấy \"nay **N** check = X C++17 + Y C11\""]
    got = tuple(int(x) for x in m.groups())
    want = totals(counts)
    if got != want:
        return [f"docs/PLAN.md dòng P0 ghi {got[0]} = {got[1]} + {got[2]} nhưng make test cho "
                f"{want[0]} = {want[1]} C++17 + {want[2]} C11"]
    return []


# ------------------------------------------------------------------ luật 3 --
def rule_readme(text: str, counts: dict[str, int] | None) -> list[str]:
    """`counts` = None khi chưa có log: vẫn kiểm phần không cần log."""
    errs = []
    for line_no, line in enumerate(text.splitlines(), 1):
        where = f"README.md:{line_no}"
        for m in TEST_WORD_RE.finditer(line):
            errs.append(f"{where}: \"{m.group(0)}\" không kiểm được từ make test — bỏ số hoặc trỏ tới tests/…")
        for m in PERF_RE.finditer(line):
            if not MEASURED_TAG.search(line):
                errs.append(f"{where}: số hiệu năng \"{m.group(0)}\" thiếu chú thích <!-- số-đo: nguồn -->")
        checks = CHECK_RE.findall(line)
        if checks:
            files = sorted(set(TEST_FILE_RE.findall(line)))
            if len(files) != 1:
                errs.append(f"{where}: \"{checks[0]} check\" cần nằm trên dòng nêu đúng một tệp tests/test_*"
                            f" (thấy {len(files)})")
            elif len(checks) != 1:
                errs.append(f"{where}: nhiều số check trên một dòng ({', '.join(checks)}) — không gán được cho test nào")
            elif counts is not None:
                want = counts.get(files[0])
                if want is None:
                    errs.append(f"{where}: {files[0]} không có trong log make test")
                elif int(checks[0]) != want:
                    errs.append(f"{where}: ghi {checks[0]} check cho {files[0]}, make test cho {want}")
        m = README_TOTAL_RE.search(line)
        if m and counts is not None:
            got = tuple(int(x) for x in m.groups())
            want = totals(counts)
            if got != want:
                errs.append(f"{where}: ghi {got[0]} kiểm thử ({got[1]} + {got[2]}) nhưng make test cho "
                            f"{want[0]} ({want[1]} + {want[2]})")
    return errs


# ------------------------------------------------------------------- chạy --
def run(root: pathlib.Path, logs: pathlib.Path) -> tuple[list[str], list[str]]:
    """(lỗi, thông tin)."""
    errs, info = [], []
    e, phrase = rule_unsafe(root)
    errs += e
    info.append(f"kernel-frame: {phrase}")
    counts = None
    if logs.is_dir() and any(logs.glob("*.log")):
        counts, e = parse_logs(logs)
        errs += e
        missing = [t for t in makefile_tests(root) if t not in counts]
        if missing:
            errs.append(f"log make test thiếu: {', '.join(missing)} (chạy lại make test)")
        errs += rule_p0(root, counts)
        t = totals(counts)
        info.append(f"make test: {t[0]} check = {t[1]} C++17 + {t[2]} C11 ({len(counts)} test)")
    else:
        info.append(f"chưa có log make test ở {logs.relative_to(root) if logs.is_relative_to(root) else logs}"
                    " — bỏ qua so số check (chạy make test trước)")
    readme = root / "README.md"
    errs += rule_readme(readme.read_text(encoding="utf-8"), counts)
    return errs, info


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--logs", default=None, help="thư mục log của make test (mặc định build/test-logs)")
    a = ap.parse_args(argv)
    root = pathlib.Path(a.root).resolve()
    logs = pathlib.Path(a.logs).resolve() if a.logs else root / "build/test-logs"
    errs, info = run(root, logs)
    for e in errs:
        print(f"FAIL {e}")
    if errs:
        return 1
    print("số liệu tài liệu khớp mã: " + "; ".join(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
