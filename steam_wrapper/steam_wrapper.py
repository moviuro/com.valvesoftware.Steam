#!/usr/bin/python3
import os
import os.path
import sys
import shutil
import errno
import fnmatch
import subprocess

STEAM_PATH = "/app/bin/steam"
STEAM_ROOT = os.path.expandvars("$HOME/.var/app/com.valvesoftware.Steam")

def mesa_shader_workaround():
    fallback = os.path.expandvars("$XDG_CACHE_HOME/mesa_shader_cache")
    path = os.environ.get("MESA_GLSL_CACHE_DIR", fallback)
    if os.path.isdir(path):
        print (f"Flushing {path}")
        shutil.rmtree(path)


def prompt():
    p = subprocess.Popen(["zenity", "--question",
                          ("--text="
                           "This is com.valvesoftware.Steam cloud sync repair. "
                           "If you have conflicting local and cloud data for "
                           "your game, this may result in partial loss of your "
                           "cloud data. If you instead prefer ensuring cloud data "
                           "persists, please relocate your "
                           "~/.var/app/com.valvesoftware.Steam/data/Steam "
                           "to a secure location, "
                           "remove ~/.var/app/com.valvesoftware.Steam "
                           "and put Steam data directory back to avoid needing to "
                           "re-download games. Do you want to allow the migration?")])
    return p.wait() == 0

def ignored(name, patterns):
    for pattern in patterns:
        if fnmatch.fnmatch(name, pattern):
            return True
    else:
        return False

def filter_names(root, names, patterns):
    _names = []
    for name in names:
        if not ignored(os.path.join(root, name), patterns):
            _names.append(name)
    return _names

def copytree(source, target, ignore=None):
    for root, d_names, f_names in os.walk(source):
        rel_root = os.path.relpath(root, source)
        if ignore:
            d_names[:] = filter_names(root, d_names, ignore)
            f_names = filter_names(root, f_names, ignore)
        if f_names:
            os.makedirs(os.path.join(target, rel_root), exist_ok=True)
        for f_name in f_names:
            full_source = os.path.join(root, f_name)
            full_target = os.path.join(target, rel_root, f_name)
            print (f"Relocating {full_source} to {full_target}")
            shutil.copy2(full_source, full_target)
            os.utime(full_target)

def check_nonempty(name):
    try:
        with open(name) as file:
            return len(file.read()) > 0
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
        else:
            return False
        
def legacy_support():
    if not check_nonempty("/etc/ld.so.conf"):
        # Fallback for flatpak < 0.9.99
        os.environ["LD_LIBRARY_PATH"] = "/app/lib:/app/lib/i386-linux-gnu"
        os.environ["STEAM_RUNTIME_PREFER_HOST_LIBRARIES"] = "0"

    steam_home = os.path.expandvars("$HOME/.var/app/com.valvesoftware.Steam/home")
    if os.path.isdir(steam_home):
        # Relocate from old migration
        ignore = ("*/.steam", "*/.local", "*/.var")
        copytree(steam_home, os.path.expandvars("$HOME"), ignore=ignore)
        shutil.rmtree(steam_home)


def migrate_config():
    """
    There's bind-mounted contents inside config dir so we need to
    1) Relocate, move to temp
    2) Next start of app, remove temp
    In theory this should not break everything
    """
    consent = True
    source = os.path.expandvars("$XDG_CONFIG_HOME")
    target = ".config"
    xdg_config_home = os.path.join(STEAM_ROOT, target)
    relocated = os.path.expandvars("$XDG_CONFIG_HOME.old")
    if not os.path.islink(source):
        if os.path.isdir(target):
            consent = prompt()
            if not consent:
                return consent
        copytree(source, target)
        os.rename(source, relocated)
        os.symlink(target, source)
    else:
        if os.path.isdir(relocated):
            shutil.rmtree(relocated)
    os.environ["XDG_CONFIG_HOME"] = xdg_config_home
    return consent

def migrate_data():
    """
    Data directory contains a directory Steam which contains all installed
    games and is massive. It needs to be separately moved
    """
    source = os.path.expandvars("$XDG_DATA_HOME")
    target = ".data"
    steam_home = os.path.join(source, "Steam")
    backup = os.path.join(source, "BAK")
    xdg_data_home = os.path.join(STEAM_ROOT, target)

    if not os.path.islink(source):
        copytree(source, target, ignore=[steam_home, backup])
        os.makedirs(target, exist_ok=True)
        if os.path.isdir(steam_home):
            os.rename(steam_home,
                      os.path.join(xdg_data_home, "Steam"))
        shutil.rmtree(source)
        os.symlink(target, source)
    os.environ["XDG_DATA_HOME"] = xdg_data_home

def migrate_shared():
    source = os.path.expandvars("$XDG_CACHE_HOME")
    target = ".local/share"
    xdg_cache_home = os.path.join(STEAM_ROOT, target)
    if not os.path.islink(source):
        copytree(source, target)
        shutil.rmtree(source)
        os.symlink(target, source)
    os.environ["XDG_CACHE_HOME"] = xdg_cache_home

def main():
    legacy_support()
    consent = migrate_config()
    if consent:
        migrate_data()
        migrate_shared()
    mesa_shader_workaround()
    os.execve(STEAM_PATH, [STEAM_PATH] + sys.argv[1:], os.environ)
