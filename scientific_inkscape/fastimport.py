# Import accelerator for Scientific Inkscape
# Copyright (c) 2026 David Burghoff <burghoff@utexas.edu>
#
# Importing dhelpers pulls in a few hundred modules (inkex, lxml, numpy and a
# large slice of the standard library). Almost none of that time is spent
# running code: it goes to the import system stat'ing every sys.path entry for
# every module and then opening and reading each .pyc. This module removes that
# overhead in two ways:
#
# 1. A bytecode cache. The first run records every file-backed module the
#    process imported into one marshal file (in si_temp). Later runs install a
#    meta-path finder that serves those modules from the cache: no path search
#    and no file reads, just the code objects. Modules keep their real __file__,
#    so tracebacks, importlib.resources and the like are unaffected.
#    The cache is keyed on the Python executable and version, and the SI
#    source directories are validated by name/size/mtime on every start (one
#    scandir per directory), so edits to SI are always picked up. Vendored
#    packages (packages/, inkex1_3_0/site-packages) only change with SI itself
#    and are not validated.
#    The cache also lists top-level names whose import failed (e.g. the
#    stdlib probing for fcntl on Windows or msvcrt elsewhere). Those are put
#    in sys.modules as None, which makes the import fail at once instead of
#    searching every sys.path entry again.
#
# 2. A lazy numpy. inkex imports numpy at module level but never touches it
#    until something actually computes, so numpy is replaced by a stub that
#    executes it on first attribute access. (importlib.util.LazyLoader can't be
#    used for this: a plain `import numpy` statement reads the module's
#    __spec__ and would trigger it.)
#
# Only builtin/frozen modules are used on the hot path, so the accelerator
# itself costs nothing to import. Everything is pure Python and platform
# independent. Set SI_FASTIMPORT=0 in the environment to disable it.

import sys
import os
import marshal
import atexit
import _thread
import _frozen_importlib as _bootstrap
import _frozen_importlib_external as _bootstrap_external

_VERSION = 2
_enabled = os.environ.get("SI_FASTIMPORT", "1") != "0"
_cache = None       # dict loaded from disk, or None
_cache_file = None
_finder = None
_si_dir = None
_vendored = ()      # SI subfolders that are not validated
_ModuleType = type(sys)


# ------------------------------------------------------------------ helpers
def _key():
    # One cache per entry script, so e.g. the Flattener never loads the
    # Gallery Viewer's Flask/watchdog bytecode.
    script = os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    return "|".join(
        [str(_VERSION), sys.version, sys.executable, str(sys.flags.optimize), _si_dir, script]
    )


def _temp_root(create):
    """si_tmp.root() without importing tempfile (which drags in shutil,
    random, re, ...). Falls back to si_tmp when the quick answer does not
    exist yet (first run) so the two always agree."""
    if sys.executable[0:4] == "/tmp" or sys.executable[0:5] == "/snap":
        base = os.path.dirname(os.path.realpath(__file__))  # Snap: see si_tmp
    else:
        base = None
        for var in ("TMPDIR", "TEMP", "TMP"):  # the order tempfile uses
            val = os.environ.get(var)
            if val and os.path.isdir(val):
                base = val
                break
        if base is None and sys.platform != "win32" and os.path.isdir("/tmp"):
            base = "/tmp"
    if base is not None:
        d = os.path.join(os.path.abspath(base), "si_temp")
        if os.path.isdir(d):
            return d
    if not create:
        return None
    import si_tmp

    return si_tmp.root()


