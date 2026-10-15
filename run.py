"""VS Code: Run Python File, or `python run.py`. First run installs/builds once."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser

ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
if hasattr(sys.stdout,'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def open_website(url):
    # Also bypass HTML cached before the server started sending no-store.
    webbrowser.open(f'{url}/?launch={time.time_ns()}')

def main():
    parser=argparse.ArgumentParser(description='PawCare 本地启动入口')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--setup-only',action='store_true')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port 必须介于 1 和 65535 之间。')
    url=f'http://127.0.0.1:{args.port}'
    if not args.setup_only:
        with socket.socket() as sock:
            occupied=sock.connect_ex(('127.0.0.1',args.port))==0
        if occupied:
            import json
            from urllib.request import urlopen
            try:
                with urlopen(url+'/api/health',timeout=3) as response:
                    health=json.load(response)
                running=health.get('status')=='ok' and health.get('database')=='pawcare'
            except Exception:
                running=False
            if running:
                print(f'PawCare 已经在运行：{url}。本次直接打开已有项目。',flush=True)
                if not args.no_browser:
                    open_website(url)
                return
            raise RuntimeError(f'端口 {args.port} 已被其他程序使用，请使用 --port 8001。')
    venv=ROOT/'.venv'
    python=venv/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    if not python.exists():
        print('正在创建 Python 虚拟环境…',flush=True)
        subprocess.run([sys.executable,'-m','venv',str(venv)],check=True)
    if Path(sys.prefix).resolve()!=venv.resolve():
        raise SystemExit(subprocess.call([str(python),str(__file__),*sys.argv[1:]]))
    requirement=ROOT/('requirements-lock.txt' if (ROOT/'requirements-lock.txt').exists() else 'requirements.txt')
    stamp=venv/'.pawcare-dependencies'
    digest=hashlib.sha256(requirement.read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text()!=digest:
        print('正在检查 Python 依赖…',flush=True)
        subprocess.run([str(python),'-m','pip','install','-r',str(requirement)],check=True)
        stamp.write_text(digest)
    from backend.bootstrap import ensure_database, stop_database
    print('正在检查独立 PostgreSQL 数据库…',flush=True)
    managed=ensure_database()
    front=ROOT/'frontend'
    npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    if not npm and Path('D:/Node/npm.cmd').exists():
        npm='D:/Node/npm.cmd'
        os.environ['PATH']='D:/Node'+os.pathsep+os.environ['PATH']
    if not npm:
        raise RuntimeError('请安装 Node.js 22.12+，然后重新运行 run.py。')
    dep_hash=hashlib.sha256((front/'package.json').read_bytes()+((front/'package-lock.json').read_bytes() if (front/'package-lock.json').exists() else b'')).hexdigest()
    npm_stamp=front/'node_modules/.pawcare-dependencies'
    if not (front/'node_modules/vite').exists() or not npm_stamp.exists() or npm_stamp.read_text()!=dep_hash:
        subprocess.run([npm,'ci' if (front/'package-lock.json').exists() else 'install','--no-audit','--no-fund'],cwd=front,check=True)
        npm_stamp.write_text(hashlib.sha256((front/'package.json').read_bytes()+(front/'package-lock.json').read_bytes()).hexdigest())
    built=front/'dist/index.html'
    sources=[front/'package.json',front/'index.html',front/'vite.config.ts',front/'tsconfig.json',*list((front/'src').rglob('*'))]
    if not built.exists() or any(p.is_file() and p.stat().st_mtime>built.stat().st_mtime for p in sources):
        print('正在构建前端…',flush=True)
        subprocess.run([npm,'run','build'],cwd=front,check=True)
    print('数据库、样例数据和前端已就绪。',flush=True)
    if args.setup_only:
        return
    with socket.socket() as sock:
        if sock.connect_ex(('127.0.0.1',args.port))==0:
            raise RuntimeError(f'端口 {args.port} 已被使用。请关闭已有 PawCare，或使用 --port 8001。')
    print(f'\nPawCare：{url}\n停止：在本终端按 Ctrl+C。数据会保留。\n',flush=True)
    if not args.no_browser:
        def open_when_ready():
            import time
            from urllib.request import urlopen
            for _ in range(40):
                try:
                    with urlopen(url+'/api/health',timeout=1):
                        open_website(url)
                        return
                except OSError:
                    time.sleep(.25)
        threading.Thread(target=open_when_ready,daemon=True).start()
    import uvicorn
    try:
        uvicorn.run('backend.api:app',host='127.0.0.1',port=args.port,log_level='info')
    finally:
        if managed:
            stop_database()

if __name__=='__main__':
    try:
        main()
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        print(f'\n启动未完成：{exc}',file=sys.stderr)
        raise SystemExit(1)
