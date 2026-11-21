# `kernel-frame/` — khung phần cứng (Tầng 0)

Đây là **crate duy nhất trong toàn dự án được phép chứa `unsafe`**. Mọi crate
khác (`kernel-cap`, `kernel-services/*`, `vmm-sandbox`, `pkg-stripper`) giữ
`#![deny(unsafe_code)]` và `scripts/verify.sh` sẽ đỏ nếu bạn thêm `unsafe` vào đó.

## Vì sao phải có `unsafe`

Bốn việc không thể làm bằng Rust an toàn:

1. **chuyển ngữ cảnh** — x86_64 khởi động ở 32-bit; phải dựng bảng trang, bật
   PAE/LME/PG rồi nhảy sang mã 64-bit (`src/arch/x86_64.rs`);
2. **ngõ vào/ra** — cổng COM1 (`in`/`out`), UART PL011 (ghi MMIO), SBI `ecall`;
3. **bộ cấp phát** — triển khai `GlobalAlloc` trên một vùng tĩnh
   (`src/allocator.rs`);
4. **framebuffer** — ghi vào vùng nhớ firmware cấp (`src/splash.rs`);
5. **zero-copy** — ép `&[u8]` → `&T` sau khi `yui_cap::frombytes::check` đã
   kiểm độ dài + căn chỉnh (`src/frombytes.rs`, đúng một khối, P2.22).

Tất cả nằm trong các tệp được liệt kê ở `scripts/verify.py` (`FRAME_UNSAFE_FILES`),
mỗi tệp có lý do bằng tiếng Việt. Tổng: 30 khối `unsafe {}` + 5 `unsafe fn` + 2 `unsafe impl` trong 8 tệp, mỗi khối có
chú thích an toàn (con số do `scripts/check_doc_numbers.py` kiểm).

## Nội dung

| Tệp | Việc |
|---|---|
| `src/main.rs` | `kmain`: serial → `YuiBootInfo` → profiler → bảng năng lực → màn hình chào |
| `src/boot.rs` | đọc multiboot 1 (x86_64) và device tree (ARM/RISC-V) → một `BootInfo` |
| `src/console.rs` | in ra cổng nối tiếp, có spinlock |
| `src/profiler.rs` | phân loại `may-yeu`/`can-bang`/`may-manh` + k/W, **cùng ngưỡng** với `kernel-services/profile.cpp` |
| `src/cap.rs` | khởi tạo `CapTable`, chứng minh dẫn xuất không mở rộng quyền + thu hồi bắc cầu |
| `src/splash.rs` | màn hình chào 5×7 trên framebuffer tuyến tính |
| `src/frombytes.rs` | `ref_from_bytes`/`ref_from_prefix` zero-copy + tự kiểm lúc boot bằng `tests/data/frombytes_vectors.txt` (P2.22) |
| `src/allocator.rs` | bump allocator 4 MiB |
| `src/arch/*` | x86_64 (multiboot + long mode), aarch64 (PL011), riscv64 (SBI) |

## Build & boot

```bash
rustup toolchain install nightly --component rust-src
./scripts/build-kernel.sh x86_64        # hoặc: make kernel ARCH=aarch64
./scripts/qemu-smoke.sh x86_64 --build  # hoặc: make qemu ARCH=aarch64
```

Ba dòng phải thấy trên serial: `yui: ready`, `Phan loai :`, `Tang 1    :`.

## Trạng thái thật (đo bằng CI, không phải lời hứa)

| Kiến trúc | Build (`kernel`) | Boot QEMU (`qemu`) |
|---|---|---|
| `riscv64` | ✅ | ✅ `yui: ready`, `Phan loai : may-yeu`, `Tang 1`, thu hồi quyền |
| `aarch64` | ✅ | ✅ cả ba dòng; RAM `0 MiB — khong doc duoc` (QEMU không truyền DTB) |
| `x86_64` | ✅ | ⛔ QEMU chỉ nạp multiboot 1 từ ELF32 → cần multiboot2 + GRUB hoặc shim 32-bit |

Bài học đã trả giá, ghi lại:

- `csrr misa` là CSR **cấp M**: S-mode đọc là trap. Dò vector qua `riscv,isa`
  trong device tree.
- PL011 phải lập trình IBRD/FBRD/LCR_H trước khi in, nếu không FIFO kẹt và
  `serial_write` bỏ byte ⇒ mất chữ giữa dòng.
- `println!("{}", chuoi_runtime)` làm nhân aarch64 dừng giữa dòng → dùng
  `console::print_str` (ghi byte trực tiếp) cho mọi `&str` tính lúc chạy.
- x86_64: `global_asm!` mặc định Intel → cần `options(att_syntax)`; cần thêm
  `-C relocation-model=static` (target mặc định PIC) và `-C target-feature=+strict-align`.
