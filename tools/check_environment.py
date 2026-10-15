"""Read-only Windows handoff checks. Uses only the Python standard library."""
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def version(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=15, creationflags=FLAGS)
        value = (result.stdout or result.stderr).strip().splitlines()
        return value[0] if value and result.returncode == 0 else ''
    except (OSError, subprocess.SubprocessError):
        return ''


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    missing = []
    print('PawCare 环境检查（只读取，不安装或修改服务）')
    print('项目目录:', ROOT)
    print('Python:', sys.version.split()[0], sys.executable)
    if sys.version_info < (3, 12):
        missing.append('需要 Python 3.12 或以上；交接验证版本为 3.12。')
    if os.name != 'nt':
        print('提示：本交接包安装验证平台为 Windows；当前平台未验证。')
    node = shutil.which('node') or ('D:/Node/node.exe' if Path('D:/Node/node.exe').exists() else None)
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm and node:
        candidate = Path(node).parent / ('npm.cmd' if os.name == 'nt' else 'npm')
        npm = str(candidate) if candidate.exists() else None
    nv = version([node, '--version']) if node else ''
    numbers = tuple(map(int, re.findall(r'\d+', nv)[:3]))
    print('Node.js:', nv or '未找到')
    if len(numbers) < 2 or numbers < (22, 12):
        missing.append('需要 Node.js 22.12 或以上，安装后重新打开终端。')
    npm_version = version([npm, '--version']) if npm else ''
    print('npm:', npm_version or '未找到')
    if not npm_version:
        missing.append('未找到 npm；请检查 Node.js 安装。')

    # Read only the optional install path, never print credentials from .env.
    configured = None
    if (ROOT / '.env').exists():
        for line in (ROOT / '.env').read_text('utf-8-sig').splitlines():
            if line.strip().startswith('PG_BIN='):
                configured = line.split('=', 1)[1].strip().strip('\"\'')
    pgpath = shutil.which('pg_ctl')
    candidates = [os.environ.get('PG_BIN'), configured, str(Path(pgpath).parent) if pgpath else None,
                  'D:/PostgreSQL/postgresql-16.14-2/bin']
    candidates += [str(p) for p in Path('C:/Program Files/PostgreSQL').glob('*/bin')]
    suffix = '.exe' if os.name == 'nt' else ''
    folder = next((Path(p) for p in candidates if p and (Path(p) / ('pg_ctl' + suffix)).exists()), None)
    if folder:
        print('PostgreSQL bin:', folder)
        pv = version([str(folder / ('postgres' + suffix)), '--version'])
        print('PostgreSQL:', pv or '无法读取版本')
        match = re.search(r'(\d+)\.', pv)
        if not match or int(match.group(1)) < 16:
            missing.append('需要 PostgreSQL 16 或以上；建议与已验证版本一致使用 16。')
        for tool in ['initdb', 'pg_ctl', 'postgres', 'psql', 'pg_dump', 'pg_restore']:
            if not (folder / (tool + suffix)).exists():
                missing.append('缺少 PostgreSQL 工具: ' + tool)
    else:
        missing.append('未找到 PostgreSQL：安装后设置 $env:PG_BIN 为实际 bin 目录。')
    for port in [8000, 55432]:
        with socket.socket() as sock:
            sock.settimeout(1)
            occupied = sock.connect_ex(('127.0.0.1', port)) == 0
        print(f'端口 {port}:', '已占用（可能是已有 PawCare，请核对；不要终止未知服务）' if occupied else '空闲')
    print('本机 .env:', '已存在，将保留' if (ROOT / '.env').exists() else '尚未生成，默认模式首次运行自动创建')
    if missing:
        print('\n需处理:')
        for item in missing:
            print('-', item)
        return 1
    print('\n基础工具检查通过。确认端口可用后执行 python run.py。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
