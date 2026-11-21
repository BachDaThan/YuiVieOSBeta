# Build — tự biên dịch & kiểm thử

## 1. Yêu cầu tối thiểu

| Thành phần | Bắt buộc | Ghi chú |
|---|---|---|
| `make` (GNU) | có | chỉ dùng biến thường, không có gì đặc biệt |
| trình biên dịch C++17 | có | `g++ ≥ 10` hoặc `clang++ ≥ 12` |
| trình biên dịch C11 | để chạy `test_capi` | `cc`, cùng máy |
| `rustc`/`cargo` ≥ 1.70 | tuỳ chọn | chỉ cần cho workspace Rust (Tầng 1–2) |
| `pkg-config` + `libibus-1.0-dev` | tuỳ chọn | chỉ cần cho adapter IBus: `make ibus`; build lõi không phụ thuộc |
| libzstd, GTK, Qt | **không** | không cần cho các target hiện tại |

Đã kiểm trên Debian 12 / g++ 12.2.0 / glibc 2.36 (x86_64). Không dùng GNU
extension nào ngoài `-D_GNU_SOURCE` (cho `strdup`, socket).

---

## 2. Build cơ bản

```bash
git clone <repo> YuiVieOS && cd YuiVieOS
make -j"$(nproc)"        # → build/bin/{yuid,libyui.so,libyui.a,yui-profiler,yui-trim,yui-shell}
make test                # 2842 kiểm thử (2781 C++17 + 61 C11 ABI) — xem mục 4
make check               # test + smoke test CLI + kiểm tra tĩnh
```

Biến thường dùng:

```bash
make CXX=clang++                 # đổi trình biên dịch
make CXXFLAGS="-std=c++17 -O2"   # ghi đè (nhớ giữ -std và -fPIC)
make BUILD=/tmp/yui-build        # thư mục trung gian khác
make PREFIX=$HOME/.local install # cài vào $HOME/.local/{bin,lib,include}
make DESTDIR=/tmp/pkg install    # đóng gói
make clean
```

Cờ mặc định (giữ nguyên nếu bạn tự đặt `CXXFLAGS`):

```
-std=c++17 -O2 -g -Wall -Wextra -Wno-unused-parameter
-Iinclude -Itests -Ikernel-services -Iuserspace-vi -D_GNU_SOURCE -fPIC
```

`-fPIC` là bắt buộc vì `libyui.so` được link từ cùng object với `libyui.a`.

### Adapter IBus (tuỳ chọn, P1.4)

Adapter dùng IBus C API, không kéo dependency vào các target lõi. Trên Debian/Ubuntu:

```bash
sudo apt install pkg-config libibus-1.0-dev
make ibus
sudo make install       # cài thêm yui-ibus-engine + component XML nếu đã build
ibus restart
ibus engine yui-telex  # hoặc yui-vni
```

Để cài không cần root, dùng `make install PREFIX="$HOME/.local"` (sau khi đã
chạy `make ibus`). Theo xác minh Ubuntu 24.04 do người dùng cung cấp cho commit
`a786a44`, `make ibus` build sạch và `make check` đạt 2831 checks; D-Bus latency
trung bình 7.16 ms/phím (min 6.18, max khoảng 12 do nhịp nghỉ `pump` trong script
Python), đạt tiêu chí trung bình `<10 ms/phím`. Kiểm thử GUI Firefox/LibreOffice
được chuyển sang Desktop QA follow-up, không chặn P1.4.

Ghi chú headless từ lần chạy Ubuntu 24.04: GI name là `IBus.Capabilite` (không phải
`IBus.Capability`); khởi chạy IBus bằng
`ibus-daemon --config=/usr/libexec/ibus-memconf --panel=disable`; đặt `IBUS_ADDRESS`
và `XDG_RUNTIME_DIR` rõ ràng **bên trong** `dbus-run-session`; cài vào `PREFIX` tạm
(`make install PREFIX="$TMP_PREFIX"`) hoặc `/usr/local` nếu phù hợp. Báo cáo GUI
Firefox/LibreOffice vẫn cần ghi ở Desktop QA.

### Cài đặt

```
$PREFIX/bin/{yuid,yui-profiler,yui-trim,yui-shell,yui-splash}
$PREFIX/lib/{libyui.so,libyui.a}
$PREFIX/include/yui/{yui.h,crypto.hpp,…}
$PREFIX/bin/yui-ibus-engine + $PREFIX/share/ibus/component/*.xml  (optional)
```

---

## 3. Rust (Tầng 1 & 2)

```bash
make rust      # cargo test --workspace, rồi build release
```

hoặc thủ công:

