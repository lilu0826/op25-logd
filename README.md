# OpenWrt 25.12.6 x86_64：禁用 logd 的内核日志读取

本仓库只修改 `logd`，不部署到路由器。仅当 GitHub Actions 的官方 SDK 编译、ELF 检查、官方 rootfs 隔离测试全部成功时，才生成 `logd-no-kmsg-openwrt-25.12.6-x86_64` 交付 artifact。工作流文件存在不代表已经编译成功；以对应提交的 Actions 结果和 artifact 为准。

## 版本和来源

| 项目 | 固定版本 |
| --- | --- |
| OpenWrt | 25.12.6，x86/64，x86_64，musl |
| 官方发布 revision | `r33311-981c978eff` |
| OpenWrt 发布源码提交 | `64900e756efa667774214f9c6b17c113222e01f7` |
| ubox / logd 包 | `2025.10.30~6f78fa49-r1` |
| ubox 源码提交 | `6f78fa496bf36c55864a41e353df7d13f04b1077` |
| SDK | `openwrt-sdk-25.12.6-x86-64_gcc-14.3.0_musl.Linux-x86_64.tar.zst` |
| SDK SHA-256 | `1864152619092e781fa36a401960c8e9ae42d6a364c44ee5f0b197ca5f3c0fcc` |
| ubox 源码归档 SHA-256 | `41c28d9152cdf2998a4d867827655548f823de9de522a113a45ed1efef97d3ae` |
| 官方测试 rootfs SHA-256 | `d09cb68dd78a7f7b1c4ed788ad42162e07ec094b20f66b382cd4f91c9443970f` |