def _hash(s):
    """32-bit FNV-1a; avoids loading zlib just to name the cache file"""
    h = 0x811C9DC5
    for b in s.encode("utf-8", "replace"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return "%08x" % h


def _cache_path(create):
    root = _temp_root(create)
    if root is None:
        return None
    tag = getattr(sys.implementation, "cache_tag", None) or "py"
    return os.path.join(root, "si_imports_%s_%s.marshal" % (tag, _hash(_key())))


def _dir_signature(d):
    """Names, sizes and mtimes of the .py files in a directory. On Windows
    DirEntry.stat() needs no extra system call; elsewhere it is one cheap lstat
    per file."""
    try:
        with os.scandir(d) as it:
            return tuple(
                sorted(
                    (e.name, e.stat().st_size, e.stat().st_mtime_ns)
                    for e in it
                    if e.name.endswith(".py")
                )
            )
    except OSError:
        return None


def _is_watched(origin):
    """SI's own sources, excluding the vendored packages"""
    o = os.path.normcase(origin)
    return o.startswith(_si_dir) and not any(o.startswith(v) for v in _vendored)


# ------------------------------------------------------------------ loaders
class _CachedSourceLoader(_bootstrap_external.SourceFileLoader):
    """SourceFileLoader whose code comes from the cache instead of the file"""

    def __init__(self, fullname, path, code):
        super().__init__(fullname, path)
        self._cached_code = code

    def get_code(self, fullname):
        return marshal.loads(self._cached_code)


class _CachedSourcelessLoader(_bootstrap_external.SourcelessFileLoader):
    def __init__(self, fullname, path, code):
        super().__init__(fullname, path)
        self._cached_code = code

    def get_code(self, fullname):
        return marshal.loads(self._cached_code)


class _Finder:
    """Meta-path finder answering only for modules in the cache"""

    def __init__(self, mods):
        self._mods = mods
        self.misses = set()  # top-level names we were asked for but don't have

    def find_spec(self, fullname, path=None, target=None):
        ent = self._mods.get(fullname)
        if ent is None:
            if path is None:
                self.misses.add(fullname)
            return None
        kind, origin, is_pkg, locs, code = ent
        if kind == "ext":
            loader = _bootstrap_external.ExtensionFileLoader(fullname, origin)
        elif kind == "src":
            loader = _CachedSourceLoader(fullname, origin, code)
        else:
            loader = _CachedSourcelessLoader(fullname, origin, code)
        return _bootstrap_external.spec_from_file_location(
            fullname, origin, loader=loader,
            submodule_search_locations=list(locs) if is_pkg else None,
        )

    def invalidate_caches(self):
        pass


# --------------------------------------------------------------- lazy numpy
_lazy_lock = _thread.RLock()
# Attributes that can be read without executing the module. __spec__ is the
# important one: every `import numpy` statement reads it.
_PASSTHROUGH = frozenset(
    ("__spec__", "__name__", "__loader__", "__package__", "__file__", "__class__")
)


def _lazy_load(mod):
    with _lazy_lock:
        if _ModuleType.__getattribute__(mod, "__class__") is not _LazyModule:
            return
        spec = _ModuleType.__getattribute__(mod, "__spec__")
        _ModuleType.__setattr__(mod, "__class__", _ModuleType)
        spec.loader.exec_module(mod)


class _LazyModule(_ModuleType):
    def __getattribute__(self, attr):
        if attr in _PASSTHROUGH:
            return _ModuleType.__getattribute__(self, attr)
        _lazy_load(self)
        return _ModuleType.__getattribute__(self, attr)

    def __setattr__(self, attr, value):
        _lazy_load(self)
        _ModuleType.__setattr__(self, attr, value)

    def __delattr__(self, attr):
        _lazy_load(self)
        _ModuleType.__delattr__(self, attr)


def make_lazy(name):
    """Put a stub for top-level module `name` in sys.modules that executes the
    real module on first use. No-op if it is already imported or not found."""
    if name in sys.modules or "." in name:
        return
    try:
        spec = _bootstrap._find_spec(name, None)
    except Exception:
        return
    if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
        return
    mod = _bootstrap.module_from_spec(spec)
    mod.__class__ = _LazyModule
    sys.modules[name] = mod


# ---------------------------------------------------------------- snapshot
def _snapshot():
    """At exit, record every file-backed module into the cache (only when
    there is something new, so quiet runs cost nothing)."""
    try:
        if not _enabled or _si_dir is None:
            return
        cache_file = _cache_file or _cache_path(True)
        if cache_file is None:
            return
        old = _cache["mods"] if _cache else {}
        # Only cache modules from places whose contents are either validated
        # (SI's own folder) or fixed for the life of the Python installation
        # (its prefix: stdlib, site-packages). Anything else -- test files, user
        # scripts, pytest plugins -- would be served stale after an edit.
        allowed = [_si_dir] + [
            os.path.normcase(os.path.abspath(p))
            for p in (sys.prefix, sys.base_prefix, sys.exec_prefix)
            if p
        ]
        # Library dirs that may sit outside the prefix (macOS framework builds,
        # Linux dist-packages)
        for p in sys.path:
            q = os.path.normcase(os.path.abspath(p)) if p else ""
            if q and any(t in q for t in ("site-packages", "dist-packages", "lib-dynload")):
                allowed.append(q)
        mods = dict(old)
        changed = False
        ext_loader = _bootstrap_external.ExtensionFileLoader
        srcless_loader = _bootstrap_external.SourcelessFileLoader
        src_loader = _bootstrap_external.SourceFileLoader
        for name, mod in list(sys.modules.items()):
            if name in mods or name == "__main__":
                continue
            spec = getattr(mod, "__spec__", None)
            origin = getattr(spec, "origin", None)
            loader = getattr(spec, "loader", None)
            if not origin or not os.path.isabs(origin) or loader is None:
                continue
            o = os.path.normcase(origin)
            if not any(o.startswith(a) for a in allowed):
                continue
            locs = spec.submodule_search_locations
            is_pkg = locs is not None
            try:
                if isinstance(loader, ext_loader):
                    ent = ("ext", origin, is_pkg, list(locs) if is_pkg else None, None)
                elif isinstance(loader, srcless_loader):
                    code = loader.get_code(name)
                    ent = ("srcless", origin, is_pkg, list(locs) if is_pkg else None, marshal.dumps(code))
                elif isinstance(loader, src_loader):
                    code = loader.get_code(name)
                    ent = ("src", origin, is_pkg, list(locs) if is_pkg else None, marshal.dumps(code))
                else:
                    continue  # zip, frozen, gi, ...
            except Exception:
                continue
            mods[name] = ent
            changed = True
        # Names that failed to import this run and really don't exist anywhere
        # on the final sys.path (not just before some path was added)
        neg = set(_cache.get("neg", ())) if _cache else set()
        if _finder is not None:
            for name in _finder.misses:
                if name in neg or sys.modules.get(name) is not None:
                    continue
                try:
                    if _bootstrap._find_spec(name, None) is None:
                        neg.add(name)
                        changed = True
                except Exception:
                    pass
        if not changed:
            return
        dirs = {}
        for name, ent in mods.items():
            if _is_watched(ent[1]):
                d = os.path.dirname(ent[1])
                if d not in dirs:
                    dirs[d] = _dir_signature(d)
        data = {"key": _key(), "dirs": dirs, "mods": mods, "neg": sorted(neg)}
        tmp = cache_file + ".%d.tmp" % os.getpid()
        with open(tmp, "wb") as f:
            marshal.dump(data, f)
        os.replace(tmp, cache_file)
    except Exception:
        pass


# ----------------------------------------------------------------- install
def install(si_dir, lazy=("numpy",)):
    """Call once, before importing inkex. si_dir is the Scientific Inkscape
    folder; its sources (but not its vendored packages) are validated against
    the cache on every start."""
    global _cache, _cache_file, _si_dir, _vendored, _finder
    if not _enabled or _si_dir is not None:
        return
    _si_dir = os.path.normcase(os.path.abspath(si_dir))
    _vendored = tuple(
        os.path.normcase(os.path.join(_si_dir, p))
        for p in ("packages", os.path.join("inkex1_3_0", "site-packages"))
    )
    atexit.register(_snapshot)
    try:
        _cache_file = _cache_path(False)
        if _cache_file is not None:
            with open(_cache_file, "rb") as f:
                data = marshal.load(f)
            ok = data.get("key") == _key()
            if ok:
                for d, sig in data["dirs"].items():
                    if _dir_signature(d) != sig:
                        ok = False
                        break
            if ok:
                _cache = data
                for name in data.get("neg", ()):
                    sys.modules.setdefault(name, None)
    except Exception:
        _cache = None
    # Installed even without a usable cache so that misses are recorded
    _finder = _Finder(_cache["mods"] if _cache else {})
    sys.meta_path.insert(0, _finder)
    for name in lazy:
        try:
            make_lazy(name)
        except Exception:
            pass
