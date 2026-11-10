"""ipgen (brief 19): external Python design tools driving AMD IP configuration.

One shape for every IP: spec -> Python design tool -> IP config (CONFIG.* + data files) -> batch create_ip ->
read back what the IP computed -> OOC synth -> bit-accurate xsim check against a Python golden -> record.
See docs/ipgen.md for the adapter interface.
"""
