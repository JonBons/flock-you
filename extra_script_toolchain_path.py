"""Prepend PlatformIO toolchain bin dirs to SCons ENV PATH so the compiler is found.

SCons builds its own execution environment and may not inherit the shell PATH.
This runs as a PRE script so the toolchain is on PATH before any compile.
"""
Import("env")
import glob
import os

if env.IsIntegrationDump():
    Return()

core_dir = os.environ.get("PLATFORMIO_CORE_DIR", os.path.expanduser("~/.platformio"))
packages_dir = os.path.join(core_dir, "packages")
glob_pattern = os.path.join(packages_dir, "toolchain-*", "bin")
toolchain_bins = [d for d in sorted(glob.glob(glob_pattern)) if os.path.isdir(d)]
if toolchain_bins:
    prefix = os.pathsep.join(toolchain_bins)
    env["ENV"]["PATH"] = prefix + os.pathsep + env["ENV"].get("PATH", "")
