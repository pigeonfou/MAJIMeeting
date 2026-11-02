"""Disable optional native runtime telemetry before creating inference sessions."""


def disable_onnx_telemetry():
    import onnxruntime
    onnxruntime.disable_telemetry_events()
