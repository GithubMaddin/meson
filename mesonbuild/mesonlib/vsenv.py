import os
import subprocess
import json
import pathlib
import shutil
import tempfile

from .. import mlog
from .universal import MesonException, is_windows


bat_template = '''@ECHO OFF

call "{}"

ECHO {}
SET
'''

# If on Windows and VS is installed but not set up in the environment,
# set it to be runnable. In this way Meson can be directly invoked
# from any shell, VS Code etc.
def _setup_vsenv(force: bool) -> bool:
    if not is_windows():
        return False
    if os.environ.get('OSTYPE') == 'cygwin':
        return False
    if 'Visual Studio' in os.environ['PATH']:
        return False
    # VSINSTALL is set when running setvars from a Visual Studio installation
    # Tested with Visual Studio 2012 and 2017
    if 'VSINSTALLDIR' in os.environ:
        return False
    # Check explicitly for cl when on Windows
    if shutil.which('cl.exe'):
        return False
    if not force:
        if shutil.which('cc'):
            return False
        if shutil.which('gcc'):
            return False
        if shutil.which('clang'):
            return False
        if shutil.which('clang-cl'):
            return False

    root = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles")
    bat_locator_bin = pathlib.Path(root, 'Microsoft Visual Studio/Installer/vswhere.exe')
    if not bat_locator_bin.exists():
        raise MesonException(f'Could not find {bat_locator_bin}')
    bat_json = subprocess.check_output(
        [
            str(bat_locator_bin),
            '-latest',
            '-prerelease',
            '-requiresAny',
            '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
            '-products', '*',
            '-utf8',
            '-format',
            'json'
        ]
    )
    bat_info = json.loads(bat_json)
    if not bat_info:
        # VS installer instelled but not VS itself maybe?
        raise MesonException(f'Could not parse vswhere.exe output')
    bat_root = pathlib.Path(bat_info[0]['installationPath'])
    bat_path = bat_root / 'VC/Auxiliary/Build/vcvars64.bat'
    if not bat_path.exists():
        raise MesonException(f'Could not find {bat_path}')

    mlog.log('Activating VS', bat_info[0]['catalog']['productDisplayVersion'])
    bat_separator = '---SPLIT---'
    bat_contents = bat_template.format(bat_path, bat_separator)
    bat_file = tempfile.NamedTemporaryFile('w', suffix='.bat', encoding='utf-8', delete=False)
    bat_file.write(bat_contents)
    bat_file.flush()
    bat_file.close()
    bat_output = subprocess.check_output(bat_file.name, universal_newlines=True)
    os.unlink(bat_file.name)
    bat_lines = bat_output.split('\n')
    bat_separator_seen = False
    for bat_line in bat_lines:
        if bat_line == bat_separator:
            bat_separator_seen = True
            continue
        if not bat_separator_seen:
            continue
        if not bat_line:
            continue
        k, v = bat_line.split('=', 1)
        os.environ[k] = v
    return True

def setup_vsenv(force: bool = False):
    try:
        _setup_vsenv(force)
    except MesonException as e:
        if force:
            raise
        mlog.warning('Failed to activate VS environment:', str(e))
