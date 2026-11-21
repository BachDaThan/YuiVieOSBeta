//! Nửa `unsafe` của `FromBytes` (P2.22): ép `&[u8]` → `&T` không chép.
//!
//! Toàn bộ phần *kiểm* (độ dài, căn chỉnh, kiểu không đệm, mọi mẫu bit hợp lệ)
//! nằm ở `yui_cap::frombytes`, crate giữ `#![deny(unsafe_code)]` và có test
//! trên host. Tệp này chỉ thêm **đúng một khối `unsafe`** trong [`cast`], chạy
//! ngay sau khi `check` trả `Ok`. Không có đường nào tới phép ép mà bỏ qua
//! `check`: [`ref_from_bytes`] và [`ref_from_prefix`] đều đi qua [`cast`].
//!
//! [`self_test`] chạy lúc boot trên cả ba kiến trúc, đọc cùng tệp
//! `tests/data/frombytes_vectors.txt` mà `cargo test` của `kernel-cap` dùng, nên
//! phép ép thật được thử trên máy đích (căn chỉnh `u64` của từng arch, aarch64
//! với MMU tắt nơi truy cập lệch gây lỗi đồng bộ).

use core::mem::size_of;
use yui_cap::frombytes::{
    check, layout_of, outcome, parse_line, DemoHeader, FromBytes, FromBytesError, Le32, LeRecord,
    Line, Mode,
};

/// Phép ép duy nhất. `check::<T>` bảo đảm: `size_of::<T>() > 0`, bộ đệm đủ dài
/// (đúng bằng với `Exact`), địa chỉ đầu chia hết cho `align_of::<T>()`.
fn cast<T: FromBytes>(bytes: &[u8], mode: Mode) -> Result<&T, FromBytesError> {
    check::<T>(bytes.as_ptr() as usize, bytes.len(), mode)?;
    // AN TOÀN: (1) con trỏ khác null, căn chỉnh đúng `T` và trỏ tới ít nhất
    // `size_of::<T>()` byte đã khởi tạo thuộc `bytes` — `check` vừa xác nhận;
    // (2) `T: FromBytes` (trait niêm phong ở kernel-cap) chỉ gồm kiểu không đệm,
    // không `UnsafeCell`, mọi mẫu bit hợp lệ — macro kiểm lúc biên dịch;
    // (3) tham chiếu trả về mượn `bytes` với cùng thời gian sống và chỉ đọc,
    // nên không ai ghi vào vùng đó trong lúc `&T` còn sống.
    Ok(unsafe { &*bytes.as_ptr().cast::<T>() })
}

/// Đọc cả bộ đệm thành `&T`; độ dài phải đúng `size_of::<T>()`.
pub fn ref_from_bytes<T: FromBytes>(bytes: &[u8]) -> Result<&T, FromBytesError> {
    cast(bytes, Mode::Exact)
}

/// Đọc `&T` ở đầu bộ đệm, trả kèm phần còn lại (ví dụ thân sau tiêu đề).
pub fn ref_from_prefix<T: FromBytes>(bytes: &[u8]) -> Result<(&T, &[u8]), FromBytesError> {
    let head = cast::<T>(bytes, Mode::Prefix)?;
    Ok((head, &bytes[size_of::<T>()..]))
}

const VECTORS: &str = include_str!("../../tests/data/frombytes_vectors.txt");
const BUF: usize = 64;

#[repr(C, align(16))]
struct Buf([u8; BUF]);

/// Chạy một ca bằng phép ép thật; trả tên kết quả. Với ca `ok`, kiểm thêm
/// tham chiếu trỏ đúng vào đệm (không chép), phần dư đúng độ dài, và giá trị
/// đọc được khớp cách giải mã từng byte.
fn run<T: FromBytes>(s: &[u8], mode: Mode, value_ok: fn(&T, &[u8]) -> bool) -> &'static str {
    let r = match mode {
        Mode::Exact => ref_from_bytes::<T>(s).map(|t| (t, s.len() - size_of::<T>())),
        Mode::Prefix => ref_from_prefix::<T>(s).map(|(t, rest)| (t, rest.len())),
    };
    match r {
        Ok((t, rest_len)) => {
            let same_addr = t as *const T as usize == s.as_ptr() as usize;
            if same_addr && rest_len == s.len() - size_of::<T>() && value_ok(t, s) {
                outcome(Ok(()))
            } else {
                "sai_noi_dung"
            }
        }
        Err(e) => outcome(Err(e)),
    }
}

fn any<T>(_: &T, _: &[u8]) -> bool {
    true
}

fn run_case(ty: &str, s: &[u8], mode: Mode) -> Option<&'static str> {
    Some(match ty {
        "u8" => run::<u8>(s, mode, |v, b| *v == b[0]),
        "u16" => run::<u16>(s, mode, |v, b| *v == u16::from_ne_bytes([b[0], b[1]])),
        "u32" => run::<u32>(s, mode, |v, b| *v == u32::from_ne_bytes([b[0], b[1], b[2], b[3]])),
        "u64" => run::<u64>(s, mode, |v, b| {
            *v == u64::from_ne_bytes([b[0], b[1], b[2], b[3], b[4], b[5], b[6], b[7]])
        }),
        "le32" => run::<Le32>(s, mode, |v, b| v.get() == u32::from_le_bytes([b[0], b[1], b[2], b[3]])),
        "u32x3" => run::<[u32; 3]>(s, mode, any),
        "demo_header" => run::<DemoHeader>(s, mode, |v, b| {
            v.magic.get() == u32::from_le_bytes([b[0], b[1], b[2], b[3]])
                && v.flags.get() == u16::from_le_bytes([b[6], b[7]])
        }),
        "le_record" => run::<LeRecord>(s, mode, |v, b| {
            v.b.get() == u32::from_le_bytes([b[2], b[3], b[4], b[5]])
        }),
        _ => return None,
    })
}

/// Tự kiểm lúc boot. In một dòng; `qemu-smoke.sh` tìm chuỗi "FromBytes : ok".
pub fn self_test() {
    let mut buf = Buf([0; BUF]);
    for (i, b) in buf.0.iter_mut().enumerate() {
        *b = (i as u8).wrapping_mul(37).wrapping_add(11);
    }

    let (mut types, mut cases, mut bad) = (0u32, 0u32, 0u32);
    for raw in VECTORS.lines() {
        match parse_line(raw) {
            Ok(None) => {}
            Ok(Some(Line::Type(name, size, align))) => {
                types += 1;
                if layout_of(name) != Some((size, align)) {
                    bad += 1;
                    print!("    LOI layout kieu ");
                    crate::console::print_str(name);
                }
            }
            Ok(Some(Line::Case(c))) => {
                cases += 1;
                let got = if c.off + c.len <= BUF {
                    run_case(c.ty, &buf.0[c.off..c.off + c.len], c.mode)
                } else {
                    None
                };
                if got != Some(c.expect) {
                    bad += 1;
                    if bad <= 5 {
                        print!("    LOI vector: ");
                        crate::console::print_str(raw);
                    }
                }
            }
            Err(()) => {
                bad += 1;
                print!("    LOI dong hong: ");
                crate::console::print_str(raw);
            }
        }
    }

    if bad == 0 && cases >= 100 {
        println!("  FromBytes : ok ({} vector, {} kieu, ep con tro that)", cases, types);
    } else {
        println!("  FromBytes : LOI {} sai / {} vector, {} kieu", bad, cases, types);
    }
}
