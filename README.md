# YuiVieOS Beta 🪷

**Hệ điều hành thuần Việt, tự chủ hoàn toàn — clean-room 100 %, nhân bằng Rust an toàn.**
*A Vietnamese-first operating system: smooth on a 2 GB netbook, unrestricted on a workstation.*

> **Dự án mã nguồn mở cá nhân**, làm vì đam mê, phục vụ học tập và nghiên cứu kỹ thuật, chia sẻ miễn phí. Cung cấp **nguyên trạng (AS-IS)**; người dùng tự chịu trách nhiệm khi sử dụng. Không dùng cho quyết định y tế, pháp lý, tài chính. Xem `docs/terms_vi.md` và `docs/privacy_vi.md`.
> *A personal open-source project made for learning and research, shared free and provided AS-IS; use at your own risk.*

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 5  TRẢI NGHIỆM NGƯỜI DÙNG VIỆT                       userspace-vi/      │
│   Smart App Stripper │ Shell VI–EN │ Telex/VNI tại dịch vụ │ App Yui (Flutter)│
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 4  CỔNG CHỜ TRÍ TUỆ LÕI                            ai-bridge-yuid/      │
│   ①IPC & C-ABI  ②Telemetry  ③OS Control MCP  ④nạp .yui v3 (mmap)            │
│   ── đường nối Phase P5 ──► libyui.so (Adaptive-MoE + Y-App, ngoài repo)     │
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 3  HỘP CÁT ZERO-TRUST (MicroVM)                     vmm-sandbox/        │
│   native │ isolated │ microvm (Wine/Proton+VKD3D, Waydroid-lite)             │
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 2  NHÂN DỊCH VỤ (Safe Rust Framekernel)            kernel-services/     │
│   Lập lịch chuyển đổi nóng │ ZRAM │ FS bất biến │ DVFS │ tickless │ Linux ABI│
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 1  LÕI GIÁM SÁT BẢO MẬT (Capability Microkernel)   kernel-cap/          │
│   CapTable │ Thẻ năng lực ký HMAC │ Thu hồi bắc cầu │ Sovereign Keyring      │
├──────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 0  PHẦN CỨNG ĐA KIẾN TRÚC                          arch/                │
│   x86_64 (BIOS Legacy + UEFI) │ ARM64 │ RISC-V 64                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

Bản vẽ đầy đủ + giao thức cổng chờ: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
Kế hoạch thi công P0–P5, tiêu chí đo được, CI QEMU 3 kiến trúc: [`docs/PLAN.md`](docs/PLAN.md).

---

## Chạy thử trong 60 giây

Yêu cầu: `g++` ≥ 10 (C++17), `make`, `python3`, POSIX. **Không** cần mạng, không
cần thư viện ngoài, không cần Rust.

```bash
make              # → build/bin/{yuid,libyui.so,libyui.a,yui-profiler,yui-hw,yui-trim,yui-shell,yui-splash,yui-update,yui-store,yui-sandbox-exec}
make test         # 15593 kiểm thử (15527 C++17 + 66 C11 ABI)
make check        # test + smoke run + kiểm tra tĩnh (scripts/verify.sh, gồm máy kiểm ranh giới P7.10)
```

```console
$ ./build/bin/yui-profiler
YuiVieOS · Hồ sơ phần cứng
  Kiến trúc : x86_64 (avx512f, 512 bit)
  CPU       : Intel(R) Xeon(R) Processor @ 2.60GHz — 2 luồng / 1 nhân
  RAM       : 3.8 GB (trống 3.6 GB)
  Phân loại : may-yeu
  Tự chỉnh  : k=2, cửa sổ=1024, luồng=2 (may-yeu)

$ ./build/bin/yui-shell
› gõ telex Tieengs Vieetj
Tiếng Việt
› ghinhớ os:yui "YuiVieOS — hệ điều hành Việt" concept
Đã ghi nhớ: os:yui
› tìm yui
· os:yui — YuiVieOS — hệ điều hành Việt [concept]
› thoát
Tạm biệt — hẹn gặp lại ở YuiVieOS. / Goodbye.
```

