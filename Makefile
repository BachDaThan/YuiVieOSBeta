# YuiVieOS — top-level build.
#
# Everything here is plain POSIX + a C++17 compiler.  The Rust workspace
# (kernel-cap, kernel-services/*) is built with cargo (see docs/BUILD.md) and is
# optional for the C++ targets.
#
#   make            build every C++ target into build/bin
#   make test       build and run the whole C++ test suite
#   make check      test + end-to-end smoke runs + static verification
#   make verify     static checks only (needs no toolchain but a C compiler)
#   make install    install into $(PREFIX) (default /usr/local)
#   make ibus       build the optional IBus adapter (needs libibus-1.0-dev)
#   make kernel     build the bare-metal frame for ARCH (nightly + QEMU image)
#   make clean

CXX      ?= g++
CC       ?= gcc
CXXFLAGS ?= -std=c++17 -O2 -g -Wall -Wextra -Wno-unused-parameter
CFLAGS   ?= -std=gnu11 -O2 -g -Wall -Wextra
CPPFLAGS += -Iinclude -Itests -Ikernel-services -Iuserspace-vi -D_GNU_SOURCE
LDFLAGS  ?=
LDLIBS   ?= -lpthread -lm
PKG_CONFIG ?= pkg-config
IBUS_CFLAGS = $(shell $(PKG_CONFIG) --cflags ibus-1.0 2>/dev/null)
IBUS_LIBS   = $(shell $(PKG_CONFIG) --libs ibus-1.0 2>/dev/null)

BUILD    := build
BIN      := $(BUILD)/bin
OBJ      := $(BUILD)/obj
PREFIX   ?= /usr/local
DESTDIR  ?=

# Tầng 1/2 primitives live in kernel-services, the AI bridge and its reference
# implementations in ai-bridge-yuid, the Vietnamese user space in userspace-vi.
LIB_SRC := \
	kernel-services/crypto.cpp \
	kernel-services/codec.cpp \
	kernel-services/profile.cpp \
	kernel-services/hw.cpp \
	kernel-services/telemetry.cpp \
	kernel-services/ed25519.cpp \
	kernel-services/bundle.cpp \
	kernel-services/power.cpp \
	kernel-services/guard.cpp \
	kernel-services/fsstore.cpp \
	kernel-services/linuxabi.cpp \
	vmm-sandbox/sandbox.cpp \
	pkg-stripper/apppack.cpp \
	pkg-stripper/store.cpp \
	pkg-stripper/archive.cpp \
	pkg-stripper/zstd.cpp \
	userspace-vi/text.cpp \
	userspace-vi/ime.cpp \
	userspace-vi/ui.cpp \
	userspace-vi/fb.cpp \
	userspace-vi/display.cpp \
	userspace-vi/shell.cpp \
	userspace-vi/trash.cpp \
	userspace-vi/posix.cpp \
	ai-bridge-yuid/reference/graph.cpp \
	ai-bridge-yuid/reference/engine.cpp \
	ai-bridge-yuid/reference/vault.cpp \
	ai-bridge-yuid/daemon/service.cpp \
	ai-bridge-yuid/daemon/server.cpp

LIB_OBJ := $(patsubst %.cpp,$(OBJ)/%.o,$(LIB_SRC))

