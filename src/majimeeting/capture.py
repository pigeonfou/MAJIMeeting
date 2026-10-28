"""WASAPI capture: callbacks enqueue PCM; one worker writes independent tracks."""
import queue
import sys
import threading
import time
from dataclasses import dataclass

from majimeeting.storage import FragmentWriter


@dataclass(frozen=True)
class Device:
    index: int
    name: str
    rate: int
    channels: int
    loopback: bool


class WasapiBackend:
    def __init__(self):
        if sys.platform != "win32":
            raise RuntimeError("La capture WASAPI nécessite Windows.")
        import pyaudiowpatch as pa
        self.pa = pa
        self.audio = pa.PyAudio()

    def devices(self):
        api = self.audio.get_host_api_info_by_type(self.pa.paWASAPI)["index"]
        result = []
        for index in range(self.audio.get_device_count()):
            d = self.audio.get_device_info_by_index(index)
            if d["hostApi"] == api and d["maxInputChannels"] > 0:
                result.append(Device(index, d["name"], int(d["defaultSampleRate"]),
                                     int(d["maxInputChannels"]), bool(d.get("isLoopbackDevice"))))
        return result

    def open(self, device, callback):
        def receive(data, count, timing, status):
            callback(data, count, status)
            return None, self.pa.paContinue
        return self.audio.open(format=self.pa.paInt16, channels=device.channels,
                               rate=device.rate, input=True, input_device_index=device.index,
                               frames_per_buffer=max(1, device.rate // 10),
                               stream_callback=receive, start=False)

    def close(self):
        self.audio.terminate()


class RecordingSession:
    def __init__(self, store, title, devices, backend_factory=WasapiBackend):
        if not devices or len({d.index for d in devices}) != len(devices):
            raise ValueError("Sélectionnez au moins une source distincte.")
        self.store, self.title, self.devices = store, title, devices
        self.backend_factory = backend_factory
        self.stop_event = threading.Event()
        self.done = threading.Event()
        self.error = ""
        self.meeting_id = None
        self.thread = threading.Thread(target=self._run, name="audio-writer", daemon=False)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _run(self):
        backend, streams, writers = None, [], []
        pending = queue.Queue(maxsize=100)  # bounded; overflow is an explicit capture failure
        faults = queue.SimpleQueue()
        origin = time.monotonic()

        def callback_for(index, device):
            def receive(data, count, status):
                if status:
                    faults.put(RuntimeError(f"Incident audio {device.name} : code {status}"))
                    self.stop_event.set()
                try:
                    pending.put_nowait((index, data, max(0, time.monotonic() - origin
                                                         - count / device.rate)))
                except queue.Full:
                    faults.put(RuntimeError("Disque trop lent : file audio saturée."))
                    self.stop_event.set()
            return receive

        def write(item):
            index, data, offset = item
            writers[index].write(data, offset)

        try:
            backend = self.backend_factory()
            self.meeting_id = self.store.create(self.title)
            for index, device in enumerate(self.devices):
                folder = self.store.root / self.meeting_id / f"track-{index:02d}"
                writers.append(FragmentWriter(folder, device.rate, device.channels, device.__dict__))
                streams.append(backend.open(device, callback_for(index, device)))
            origin = time.monotonic()
            for stream in streams:
                stream.start_stream()
            while not self.stop_event.is_set():
                try:
                    write(pending.get(timeout=0.1))
                except queue.Empty:
                    if any(not s.is_active() for s in streams):
                        raise RuntimeError("Une source audio s'est arrêtée inopinément.")
        except Exception as exc:
            self.error = str(exc)
        finally:
            for stream in streams:
                try:
                    stream.stop_stream()
                except Exception as exc:
                    self.error = self.error or str(exc)
                try:
                    stream.close()
                except Exception as exc:
                    self.error = self.error or str(exc)
            try:
                while not pending.empty():
                    write(pending.get_nowait())
            except Exception as exc:
                self.error = self.error or str(exc)
            for writer in writers:
                try:
                    writer.close()
                except Exception as exc:
                    self.error = self.error or str(exc)
            if backend:
                try:
                    backend.close()
                except Exception as exc:
                    self.error = self.error or str(exc)
            if not faults.empty():
                self.error = self.error or str(faults.get())
            try:
                if self.meeting_id:
                    self.store.finish(self.meeting_id, "failed" if self.error else "completed",
                                      self.error)
            except Exception as exc:
                self.error = self.error or str(exc)
            self.done.set()
