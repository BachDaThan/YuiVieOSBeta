//! aarch64 — QEMU `virt` nạp ELF tại 0x4008_0000 và nhảy vào `_start` ở EL1
//! với `x0 =` con trỏ device tree. Không cần bật MMU cho pha khởi động; ngăn
//! xếp đặt trong .bss.

use crate::boot::RawBoot;

const PL011_DR: usize = 0x0900_0000;
const PL011_FR: usize = 0x0900_0018;

core::arch::global_asm!(
    r#"
.section .text.entry, "ax"
.global _start
_start:
    mov x19, x0               /* device tree pointer */
    /* Bật FP/SIMD cho EL1/EL0 (CPACR_EL1.FPEN = 0b11). Giá trị lúc reset là
       UNKNOWN; khi FPEN chặn, lệnh NEON đầu tiên (rustc dùng NEON cho vòng
       lặp được vector hoá, khởi tạo mảng, đếm ký tự trong Formatter::pad)
       gây trap đồng bộ mà chưa có bảng vector ⇒ nhân treo im lặng. Lần tự
       kiểm FromBytes (P2.22) treo đúng kiểu đó trên CI (run 44894963668);
       lỗi cũ "định dạng &str qua Formatter treo nhân" nhiều khả năng cùng
       gốc. (Không viết dấu ngoặc nhọn trong global_asm: đó là chỗ thế đối số.)
       Ghi CPACR_EL1 hợp lệ ở EL1, EL2 và EL3. */
    mrs x1, cpacr_el1
    orr x1, x1, #(3 << 20)
    msr cpacr_el1, x1
    isb
    ldr x1, =__yui_stack_top
    mov sp, x1
    mov x0, x19
    bl kmain_arm
1:
    wfe
    b 1b

.section .bss
.align 12
__yui_stack:
    .skip 65536
__yui_stack_top:
"#
);

pub fn init_console() {
    // PL011 trên QEMU virt: UART_CLK = 24 MHz. Muốn 115200 8N1 thì
    //   IBRD = 24e6 / (16 * 115200) = 13, FBRD = 0.0208 * 64 ≈ 1
    // Ban đầu tôi chỉ ghi CR và bỏ qua divisor ⇒ sau vài chục byte TXFF kẹt và
    // serial_write rơi vào nhánh "quá số lần chờ" nên **mất chữ giữa dòng**
    // ("Kien truc : " rồi không có tên kiến trúc). Đó là lỗi, không phải ma.
    let uart = 0x0900_0000usize as *mut u32;
    unsafe {
        write(uart, 0x30, 0); // UARTEN = 0 trong lúc cấu hình
        write(uart, 0x24, 13); // IBRD
        write(uart, 0x28, 1); // FBRD
        write(uart, 0x2C, 0x70); // LCR_H: FIFO bật, 8 bit, không parity, 1 stop
        write(uart, 0x38, 0); // IMSC: không ngắt
        write(uart, 0x44, 0x7FF); // ICR: xoá mọi cờ ngắt
        write(uart, 0x30, 0x301); // CR: UARTEN | TXE | RXE
    }
}

unsafe fn write(uart: *mut u32, offset: usize, value: u32) {
    core::ptr::write_volatile(uart.add(offset / 4), value);
}

pub fn serial_write(byte: u8) {
    unsafe {
        let mut spins = 0u32;
        // FR bit 5 = TXFF (transmit FIFO full)
        while core::ptr::read_volatile(PL011_FR as *const u32) & (1 << 5) != 0 {
            spins += 1;
            if spins > 10_000_000 {
                return;
            }
            core::hint::spin_loop();
        }
        core::ptr::write_volatile(PL011_DR as *mut u32, byte as u32);
    }
}

pub fn detect_simd() -> &'static str {
    // ARMv8-A **bắt buộc** có NEON nên không cần đọc thanh ghi nào.
    // (Trước đây tôi đọc ID_AA64PFR0_EL1 để dò SVE; lần chạy QEMU đầu tiên cho
    // thấy đọc thanh ghi ID ở EL1 có thể trap tuỳ cấu hình EL2 — không đáng để
    // mạo hiểm trong khung khởi động. Dò SVE sẽ làm ở P2.5 bằng bảng CPU.)
    "neon"
}

pub fn cpu_vendor() -> [u8; 12] {
    // MIDR_EL1 không phải chuỗi; in tên kiến trúc và để trống vendor.
    let mut v = [0u8; 12];
    v[0] = b'A';
    v[1] = b'R';
    v[2] = b'M';
    v
}

#[no_mangle]
pub extern "C" fn kmain_arm(dtb: usize) -> ! {
    // Khởi tạo UART TRƯỚC mọi println!: PL011 chưa bật thì từng byte phải đợi
    // tới hạn trong serial_write và không phát ra gì cả — cả dải banner sẽ câm.
    init_console();
    let mut addr = dtb as u64;
    if addr == 0 {
        // QEMU `-kernel` với ảnh ELF: bootloader QEMU coi đây là "ELF không
        // phải Linux" nên nhảy thẳng vào _start mà KHÔNG đặt x0 (xem
        // hw/arm/boot.c: "Assume that raw images are linux kernels, and ELF
        // images are not"), nhưng nó vẫn sinh DTB và đặt ngay tại đầu RAM
        // (`loader_start` = 0x4000_0000 trên QEMU virt, dưới ảnh nhân ở
        // 0x4100_0000). U-Boot/UEFI thì truyền x0 đúng chuẩn. Khi x0 = 0,
        // quét cửa sổ đầu RAM để tìm magic FDT — không thấy thì để 0 và báo
        // "khong doc duoc", tuyệt đối không bịa số.
        //
        // Cửa sổ quét = ĐÚNG khoảng trống dưới ảnh nhân (0x4000_0000 .. 0x4100_
        // 0000): không được mở rộng vào trong ảnh — hằng FDT_MAGIC nằm trong
        // .rodata của chính nhân sẽ thành "magic" giả. Khoảng trống 16 MiB cũng
        // là nơi QEMU cam kết đặt DTB (dtb_start = loader_start, dtb_limit =
        // image_low_addr).
        addr = crate::boot::find_fdt(0x4000_0000, 0x100_0000);
        if addr == 0 {
            // Chẩn đoán cho CI: in 8 từ đầu tại 0x4000_0000 để biết firmware
            // (không) đặt gì ở đó — một dòng duy nhất, đọc được từ annotation.
            let p = 0x4000_0000u64 as *const u32;
            let mut words = [0u32; 8];
            for (i, w) in words.iter_mut().enumerate() {
                *w = unsafe { core::ptr::read_unaligned(p.add(i)) };
            }
            println!(
                "    - chua thay FDT; 8 tu @ 0x40000000: {:#x} {:#x} {:#x} {:#x} {:#x} {:#x} {:#x} {:#x}",
                words[0], words[1], words[2], words[3], words[4], words[5], words[6], words[7]
            );
        }
    }
    crate::kmain(RawBoot::DeviceTree(addr))
}
