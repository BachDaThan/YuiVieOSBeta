#!/usr/bin/env python3
"""Static verification for YuiVieOS Beta (no cargo/qemu needed).

Checks, in order:
  1. the monorepo layout the docs promise actually exists;
  2. every shipped sandbox policy and the micro-VM schema parse;
  3. no Rust source outside `kernel-frame/` contains `unsafe` (the whole repo
     is scanned, so a new crate cannot slip past); the single hardware frame
     (`kernel-frame/`) is the only place where `unsafe` may appear, and only in
     the files that touch hardware; all Rust sources have balanced brackets;
  4. internal documentation links resolve;
  5. every repository path quoted in the docs exists;
  6. sources are LF-only;
  7. no secrets leak (P7.3) and the "no spoofing / no check evasion" boundary
     holds (P7.10, scripts/check_boundaries.py);
  8. numbers quoted in the docs match the code: `unsafe` counted by kind,
     the P0 check total and README check counts vs. the `make test` logs,
     no untagged performance numbers in README (P0.16,
     scripts/check_doc_numbers.py).

Exit code 0 only if everything passes.  Run through scripts/verify.sh.
"""
from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib  # type: ignore
    except ImportError:
        tomllib = None  # type: ignore

ROOT = pathlib.Path(__file__).resolve().parent.parent
failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  \033[32mok\033[0m   {msg}")


def bad(msg: str) -> None:
    print(f"  \033[31mFAIL\033[0m {msg}")
    failures.append(msg)


def header(msg: str) -> None:
    print(f"\n── {msg}")


# --------------------------------------------------------------------------- 1
REQUIRED_DIRS = [
    "docs", "kernel-cap", "kernel-services", "vmm-sandbox", "ai-bridge-yuid",
    "pkg-stripper", "userspace-vi", "userspace-vi/ibus", "tools", "arch", "include", "tests",
    "scripts", ".github/workflows",
]
REQUIRED_FILES = [
    "Cargo.toml", "Makefile", "README.md", "LICENSE", "include/yui/yui.h",
    "kernel-cap/src/lib.rs", "kernel-cap/src/sha256.rs", "kernel-cap/src/input.rs",
    "kernel-cap/src/sha512.rs", "kernel-cap/src/ed25519.rs",
    "kernel-cap/src/keyring.rs", "kernel-cap/src/bundle.rs",
    "kernel-services/yui-sched/src/lib.rs", "kernel-services/yui-sched/src/guard.rs",
    "kernel-services/yui-zram/src/lib.rs",
    "kernel-services/yui-zram/src/lz.rs", "kernel-services/yui-zram/src/store.rs",
    "kernel-services/ed25519.cpp", "kernel-services/bundle.cpp",
    "kernel-services/power.cpp", "kernel-services/guard.cpp",
    "kernel-services/fsstore.cpp", "kernel-services/linuxabi.cpp",
    "include/yui/ed25519.hpp", "include/yui/bundle.hpp",
    "include/yui/power.hpp", "include/yui/guard.hpp",
    "include/yui/fsstore.hpp", "include/yui/linuxabi.hpp",
    "docs/ARCHITECTURE.md", "docs/PLAN.md", "docs/PROTOCOL.md",
    "docs/SECURITY.md", "docs/FORMAT-YUIP.md", "docs/BUILD.md",
    "docs/THIRD-PARTY.md", "docs/HARDENING-P3.md",
    "tests/test_capi.c", "tests/test_ed25519.cpp", "tests/test_redteam.cpp",
    "include/yui/ime.hpp", "userspace-vi/ibus/engine.cpp",
    "userspace-vi/ibus/main.cpp", "userspace-vi/ibus/org.freedesktop.IBus.Yui.xml.in",
    "tests/test_ime.cpp",
    "include/yui/store.hpp", "pkg-stripper/store.cpp", "tools/store/main.cpp",
    "tests/test_store.cpp",
    "include/yui/hw.hpp", "kernel-services/hw.cpp", "tools/hw/main.cpp",
    "tests/test_hw.cpp", "docs/hwdb.tsv",
    "include/yui/trash.hpp", "userspace-vi/trash.cpp", "tests/test_trash.cpp",
    "include/yui/posix.hpp", "userspace-vi/posix.cpp", "tests/test_posix.cpp",
    "tools/sandbox-exec/main.cpp",
    "include/yui/archive.hpp", "pkg-stripper/archive.cpp", "pkg-stripper/zstd.cpp", "tests/test_archive.cpp",
    "tests/archive_fixtures.hpp", "scripts/gen_archive_fixtures.py",
    "scripts/check_boundaries.py", "scripts/test_check_boundaries.py",
    "scripts/check_doc_numbers.py", "scripts/test_check_doc_numbers.py",
    "include/yui/display.hpp", "userspace-vi/display.cpp", "tests/test_display.cpp",
    "kernel-cap/src/display.rs", "tests/data/display_vectors.txt", "scripts/gen_display_vectors.py",
    "kernel-cap/src/fdt.rs", "tests/data/fdt_fb_vectors.txt", "scripts/gen_fdt_vectors.py",
    "kernel-cap/src/frombytes.rs", "kernel-frame/src/frombytes.rs",
    "tests/data/frombytes_vectors.txt", "scripts/gen_frombytes_vectors.py",
    "scripts/qemu-splash-dt.sh",
    "scripts/qemu-splash.sh", "scripts/check_splash_ppm.py",
]
STALE = ["core", "crates", "sandbox", "ui"]  # old layout must not come back


def check_layout() -> None:
    header("cấu trúc monorepo")
    for name in REQUIRED_DIRS:
        (ok if (ROOT / name).is_dir() else bad)(f"thư mục {name}")
    for name in REQUIRED_FILES:
        (ok if (ROOT / name).is_file() else bad)(f"tệp {name}")
    for name in STALE:
        if (ROOT / name).exists():
            bad(f"thư mục cũ '{name}' vẫn còn — nội dung phải nằm trong cấu trúc mới")


# --------------------------------------------------------------------------- 2
def check_policies() -> None:
    header("chính sách hộp cát & schema")
    policies = sorted((ROOT / "vmm-sandbox/policies").glob("*.json"))
    if not policies:
        bad("không có policy nào trong vmm-sandbox/policies")
        return
    for path in policies:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            bad(f"{path.relative_to(ROOT)}: JSON hỏng: {exc}")
            continue
        missing = [k for k in ("app", "tier", "capabilities") if k not in data]
        if missing:
            bad(f"{path.relative_to(ROOT)}: thiếu khoá {missing}")
        elif data["tier"] not in ("native", "isolated", "microvm"):
            bad(f"{path.relative_to(ROOT)}: tier lạ '{data['tier']}'")
        else:
            ok(str(path.relative_to(ROOT)))
    schema = ROOT / "vmm-sandbox/vmm/vm-manifest.schema.json"
    try:
        json.loads(schema.read_text(encoding="utf-8"))
        ok(str(schema.relative_to(ROOT)))
    except Exception as exc:  # noqa: BLE001
        bad(f"{schema.relative_to(ROOT)}: JSON hỏng: {exc}")


def check_ibus_component() -> None:
    header("IBus component metadata")
    path = ROOT / "userspace-vi/ibus/org.freedesktop.IBus.Yui.xml.in"
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:  # noqa: BLE001 - report malformed metadata
        bad(f"{path.relative_to(ROOT)}: XML hỏng: {exc}")
        return

    component_name = root.findtext("name", default="")
    exec_path = root.findtext("exec", default="")
    engines = root.findall("./engines/engine")
    names = {engine.findtext("name", default="") for engine in engines}
    if root.tag != "component" or component_name != "org.freedesktop.IBus.Yui":
        bad(f"{path.relative_to(ROOT)}: component name/root không đúng")
    elif "@PREFIX@" not in exec_path or not exec_path.endswith("/bin/yui-ibus-engine"):
        bad(f"{path.relative_to(ROOT)}: exec phải trỏ tới binary theo PREFIX")
    elif names != {"yui-telex", "yui-vni"}:
        bad(f"{path.relative_to(ROOT)}: cần đúng hai engine yui-telex/yui-vni, có {sorted(names)}")
    elif any(engine.findtext("language") != "vi" for engine in engines):
        bad(f"{path.relative_to(ROOT)}: cả hai engine phải khai báo ngôn ngữ vi")
    else:
        ok(f"{path.relative_to(ROOT)}: Telex + VNI, ngôn ngữ vi")


# --------------------------------------------------------------------------- 3
CHAR_LITERAL = re.compile(r"'(?:\\.|[^'\\])'")


def strip_rust(src: str) -> str:
    """Remove comments, strings and char literals, keeping line structure.

    Lifetimes (`'a`, `'static`) are *not* char literals, so they are skipped
    without swallowing the following code — that mistake is what makes naive
    bracket checkers useless on Rust.
    """
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if c == "/" and nxt == "*":
            depth = 1
            i += 2
            while i < n and depth:
                if src.startswith("/*", i):
                    depth += 1
                    i += 2
                elif src.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    if src[i] == "\n":
                        out.append("\n")
                    i += 1
            continue
        if c == "r" and nxt in ('"', "#"):
            # raw string r"..." or r#"..."#
            j = i + 1
            hashes = 0
            while j < n and src[j] == "#":
                hashes += 1
                j += 1
            if j < n and src[j] == '"':
                terminator = '"' + "#" * hashes
                end = src.find(terminator, j + 1)
                end = n if end == -1 else end + len(terminator)
                out.append(" " * (end - i))
                i = end
                continue
        if c == '"':
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == '"':
                    i += 1
                    break
                if src[i] == "\n":
                    out.append("\n")
                i += 1
            continue
        if c == "'":
            m = CHAR_LITERAL.match(src, i)
            if m:
                i = m.end()
                continue
            i += 1  # lifetime or label: drop the quote only
            continue
        out.append(c)
        i += 1
    return "".join(out)


BRACKETS = {"(": ")", "[": "]", "{": "}"}


# Những tệp trong khung phần cứng được phép có `unsafe`, kèm lý do. Bất kỳ tệp
# nào khác xuất hiện `unsafe` đều là hồi quy.
FRAME_UNSAFE_FILES = {
    "arch/mod.rs": "lệnh hlt / wfi để dừng máy",
    "arch/x86_64.rs": "cổng nối tiếp (in/out), CPUID, cầu nối 32→64 bit",
    "arch/aarch64.rs": "UART PL011 qua con trỏ MMIO, đọc thanh ghi hệ thống",
    "arch/riscv64.rs": "lời gọi SBI qua ecall, đọc thanh ghi misa",
    "boot.rs": "đọc multiboot info / device tree do firmware cấp",
    "allocator.rs": "triển khai GlobalAlloc",
    "splash.rs": "ghi framebuffer tuyến tính do firmware cấp",
    "frombytes.rs": "ép &[u8] → &T zero-copy sau check của kernel-cap (P2.22, đúng 1 khối)",
    "main.rs": "thuộc tính #[global_allocator] và #![no_main] đặt ở crate root",
}


def bracket_problems(clean: str) -> list[str]:
    stack: list[tuple[str, int]] = []
    problems: list[str] = []
    line = 1
    for ch in clean:
        if ch == "\n":
            line += 1
        elif ch in BRACKETS:
            stack.append((ch, line))
        elif ch in BRACKETS.values():
            if not stack:
                problems.append(f"dòng {line}: đóng '{ch}' không có mở")
                return problems
            opener, oline = stack.pop()
            if BRACKETS[opener] != ch:
                problems.append(f"dòng {line}: '{ch}' đóng '{opener}' mở ở dòng {oline}")
                return problems
    if stack:
        problems.append(f"còn {len(stack)} ngoặc chưa đóng (gần nhất dòng {stack[-1][1]})")
    return problems


# Thư mục không phải mã nguồn của mình (sản phẩm build, phụ thuộc tải về).
RUST_SKIP_DIRS = {".git", "target", "build", "node_modules", ".venv", "vendor"}


def rust_sources_outside_frame() -> list[pathlib.Path]:
    """Mọi tệp .rs của repo trừ `kernel-frame/` (P2.22: `unsafe` chỉ ở khung).

    Quét cả repo thay vì danh sách crate cố định, để một crate Rust mới (ví dụ
    `link-core/`) không lọt khỏi luật chỉ vì chưa ai thêm nó vào danh sách.
    """
    out = []
    for path in ROOT.rglob("*.rs"):
        parts = path.relative_to(ROOT).parts
        if parts[0] == "kernel-frame" or RUST_SKIP_DIRS.intersection(parts):
            continue
        out.append(path)
    return sorted(out)


def check_rust() -> None:
    header("an toàn Rust (không unsafe, ngoặc cân)")
    sources = rust_sources_outside_frame()
    if not sources:
        bad("không tìm thấy tệp .rs nào trong crate nhân")
        return
    unsafe_found = False
    for path in sources:
        rel = path.relative_to(ROOT)
        clean = strip_rust(path.read_text(encoding="utf-8"))
        for match in re.finditer(r"\bunsafe\b", clean):
            line = clean[: match.start()].count("\n") + 1
            bad(f"{rel}:{line}: dùng 'unsafe' — crate nhân phải giữ deny(unsafe_code)")
            unsafe_found = True
        problems = bracket_problems(clean)
        if problems:
            for problem in problems:
                bad(f"{rel}: {problem}")
        else:
            ok(f"ngoặc cân: {rel}")
    if not unsafe_found:
        ok("không có 'unsafe' trong crate nhân")


def parse_enum_cpp(src: str, name: str) -> list[tuple[str, int]] | None:
    m = re.search(r"enum\s+class\s+" + name + r"\s*\{(.*?)\};", src, re.S)
    if not m:
        return None
    body = re.sub(r"//[^\n]*", "", m.group(1))
    out, nxt = [], 0
    for item in (x.strip() for x in body.split(",")):
        if not item:
            continue
        if "=" in item:
            n, v = (t.strip() for t in item.split("=", 1))
            nxt = int(v, 0)
        else:
            n = item
        out.append((n, nxt))
        nxt += 1
    return out


def parse_enum_rust(src: str, name: str) -> list[tuple[str, int]] | None:
    m = re.search(r"pub\s+enum\s+" + name + r"\s*\{(.*?)\}", src, re.S)
    if not m:
        return None
    body = re.sub(r"//[^\n]*", "", m.group(1))
    out, nxt = [], 0
    for item in (x.strip() for x in body.split(",")):
        if not item:
            continue
        if "=" in item:
            n, v = (t.strip() for t in item.split("=", 1))
            nxt = int(v, 0)
        else:
            n = item
        out.append((n, nxt))
        nxt += 1
    return out


# Enum dùng chung C++ ↔ Rust: (tệp C++, tệp Rust, tên enum).
MIRRORED_ENUMS = [
    ("include/yui/sandbox.hpp", "kernel-cap/src/input.rs", "InputSourceKind"),
    ("include/yui/sandbox.hpp", "kernel-cap/src/input.rs", "InputPrivilege"),
    ("include/yui/display.hpp", "kernel-cap/src/display.rs", "PickReason"),
    ("include/yui/display.hpp", "kernel-cap/src/fdt.rs", "FdtReason"),
]


def check_mirrored_enums() -> None:
    header("enum phản chiếu C++ ↔ Rust (P2.21)")
    for cpp, rs, name in MIRRORED_ENUMS:
        a = parse_enum_cpp((ROOT / cpp).read_text(encoding="utf-8"), name)
        b = parse_enum_rust((ROOT / rs).read_text(encoding="utf-8"), name)
        if a is None or b is None:
            bad(f"không tìm thấy enum {name} ở {cpp if a is None else rs}")
        elif a != b:
            bad(f"{name} lệch: C++ {a} ≠ Rust {b}")
        else:
            ok(f"{name}: {len(a)} biến thể khớp ({', '.join(n for n, _ in a)})")


def check_frame() -> None:
    """Khung phần cứng: `unsafe` chỉ được phép ở những tệp đã được kiểm toán."""
    header("khung phần cứng (unsafe có kiểm soát)")
    frame = ROOT / "kernel-frame"
    if not frame.is_dir():
        bad("thiếu thư mục kernel-frame")
        return
    required = ["Cargo.toml", "src/main.rs", "src/arch/mod.rs", "src/boot.rs",
                "src/console.rs", "src/profiler.rs", "src/cap.rs", "src/splash.rs",
                "src/allocator.rs", "src/frombytes.rs"]
    for name in required:
        (ok if (frame / name).is_file() else bad)(f"kernel-frame/{name}")

    lib = (frame / "src/main.rs").read_text(encoding="utf-8")
    if "deny(unsafe_code)" in lib.replace(" ", ""):
        bad("kernel-frame/src/main.rs: khung phần cứng không thể deny(unsafe_code) — "
            "hãy để lệnh cấm ở các crate an toàn, không ở khung")
    else:
        ok("khung không tuyên bố deny(unsafe_code) (đúng: unsafe nằm ở đây)")

    total = 0
    rogue: list[str] = []
    for path in sorted((frame / "src").rglob("*.rs")):
        rel = path.relative_to(frame / "src").as_posix()
        clean = strip_rust(path.read_text(encoding="utf-8"))
        problems = bracket_problems(clean)
        if problems:
            for problem in problems:
                bad(f"kernel-frame/src/{rel}: {problem}")
        else:
            ok(f"ngoặc cân: kernel-frame/src/{rel}")
        count = len(re.findall(r"\bunsafe\b", clean))
        total += count
        if count and rel not in FRAME_UNSAFE_FILES:
            rogue.append(rel)
            bad(f"kernel-frame/src/{rel}: có unsafe nhưng không nằm trong danh sách "
                f"kiểm toán ({', '.join(sorted(FRAME_UNSAFE_FILES))})")
    if not rogue:
        ok(f"{total} khối unsafe, tất cả nằm trong tệp đã kiểm toán")

    # Mỗi kiến trúc phải có mặt và mỗi kiến trúc phải in được banner thành công.
    for arch in ("x86_64", "aarch64", "riscv64"):
        path = frame / "src" / "arch" / f"{arch}.rs"
        if not path.is_file():
            bad(f"thiếu nhánh kiến trúc {arch}")
            continue
        text = path.read_text(encoding="utf-8")
        if "kmain" not in text:
            bad(f"kernel-frame/src/arch/{arch}.rs: không gọi vào kmain")
        else:
            ok(f"nhánh {arch} gọi kmain")

    # Lời hứa với CI: banner "yui: ready" phải tồn tại đâu đó trong khung.
    if "yui: ready" not in lib:
        bad("kernel-frame/src/main.rs: thiếu banner 'yui: ready' mà qemu-smoke.sh chờ")
    else:
        ok("banner 'yui: ready' có trong khung")


def load_toml(path: pathlib.Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)
    data: dict[str, dict] = {}
    current_sec = ""
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current_sec = line[1:-1].strip()
            data.setdefault(current_sec, {})
            continue
        if "=" in line and current_sec:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if v.startswith("{") and v.endswith("}"):
                inner: dict[str, str] = {}
                for part in v[1:-1].split(","):
                    if "=" in part:
                        ik, iv = part.split("=", 1)
                        inner[ik.strip()] = iv.strip().strip('"\' ')
                data[current_sec][k] = inner
            else:
                data[current_sec][k] = v.strip('"\' ')
    return data


def check_kernel_dependencies() -> None:
    """Tầng 1-2 không dependency ngoài (P0.14)."""
    header("kiểm tra dependency Tầng 1–2 (không dependency ngoài)")
    tier_crates = [ROOT / "kernel-cap/Cargo.toml"]
    tier_crates.extend(sorted((ROOT / "kernel-services").glob("*/Cargo.toml")))

    dep_sections = ("dependencies", "dev-dependencies", "build-dependencies")

    for cargo_path in tier_crates:
        if not cargo_path.is_file():
            continue
        rel = cargo_path.relative_to(ROOT)
        data = load_toml(cargo_path)
        has_dep = False
        crate_failed = False
        for sec in dep_sections:
            deps = data.get(sec, {})
            for name, spec in deps.items():
                has_dep = True
                if isinstance(spec, str):
                    bad(f"{rel}: dependency '{name} = \"{spec}\"' không phải path nội bộ (cấm dependency ngoài)")
                    crate_failed = True
                elif isinstance(spec, dict):
                    path_val = spec.get("path")
                    if not path_val:
                        bad(f"{rel}: dependency '{name}' thiếu 'path' (cấm dependency ngoài)")
                        crate_failed = True
                    else:
                        target = (cargo_path.parent / path_val).resolve()
                        if not target.exists() or not str(target).startswith(str(ROOT)):
                            bad(f"{rel}: dependency '{name}' có path '{path_val}' nằm ngoài repo")
                            crate_failed = True
                else:
                    bad(f"{rel}: dependency '{name}' không hợp lệ (cấm dependency ngoài)")
                    crate_failed = True
        if not crate_failed:
            if not has_dep:
                ok(f"{rel}: [dependencies] rỗng, 0 dependency ngoài")
            else:
                ok(f"{rel}: tất cả dependency đều là path nội bộ trong repo")

    frame_cargo = ROOT / "kernel-frame/Cargo.toml"
    if frame_cargo.is_file():
        rel = frame_cargo.relative_to(ROOT)
        data = load_toml(frame_cargo)
        frame_failed = False
        for sec in dep_sections:
            deps = data.get(sec, {})
            for name, spec in deps.items():
                if name != "yui-cap":
                    bad(f"{rel}: dependency '{name}' không được phép (chỉ được phụ thuộc yui-cap)")
                    frame_failed = True
                else:
                    if not isinstance(spec, dict) or "path" not in spec:
                        bad(f"{rel}: yui-cap phải dùng path dependency trong repo")
                        frame_failed = True
                    else:
                        target = (frame_cargo.parent / spec["path"]).resolve()
                        if not target.exists() or not str(target).startswith(str(ROOT)):
                            bad(f"{rel}: yui-cap có path '{spec['path']}' nằm ngoài repo")
                            frame_failed = True
        if not frame_failed:
            ok(f"{rel}: chỉ phụ thuộc yui-cap nội bộ")


def check_third_party() -> None:
    """Kiểm tra tài liệu giấy phép thành phần ngoài và rà soát vendor (P7.2)."""
    header("thành phần bên thứ ba & rà soát giấy phép (P7.2)")
    third_party_doc = ROOT / "docs/THIRD-PARTY.md"
    if not third_party_doc.is_file():
        bad("docs/THIRD-PARTY.md không tồn tại")
        return

    content = third_party_doc.read_text(encoding="utf-8")
    required_components = [
        "Wine", "VKD3D-Proton", "DXVK", "Waydroid", "Box64", "FEX-Emu", "MangoHud"
    ]
    missing = [c for c in required_components if c not in content]
    if missing:
        bad(f"docs/THIRD-PARTY.md thiếu mục cho các thành phần: {missing}")
    else:
        ok("docs/THIRD-PARTY.md bao phủ đủ 7 thành phần ngoài dự kiến")

    vendor_dir = ROOT / "vendor"
    if vendor_dir.exists():
        bad("phát hiện thư mục 'vendor/' — mã nguồn ngoài chưa được phê duyệt")
    else:
        ok("không có thư mục 'vendor/' trái phép trong repo")


# --------------------------------------------------------------------------- 4
LINK = re.compile(r"\]\(([^)\s]+)\)")


def doc_files() -> list[pathlib.Path]:
    files = [ROOT / "README.md"]
    files += sorted((ROOT / "docs").glob("*.md"))
    for extra in ("kernel-cap", "kernel-services", "vmm-sandbox", "ai-bridge-yuid",
                  "pkg-stripper", "userspace-vi", "userspace-vi/ui",
                  "ai-bridge-yuid/reference"):
        files += sorted((ROOT / extra).glob("README.md"))
    return [f for f in files if f.exists()]


def check_links() -> None:
    header("liên kết tài liệu")
    docs = doc_files()
    broken = 0
    for doc in docs:
        for target in LINK.findall(doc.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            path = target.split("#")[0]
            if not path:
                continue
            if not (doc.parent / path).resolve().exists():
                bad(f"{doc.relative_to(ROOT)}: liên kết hỏng → {target}")
                broken += 1
    if not broken:
        ok(f"{len(docs)} tệp tài liệu, mọi liên kết nội bộ tồn tại")


# --------------------------------------------------------------------------- 5
PATH_ROOTS = ("docs/", "kernel-cap/", "kernel-services/", "vmm-sandbox/",
              "ai-bridge-yuid/", "pkg-stripper/", "userspace-vi/", "tools/",
              "arch/", "tests/", "scripts/", "include/")
# MCP method names look like paths but are protocol, not files.
PROTOCOL_NAMES = {"tools/list", "tools/call", "ping", "sys/search"}
QUOTED = re.compile(r"`((?:" + "|".join(PATH_ROOTS) + r")[A-Za-z0-9_./-]+)`")


def check_doc_paths() -> None:
    header("đường dẫn trong tài liệu có thật")
    missing = 0
    for doc in [ROOT / "README.md"] + sorted((ROOT / "docs").glob("*.md")):
        for rel in sorted(set(QUOTED.findall(doc.read_text(encoding="utf-8")))):
            if rel in PROTOCOL_NAMES:
                continue
            target = ROOT / rel
            present = target.is_dir() if rel.endswith("/") else target.exists()
            if not present:
                bad(f"{doc.relative_to(ROOT)}: nhắc tới '{rel}' nhưng không tồn tại")
                missing += 1
    if not missing:
        ok("mọi đường dẫn được nêu đều tồn tại")


# --------------------------------------------------------------------------- 6
def check_line_endings() -> None:
    header("định dạng nguồn")
    exts = {".cpp", ".hpp", ".h", ".c", ".rs", ".json", ".md", ".sh", ".py", ".toml", ".ld", ".yml", ".xml", ".in"}
    problems = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in exts:
            continue
        if any(part in {"build", "target", ".git"} for part in path.parts):
            continue
        if b"\r" in path.read_bytes():
            problems.append(str(path.relative_to(ROOT)))
    if problems:
        for name in problems:
            bad(f"CRLF: {name}")
    else:
        ok("không có CRLF")


def check_secrets() -> None:
    """Quét bí mật rò rỉ trong cây làm việc (P7.3)."""
    header("quét bí mật trong cây làm việc (P7.3)")
    scan_script = ROOT / "scripts/scan_secrets.py"
    if not scan_script.is_file():
        bad("scripts/scan_secrets.py không tồn tại")
        return
    res = subprocess.run([sys.executable, str(scan_script)], cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        bad(f"phát hiện bí mật tiềm ẩn:\n{res.stdout.strip()}")
    else:
        ok("quét bí mật sạch (0 bí mật/khoá/token lộ)")


def check_display_vectors() -> None:
    """P2.16: tệp vector dùng chung C++/Rust phải khớp bản tham chiếu Python."""
    header("vector chế độ hiển thị + framebuffer device tree (P2.16) + FromBytes (P2.22)")
    for name in ("gen_display_vectors.py", "gen_fdt_vectors.py", "gen_frombytes_vectors.py"):
        gen = ROOT / "scripts" / name
        res = subprocess.run([sys.executable, str(gen), "--check"], capture_output=True, text=True)
        if res.returncode == 0:
            ok(res.stdout.strip() or f"{name}: vector khớp")
        else:
            bad((res.stderr or res.stdout).strip() or f"{name}: tệp vector lỗi thời")


def check_boundaries() -> None:
    """Ranh giới "không giả mạo, không né kiểm tra" có máy kiểm (P7.10)."""  # ranh-giới-ok: tên bước kiểm P7.10
    header("ranh giới không giả mạo / không né kiểm tra (P7.10)")  # ranh-giới-ok: tên bước kiểm P7.10
    script = ROOT / "scripts/check_boundaries.py"
    if not script.is_file():
        bad("scripts/check_boundaries.py không tồn tại")
        return
    res = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        bad(f"vi phạm ranh giới:\n{res.stdout.strip()}")
    else:
        ok(res.stdout.strip())


def check_doc_numbers() -> None:
    """Số liệu trong tài liệu khớp mã (P0.16)."""
    header("số liệu tài liệu khớp mã (P0.16)")
    script = ROOT / "scripts/check_doc_numbers.py"
    if not script.is_file():
        bad("scripts/check_doc_numbers.py không tồn tại")
        return
    res = subprocess.run([sys.executable, str(script)], cwd=str(ROOT), capture_output=True, text=True)
    if res.returncode != 0:
        bad(f"số liệu tài liệu lệch mã:\n{(res.stdout + res.stderr).strip()}")
    else:
        ok(res.stdout.strip())


def main() -> int:
    if not (ROOT / "docs/PLAN.md").exists():
        print("verify.py: chạy từ trong repo YuiVieOS Beta")
        return 2
    check_layout()
    check_policies()
    check_ibus_component()
    check_rust()
    check_mirrored_enums()
    check_display_vectors()
    check_frame()
    check_kernel_dependencies()
    check_third_party()
    check_secrets()
    check_boundaries()
    check_doc_numbers()
    check_links()
    check_doc_paths()
    check_line_endings()
    print()
    if failures:
        print(f"\033[31m✗ {len(failures)} kiểm tra thất bại\033[0m")
        return 1
    print("\033[32m✓ tất cả kiểm tra tĩnh đều đạt\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