# Header changes must trigger a rebuild (otherwise a comment/doc fix looks like
# "nothing to be done" and stale objects are silently reused).
HEADERS := $(wildcard include/yui/*.hpp include/yui/*.h) \
           $(wildcard tests/*.hpp) $(wildcard userspace-vi/*.inc)

TESTS := test_crypto test_codec_json test_core test_sandbox test_ime test_daemon test_tools \
         test_telemetry test_fb test_ed25519 test_power test_fsstore test_linuxabi \
         test_redteam test_store test_trash test_posix test_archive test_display test_hw

# `kernel` is declared before `all`, so pin the default goal explicitly.
.DEFAULT_GOAL := all

.PHONY: all test check verify install install-ibus clean rust fmt kernel qemu ibus

# Optional desktop input method. The core build stays dependency-free; this
# adapter is built only when explicitly requested.
ibus:
	@$(PKG_CONFIG) --exists ibus-1.0 || { \
		echo "make ibus needs pkg-config and the ibus-1.0 development package" >&2; \
		exit 1; \
	}
	@$(MAKE) --no-print-directory $(BIN)/yui-ibus-engine

$(BIN)/yui-ibus-engine: userspace-vi/ibus/main.cpp userspace-vi/ibus/engine.cpp \
                       userspace-vi/ibus/engine.hpp $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) $(IBUS_CFLAGS) -Iuserspace-vi/ibus \
		-o $@ userspace-vi/ibus/main.cpp userspace-vi/ibus/engine.cpp \
		$(BIN)/libyui.a $(IBUS_LIBS) $(LDLIBS)

# Bare-metal frame: separate toolchain (nightly + rust-src), separate workspace.
# Kept out of `all` so a C++ checkout still builds on a machine without Rust.
ARCH ?= x86_64
kernel:
	./scripts/build-kernel.sh $(ARCH)

qemu:
	./scripts/qemu-smoke.sh $(ARCH) --build

all: $(BIN)/yuid $(BIN)/libyui.a $(BIN)/libyui.so.1 $(BIN)/libyui.so $(BUILD)/yui.pc \
     $(BIN)/yui-profiler $(BIN)/yui-trim $(BIN)/yui-shell $(BIN)/yui-splash $(BIN)/yui-update $(BIN)/yui-store \
     $(BIN)/yui-sandbox-exec $(BIN)/yui-hw

$(OBJ)/%.o: %.cpp $(HEADERS)
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) -fPIC -c $< -o $@

$(OBJ)/capi.o: ai-bridge-yuid/capi.cpp $(HEADERS)
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) -fPIC -c $< -o $@

$(BIN)/libyui.a: $(LIB_OBJ) $(OBJ)/capi.o
	@mkdir -p $(dir $@)
	ar rcs $@ $^

$(BIN)/libyui.so.1: $(LIB_OBJ) $(OBJ)/capi.o
	@mkdir -p $(dir $@)
	$(CXX) -shared -Wl,-soname,libyui.so.1 -o $@ $^ $(LDLIBS)

$(BIN)/libyui.so: $(BIN)/libyui.so.1
	@mkdir -p $(dir $@)
	ln -sf libyui.so.1 $@

$(BUILD)/yui.pc: Makefile
	@mkdir -p $(dir $@)
	@printf "prefix=%s\nexec_prefix=\$${prefix}\nlibdir=%s/build/bin\nincludedir=%s/include\n\nName: yui\nDescription: YuiVieOS C-ABI library for AI, IME, graph, vault, telemetry and capabilities\nVersion: 0.1.0\nLibs: -L\$${libdir} -lyui -lpthread -lm\nCflags: -I\$${includedir}\n" "$(PREFIX)" "$(CURDIR)" "$(CURDIR)" > $@

$(BIN)/yuid: $(OBJ)/ai-bridge-yuid/daemon/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-profiler: $(OBJ)/tools/profiler/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-hw: $(OBJ)/tools/hw/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-trim: $(OBJ)/tools/trim/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-shell: $(OBJ)/tools/shell/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-splash: $(OBJ)/tools/splash/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-update: $(OBJ)/tools/update/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

$(BIN)/yui-store: $(OBJ)/tools/store/main.o $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDLIBS)

# Bệ phóng hộp cát (Landlock + no_new_privs) cho lệnh POSIX của yui-shell — không cần libyui.
$(BIN)/yui-sandbox-exec: $(OBJ)/tools/sandbox-exec/main.o
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) -o $@ $^

$(OBJ)/test/%: tests/%.cpp $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CXX) $(CXXFLAGS) $(CPPFLAGS) -DYUI_SOURCE_DIR='"$(CURDIR)"' -o $@ $< $(BIN)/libyui.a $(LDLIBS)

$(BUILD)/test_capi: tests/test_capi.c $(BIN)/libyui.a
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -Iinclude -o $@ $< $(BIN)/libyui.a -lstdc++ $(LDLIBS)

test: all $(addprefix $(OBJ)/test/,$(TESTS)) $(BUILD)/test_capi   # `all` trước: test_tools gọi build/bin/yui-update (P0.15)
	@set -e; L=$(BUILD)/test-logs; rm -rf $$L; mkdir -p $$L; \
	for t in $(TESTS); do echo "── $$t"; \
	  ./$(OBJ)/test/$$t > $$L/$$t.log 2>&1 && st=0 || st=$$?; cat $$L/$$t.log; [ $$st -eq 0 ] || exit $$st; \
	done; \
	echo "── test_capi (C11)"; \
	./$(BUILD)/test_capi > $$L/test_capi.log 2>&1 && st=0 || st=$$?; cat $$L/test_capi.log; [ $$st -eq 0 ] || exit $$st

verify:
	@./scripts/verify.sh

check: all test verify
	@echo "── smoke: yuid --info"
	@./$(BIN)/yuid --info > /dev/null
	@echo "── smoke: yuid --profile"
	@./$(BIN)/yuid --profile | head -5
	@echo "── smoke: yui-profiler"
	@./$(BIN)/yui-profiler | head -4
	@echo "── smoke: yui-hw (quét chỉ-đọc, JSON ổn định giữa hai lần quét)"
	@./$(BIN)/yui-hw --json > /tmp/smoke-hw-1.json && ./$(BIN)/yui-hw --json > /tmp/smoke-hw-2.json && cmp /tmp/smoke-hw-1.json /tmp/smoke-hw-2.json
	@echo "── smoke: shell script"
	@printf 'thôngtin\nthoát\n' | ./$(BIN)/yui-shell > /dev/null
	@echo "── smoke: thùng rác (xoá → khôi phục, băm khớp)"
	@rm -rf /tmp/smoke-trash && mkdir -p /tmp/smoke-trash/state && echo "dữ liệu" > /tmp/smoke-trash/tệp.txt && sha256sum /tmp/smoke-trash/tệp.txt > /tmp/smoke-trash.sum
	@printf 'xoá /tmp/smoke-trash/tệp.txt\nkhôiphục tệp.txt\nthoát\n' | YUI_STATE_DIR=/tmp/smoke-trash/state ./$(BIN)/yui-shell > /dev/null
	@sha256sum -c --quiet /tmp/smoke-trash.sum
	@echo "── yui-shell: chế độ POSIX (ống dẫn + chuyển hướng trong hộp cát) + dòng lạ không tự chạy"
	@rm -rf /tmp/smoke-posix && mkdir -p /tmp/smoke-posix/state
	@ALLOW=$$(./$(BIN)/yui-sandbox-exec --probe >/dev/null 2>&1 || echo 1); \
	 printf '!echo xin chao | tr a-z A-Z > /tmp/smoke-posix/out.txt\ntouch /tmp/smoke-posix/khong-duoc\nthoát\n' | \
	 YUI_STATE_DIR=/tmp/smoke-posix/state YUI_POSIX_ALLOW_UNSANDBOXED=$$ALLOW ./$(BIN)/yui-shell > /dev/null
	@grep -qx 'XIN CHAO' /tmp/smoke-posix/out.txt && test ! -e /tmp/smoke-posix/khong-duoc
	@grep -q 'shell.exec' /tmp/smoke-posix/state/audit.log
	@echo "── smoke: splash → PPM"
	@./$(BIN)/yui-splash --width 320 --height 200 --out /tmp/yui-splash.ppm > /dev/null
	@test -s /tmp/yui-splash.ppm
	@echo "── smoke: yui-update"
	@./$(BIN)/yui-update --trogiup > /dev/null
	@./$(BIN)/yui-update status --state-dir /tmp/smoke-update > /dev/null
	@echo "── smoke: yui-store"
	@./$(BIN)/yui-store --trogiup > /dev/null
	@./$(BIN)/yui-store list --root /tmp/smoke-store > /dev/null
	@echo "── smoke: pkg-config + C demo"
	@PKG_CONFIG_PATH=$(CURDIR)/build $(CC) examples/c/demo.c $$(PKG_CONFIG_PATH=$(CURDIR)/build pkg-config --cflags --libs yui) -o $(BUILD)/demo_c
	@LD_LIBRARY_PATH=$(BIN):$$LD_LIBRARY_PATH $(BUILD)/demo_c > /dev/null
	@echo "── smoke: python bindings demo"
	@python3 examples/python/demo.py > /dev/null
	@echo "── smoke: mcp integration client"
	@python3 tools/mcp_client.py --server ./$(BIN)/yuid > /dev/null
	@echo "── boundary checker (P7.10)"
	@python3 scripts/test_check_boundaries.py > /dev/null
	@echo "── doc-number checker (P0.16)"
	@python3 scripts/test_check_doc_numbers.py > /dev/null
	@echo "all checks passed"

install: all
	install -Dm755 $(BIN)/yuid $(DESTDIR)$(PREFIX)/bin/yuid
	install -Dm755 $(BIN)/yui-profiler $(DESTDIR)$(PREFIX)/bin/yui-profiler
	install -Dm755 $(BIN)/yui-hw $(DESTDIR)$(PREFIX)/bin/yui-hw
	install -Dm644 docs/hwdb.tsv $(DESTDIR)$(PREFIX)/share/yui/hwdb.tsv
	install -Dm755 $(BIN)/yui-trim $(DESTDIR)$(PREFIX)/bin/yui-trim
	install -Dm755 $(BIN)/yui-shell $(DESTDIR)$(PREFIX)/bin/yui-shell
	install -Dm755 $(BIN)/yui-splash $(DESTDIR)$(PREFIX)/bin/yui-splash
	install -Dm755 $(BIN)/yui-update $(DESTDIR)$(PREFIX)/bin/yui-update
	install -Dm755 $(BIN)/yui-store $(DESTDIR)$(PREFIX)/bin/yui-store
	install -Dm755 $(BIN)/yui-sandbox-exec $(DESTDIR)$(PREFIX)/bin/yui-sandbox-exec
	install -Dm644 $(BIN)/libyui.a $(DESTDIR)$(PREFIX)/lib/libyui.a
	install -Dm755 $(BIN)/libyui.so.1 $(DESTDIR)$(PREFIX)/lib/libyui.so.1
	ln -sf libyui.so.1 $(DESTDIR)$(PREFIX)/lib/libyui.so
	install -Dm644 $(BUILD)/yui.pc $(DESTDIR)$(PREFIX)/lib/pkgconfig/yui.pc
	install -Dm644 include/yui/yui.h $(DESTDIR)$(PREFIX)/include/yui/yui.h
	@if test -x "$(BIN)/yui-ibus-engine"; then \
		$(MAKE) --no-print-directory install-ibus; \
	fi

install-ibus: ibus
	install -Dm755 $(BIN)/yui-ibus-engine $(DESTDIR)$(PREFIX)/bin/yui-ibus-engine
	install -d $(DESTDIR)$(PREFIX)/share/ibus/component
	sed 's|@PREFIX@|$(PREFIX)|g' userspace-vi/ibus/org.freedesktop.IBus.Yui.xml.in \
		> $(DESTDIR)$(PREFIX)/share/ibus/component/org.freedesktop.IBus.Yui.xml

# Rust workspace at the repository root: kernel-cap (Tầng 1) and the
# kernel-services crates (Tầng 2).  Needs cargo; the C++ targets do not.
rust:
	cargo test --workspace
	cargo build --workspace --release

fmt:
	cargo fmt --all
	cargo clippy --workspace --all-targets

clean:
	rm -rf $(BUILD)
