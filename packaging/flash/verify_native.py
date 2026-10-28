"""Check the actual native DLL compile flag, not just a Python build marker."""
import json

from majimeeting.flash_build import verify_native_flash

print(json.dumps(verify_native_flash(), indent=2))
