#!/usr/bin/env bash
set -euo pipefail
export LC_ALL=C
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
test "$(id -u)" -eq 0
test -n "${LOGD_TEST_HOST_PID_NS:-}"
test "$(readlink /proc/self/ns/pid)" != "$LOGD_TEST_HOST_PID_NS"
mount --make-rprivate /
TESTROOT="$ROOT/work/test-rootfs"
test ! -e "$TESTROOT"
mkdir -p "$TESTROOT"
tar -xzf work/downloads/openwrt-25.12.6-x86-64-generic-targz-rootfs.tar.gz -C "$TESTROOT"
install -m 0755 work/logd "$TESTROOT/sbin/logd"
mkdir -p "$TESTROOT/proc" "$TESTROOT/dev" "$TESTROOT/tmp"
mount -t proc proc "$TESTROOT/proc"
mount -t tmpfs -o mode=755 tmpfs "$TESTROOT/dev"
mknod -m 666 "$TESTROOT/dev/null" c 1 3
mknod -m 666 "$TESTROOT/dev/zero" c 1 5
mkdir -p "$TESTROOT/var/run/ubus" "$TESTROOT/var/lock"
chmod 1777 "$TESTROOT/tmp"
chroot "$TESTROOT" /lib/ld-musl-x86_64.so.1 --list /sbin/logd > logs/loader-check.txt 2>&1
cat logs/loader-check.txt
! grep -E 'Error|not found' logs/loader-check.txt
python3 scripts/test-runtime.py "$TESTROOT"
touch logs/runtime-PASS
