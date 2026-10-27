#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
mkdir -p work/downloads work/source logs
BASE=https://downloads.openwrt.org/releases/25.12.6/targets/x86/64
SDK=openwrt-sdk-25.12.6-x86-64_gcc-14.3.0_musl.Linux-x86_64.tar.zst
ROOTFS=openwrt-25.12.6-x86-64-generic-targz-rootfs.tar.gz
OPENWRT_COMMIT=64900e756efa667774214f9c6b17c113222e01f7
UBOX_COMMIT=6f78fa496bf36c55864a41e353df7d13f04b1077
fetch_checked() {
    local name=$1 hash=$2 url=$3
    if ! (cd work/downloads && printf '%s  %s\n' "$hash" "$name" | sha256sum -c -); then
        curl --fail --location --retry 4 "$url" -o "work/downloads/$name"
    fi
    (cd work/downloads && printf '%s  %s\n' "$hash" "$name" | sha256sum -c -)
}
fetch_checked "$SDK" 1864152619092e781fa36a401960c8e9ae42d6a364c44ee5f0b197ca5f3c0fcc "$BASE/$SDK"
fetch_checked "$ROOTFS" d09cb68dd78a7f7b1c4ed788ad42162e07ec094b20f66b382cd4f91c9443970f "$BASE/$ROOTFS"
fetch_checked manifest c9134de86be04c546a196190f463720300bd8f47859a55d8b21f42277ee5b9c8 "$BASE/openwrt-25.12.6-x86-64.manifest"
fetch_checked version.buildinfo 47cc6a2e45cd952f6b4d5edaf3ba2259a038a8f7f834b37edcdac78f97078c9c "$BASE/version.buildinfo"
SDKDIR="$ROOT/work/${SDK%.tar.zst}"
# A fresh SDK is required; never silently reuse a modified build tree.
test ! -e "$SDKDIR"
tar --zstd -xf "work/downloads/$SDK" -C work
cd "$SDKDIR"
grep -Fx "src-git --root=package base https://git.openwrt.org/openwrt/openwrt.git^$OPENWRT_COMMIT" feeds.conf.default
# Update only the SDK-pinned base feed, never current branch heads.
./scripts/feeds update base
test "$(git -C feeds/base rev-parse HEAD)" = "$OPENWRT_COMMIT"
PKG=feeds/base/system/ubox
test -d "$PKG"
test ! -d "$PKG/patches"
grep -Fx "PKG_SOURCE_VERSION:=$UBOX_COMMIT" "$PKG/Makefile"
grep -Fx 'PKG_SOURCE_DATE:=2025-10-30' "$PKG/Makefile"
grep -Fx 'PKG_RELEASE:=1' "$PKG/Makefile"
cp -a "$PKG" "$ROOT/work/source/ubox-package-original"
mkdir -p "$PKG/patches"
cp "$ROOT/patches/100-logd-disable-kernel-log.patch" "$PKG/patches/"
./scripts/feeds install -p base ubox
cat >> .config <<'EOF'
CONFIG_ALL_NONSHARED=n
CONFIG_ALL_KMODS=n
CONFIG_ALL=n
CONFIG_AUTOREMOVE=n
CONFIG_PACKAGE_logd=m
CONFIG_PACKAGE_ubox=n
CONFIG_PACKAGE_getrandom=n
CONFIG_SIGNED_PACKAGES=n
EOF
make defconfig
make package/ubox/download V=s
SOURCE=ubox-2025.10.30~6f78fa49.tar.zst
printf '%s  %s\n' 41c28d9152cdf2998a4d867827655548f823de9de522a113a45ed1efef97d3ae "dl/$SOURCE" | sha256sum -c -
cp "dl/$SOURCE" "$ROOT/work/source/"
make package/ubox/prepare V=s
mapfile -t SOURCES < <(find build_dir -path '*/ubox-2025.10.30~6f78fa49/log/syslog.c' -type f)
test "${#SOURCES[@]}" -eq 1
python3 "$ROOT/scripts/check-source.py" "${SOURCES[0]}"
make -j2 package/ubox/compile V=s
mapfile -t BINARIES < <(find build_dir -path '*/ipkg-x86_64/logd/sbin/logd' -type f)
test "${#BINARIES[@]}" -eq 1
cp "${BINARIES[0]}" "$ROOT/work/logd"
chmod 0755 "$ROOT/work/logd"
cp .config "$ROOT/logs/sdk.config"
cp feeds.conf.default "$ROOT/logs/feeds.conf.default"
cp feeds/base/libs/libubox/Makefile "$ROOT/logs/libubox.Makefile"
cp feeds/base/system/ubus/Makefile "$ROOT/logs/ubus.Makefile"
cp feeds/base/libs/udebug/Makefile "$ROOT/logs/udebug.Makefile"
find staging_dir -path '*/bin/*openwrt-linux-musl-gcc' -type f -exec {} --version \; > "$ROOT/logs/compiler.txt"
test -s "$ROOT/logs/compiler.txt"
cd "$ROOT"
python3 scripts/check-elf.py
