"""Compare ELF/ABI against the pinned official 25.12.6 rootfs, not Ubuntu."""
import hashlib
import io
import json
import pathlib
import subprocess
import tarfile

from elftools.elf.elffile import ELFFile

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORK = ROOT / 'work'
LOGS = ROOT / 'logs'
rootfs = WORK / 'downloads/openwrt-25.12.6-x86-64-generic-targz-rootfs.tar.gz'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inspect(data):
    elf = ELFFile(io.BytesIO(data))
    result = {'class': elf.elfclass, 'little_endian': elf.little_endian,
              'machine': elf['e_machine'], 'type': elf['e_type'],
              'interpreter': None, 'needed': [], 'rpath': [], 'sha256': sha(data)}
    for segment in elf.iter_segments():
        if segment['p_type'] == 'PT_INTERP':
            result['interpreter'] = segment.get_interp_name()
        if segment['p_type'] == 'PT_DYNAMIC':
            for tag in segment.iter_tags():
                if tag.entry.d_tag == 'DT_NEEDED':
                    result['needed'].append(tag.needed)
                elif tag.entry.d_tag in ('DT_RPATH', 'DT_RUNPATH'):
                    result['rpath'].append(str(tag))
    return result


new_data = (WORK / 'logd').read_bytes()
new = inspect(new_data)
assert new['class'] == 64 and new['little_endian']
assert new['machine'] == 'EM_X86_64'
assert new['interpreter'] == '/lib/ld-musl-x86_64.so.1'
assert not new['rpath'], new['rpath']
assert b'/proc/kmsg' not in new_data and b'/dev/kmsg' not in new_data

with tarfile.open(rootfs) as archive:
    members = {m.name.removeprefix('./'): m for m in archive.getmembers()}

    def read(name):
        return archive.extractfile(members[name]).read()

    original = inspect(read('sbin/logd'))
    assert sorted(original['needed']) == sorted(new['needed']), (original, new)
    assert original['interpreter'] == new['interpreter']
    assert original['type'] == new['type']
    assert original['sha256'] != new['sha256']
    libraries = {}
    pending = list(new['needed'])
    while pending:
        name = pending.pop()
        if name in libraries:
            continue
        locations = [f'{prefix}/{name}' for prefix in ['lib', 'usr/lib']
                     if f'{prefix}/{name}' in members]
        assert locations, f'Missing official rootfs library: {name}'
        info = inspect(read(locations[0]))
        assert info['machine'] == 'EM_X86_64' and info['class'] == 64
        assert not info['rpath']
        libraries[name] = {'path': locations[0], **info}
        pending.extend(info['needed'])
    release = read('etc/openwrt_release').decode()
    assert "DISTRIB_RELEASE='25.12.6'" in release
    assert "DISTRIB_TARGET='x86/64'" in release

report = {'result': 'PASS', 'modified': new, 'official_original': original,
          'official_libraries': libraries,
          'note': 'Static dependency check; loader and runtime tests are separate mandatory gates.'}
(LOGS / 'static-check.json').write_text(json.dumps(report, indent=2) + '\n')
provenance = {
    'openwrt_release': '25.12.6', 'target': 'x86/64', 'arch': 'x86_64',
    'openwrt_commit': '64900e756efa667774214f9c6b17c113222e01f7',
    'openwrt_revision': 'r33311-981c978eff',
    'ubox_commit': '6f78fa496bf36c55864a41e353df7d13f04b1077',
    'package_version': '2025.10.30~6f78fa49-r1',
    'distribution_ubox_patches': [],
    'patch_sha256': sha((ROOT / 'patches/100-logd-disable-kernel-log.patch').read_bytes()),
    'binary_sha256': new['sha256'],
    'sdk_url': 'https://downloads.openwrt.org/releases/25.12.6/targets/x86/64/'
               'openwrt-sdk-25.12.6-x86-64_gcc-14.3.0_musl.Linux-x86_64.tar.zst',
    'sdk_sha256': '1864152619092e781fa36a401960c8e9ae42d6a364c44ee5f0b197ca5f3c0fcc',
    'rootfs_sha256': sha(rootfs.read_bytes()),
    'compiler': (LOGS / 'compiler.txt').read_text(),
    'manifest': (WORK / 'downloads/manifest').read_text(),
    'build_config_sha256': sha((LOGS / 'sdk.config').read_bytes()),
    'git_workflow_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
}
(WORK / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
print(json.dumps(report, indent=2))
