"""
Barebones Cocoa wrappers using ctypes.
"""

import ctypes
import ctypes.util
from functools import wraps

foundation = ctypes.cdll.LoadLibrary(ctypes.util.find_library('Foundation'))
appkit = ctypes.cdll.LoadLibrary(ctypes.util.find_library('AppKit'))
objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))

objc.objc_getClass.argtypes = [ctypes.c_void_p]
objc.objc_getClass.restype = ctypes.c_void_p

objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
objc.objc_msgSend.restype = ctypes.c_void_p

objc.sel_registerName.argtypes = [ctypes.c_char_p]
objc.sel_registerName.restype = ctypes.c_void_p

objc.object_getClassName.argtypes = [ctypes.c_void_p]
objc.object_getClassName.restype = ctypes.c_char_p


def memo(f):
    cache = {}

    @wraps(f)
    def memoized(*args, **kwargs):
        if args not in cache or kwargs.get('force'):
            cache[args] = f(*args)
        return cache[args]
    return memoized


@memo
def objc_class(name):
    return objc.objc_getClass(name)


@memo
def objc_sel(name):
    return objc.sel_registerName(name)


def objc_from_python(x):
    cls_map = {str: NSString,
               unicode: NSString}
    if type(x) in cls_map:
        return cls_map[type(x)].from_python(x).objc_obj
    elif isinstance(type(x), ObjCMeta):
        return x.objc_obj
    return x


def objc_send(obj, *args, **kwargs):
    sel = objc_sel(''.join(x for x in args[0::2]))
    objs = tuple(objc_from_python(x) for x in args[1::2])

    objc.objc_msgSend.argtypes = kwargs.get('argtypes') or \
        [ctypes.c_void_p] * (len(objs) + 2)
    objc.objc_msgSend.restype = kwargs.get('restype') or ctypes.c_void_p
    return objc.objc_msgSend(obj, sel, *objs)


def log(fmt, *args):
    foundation.NSLog.argtypes = [ctypes.c_void_p] * (len(args) + 1)
    foundation.NSLog(objc_from_python(fmt),
                     *[objc_from_python(x) for x in args])


class ObjCMeta(type):
    objc_map = {}

    def __new__(mcs, name, bases, dct):
        objc_name = None
        if not name.startswith("ObjC") or "__objc_name__" in dct:
            objc_name = dct.get("__objc_name__") or name
            dct['objc_class'] = objc_class(objc_name)
        cls = type.__new__(mcs, name, bases, dct)

        if objc_name:
            mcs.objc_map[objc_name] = cls
        return cls

    @classmethod
    def to_python(mcs, obj):
        if obj is None:
            return None
        objc_class = obj
        while objc_class:
            cls_name = objc.object_getClassName(objc_class)
            if cls_name in mcs.objc_map:
                return mcs.objc_map[cls_name](obj=obj)
            objc_class = objc_send(objc_class, 'superclass')
        return ObjCObj(obj=obj)


class ObjCObj(object):
    __metaclass__ = ObjCMeta

    def __init__(self, obj=None):
        if obj is None:
            obj = objc_send(self.objc_class, 'alloc')

        self.objc_obj = obj

    def __nonzero__(self):
        return self.objc_obj is not None

    def send(self, *args, **kwargs):
        if self.objc_obj:
            ret = objc_send(self.objc_obj, *args, **kwargs)
            if kwargs.get('raw'):
                return ret
            return ObjCMeta.to_python(ret) or ret

    def __str__(self):
        d = self.send('description')
        return str(d)


class NSString(ObjCObj):
    @classmethod
    def from_python(cls, s):
        obj = objc_send(cls.objc_class, 'stringWithUTF8String:',
                        ctypes.c_char_p(s.encode('utf8')))
        return cls(obj)

    def __str__(self):
        s = ctypes.string_at(self.send('UTF8String', raw=True))
        return s.decode('utf8')


class NSAutoreleasePool(object):
    def __init__(self):
        self.pool = None
        self.drained = False

    def alloc(self):
        pool = objc_send(objc_class('NSAutoreleasePool'), 'alloc')
        self.pool = objc_send(pool, 'init')

    def drain(self):
        if self.pool and not self.drained:
            objc_send(self.pool, 'drain')
            self.drained = True

    def __enter__(self):
        self.alloc()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.drain()

    def __del__(self):
        self.drain()


class NSRunningApplication(ObjCObj):
    @classmethod
    def for_pid(cls, pid):
        obj = objc_send(cls.objc_class,
                        'runningApplicationWithProcessIdentifier:',
                        int(pid))
        return cls(obj)

    def activate(self, all_windows=True):
        opt = 1 if all_windows else 2
        self.send('activateWithOptions:', opt, raw=True)


_root_autorelease_pool = NSAutoreleasePool()
_root_autorelease_pool.alloc()
