//! yui-cap — the capability core of Tầng 1 (Capability Microkernel).
//!
//! YuiVieOS does not hand out ambient authority: every task holds an explicit
//! set of [`Capability`] values in its own [`CapTable`]. Creating a task means
//! *deriving* a subset of the parent's rights, so a child can never end up with
//! more authority than the parent had. Revocation walks the derivation tree.
//!
//! [`Token`] is the wire form: a subject, a rights mask, an expiry and an
//! HMAC-SHA-256 MAC minted by the capability authority. The exact canonical
//! serialisation is shared with libyui's C++ side (see docs/PROTOCOL.md), which
//! is what lets `yuid` re-verify a token the kernel issued.
//!
//! The crate is `no_std` outside tests; only `alloc` is required.
#![cfg_attr(not(test), no_std)]
#![deny(unsafe_code)]

extern crate alloc;

pub mod sha256;
pub mod sha512;
pub mod ed25519;
pub mod keyring;
pub mod bundle;
pub mod input;
pub mod display;
pub mod fdt;
pub mod frombytes;

use alloc::collections::BTreeMap;
use alloc::string::{String, ToString};
use alloc::vec::Vec;
use alloc::format;

pub use sha256::{ct_eq, hmac_sha256, sha256};
pub use ed25519::{public_key, sign, verify};
pub use sha512::sha512;

// ------------------------------------------------------------------ rights --
pub const RIGHT_NONE: u64 = 0;
pub const RIGHT_FS_READ: u64 = 1 << 0;
pub const RIGHT_FS_WRITE: u64 = 1 << 1;
pub const RIGHT_NET_CONNECT: u64 = 1 << 2;
pub const RIGHT_NET_LISTEN: u64 = 1 << 3;
pub const RIGHT_SPAWN: u64 = 1 << 4;
pub const RIGHT_GPU: u64 = 1 << 5;
pub const RIGHT_INPUT: u64 = 1 << 6;
pub const RIGHT_CAMERA: u64 = 1 << 7;
pub const RIGHT_MIC: u64 = 1 << 8;
pub const RIGHT_LOCATION: u64 = 1 << 9;
pub const RIGHT_POWER: u64 = 1 << 10;
pub const RIGHT_VAULT: u64 = 1 << 11;
pub const RIGHT_GRAPH: u64 = 1 << 12;
pub const RIGHT_MODEL: u64 = 1 << 13;
pub const RIGHT_ADMIN: u64 = 1 << 20;
pub const RIGHT_COMPUTE_HEAVY: u64 = 1 << 21;

/// Human-readable list of rights, comma separated — same vocabulary the policy
/// files and the C++ enforcer use.
pub fn rights_to_string(rights: u64) -> String {
    const NAMES: [(u64, &str); 16] = [
        (RIGHT_FS_READ, "fs.read"),
        (RIGHT_FS_WRITE, "fs.write"),
        (RIGHT_NET_CONNECT, "net.connect"),
        (RIGHT_NET_LISTEN, "net.listen"),
        (RIGHT_SPAWN, "spawn"),
        (RIGHT_GPU, "gpu"),
        (RIGHT_INPUT, "input"),
        (RIGHT_CAMERA, "camera"),
        (RIGHT_MIC, "mic"),
        (RIGHT_LOCATION, "location"),
        (RIGHT_POWER, "power"),
        (RIGHT_VAULT, "vault"),
        (RIGHT_GRAPH, "graph"),
        (RIGHT_MODEL, "model"),
        (RIGHT_ADMIN, "admin"),
        (RIGHT_COMPUTE_HEAVY, "compute.heavy"),
    ];
    // Built by hand rather than with slice::join: this keeps the crate free of
    // the alloc slice internals and works identically in no_std builds.
    let mut out = String::new();
    for (bit, name) in NAMES.iter() {
        if rights & bit != 0 {
            if !out.is_empty() {
                out.push(',');
            }
            out.push_str(name);
        }
    }
    out
}