来源：[官方发行目录](https://downloads.openwrt.org/releases/25.12.6/targets/x86/64/)、[官方包 Makefile](https://github.com/openwrt/openwrt/blob/64900e756efa667774214f9c6b17c113222e01f7/package/system/ubox/Makefile)、[官方 ubox 仓库](https://git.openwrt.org/project/ubox.git)。SDK 内 `feeds.conf.default` 的 base feed 正好固定到上面的 OpenWrt 提交。发布 revision 与发布提交的哈希不同，是官方 `include/version.mk` 的版本设定，不是混用另一个 SDK。

已核实该发布提交的 `package/system/ubox` 没有 `patches/` 目录。构建会再次检查，没有通过就停止。SDK、rootfs、manifest 和源码归档均检查固定 SHA-256；本工作流未额外实现 GPG 签名验证。

官方 manifest 的相关依赖：

- `libc 1.2.5-r5`
- `libubox20260213 2026.06.19~7dd12784-r1`
- `libubus20251202 2026.06.28~24864e78-r2`
- `libudebug 2026.01.16~875e1a7a`

官方原版 `/sbin/logd` 的直接依赖为 `libubox.so.20260213`、`libubus.so.20251202`、`libudebug.so`、`libgcc_s.so.1`、`libc.so`，解释器为 `/lib/ld-musl-x86_64.so.1`。这只是原版检查结果；**新二进制的实测结果必须查看交付的 `static-check.json`、`loader-check.txt` 和 `runtime.log`**。脚本要求新旧直接依赖集合相同，且全部传递依赖能够在官方 rootfs 中找到，并通过实际加载与运行测试。

## 最小补丁

`patches/100-logd-disable-kernel-log.patch` 只改 `log/syslog.c`，共 2 行新增、4 行删除：

1. `log_init()` 不再调用 `klog_open()`；保留 `syslog_open()`。
2. `log_shutdown()` 不再对未初始化的 `klog.stream` 调用 `ustream_free()`，也不再关闭默认值可能为 0 的 `klog.fd.fd`。
3. 给保留的静态 `klog_open()` 加 `__attribute__((unused))`。上游启用了 `-Wall -Werror`；这样避免未使用函数警告，无需删除整段内核解析代码或修改编译选项。优化后的交付二进制必须不含 `/proc/kmsg`、`/dev/kmsg` 字符串，并通过启动至退出的系统调用跟踪确认没有访问它们。

不更改日志格式、缓冲区、启动参数、ubus 接口、udebug 环形缓冲区、`logread`、初始化脚本或其他组件。内核消息不再由 logd 采集；用户态日志仍正常处理。构建依赖库可能在 SDK 内按原版源码编译以提供链接依赖，但不修改这些组件，也不向生产机器交付或安装它们。

## GitHub Actions 构建

将 `.github/`、`scripts/`、`patches/`、本 README 和 `.gitattributes` 放入仓库。相关文件 push 会触发工作流，也可在 Actions 页手动运行。不要上传本地 `source/`、`downloads/`、`.tools/` 等临时目录。

工作流使用 GitHub 托管 `ubuntu-24.04` x86_64 runner，Ubuntu 仅提供运行 SDK 的宿主工具。目标程序由官方 SDK 的 GCC 14.3.0 / musl 工具链编译。仅更新 SDK 固定提交的 base feed，走 `make package/ubox/compile`；不构建整个固件。

成功后下载 `logd-no-kmsg-openwrt-25.12.6-x86_64` artifact，其中有：

- `logd`：唯一用于替换的二进制。
- `.patch`、`provenance.json`、`static-check.json`、`loader-check.txt`、`runtime.log`、`SHA256SUMS`。
- `source-and-build-recipe.tar.gz`：准确源码归档、原始发行版包定义、补丁、构建与测试脚本。

`build-and-test-logs` artifact 是诊断材料；即使编译失败也可能存在，不能当作可部署交付包。GitHub ZIP 下载可能不保留 Unix 可执行位，部署时显式设置权限。

隔离测试使用独立 PID、mount、network namespace 与官方 rootfs，不启动网络服务、不挂载宿主机 `/dev`、不启动完整 OpenWrt。它验证：musl 加载、logd 启动、`/dev/log` socket、`logger → logread`、ubus `log` 的 read/write、持续日志流、进程 FD、无 `/proc/kmsg` 和 `/dev/kmsg` 系统调用、SIGTERM 正常退出。测试使用官方原版 `logread`、`ubusd`、ubus CLI 和动态库。

不能据此声称已经在用户的 PVE 9 / Linux 7.0.14-23-pve LXC 或 LuCI 页面完成验收；这些需要确认部署后再检查。

## 安全替换：仅供确认后人工执行

以下命令均在 **OpenWrt 容器内** 执行，不是在 PVE 宿主机。此次构建任务不会执行这些命令。预留独立控制台会话。只重启 `log` 服务；不重启容器、宿主机或网络，不改 PPPoE、防火墙、路由配置。重启日志服务会清空内存日志并短暂中断日志收集；先保存需要的日志。

如果当前 logd 已陷入不可中断的内核等待，或 procd 已阻塞，先停止部署；普通 stop/kill 可能无法解除该状态，不能直接启动第二个 logd 抢占 `/dev/log`。本流程不自动向宿主机 `/dev/kmsg` 写入消息。

### 1. 上传和预检查

将已通过 CI 的交付目录上传到 `/tmp/logd-no-kmsg/`。不要直接上传覆盖 `/sbin/logd`。检查 `provenance.json` 和 CI 提交来源。

```sh
cd /tmp/logd-no-kmsg
sha256sum -c SHA256SUMS || exit 1
cat /etc/openwrt_release
uname -m
apk info -v logd libc libubox20260213 libubus20251202 libudebug
chmod 0755 ./logd
/lib/ld-musl-x86_64.so.1 --list /tmp/logd-no-kmsg/logd
```

确认版本为 25.12.6、目标 x86/64，依赖版本与上表一致，加载检查没有 `not found`、`Error loading shared library` 或 `symbol not found`。有差异就暂停。这里只调用动态加载器的 `--list`，**不要直接执行候选 logd**，因为它会重新创建 `/dev/log`。

### 2. 备份并准备候选文件

```sh
backup="/root/logd-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -m 700 "$backup" || exit 1
cp -p /sbin/logd "$backup/logd" || exit 1
sha256sum "$backup/logd" > "$backup/original.sha256"
cp -p /etc/init.d/log "$backup/log.init.reference"
logread > "$backup/log-before.txt"
ubus call service list '{"name":"log"}' > "$backup/service-before.json"
printf '%s\n' "$backup"

# 保留当前所有者/权限；内容来自已校验 artifact。
cp -p /sbin/logd /sbin/logd.new || exit 1
cat /tmp/logd-no-kmsg/logd > /sbin/logd.new || exit 1
chmod 0755 /sbin/logd.new
cmp /tmp/logd-no-kmsg/logd /sbin/logd.new || exit 1
```

记下输出的备份目录。启动脚本和 UCI 配置只用于参考，不修改它们。

### 3. 停止日志服务并原子替换

分步执行，任何一步失败就停止。`stop` 若挂住，不继续后面的操作。

```sh
/etc/init.d/log stop
sleep 2
pidof logd
```

只有 `pidof logd` **无输出**，并且 `ubus call service list '{"name":"log"}'` 确认没有运行的 logd 实例时，才继续：

```sh
mv -f /sbin/logd.new /sbin/logd || exit 1
/etc/init.d/log start
```

同目录 `mv` 避免就地覆盖正在映射的二进制；原有 `/etc/init.d/log` 会使用原配置和启动参数启动。不要自行添加、删除或改变 `-S`。

### 4. 部署后验收

```sh
pidof logd
ubus call service list '{"name":"log"}'
test -S /dev/log && echo '/dev/log socket OK'
ubus -v list log

marker="logd-no-kmsg-$(date +%s)-$$"
logger -p user.notice -t logd-test "$marker"
logread -l 50 | grep -F "$marker"
ubus call log read '{"lines":50,"stream":false}' | grep -F "$marker"

for pid in $(pidof logd); do
    echo "logd PID=$pid"
    readlink "/proc/$pid/exe"
    tr '\000' ' ' < "/proc/$pid/cmdline"; echo
    for fd in /proc/"$pid"/fd/*; do
        printf '%s -> %s\n' "$fd" "$(readlink "$fd")"
    done
done
```

必须有 logd 进程、测试消息出现在 logread 和 ubus 输出中；FD 列表不得包含 `/proc/kmsg` 或 `/dev/kmsg`。可将 FD 中的 `socket:[inode]` 与 `/proc/net/unix` 中 `/dev/log` 的 inode 对照。启动参数应与备份的 `service-before.json` 一致。

另开终端运行 `logread -f`，再用 `logger` 写入一条新标记，应立即出现。浏览器打开 LuCI「状态 → 系统日志」，刷新并确认新标记可见且页面能正常访问。若原来配置了写文件或远程日志，也应检查新标记正常送达原目的地，不改变这些配置。

## 回滚

将下面路径替换为第 2 步实际备份目录。先检查备份完整性和动态加载，再停止日志服务；如 stop 挂住或旧进程无法退出，不启动另一个实例。

```sh
backup=/root/logd-backup-YYYYMMDD-HHMMSS
sha256sum -c "$backup/original.sha256" || exit 1
/lib/ld-musl-x86_64.so.1 --list "$backup/logd"
cp -p "$backup/logd" /sbin/logd.rollback || exit 1
/etc/init.d/log stop
sleep 2
pidof logd
```

确认 logd 已退出后：

```sh
mv -f /sbin/logd.rollback /sbin/logd || exit 1
/etc/init.d/log start
pidof logd
logger -t logd-test 'logd rollback check'
logread -l 20
```

回滚恢复原来的内核日志读取行为，因此原先的阻塞风险也会恢复。无需修改或恢复网络配置。后续升级 logd 包或固件可能覆盖这个定制二进制，应重新核实版本后再决定是否保留此补丁。
