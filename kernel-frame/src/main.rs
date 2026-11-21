//! yui-frame — khung phần cứng của YuiVieOS Beta (Tầng 0 + Tầng 1).
//!
//! Tệp này là **crate root của một binary** (`[[bin]]` trong Cargo.toml): một
//! crate `lib` chỉ sinh `.rlib`, không có mục vào để QEMU nhảy tới.
//!
//! Nhiệm vụ duy nhất: đưa máy từ trạng thái "firmware vừa nhảy vào" tới trạng
//! thái "dịch vụ Rust an toàn có thể chạy". Cụ thể:
//!
//! 1. dựng ngăn xếp, cổng nối tiếp (serial), bộ cấp phát bộ nhớ;
//! 2. đọc `YuiBootInfo` (RAM, CPU, framebuffer) từ multiboot (x86_64) hoặc
//!    device tree (ARM64, RISC-V);
//! 3. in **Hardware Auto-Profiler**: kiến trúc, CPU, RAM, chế độ
//!    `may-yeu` / `can-bang` / `may-manh` và k/W;
//! 4. khởi tạo **bảng năng lực** của Tầng 1 (`yui-cap`): cấp quyền gốc, dẫn
//!    xuất một quyền con, thu hồi nó — để chứng minh vi nhân sống trên máy thật;
//! 5. vẽ màn hình chào lên framebuffer tuyến tính nếu firmware cung cấp.
//!
//! Sau bước 5 nhân dừng (`halt`) — Phase P2 sẽ thay bằng vòng lặp dịch vụ. Việc
//! dừng có chủ ý: một khung chưa có lập lịch thì không được giả vờ đang chạy.
#![no_std]
#![no_main]
#![feature(alloc_error_handler)]

extern crate alloc;

// `console` phải đứng đầu và có `#[macro_use]`: `print!`/`println!` chỉ sống
// trong phạm vi văn bản (textual scope) tính từ đây trở xuống.
#[macro_use]
pub mod console;

pub mod allocator;
pub mod arch;
pub mod boot;
pub mod cap;
pub mod frombytes;
pub mod profiler;
pub mod splash;

use crate::console::print_str_no_newline;
use core::panic::PanicInfo;

#[global_allocator]
static ALLOCATOR: allocator::BumpAllocator = allocator::BumpAllocator::new();

/// Hết bộ nhớ trong khung: dừng, không tiếp tục với trạng thái không xác định.
#[alloc_error_handler]
fn on_alloc_error(_layout: core::alloc::Layout) -> ! {
    println!("yui: HET BO NHO trong khung cap phat — dung");
    arch::halt_forever()
}

#[panic_handler]
fn on_panic(info: &PanicInfo<'_>) -> ! {
    // Không unwinding trên bare metal: in rồi dừng. Thông điệp song ngữ để log
    // QEMU vẫn đọc được bởi người không quen tiếng Anh.
    println!("\nyui: PANIC — kernel dung");
    if let Some(location) = info.location() {
        print!("  tai ");
        print_str_no_newline(location.file());
        println!(":{}", location.line());
    }
    print!("  ");
    let _ = info; // thông điệp panic đi qua fmt::Arguments; in nhãn trước đã đủ
    println!();
    println!("  (panic = abort: khong co unwinding)");
    arch::halt_forever()
}

/// Điểm vào chung cho cả ba kiến trúc: mỗi `arch::*` chỉ chuẩn bị ngăn xếp và
/// gọi hàm này với thông tin khởi động thô (địa chỉ multiboot info hoặc DTB).
pub fn kmain(raw_boot: boot::RawBoot) -> ! {
    arch::init_console();
    println!();
    println!("yui: ready");
    println!("YuiVieOS Beta · khung phan cung (Tầng 0 + Tầng 1)");
    print!("  Kien truc : ");
    println_str!(boot::arch_name());

    // Các mốc "[n]" có mục đích thực dụng: nếu chỉ thấy mốc n-1 trên cổng nối
    // tiếp là biết khung chết ở bước nào, không phải đoán.
    match raw_boot {
        boot::RawBoot::Multiboot(addr, magic) => {
            print!("  Nguon     : ");
            if magic == 0x36D7_6289 {
                print!("multiboot 2");
            } else {
                print!("multiboot 1");
            }
            println!(" @ {:#x} (magic {:#x})", addr, magic)
        }
        boot::RawBoot::DeviceTree(addr) => println!("  Nguon     : device tree @ {:#x}", addr),
        boot::RawBoot::None => println!("  Nguon     : khong co (firmware khong truyen gi)"),
    }

    println!("  [1] doc YuiBootInfo");
    let info = boot::parse(raw_boot);
    println!("  [2] Hardware Auto-Profiler");
    profiler::report(&info);
    println!("  [3] khoi tao bang nang luc");
    cap::self_test();
    println!("  [3b] FromBytes zero-copy (P2.22)");
    frombytes::self_test();
    println!("  [4] man hinh chao");

    if let Some(fb) = info.framebuffer {
        match splash::render(&fb, &info) {
            Some(d) => {
                // `fb.source` in thẳng: định dạng biến `&str` bằng `{}` treo
                // nhân trên aarch64 (xem console.rs).
                print!(
                    "  Man hinh : ve xong {} pixel ({}x{}x{}, k={}, nguon ",
                    d.pixels, fb.width, fb.height, fb.bpp, d.k
                );
                print_str_no_newline(fb.source);
                println!(")");
            }
            None => println!("  Man hinh : framebuffer khong dung duoc, bo qua"),
        }
    } else {
        println!("  Man hinh : firmware khong cap framebuffer (boot bang serial)");
    }

    println!();
    println!("yui: boot ok — dung o day (P2.2 se bat vong lap dich vu)");
    arch::halt_forever()
}
