# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('D:\\FASE REM_automix\\RedLineEngine\\app\\web', 'web'),
    # Bundled offline LLM (Fase 4 advisory fallback) -- ~1GB, the deliberate
    # tradeoff for a true "double-click, zero installs" exe. Only included
    # if it's actually present on disk (still a normal dev build otherwise).
]
binaries = []
hiddenimports = ['soundfile']
tmp_ret = collect_all('librosa')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pedalboard')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pyloudnorm')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('redline')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# llama_cpp ships its own native llama.cpp shared library (llama.dll/libllama)
# next to the Python bindings -- collect_all is what actually pulls that
# binary into the frozen exe, a plain hiddenimport would miss it entirely.
try:
    tmp_ret = collect_all('llama_cpp')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception:
    pass  # llama-cpp-python not installed in this build env -- LLM advisory simply won't be available in this exe

import os
_MODEL_PATH = os.path.join(
    'D:\\FASE REM_automix\\RedLineEngine', 'models', 'qwen2.5-1.5b-instruct-q4_0.gguf'
)
if os.path.exists(_MODEL_PATH):
    datas += [(_MODEL_PATH, 'models')]


a = Analysis(
    ['D:\\FASE REM_automix\\RedLineEngine\\app\\main.py'],
    pathex=['D:\\FASE REM_automix\\RedLineEngine'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RedLineEngine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RedLineEngine',
)