**Chế độ POSIX của `yui-shell` (P4.12):** chỉ chạy lệnh hệ thống khi bạn nói rõ —
dòng bắt đầu bằng `!` hoặc lệnh `chạy`. Dòng không nhận ra **không bao giờ** tự chạy.

```
yui› !ls *.txt | sort > ds.txt        # ống dẫn + chuyển hướng, chạy trong hộp cát Landlock
yui› chạy sleep 60 &                  # [1] 1234
yui› !jobs                            # [1] Đang chạy  sleep 60 &
yui› !kill %1                         # chỉ việc do shell này tạo
yui› !echo x > /etc/hosts             # Từ chối (hộp cát) … — không tiến trình nào được tạo
```

**Kho Ứng Dụng — lõi (P4.15):** `yui-store` đọc danh mục ký Ed25519, tải **từ nguồn
chính thức** (chỉ https, host phải nằm trong danh sách của danh mục), kiểm sha256,
gọt cục bộ bằng `yui-trim`, đặt app vào hộp cát theo policy và tạo biểu tượng. Danh mục
chưa ký/sai chữ ký/băm lệch ⇒ từ chối; app không có chữ ký nhà phát hành ⇒ hộp cát hạn
chế, không mạng (P3.12). `cài` luôn hỏi xác nhận trên TTY (CLI) hoặc hộp thoại tin cậy
(RPC/shell), không có `--yes`. Chưa có danh mục thật; mới nhận gói `.tar` thường.

```console
$ yui-store nhập catalog.json catalog.sig --keyring khoa/   # nạp danh mục đã ký
$ yui-store tìm chao                                        # tìm không dấu vẫn ra "Xin Chào"
$ yui-store cài org.example.hello                           # hiện kế hoạch, hỏi gõ lại mã app
$ yui-store gỡ org.example.hello                            # xoá tệp, policy, biểu tượng, cache
```

---

## Cấu trúc monorepo

```
docs/                ARCHITECTURE · PLAN · SECURITY · PROTOCOL · FORMAT-YUIP · BUILD
kernel-frame/        Tầng 0 (Rust no_std, **khung unsafe duy nhất**): boot, serial, profiler, splash
kernel-cap/          Tầng 1 (Rust no_std): quyền, CapTable, thẻ HMAC, SHA-256/512, Ed25519, keyring, bundle
kernel-services/     Tầng 2: yui-sched/ (LAVD) · yui-zram/ (ZRAM) + codec/crypto/ed25519/bundle/power/guard/fsstore/linuxabi
vmm-sandbox/         Tầng 3: bộ thực thi chính sách · policies/ · vmm/ (manifest schema)
ai-bridge-yuid/      Tầng 4: daemon/ · capi.cpp · reference/ (chờ thay ở P5)
pkg-stripper/        Tầng 5: Smart App Stripper (apppack)
userspace-vi/        Tầng 5: text · ime · ui · shell · ui/app (Flutter)
include/yui/         API công khai + header C `yui.h`
tests/               9 bộ test C++17 + 1 bộ test C11
tools/               yui-profiler · yui-hw · yui-trim · yui-shell · yui-splash
arch/                linkerscript per arch: x86_64 · arm64 · riscv64
scripts/             verify.sh · verify.py · build-kernel.sh · qemu-smoke.sh
.github/workflows/   CI: cpp · rust · docs · cross-arch · kernel · qemu
```

Chi tiết từng thư mục: mỗi thư mục có `README.md` riêng nói nó làm gì, đã xong
phần nào, còn thiếu phần nào.

---

## Trạng thái thật (không tô hồng)

Mỗi dòng "đã có" đều trỏ tới tệp và test cụ thể; mỗi dòng "chưa" đều trỏ tới
task trong [`docs/PLAN.md`](docs/PLAN.md).

