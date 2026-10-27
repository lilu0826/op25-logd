"""Reject any accidental deviation from the six-line kernel-reader patch."""
import pathlib
import sys
import tarfile
import subprocess

source = pathlib.Path(sys.argv[1]).read_bytes()
archive = pathlib.Path(__file__).resolve().parents[1] / 'work/source/ubox-2025.10.30~6f78fa49.tar.zst'
result = subprocess.run(['tar', '--zstd', '-xOf', str(archive),
                         'ubox-2025.10.30~6f78fa49/log/syslog.c'],
                        check=True, capture_output=True)
original = result.stdout
expected = original.replace(b'static int\nklog_open(void)',
                            b'static int __attribute__((unused))\nklog_open(void)')
expected = expected.replace(b'\tklog_open();',
                            b'\t/* Kernel log collection is disabled in this LXC build. */')
expected = expected.replace(b'\tustream_free(&klog.stream);\n\tclose(klog.fd.fd);\n', b'')
assert source == expected, 'Unexpected source changes'
assert b'\tklog_open();' not in source
assert b'\tsyslog_open();' in source
assert b'/dev/kmsg' not in source
assert b'ustream_free(&klog.stream)' not in source
assert b'close(klog.fd.fd)' not in source
print('PASS: exact minimal source patch; syslog enabled, kernel init and cleanup disabled')
