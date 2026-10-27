"""Run only in a disposable mount/PID/network namespace, using stock rootfs libs."""
import json
import os
import pathlib
import signal
import subprocess
import sys
import time

root = pathlib.Path(sys.argv[1]).resolve()
logs = pathlib.Path('logs').resolve()
trace = logs / 'logd.strace'


def run(*args):
    p = subprocess.run(['chroot', str(root), *args], capture_output=True,
                       text=True, timeout=15, check=True)
    print('COMMAND', ' '.join(args), '\n', p.stdout, p.stderr, flush=True)
    return p.stdout


def wait_for(callback, label):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if callback():
            return
        time.sleep(0.1)
    raise AssertionError(f'Timeout: {label}')


def log_pid():
    found = []
    for p in pathlib.Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            if (p / 'comm').read_text().strip() == 'logd':
                found.append(int(p.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    assert len(found) <= 1, found
    return found[0] if found else None


def wait_marker(marker):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        text = run('/sbin/logread', '-l', '50')
        if marker in text:
            return text
        time.sleep(0.1)
    raise AssertionError(f'Missing log entry: {marker}')


with (logs / 'ubusd.stderr').open('w') as ubuserr, (logs / 'logd.stderr').open('w') as logerr:
    ubus = subprocess.Popen(['chroot', str(root), '/sbin/ubusd'], stdout=ubuserr, stderr=ubuserr)
    daemon = None
    pid = None
    try:
        wait_for(lambda: (root / 'var/run/ubus/ubus.sock').exists(), 'ubus socket')
        daemon = subprocess.Popen(['strace', '-ff', '-s', '256', '-o', str(trace),
                                   '-e', 'trace=open,openat,openat2,close,read,recvfrom,bind',
                                   'chroot', str(root), '/sbin/logd', '-S', '64'],
                                  stdout=logerr, stderr=logerr)
        wait_for(lambda: (root / 'dev/log').is_socket() and log_pid(), 'logd /dev/log')
        pid = log_pid()
        wait_for(lambda: 'log' in run('/bin/ubus', 'list').splitlines(), 'ubus log registration')
        methods = run('/bin/ubus', '-v', 'list', 'log')
        assert 'read' in methods and 'write' in methods
        marker = 'logd-no-kmsg-test-' + str(time.time_ns())
        run('/usr/bin/logger', '-p', 'user.notice', '-t', 'logd-test', marker)
        output = wait_marker(marker)
        assert 'user.notice' in output and 'logd-test' in output
        data = json.loads(run('/bin/ubus', 'call', 'log', 'read', '{"lines":50,"stream":false}'))
        assert any(marker in row.get('msg', '') for row in data['log'])
        ubus_marker = marker + '-ubus'
        run('/bin/ubus', 'call', 'log', 'write', json.dumps({'event': ubus_marker}))
        wait_marker(ubus_marker)
        # Exercise the streaming API used for file/remote log forwarding.
        with (logs / 'logread-stream.txt').open('w') as stream:
            reader = subprocess.Popen(['chroot', str(root), '/sbin/logread', '-f'],
                                      stdout=stream, stderr=subprocess.STDOUT)
            try:
                time.sleep(0.5)
                stream_marker = marker + '-stream'
                run('/usr/bin/logger', '-t', 'logd-test', stream_marker)
                wait_for(lambda: stream_marker in (logs / 'logread-stream.txt').read_text(), 'logread -f')
            finally:
                reader.terminate()
                reader.wait(timeout=10)
        targets = {}
        for fd in pathlib.Path(f'/proc/{pid}/fd').iterdir():
            try:
                targets[fd.name] = os.readlink(fd)
            except FileNotFoundError:
                pass
        assert all('/proc/kmsg' not in v and '/dev/kmsg' not in v for v in targets.values()), targets
        print('logd file descriptors:', json.dumps(targets, indent=2), flush=True)
        assert daemon.poll() is None
        # SIGTERM returns through log_shutdown(): also verify cleanup is harmless.
        os.kill(pid, signal.SIGTERM)
        daemon.wait(timeout=10)
        assert daemon.returncode == 0, daemon.returncode
        pid = None
        trace_text = '\n'.join(p.read_text() for p in logs.glob('logd.strace.*'))
        assert trace_text, 'Missing syscall trace'
        assert '/proc/kmsg' not in trace_text and '/dev/kmsg' not in trace_text
        assert '/dev/log' in trace_text
        print('PASS: startup, logger, logread, ubus read/write, streaming, /dev/log, no kmsg access, clean shutdown', flush=True)
        print('NOT TESTED: production PVE/LXC kernel behavior and LuCI browser page.', flush=True)
    finally:
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if daemon and daemon.poll() is None:
            daemon.terminate()
            daemon.wait(timeout=10)
        ubus.terminate()
        ubus.wait(timeout=10)
