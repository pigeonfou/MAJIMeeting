"""Fail closed: allow local Unix IPC, deny creation of all network socket families."""
import ctypes
import os
import sys


class Compare(ctypes.Structure):
    _fields_=[('arg',ctypes.c_uint),('op',ctypes.c_int),('a',ctypes.c_uint64),('b',ctypes.c_uint64)]
lib=ctypes.CDLL('/lib/x86_64-linux-gnu/libseccomp.so.2',use_errno=True)
lib.seccomp_init.argtypes=[ctypes.c_uint32]
lib.seccomp_init.restype=ctypes.c_void_p
lib.seccomp_syscall_resolve_name.argtypes=[ctypes.c_char_p]
lib.seccomp_syscall_resolve_name.restype=ctypes.c_int
lib.seccomp_rule_add_array.argtypes=[ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int,ctypes.c_uint,ctypes.POINTER(Compare)]
lib.seccomp_load.argtypes=[ctypes.c_void_p]
lib.seccomp_release.argtypes=[ctypes.c_void_p]
for name in os.listdir('/proc/self/fd'):
    try:
        if os.readlink('/proc/self/fd/'+name).startswith('socket:'):
            if int(name)<=2:
                raise SystemExit('Cannot safely reuse socket stdio')
            os.close(int(name))
    except FileNotFoundError:
        pass
ctx=lib.seccomp_init(0x7fff0000)
if not ctx:
    raise SystemExit('Cannot create network filter')
try:
    number=lib.seccomp_syscall_resolve_name(b'socket')
    compare=Compare(0,1,1,0)  # argument 0 != AF_UNIX
    if number<0 or lib.seccomp_rule_add_array(ctx,0x00050001,number,1,ctypes.byref(compare)):
        raise SystemExit('Cannot deny network socket creation')
    for name in ('socketcall','io_uring_setup'):
        number=lib.seccomp_syscall_resolve_name(name.encode())
        if number>=0 and lib.seccomp_rule_add_array(ctx,0x00050001,number,0,None):
            raise SystemExit('Cannot deny '+name)
    if lib.seccomp_load(ctx):
        raise SystemExit('Kernel network isolation unavailable')
finally:
    lib.seccomp_release(ctx)
if len(sys.argv)<2:
    raise SystemExit('Expected command')
os.execvp(sys.argv[1],sys.argv[1:])
