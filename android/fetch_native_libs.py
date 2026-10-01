"""Fetch the shared C/C++ libraries that some of the app's Python packages load.

numpy and pandas need libc++, lxml needs libxml2 and libxslt, PyYAML needs
libyaml. Flet's package index ships each as a small wheel holding the .so; this
copies them into the app's jniLibs, where Android's loader finds them when the
Python packages are imported. Run it once, and again if requirements.txt moves
to package versions that name other library versions:

    py -3.13 fetch_native_libs.py
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

LIBRARIES = ["flet-libcpp-shared==27.2.12479018", "flet-libxml2==2.15.3",
             "flet-libxslt==1.1.45", "flet-libyaml==0.2.5"]
# Android ABI name -> the platform tag its wheels carry.
ABIS = {"arm64-v8a": "android_24_arm64_v8a", "x86_64": "android_24_x86_64"}

jni_libs = Path(__file__).resolve().parent / "app" / "src" / "main" / "jniLibs"

for abi, platform in ABIS.items():
    target = jni_libs / abi
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as downloads:
        subprocess.run(
            [sys.executable, "-m", "pip", "download", "--quiet", "--no-deps", "--only-binary=:all:",
             "--index-url", "https://pypi.flet.dev", "--platform", platform, "--dest", downloads, *LIBRARIES],
            check=True,
        )
        for wheel in Path(downloads).glob("*.whl"):
            with zipfile.ZipFile(wheel) as archive:
                for name in archive.namelist():
                    if name.endswith(".so"):
                        (target / Path(name).name).write_bytes(archive.read(name))
                        print(f"{abi}: {Path(name).name}")