| Tầng | Thành phần | Trạng thái | Bằng chứng |
|---|---|---|---|
| 0 | Hardware Auto-Profiler: CPU/RAM/GPU/pin/nhiệt → `may-yeu`/`can-bang`/`may-manh` + k/W | ✅ chạy | `kernel-services/profile.cpp`, `tools/profiler` |
| 0 | Trợ lý phần cứng `yui-hw` (P6.31): quét PCI/USB/IOMMU/VT-x/EPT/firmware/ổ đĩa ⇒ hạng A/B/C/D **dự kiến** theo quy tắc + hạng **đã đo** chỉ từ bảng `docs/hwdb.tsv` (`real`/`qemu` có bằng chứng); báo cáo chỉ ghi ra tệp cục bộ | 🟡 kiểm thử trên cây sysfs giả + 31 mô tả tổng hợp; **chưa chạy trên máy thật nào** — không có con số "% phần cứng được hỗ trợ" | `kernel-services/hw.cpp`, `tools/hw`, `tests/test_hw.cpp` (290 check) |
| 0 | Luồng khởi động 3 kiến trúc + linker script | ✅ build 3/3, boot 2/3 | `arch/{x86_64,arm64,riscv64}/linker.ld` |
| 0 | Khung nhân bare-metal: serial, bộ cấp phát, `YuiBootInfo`, profiler, bảng năng lực trên ring 0 | ✅ boot thật (aarch64, riscv64) / 🔄 x86_64 đã sửa boot path (multiboot2 + ELF32 objcopy), đợi CI xác nhận | `kernel-frame/`; CI `qemu` bắt buộc 3 kiến trúc |
| 0 | Màn hình chào trên framebuffer tuyến tính (font 5×7) + **chữ Việt có dấu** | ✅ kiểm thử | `userspace-vi/fb.cpp`, `tests/test_fb.cpp` (1184 check, gồm chữ Việt có dấu), `tools/splash`, [`docs/splash.png`](docs/splash.png) |
| 0 | Chọn chế độ hiển thị gốc (EDID) + hệ số phóng nguyên HiDPI 1–4 theo DPI thật + viền đen thay vì kéo giãn; thẻ framebuffer Multiboot2 + nút simple-framebuffer Device Tree trong nhân (P2.16) | 🟡 logic C++ + Rust có test; splash qua GRUB/VBE (x86_64) và Device Tree (aarch64 + riscv64, có 4K) xanh trên CI; GOP chờ P6.4 | `userspace-vi/display.cpp`, `kernel-cap/src/display.rs`, `kernel-cap/src/fdt.rs`, `tests/test_display.cpp` (2113 check, 34 bảng EDID + 48 DTB), `scripts/qemu-splash.sh`, `scripts/qemu-splash-dt.sh` |
| 1 | Bảng năng lực: 16 quyền (kể cả `compute.heavy`), dẫn xuất chỉ thu hẹp, thu hồi bắc cầu | ✅ Rust | `kernel-cap/src/lib.rs` |
| 1 | Thẻ năng lực ký HMAC-SHA-256, xác minh hằng thời gian, lỗi có kiểu | ✅ hai phía | `kernel-cap/src/lib.rs`, `vmm-sandbox/sandbox.cpp` |
| 1 | SHA-256 / HMAC / SHAKE-256 / scrypt tự viết, có vector RFC | ✅ | `kernel-services/crypto.cpp`, `tests/test_crypto.cpp` |
| 1 | Sovereign Keyring + `.bundle` ký Ed25519 (clean-room, vector RFC 8032) | ✅ hai phía | `kernel-services/ed25519.cpp` + `kernel-cap/src/{sha512,ed25519,keyring,bundle}.rs`, `tests/test_ed25519.cpp` (132 check) |
| 2 | Guard đào coin ngầm (70 %/15 s ⇒ hạ Idle + bóp xung + hỏi người dùng) | ✅ kiểm thử | `kernel-services/guard.cpp`, `yuid` `guard.*`, `tests/test_redteam.cpp` |
| 2 | Bộ lọc egress theo năng lực (mặc định chặn, allowlist policies/*.json) | ✅ kiểm thử | `vmm-sandbox/sandbox.cpp::EgressFilter`, `tests/test_redteam.cpp` |
| 2 | Lập lịch chuyển đổi nóng LAVD (P/E-core, tín dụng đánh thức, công bằng) | ✅ Rust | `kernel-services/yui-sched` (`cargo test` trên CI) |
| 2 | ZRAM: codec YUI-LZ + kho trang nén, fallback verbatim | ✅ Rust + C++ | `kernel-services/yui-zram` (`cargo test` trên CI), `kernel-services/codec.cpp` |
| 2 | `yui-frame` (khung unsafe duy nhất) | ✅ boot được (2 kiến trúc) | `kernel-frame/` — 30 khối `unsafe {}` + 5 `unsafe fn` + 2 `unsafe impl`, nằm trong 8 tệp được `verify.sh` kiểm toán |
| 2 | Tickless, DVFS, FS bất biến, Linux ABI | 🟡 chính sách + fsstore/ABI model có test; kernel integration và QEMU/hardware QA còn thiếu | P2.5, P2.7–P2.9 |
| 3 | Hộp cát 3 bậc + audit + 4 policy mẫu có test | ✅ | `vmm-sandbox/`, `tests/test_sandbox.cpp` (340 check) |
| 3 | Manifest micro-VM (JSON Schema) | 🟡 đặc tả | `vmm-sandbox/vmm/` |
| 3 | VMM thật (KVM), Wine/VKD3D, Waydroid-lite | ❌ chưa có | P3 |
| 4 | `yuid`: socket `/run/yuid.sock`, JSON-RPC 2.0 | ✅ chạy | `ai-bridge-yuid/daemon/`, `tests/test_daemon.cpp` (1260 check) |
| 4 | C-ABI `libyui.so/.a` + header C, kiểm từ **C11** | ✅ chạy | `include/yui/yui.h`, `tests/test_capi.c` (66 check) |
| 4 | MCP `2024-11-05`, 8 công cụ dữ liệu | ✅ chạy | `ai-bridge-yuid/daemon/server.cpp` |
| 4 | Telemetry Hook: `telemetry.read` + `yui_telemetry()` đọc pin/nhiệt/RAM thật, tự chỉnh k/W | ✅ chạy | `kernel-services/telemetry.cpp`, `tests/test_telemetry.cpp` (567 check); C-ABI `yui_telemetry()` do `test_capi` kiểm |
| 4 | 5 công cụ OS MCP `sys_power`/`sys_scheduler`/`sys_app_stripper`/`sys_proc`/`sys_search_vault` + xác nhận | ✅ chạy (P4.3 `[x]`) | `ai-bridge-yuid/daemon/`, P4.3 |
| 4 | Cài đặt tham chiếu graph/vault/engine (**sẽ thay ở P5**) | 🟡 tạm | `ai-bridge-yuid/reference/` |
| 5 | Smart App Stripper: strip ELF, khử trùng lặp, lọc locale, chống zip-slip | ✅ chạy | `pkg-stripper/apppack.cpp`, `tools/trim`, `tests/test_tools.cpp` (414 check, chung cho các công cụ CLI) |
| 5 | Giải nén an toàn (P4.33): DEFLATE + zstd tự viết, `zip`/`gz`/`zst`/`tar`/`tar.gz`/`tar.zst`, chặn zip-slip/liên kết/bom nén, CRC/XXH64, xoá sạch khi lỗi | ✅ chạy (chưa 7z) | `pkg-stripper/archive.cpp`, `pkg-stripper/zstd.cpp`, `tests/test_archive.cpp` (429 check) |
| 5 | Bộ gõ Telex **và** VNI, đặt dấu đúng chính tả | ✅ kiểm thử | `userspace-vi/ime.cpp`, `tests/test_ime.cpp` (7149 check) |
| 5 | Shell song ngữ Việt–Anh, 36 lệnh (gồm `tìmapp`/`cài`/`gỡ` của Kho, `xoá`/`khôiphục`/`dọnrác` của thùng rác) | ✅ chạy | `userspace-vi/shell.cpp` |
| 5 | Chế độ POSIX trong `yui-shell` (`!lệnh` hoặc `chạy …`): ống dẫn, `>` `>>` `<` `2>&1`, `&`/`jobs`/`kill`/`wait`, biến, trích dẫn; `yuid` kiểm + audit từng lệnh, Landlock + no_new_privs qua `yui-sandbox-exec`; dòng lạ không tự chạy | ✅ chạy trên Linux host (Landlock); nhân riêng chờ P2.7 | `userspace-vi/posix.cpp`, `tools/sandbox-exec/`, `tests/test_posix.cpp` (141 check), P4.12 |
| 5 | Thùng rác (khôi phục kiểm băm, thùng đầy thì cảnh báo, không tự xoá) + dọn rác chỉ trong danh sách có tên, xoá vĩnh viễn cần xác nhận tin cậy | ✅ chạy trên Linux host; chưa nối snapshot nhân | `userspace-vi/trash.cpp`, `tests/test_trash.cpp` (203 check), P4.17 |
| 5 | Kho Ứng Dụng — lõi: danh mục ký Ed25519, tải https từ nguồn chính thức, kiểm sha256, gọt cục bộ, hộp cát, biểu tượng; CLI `yui-store` + RPC `store.*` | ✅ chạy, chưa có danh mục thật, chỉ gói `.tar` | `pkg-stripper/store.cpp`, `tests/test_store.cpp` (215 check), P4.15 |
| 5 | Kế hoạch giao diện thích ứng (Framebuffer ⇄ Vulkan/DRM) | ✅ logic + test | `userspace-vi/ui.cpp` |
| 5 | IBus Telex/VNI engine | ✅ Người dùng xác minh Ubuntu 24.04: build sạch, `make check` 2831, D-Bus avg 7.16 ms; Firefox/LibreOffice để Desktop QA follow-up | `userspace-vi/ibus/`, P1.4 <!-- số-đo: người dùng đo trên Ubuntu 24.04, commit a786a44, 2026-11-16 (PLAN P1.4, §12) --> |
| 5 | Compositor thật (DRM/Vulkan), App Yui build được | ❌ chưa có (đã có bộ vẽ pixel + màn hình chào) | P2.6, P4.1, P4.5 |

### Phạm vi: những gì dự án không làm và không hứa

- **Không giả mạo, không né kiểm tra.** Không giả IMEI/ID thiết bị/vị trí, không vượt Play Integrity, không né chống gian lận của game (task P7.10). Game kiểm nghiêm sẽ từ chối máy ảo/container; bạn tự tuân thủ điều khoản của ứng dụng/game (đa tài khoản, giả vùng, công cụ ngoài). Dự án không quảng bá việc "treo/cày nhiều tài khoản". <!-- ranh-giới-ok: phạm vi: tuyên bố dự án KHÔNG làm các việc này -->
- **Không đóng gói** Windows, Google Mobile Services, bộ dịch mã đóng nguồn hay bản vá game: tải theo nhu cầu từ nguồn chính thức, theo [`docs/THIRD-PARTY.md`](docs/THIRD-PARTY.md).
- **Không hứa con số chưa đo** (FPS, độ trễ, RAM so với Windows/Linux). Chỉ ghi số có phép đo kèm máy và lệnh (P6.25–P6.26).
- **Chưa có:** đồ họa 3D trên nhân riêng (chưa có đường GPU, P6.28), Android/Windows trong micro-VM (P3), giao diện Kho Ứng Dụng (P4.16; mới có lõi CLI/RPC P4.15, chưa có danh mục thật; `.tar.gz`/`.tar.zst`/`.zip` đã nhận qua bộ giải nén an toàn P4.33, chưa có 7z/`.deb`), lọc quảng cáo (P4.18), server/NAS (backlog). Xem [`docs/PLAN.md`](docs/PLAN.md).

**Chưa kiểm chứng được trong môi trường soạn thảo này**: biên dịch Rust (không có
`cargo`), boot QEMU (không có `qemu-system-*`), build Flutter (không có SDK). Cả
ba đều có job CI và task tương ứng trong `PLAN.md` — chúng tôi **không** tuyên bố
chúng đã chạy.

Riêng khung nhân: máy soạn thảo **không** biên dịch được Rust, nhưng CI thì có.
Kết quả thật từ CI (job `kernel` + `qemu`):

| Kiến trúc | Build | Boot QEMU | Ghi chú |
|---|---|---|---|
| `riscv64` | ✅ | ✅ `yui: ready` + `Phan loai` + `Tang 1` | đọc RAM từ device tree |
| `aarch64` | ✅ | ✅ cả ba dòng | RAM in `0 MiB — khong doc duoc` vì QEMU không truyền DTB cho ELF `-kernel` — **không bịa số** |
| `x86_64` | ✅ | ⛔ | QEMU: *Cannot load x86-64 image, give a 32bit one* — cần multiboot2 + GRUB hoặc shim 32-bit (P2.2) |

Chú thích kỹ thuật đáng nhớ (đã tìm ra nhờ CI, ghi lại để không lặp lại):
`csrr misa` là CSR cấp M — S-mode đọc sẽ trap; PL011 phải đặt divisor trước khi
in; `{}` với `&str` tính lúc chạy làm nhân aarch64 dừng giữa dòng (dùng
`console::print_str`); x86_64 cần `-C relocation-model=static` và
`options(att_syntax)`.

---

## Phase P5 — dự trữ, chưa kích hoạt

Lõi AI (`yui.cpp`, `.yui v3`, `yui_graph`, `yui_vault`, `Y-App`) phát triển ở hai
repo riêng. Repo này chỉ dựng **cổng chờ** với hợp đồng ổn định:

- `telemetry.read` + `yui_telemetry()` — pin, nhiệt, RAM, khuyến nghị k/W
  (`k=1,W=16` khi yếu/pin thấp; `k=2..4` khi cắm sạc/máy mạnh)
- `sys_power`, `sys_scheduler`, `sys_app_stripper`, `sys_proc`, `sys_search_vault`
  qua MCP, mỗi hành động cần quyền + xác nhận người dùng + audit
- `mmap` trực tiếp tệp `.yui v3` (trọng số không bao giờ đi qua socket)

Khi bạn ra lệnh **"Tích hợp AI vào hệ điều hành"**, quy trình ở
[`docs/PLAN.md`](docs/PLAN.md) §P5 được thực hiện tuần tự: kéo mã → đóng băng SHA →
build `libyui.so` 3 kiến trúc → kiểm C-ABI → cắm vào bridge → bật `yuid` → bật
điều khiển tiếng Việt. Có đường rollback một lệnh (`--reference-engine`).

---

## Nguyên tắc

1. **Clean-room**: không một dòng mã từ Linux/seL4/Asterinas; chỉ dùng nguyên lý
   công khai + chuẩn giao tiếp. MIT, không nghĩa vụ GPL.
2. **Rust an toàn**: `#![deny(unsafe_code)]` cho mọi crate nhân; `unsafe` chỉ được
   tồn tại trong khung phần cứng `yui-frame` (P2.1) và được `scripts/verify.sh` canh.
3. **Tiếng Việt hạng nhất**: tìm không dấu, bộ gõ đúng chính tả, shell hai tên lệnh.
4. **Máy yếu không phải bản cắt bớt**: cùng binary, khác chế độ vận hành.
5. **Không hứa điều chưa đo**: mỗi mục tiêu có số đo trong `PLAN.md`; giới hạn bảo
   mật được liệt kê thẳng ở [`docs/SECURITY.md`](docs/SECURITY.md) §7.

## Giấy phép

MIT — xem [`LICENSE`](LICENSE).
