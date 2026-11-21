//! `FromBytes` tự viết cho zero-copy an toàn (P2.22, thay crate `zerocopy`).
//!
//! Đọc tiêu đề `.yui`/`.yuit` hay khung `link-core` thẳng từ bộ đệm byte, không
//! chép, cần ba điều:
//!
//! 1. **Kiểu đích chấp nhận mọi mẫu bit.** Chỉ các kiểu trong module này được
//!    cài [`FromBytes`] (trait bị niêm phong — crate khác không cài được): số
//!    nguyên không dấu, [`Le16`]/[`Le32`]/[`Le64`], mảng của chúng, và struct
//!    khai báo qua macro `frombytes_struct!` (mỗi trường phải là `FromBytes`).
//! 2. **Không có byte đệm.** Macro kiểm *lúc biên dịch*: `size_of` của struct
//!    `repr(C)` phải bằng tổng `size_of` các trường; sai thì không build được.
//! 3. **Độ dài và căn chỉnh đúng.** [`check`] kiểm *lúc chạy* và trả `Err` khi
//!    sai — không bao giờ panic.
//!
//! Crate này giữ `#![deny(unsafe_code)]` nên chỉ làm phần *kiểm*. Phép ép con
//! trỏ `&[u8]` → `&T` (cần đúng một khối `unsafe`) sống ở
//! `kernel-frame/src/frombytes.rs`, gọi [`check`] ngay trước khi ép.
//!
//! Thứ tự quy tắc (khớp `scripts/gen_frombytes_vectors.py`):
//! `ZeroSized` → `TooShort` → `LengthMismatch` (chỉ chế độ `Exact`) →
//! `Misaligned` → `Ok`.

use core::mem::{align_of, size_of};

/// Kết quả sai của [`check`].
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FromBytesError {
    /// Kiểu có kích thước 0 (ví dụ `[u32; 0]`): không có gì để đọc.
    ZeroSized,
    /// Bộ đệm ngắn hơn `size_of::<T>()`.
    TooShort,
    /// Chế độ `Exact` nhưng bộ đệm dài hơn `size_of::<T>()`.
    LengthMismatch,
    /// Địa chỉ đầu không chia hết cho `align_of::<T>()`.
    Misaligned,
}

impl FromBytesError {
    /// Tên dùng trong `tests/data/frombytes_vectors.txt`.
    pub const fn as_str(self) -> &'static str {
        match self {
            FromBytesError::ZeroSized => "zero_sized",
            FromBytesError::TooShort => "too_short",
            FromBytesError::LengthMismatch => "length_mismatch",
            FromBytesError::Misaligned => "misaligned",
        }
    }
}

/// Chế độ đọc.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    /// Bộ đệm phải dài đúng `size_of::<T>()`.
    Exact,
    /// Bộ đệm dài ít nhất `size_of::<T>()`; phần dư trả lại cho người gọi.
    Prefix,
}

/// Kiểm thuần số học — không cần kiểu, dùng chung cho test vector và nhân.
///
/// `align` phải là luỹ thừa của 2 (luôn đúng với `align_of`).
pub const fn check_layout(
    size: usize,
    align: usize,
    addr: usize,
    len: usize,
    mode: Mode,
) -> Result<(), FromBytesError> {
    if size == 0 {
        return Err(FromBytesError::ZeroSized);
    }
    if len < size {
        return Err(FromBytesError::TooShort);
    }
    if matches!(mode, Mode::Exact) && len > size {
        return Err(FromBytesError::LengthMismatch);
    }
    if align == 0 || addr & (align - 1) != 0 {
        return Err(FromBytesError::Misaligned);
    }
    Ok(())
}

/// Kiểm một bộ đệm (địa chỉ đầu `addr`, dài `len`) có đọc được thành `&T`.
///
/// `Ok(())` ⇒ ép `addr as *const T` thành `&T` là hợp lệ, miễn bộ đệm sống ít
/// nhất bằng tham chiếu trả về và không bị ghi trong lúc đó (`&[u8]` bảo đảm).
pub fn check<T: FromBytes>(addr: usize, len: usize, mode: Mode) -> Result<(), FromBytesError> {
    check_layout(size_of::<T>(), align_of::<T>(), addr, len, mode)
}