pub fn rights_from_string(s: &str) -> u64 {
    let mut mask = 0u64;
    for name in s.split(',') {
        mask |= match name.trim() {
            "fs.read" => RIGHT_FS_READ,
            "fs.write" => RIGHT_FS_WRITE,
            "net.connect" => RIGHT_NET_CONNECT,
            "net.listen" => RIGHT_NET_LISTEN,
            "spawn" => RIGHT_SPAWN,
            "gpu" => RIGHT_GPU,
            "input" => RIGHT_INPUT,
            "camera" => RIGHT_CAMERA,
            "mic" => RIGHT_MIC,
            "location" => RIGHT_LOCATION,
            "power" => RIGHT_POWER,
            "vault" => RIGHT_VAULT,
            "graph" => RIGHT_GRAPH,
            "model" => RIGHT_MODEL,
            "admin" => RIGHT_ADMIN,
            "compute.heavy" => RIGHT_COMPUTE_HEAVY,
            _ => RIGHT_NONE,
        };
    }
    mask
}

// -------------------------------------------------------------- capability --
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Capability {
    /// Kernel object the capability refers to (opaque id).
    pub object: u64,
    /// Allowed rights on that object.
    pub rights: u64,
    /// Badge distinguishes derived copies of the same object in audits.
    pub badge: u32,
}

impl Capability {
    pub const fn new(object: u64, rights: u64, badge: u32) -> Self {
        Self { object, rights, badge }
    }

    /// Deriving a capability may only narrow it — never widen.
    pub fn derive(&self, rights: u64, badge: u32) -> Option<Capability> {
        let narrowed = rights & self.rights;
        if narrowed == 0 {
            return None;
        }
        Some(Capability { object: self.object, rights: narrowed, badge })
    }

    pub fn allows(&self, right: u64) -> bool {
        self.rights & right == right && right != 0
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CapError {
    OutOfSlots,
    NoSuchSlot,
    InsufficientRights,
    Revoked,
}

/// Per-task capability table. Slots are stable handles, like a file descriptor.
#[derive(Debug, Default)]
pub struct CapTable {
    slots: BTreeMap<u32, Slot>,
    next_slot: u32,
}

#[derive(Debug, Clone)]
struct Slot {
    cap: Capability,
    /// Parent slot this capability was derived from, for revocation walks.
    parent: Option<u32>,
    revoked: bool,
}

impl CapTable {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn insert(&mut self, cap: Capability) -> Result<u32, CapError> {
        let slot = self.next_slot;
        self.next_slot += 1;
        self.slots.insert(slot, Slot { cap, parent: None, revoked: false });
        Ok(slot)
    }

    pub fn derive(&mut self, parent_slot: u32, rights: u64, badge: u32) -> Result<u32, CapError> {
        let parent = self.slots.get(&parent_slot).ok_or(CapError::NoSuchSlot)?;
        if parent.revoked {
            return Err(CapError::Revoked);
        }
        let child = parent.cap.derive(rights, badge).ok_or(CapError::InsufficientRights)?;
        let slot = self.next_slot;
        self.next_slot += 1;
        self.slots.insert(slot, Slot { cap: child, parent: Some(parent_slot), revoked: false });
        Ok(slot)
    }

    pub fn get(&self, slot: u32) -> Option<&Capability> {
        match self.slots.get(&slot) {
            Some(s) if !s.revoked => Some(&s.cap),
            _ => None,
        }
    }

    pub fn check(&self, slot: u32, right: u64) -> Result<(), CapError> {
        match self.slots.get(&slot) {
            None => Err(CapError::NoSuchSlot),
            Some(s) if s.revoked => Err(CapError::Revoked),
            Some(s) if !s.cap.allows(right) => Err(CapError::InsufficientRights),
            Some(_) => Ok(()),
        }
    }

    /// Revokes a slot and everything derived from it.
    pub fn revoke(&mut self, slot: u32) -> bool {
        if !self.slots.contains_key(&slot) {
            return false;
        }
        let mut frontier = Vec::new();
        frontier.push(slot);
        while let Some(current) = frontier.pop() {
            if let Some(s) = self.slots.get_mut(&current) {
                s.revoked = true;
            }
            for (child_slot, s) in self.slots.iter() {
                if s.parent == Some(current) {
                    frontier.push(*child_slot);
                }
            }
        }
        true
    }

    pub fn len(&self) -> usize {
        self.slots.values().filter(|s| !s.revoked).count()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }
}

// ------------------------------------------------------------------ tokens --
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Token {
    pub subject: String,
    pub issuer: String,
    pub rights: u64,
    pub issued_at: i64,
    pub expires_at: i64,
    pub serial: u32,
    pub scopes: Vec<String>,
    pub mac: [u8; 32],
}

impl Token {
    /// Canonical, byte-for-byte stable serialisation. The field order is frozen
    /// because it is what gets signed (and what the C++ side re-creates).
    pub fn canonical(&self) -> String {
        let mut scopes = String::from("[");
        for (i, scope) in self.scopes.iter().enumerate() {
            if i > 0 {
                scopes.push(',');
            }
            scopes.push('"');
            scopes.push_str(&escape_json(scope));
            scopes.push('"');
        }
        scopes.push(']');
        format!(
            "{{\"sub\":\"{}\",\"iss\":\"{}\",\"rights\":\"{}\",\"iat\":{},\"exp\":{},\"serial\":{},\"scopes\":{}}}",
            escape_json(&self.subject),
            escape_json(&self.issuer),
            rights_to_string(self.rights),
            self.issued_at,
            self.expires_at,
            self.serial,
            scopes
        )
    }
}

fn escape_json(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            _ => out.push(c),
        }
    }
    out
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TokenError {
    Expired,
    NotYetValid,
    BadMac,
    UnknownIssuer,
}

/// The capability authority: mints and verifies tokens with a shared secret.
pub struct Authority {
    key: Vec<u8>,
}

impl Authority {
    pub fn new(key: &[u8]) -> Self {
        Self { key: key.to_vec() }
    }