```bash
cd kernel-cap   && cargo test
cd kernel-services/yui-sched && cargo test
cd kernel-services/yui-zram  && cargo test
```

Ba crate đều `#![no_std]` + `alloc` khi **không** ở chế độ `test`, và dùng `std`
khi chạy test (để có `Vec`, `format!`, harness). `#![deny(unsafe_code)]` ở cả ba:
nếu bạn thêm `unsafe`, build sẽ **thất bại** — đó là chủ ý, không phải tai nạn.

Ràng buộc:

- `panic = "abort"`, `lto = true`, `codegen-units = 1` trong profile release
  (xem `Cargo.toml`) — hợp với mã nhân, nơi không có unwinding.
- Không có dependency ngoài (cả ba crate chỉ dùng `core`/`alloc`). `Cargo.lock`
  **chưa có** vì môi trường soạn thảo không có `cargo`; lần build đầu tiên sẽ sinh
  ra nó và phải được commit — nếu không thì CI và máy dev có thể lệch phiên bản.
- MSRV: 1.70 (do dùng `let … else` và `core::cmp` ổn định từ lâu).

Nếu máy bạn không có Rust, mọi thứ C++ vẫn build và test được; `make rust` chỉ
báo "cargo không có trong PATH" và thoát khác 0.

---

## 4. Kiểm thử

```bash
make test                          # tất cả
./build/obj/test/test_core         # một bộ (dùng YUI_TEST_MAIN, in ✓/FAIL từng check)
./build/obj/test/test_sandbox -v   # (tuỳ bộ) in cả check thành công
```

| Bộ | Số check | Kiểm gì |
|---|---|---|
| `test_crypto` | 28 | SHA-256/HMAC/SHAKE/scrypt với vector RFC, vault tròn vẹn, sai khoá/hỏng tag |
| `test_codec_json` | 102 | YUI-LZ tròn vẹn, biên kích thước, JSON parse/serialize, CRC/SHA |
| `test_core` | 163 | đồ thị, engine q4/t2 + SIMD, text tiếng Việt, profiler, apppack |
| `test_sandbox` | 238 | bảng năng lực, thu hồi, token, hộp cát 3 bậc, **4 chính sách mẫu**, 10 kịch bản sandbox escape, AppSignatureGate, ThirdPartyImeHost |
| `test_ime` | 7149 | Telex/VNI, đúng sequence tone, English allowlist auto-restore, backspace, commit và DirectComposition NFC common-prefix optimization |
| `test_daemon` | 1218 | JSON-RPC, 14 công cụ MCP (9 data + 5 OS sys_*), xác nhận người dùng, sanitized audit.log, stress 1.000 lời gọi |
| `test_tools` | 309 | `yui-trim`, strip ELF, ui::plan, shell song ngữ 25 lệnh + Levenshtein, `yui-update` CLI trọn vẹn |
| `test_telemetry` | 471 | đọc sysfs pin/nhiệt/RAM, ranh giới 20 %/75 °C, quét toàn miền k/W, `telemetry.read` + MCP |
| `test_fb` | 1184 | ghi pixel có chặn biên (guard band), font 5×7, tiếng Việt có dấu, clipping, xuất PPM |
| `test_ed25519` | 132 | SHA-512 FIPS 180-4, Ed25519 RFC 8032, sign_bundle ngoại tuyến, multi-stream A/B update, deferred reboot, atomic rollback |
| `test_power` | 47 | tickless, DVFS, giới hạn nhiệt/pin, clock gating |
| `test_fsstore` | 96 | lõi chỉ đọc, ghi gộp, nested reads, chặn symlink escape, CowStore copy-on-write snapshot, RansomwareDetector |
| `test_linuxabi` | 89 | phân phối syscall, quyền file, mmap file/anon W^X, futex, epoll, i386 nr_from32 |
| `test_redteam` | 231 | guard chống đào coin, egress policy, IdleGuard thu hồi quyền khi nhàn rỗi, keylogger injection defense |
| `test_capi` (C11) | 61 | toàn bộ bề mặt `libyui` gọi từ C thuần: `YUI_E_TOO_SMALL`, hộp cát, `yui_telemetry`, `yui_telemetry_advise` |

Tổng trong nhánh hiện tại: **11.518 check** (11.457 C++17 + 61 C11 ABI). CI có bước
biên dịch adapter qua `make ibus`; bản build Ubuntu 24.04 và phép đo trung bình
7.16 ms/phím được người dùng xác nhận cho commit `a786a44`, nhưng sandbox này
không có IBus dev dependencies để tái lập. P1.4 đã đạt DoD; Firefox/LibreOffice
GUI còn là Desktop QA follow-up, không chặn hoàn tất.