mod private {
    /// Niêm phong: chỉ module `frombytes` cài được [`super::FromBytes`].
    pub trait Sealed {}
}

/// Kiểu đọc được thẳng từ byte: `repr(C)`/`repr(transparent)`, không đệm, mọi
/// mẫu bit hợp lệ, không có `UnsafeCell`. Bị niêm phong — thêm kiểu mới bằng
/// `frombytes_struct!` trong module này để macro kiểm đệm lúc biên dịch.
pub trait FromBytes: private::Sealed + Sized {}

/// Dùng trong `const _` của macro: chỉ biên dịch được khi `T: FromBytes`.
#[doc(hidden)]
pub const fn assert_frombytes<T: FromBytes>() {}

macro_rules! frombytes_prim {
    ($($t:ty),*) => {$(
        impl private::Sealed for $t {}
        impl FromBytes for $t {}
    )*};
}
// Chỉ số nguyên không dấu: `bool`/`char`/enum có mẫu bit không hợp lệ, số có
// dấu thì hợp lệ nhưng chưa ai cần — thêm khi có người dùng thật.
frombytes_prim!(u8, u16, u32, u64);

impl<T: FromBytes, const N: usize> private::Sealed for [T; N] {}
impl<T: FromBytes, const N: usize> FromBytes for [T; N] {}