    pub fn issue(
        &self,
        subject: &str,
        rights: u64,
        scopes: &[&str],
        issued_at: i64,
        ttl_seconds: i64,
        serial: u32,
    ) -> Token {
        let mut token = Token {
            subject: subject.to_string(),
            issuer: String::from("yui-cap"),
            rights,
            issued_at,
            expires_at: if ttl_seconds > 0 { issued_at + ttl_seconds } else { 0 },
            serial,
            scopes: scopes.iter().map(|s| s.to_string()).collect(),
            mac: [0u8; 32],
        };
        token.mac = hmac_sha256(&self.key, token.canonical().as_bytes());
        token
    }

    pub fn verify(&self, token: &Token, now: i64) -> Result<(), TokenError> {
        if token.issuer != "yui-cap" {
            return Err(TokenError::UnknownIssuer);
        }
        if token.expires_at != 0 && now > token.expires_at {
            return Err(TokenError::Expired);
        }
        if token.issued_at > now + 300 {
            return Err(TokenError::NotYetValid);
        }
        let expect = hmac_sha256(&self.key, token.canonical().as_bytes());
        if !ct_eq(&expect, &token.mac) {
            return Err(TokenError::BadMac);
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const KEY: &[u8] = b"00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";

    #[test]
    fn rights_vocabulary_roundtrip() {
        let mask = RIGHT_FS_READ | RIGHT_NET_CONNECT | RIGHT_MODEL;
        assert_eq!(rights_to_string(mask), "fs.read,net.connect,model");
        assert_eq!(rights_from_string("fs.read,net.connect,model"), mask);
        assert_eq!(rights_from_string("bogus,fs.write"), RIGHT_FS_WRITE);
        assert_eq!(rights_from_string(""), RIGHT_NONE);
    }

    #[test]
    fn derivation_only_narrows() {
        let cap = Capability::new(7, RIGHT_FS_READ | RIGHT_FS_WRITE, 1);
        let child = cap.derive(RIGHT_FS_READ | RIGHT_ADMIN, 2).unwrap();
        assert_eq!(child.rights, RIGHT_FS_READ);
        assert!(!child.allows(RIGHT_FS_WRITE));
        assert!(child.allows(RIGHT_FS_READ));
        assert_eq!(cap.derive(RIGHT_ADMIN, 3), None);
        assert_eq!(cap.derive(RIGHT_NONE, 4), None);
    }

    #[test]
    fn table_insert_check_revoke() {
        let mut table = CapTable::new();
        let root = table.insert(Capability::new(1, RIGHT_FS_READ | RIGHT_FS_WRITE, 0)).unwrap();
        assert!(table.check(root, RIGHT_FS_READ).is_ok());
        assert_eq!(table.check(root, RIGHT_GPU), Err(CapError::InsufficientRights));

        let child = table.derive(root, RIGHT_FS_READ, 1).unwrap();
        let grandchild = table.derive(child, RIGHT_FS_READ, 2).unwrap();
        assert_eq!(table.len(), 3);

        assert!(table.revoke(child));
        assert_eq!(table.check(child, RIGHT_FS_READ), Err(CapError::Revoked));
        assert_eq!(table.check(grandchild, RIGHT_FS_READ), Err(CapError::Revoked));
        assert!(table.check(root, RIGHT_FS_READ).is_ok(), "parent stays valid");
        assert_eq!(table.len(), 1);

        assert_eq!(table.check(99, RIGHT_FS_READ), Err(CapError::NoSuchSlot));
        assert_eq!(table.derive(child, RIGHT_FS_READ, 3), Err(CapError::Revoked));
        assert!(!table.revoke(99));
    }

    #[test]
    fn tokens_verify_and_reject_tampering() {
        let authority = Authority::new(KEY);
        let now = 1_700_000_000i64;
        let token = authority.issue("app:trim", RIGHT_FS_READ | RIGHT_VAULT, &["/home/user/Documents"], now, 600, 42);
        assert_eq!(authority.verify(&token, now + 10), Ok(()));
        assert_eq!(authority.verify(&token, now + 601), Err(TokenError::Expired));

        let mut widened = token.clone();
        widened.rights |= RIGHT_ADMIN;
        assert_eq!(authority.verify(&widened, now), Err(TokenError::BadMac));

        // Thời gian được kiểm TRƯỚC MAC (không tiết lộ gì, và cho lỗi dễ hiểu hơn):
        // một thẻ "phát hành ở tương lai" xa hơn 300 s => NotYetValid.
        let mut future = token.clone();
        future.issued_at = now + 3600;
        assert_eq!(authority.verify(&future, now), Err(TokenError::NotYetValid));

        // Còn trong cửa sổ lệch 300 s thì lỗi phải là MAC sai (dữ liệu bị sửa),
        // không phải NotYetValid — nếu không thì kẻ sửa thẻ sẽ được báo sai loại lỗi.
        let mut shifted = token.clone();
        shifted.issued_at = now + 100;
        assert_eq!(authority.verify(&shifted, now), Err(TokenError::BadMac));

        let other = Authority::new(b"another-key");
        assert_eq!(other.verify(&token, now), Err(TokenError::BadMac));

        let mut foreign = token.clone();
        foreign.issuer = String::from("someone-else");
        assert_eq!(authority.verify(&foreign, now), Err(TokenError::UnknownIssuer));
    }

    #[test]
    fn canonical_form_is_stable() {
        let authority = Authority::new(KEY);
        let t = authority.issue("app:yui", RIGHT_MODEL, &["graph:profile", "vault:notes"], 1_700_000_000, 300, 7);
        let canonical = t.canonical();
        assert!(canonical.starts_with("{\"sub\":\"app:yui\",\"iss\":\"yui-cap\""));
        assert!(canonical.contains("\"scopes\":[\"graph:profile\",\"vault:notes\"]"));
        // Re-issuing with the same inputs must produce the identical MAC input.
        let t2 = authority.issue("app:yui", RIGHT_MODEL, &["graph:profile", "vault:notes"], 1_700_000_000, 300, 7);
        assert_eq!(canonical, t2.canonical());
        assert_eq!(t.mac, t2.mac);
        // ...and a changed scope changes both the canonical form and the MAC.
        let t3 = authority.issue("app:yui", RIGHT_MODEL, &["graph:other"], 1_700_000_000, 300, 7);
        assert_ne!(canonical, t3.canonical());
        assert_ne!(t.mac, t3.mac);
    }

    #[test]
    fn token_without_expiry_is_valid_forever() {
        let authority = Authority::new(KEY);
        let token = authority.issue("svc:root", RIGHT_ADMIN, &["*"], 1_700_000_000, 0, 1);
        assert_eq!(token.expires_at, 0);
        assert_eq!(authority.verify(&token, 1_900_000_000), Ok(()));
    }
}