Test dùng `YUI_SOURCE_DIR` (Makefile chèn `-DYUI_SOURCE_DIR='"$(CURDIR)"'`) để
nạp chính sách thật trong `vmm-sandbox/policies/` — nhờ vậy tài liệu và mã không thể
lệch nhau mà test vẫn xanh.

### Chạy test trong môi trường tối thiểu

Không cần mạng, không cần root, không cần `/run`. `test_daemon` tạo socket trong
thư mục tạm; `test_tools` tạo cây thư mục tạm và tự dọn.

---

## 5. Khung nhân bare-metal (Tầng 0)

`kernel-frame/` là **crate Rust duy nhất được phép chứa `unsafe`** và **không**
nằm trong workspace ở gốc (nó nhắm target bare-metal, còn workspace chỉ build
cho host). Build bằng script:

```bash
rustup toolchain install nightly --component rust-src
./scripts/build-kernel.sh x86_64      # → build/kernel/yui-kernel-x86_64.elf
./scripts/build-kernel.sh aarch64
./scripts/build-kernel.sh riscv64
./scripts/build-kernel.sh all
```

Vì sao cần nightly (và chỉ ở đây):

| Lý do | Chi tiết |
|---|---|
| `#[alloc_error_handler]` | bắt buộc khi `no_std` + `alloc`, vẫn là feature không ổn định |
| `-Z build-std=core,alloc` | phải tự biên dịch `core`/`alloc` cho target `*-unknown-none` |
| `-Z build-std-features=compiler-builtins-mem` | cần `memcpy`/`memset` cho Rust trên bare metal |

Boot thử:

```bash
./scripts/qemu-smoke.sh x86_64 --build        # build + boot, tìm 3 dấu hiệu
./scripts/qemu-smoke.sh riscv64 --strict      # CI: thiếu nhân/qemu ⇒ đỏ
```

Ba dòng phải thấy trên serial: `yui: ready`, `Phan loai :` (auto-profiler),
`Tang 1    :` (bảng năng lực). Xem `docs/PLAN.md` §8.

Ranh giới `unsafe` do `scripts/verify.py` (`check_frame`) canh: chỉ các tệp được
liệt kê (arch/*, boot, allocator, splash, frombytes, main) mới được có `unsafe`; tệp khác
xuất hiện `unsafe` ⇒ `verify.sh` đỏ. Tổng hiện tại: 30 khối `unsafe {}` + 5 `unsafe fn` + 2 `unsafe impl` trong 8 tệp (đếm theo loại bởi
`scripts/check_doc_numbers.py`, P0.16), có chú thích an toàn.

Kết quả CI (2026-11-15): build **3/3** target; boot QEMU **2/3** — `riscv64` và
`aarch64` in đủ `yui: ready`, `Phan loai`, `Tang 1`; `x86_64` bị QEMU từ chối
(`Cannot load x86-64 image, give a 32bit one`) nên cần multiboot2 + GRUB hoặc
shim 32-bit trước khi đạt — xem `docs/PLAN.md` P2.2. Job `qemu` của x86_64 để
`required: false`, nhưng vẫn chạy thật và vẫn đỏ.

---

## 6. CI

`.github/workflows/ci.yml` chạy build C++/C11, Rust, cross-arch và boot kernel/QEMU
trên push/PR. Job C++ chạy `make -j`, build adapter IBus (`make ibus`),
`make test` (**2842 check**), `make check`, cài vào `$RUNNER_TEMP` rồi link
chương trình C ngoài cây với `libyui.a`. Job Rust chạy test/build; các job kernel
và QEMU xác nhận ba kiến trúc theo `docs/PLAN.md` §8.

---

## 7. Sự cố thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
|---|---|---|
| `undefined reference to lroundf` khi link C | thiếu `-lm` sau `-lstdc++` | dùng `$(LDLIBS)` (đã có `-lm`), đừng viết danh sách lib tay |
| `-Wstringop-overflow` trong `server.cpp` | đọc 1 byte vào `char` | đã sửa: dùng đệm 512 byte |
| `error: 'Edge' was not declared` | viết `Graph::Edge` ngoài lớp | viết `Edge` (xem `graph.cpp`) |
| test fail vì kích thước gói | dữ liệu nhỏ hơn header 78 byte | dùng ≥ 1 KiB dữ liệu lặp |
| `cargo: not found` | chưa cài Rust | `make` (C++) vẫn đủ; cài rustup nếu cần phần Rust |
| test_sandbox không tìm thấy policy | thiếu `-DYUI_SOURCE_DIR` | dùng `make test`, đừng tự biên dịch tay |