macro_rules! le_int {
    ($(#[$m:meta])* $name:ident, $int:ty, $n:expr) => {
        $(#[$m])*
        #[repr(transparent)]
        #[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
        pub struct $name(pub [u8; $n]);

        impl $name {
            pub const fn new(v: $int) -> Self { $name(v.to_le_bytes()) }
            pub const fn get(self) -> $int { <$int>::from_le_bytes(self.0) }
        }

        impl private::Sealed for $name {}
        impl FromBytes for $name {}
    };
}
le_int!(
    /// `u16` little-endian, căn 1 — dùng cho định dạng trên đĩa/dây.
    Le16, u16, 2
);
le_int!(
    /// `u32` little-endian, căn 1.
    Le32, u32, 4
);
le_int!(
    /// `u64` little-endian, căn 1.
    Le64, u64, 8
);

/// Khai báo struct `repr(C)` đọc được thẳng từ byte. Kiểm lúc biên dịch:
/// mỗi trường là `FromBytes`, và không có byte đệm (kể cả đệm đuôi).
macro_rules! frombytes_struct {
    (
        $(#[$m:meta])*
        $vis:vis struct $name:ident { $($(#[$fm:meta])* $fvis:vis $f:ident : $ft:ty),* $(,)? }
    ) => {
        $(#[$m])*
        #[repr(C)]
        #[derive(Clone, Copy, Debug, PartialEq, Eq)]
        $vis struct $name { $($(#[$fm])* $fvis $f: $ft),* }

        impl private::Sealed for $name {}
        impl FromBytes for $name {}

        const _: () = {
            $( assert_frombytes::<$ft>(); )*
            assert!(
                size_of::<$name>() == 0 $(+ size_of::<$ft>())*,
                "frombytes_struct!: struct có byte đệm — sắp lại trường hoặc dùng Le16/Le32/Le64"
            );
        };
    };
}

frombytes_struct! {
    /// Tiêu đề mẫu 16 byte, căn 8 (`u64` gốc): mô phỏng đầu tệp `.yui`.
    pub struct DemoHeader {
        pub magic: Le32,
        pub version: Le16,
        pub flags: Le16,
        pub length: u64,
    }
}

frombytes_struct! {
    /// Bản ghi 8 byte căn 1: trường lẻ vị trí, chỉ đọc được nhờ `LeNN`.
    pub struct LeRecord {
        pub a: Le16,
        pub b: Le32,
        pub c: Le16,
    }
}

/// Bảng kiểu trong `tests/data/frombytes_vectors.txt`: tên → (size, align)
/// thật trên đích đang build. Test (host) và tự kiểm lúc boot (nhân) so bảng
/// này với dòng `type` của tệp vector.
pub fn layout_of(name: &str) -> Option<(usize, usize)> {
    fn l<T>() -> Option<(usize, usize)> {
        Some((size_of::<T>(), align_of::<T>()))
    }
    match name {
        "u8" => l::<u8>(),
        "u16" => l::<u16>(),
        "u32" => l::<u32>(),
        "u64" => l::<u64>(),
        "le32" => l::<Le32>(),
        "u32x3" => l::<[u32; 3]>(),
        "demo_header" => l::<DemoHeader>(),
        "le_record" => l::<LeRecord>(),
        _ => None,
    }
}

/// Một dòng ca thử đã tách: (kiểu, chế độ, độ dài, lệch, kết quả mong đợi).
pub struct Case<'a> {
    pub ty: &'a str,
    pub mode: Mode,
    pub len: usize,
    pub off: usize,
    pub expect: &'a str,
}

/// Một dòng của tệp vector.
pub enum Line<'a> {
    /// `type <tên> <size> <align>`
    Type(&'a str, usize, usize),
    Case(Case<'a>),
}

/// Tách một dòng tệp vector; `Ok(None)` cho dòng trống/chú thích. Dùng chung
/// cho `cargo test` và tự kiểm lúc boot để hai bên đọc tệp y như nhau.
pub fn parse_line(line: &str) -> Result<Option<Line<'_>>, ()> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('#') {
        return Ok(None);
    }
    let mut it = line.split_whitespace();
    let first = it.next().ok_or(())?;
    fn num(s: Option<&str>) -> Result<usize, ()> {
        s.ok_or(())?.parse::<usize>().map_err(|_| ())
    }
    if first == "type" {
        let name = it.next().ok_or(())?;
        let size = num(it.next())?;
        let align = num(it.next())?;
        return if it.next().is_none() { Ok(Some(Line::Type(name, size, align))) } else { Err(()) };
    }
    let mode = match it.next().ok_or(())? {
        "exact" => Mode::Exact,
        "prefix" => Mode::Prefix,
        _ => return Err(()),
    };
    let len = num(it.next())?;
    let off = num(it.next())?;
    let expect = it.next().ok_or(())?;
    if it.next().is_some() {
        return Err(());
    }
    Ok(Some(Line::Case(Case { ty: first, mode, len, off, expect })))
}

/// Kết quả dạng tên (`"ok"` hoặc [`FromBytesError::as_str`]).
pub fn outcome(r: Result<(), FromBytesError>) -> &'static str {
    match r {
        Ok(()) => "ok",
        Err(e) => e.as_str(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const VECTORS: &str = include_str!("../../tests/data/frombytes_vectors.txt");

    #[test]
    fn vectors_match_reference() {
        // Gốc đệm giả lập căn 16 như đệm thật trong nhân; thử vài gốc khác
        // nhau (đều căn 16) để chắc kết quả chỉ phụ thuộc `lệch`.
        let mut types = 0;
        let mut cases = 0;
        let mut by_kind = std::collections::BTreeMap::new();
        for (no, raw) in VECTORS.lines().enumerate() {
            match parse_line(raw).unwrap_or_else(|_| panic!("dòng {} hỏng: {raw}", no + 1)) {
                None => {}
                Some(Line::Type(name, size, align)) => {
                    assert_eq!(layout_of(name), Some((size, align)), "kiểu {name} đổi layout");
                    types += 1;
                }
                Some(Line::Case(c)) => {
                    let (size, align) = layout_of(c.ty).expect("kiểu lạ");
                    for base in [0x1000usize, 0x2010, 0xFFF0] {
                        let got = outcome(check_layout(size, align, base + c.off, c.len, c.mode));
                        assert_eq!(got, c.expect, "dòng {}: {raw} (gốc {base:#x})", no + 1);
                    }
                    *by_kind.entry(c.expect).or_insert(0) += 1;
                    cases += 1;
                }
            }
        }
        assert_eq!(types, 8);
        // DoD P2.22: ≥ 100 vector, đủ cả ngắn / lệch căn chỉnh / đúng.
        assert!(cases >= 100, "chỉ có {cases} ca");
        for k in ["ok", "too_short", "misaligned", "length_mismatch"] {
            assert!(by_kind.get(k).copied().unwrap_or(0) > 0, "thiếu ca {k}");
        }
    }

    #[test]
    fn check_generic_matches_layout() {
        let a = align_of::<DemoHeader>();
        assert_eq!(check::<DemoHeader>(0x1000, 16, Mode::Exact), Ok(()));
        assert_eq!(check::<DemoHeader>(0x1000 + a / 2, 16, Mode::Exact), Err(FromBytesError::Misaligned));
        assert_eq!(check::<DemoHeader>(0x1000, 15, Mode::Prefix), Err(FromBytesError::TooShort));
        assert_eq!(check::<DemoHeader>(0x1000, 17, Mode::Exact), Err(FromBytesError::LengthMismatch));
        assert_eq!(check::<DemoHeader>(0x1000, 17, Mode::Prefix), Ok(()));
        // Le32 căn 1: địa chỉ lẻ vẫn đọc được.
        assert_eq!(check::<LeRecord>(0x1001, 8, Mode::Exact), Ok(()));
    }

    #[test]
    fn zero_sized_rejected_first() {
        assert_eq!(check::<[u32; 0]>(0x1000, 0, Mode::Exact), Err(FromBytesError::ZeroSized));
        // ZeroSized đứng trước mọi quy tắc khác, kể cả lệch căn chỉnh.
        assert_eq!(check::<[u64; 0]>(0x1001, 5, Mode::Exact), Err(FromBytesError::ZeroSized));
    }

    #[test]
    fn length_checked_before_alignment() {
        // Ngắn và lệch cùng lúc ⇒ báo TooShort (thứ tự trong tài liệu module).
        assert_eq!(check_layout(8, 8, 0x1001, 3, Mode::Exact), Err(FromBytesError::TooShort));
        assert_eq!(check_layout(8, 8, 0x1001, 9, Mode::Exact), Err(FromBytesError::LengthMismatch));
        assert_eq!(check_layout(8, 8, 0x1001, 9, Mode::Prefix), Err(FromBytesError::Misaligned));
    }

    #[test]
    fn huge_lengths_do_not_overflow() {
        assert_eq!(check_layout(16, 8, usize::MAX & !7, usize::MAX, Mode::Prefix), Ok(()));
        assert_eq!(check_layout(16, 8, usize::MAX, usize::MAX, Mode::Prefix), Err(FromBytesError::Misaligned));
    }

    #[test]
    fn le_types_roundtrip() {
        assert_eq!(Le16::new(0xBEEF).get(), 0xBEEF);
        assert_eq!(Le32::new(0x0102_0304).0, [4, 3, 2, 1]);
        assert_eq!(Le64::new(u64::MAX - 1).get(), u64::MAX - 1);
        assert_eq!(size_of::<LeRecord>(), 8);
        assert_eq!(align_of::<LeRecord>(), 1);
        assert_eq!(size_of::<DemoHeader>(), 16);
    }

    #[test]
    fn parse_line_rejects_garbage() {
        assert!(parse_line("u8 sideways 1 0 ok").is_err());
        assert!(parse_line("u8 exact x 0 ok").is_err());
        assert!(parse_line("u8 exact 1 0 ok extra").is_err());
        assert!(parse_line("type u8 1").is_err());
        assert!(matches!(parse_line("  # chú thích"), Ok(None)));
        assert!(matches!(parse_line(""), Ok(None)));
    }
}
