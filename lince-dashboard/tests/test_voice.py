"""Voice lifecycle tests use fake microphones/models, never the host microphone."""

import importlib.machinery
import importlib.util
from pathlib import Path
import queue
import os
import subprocess
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_loader(
    "lince_voice", importlib.machinery.SourceFileLoader("lince_voice", str(ROOT / "lince-voice"))
)
voice = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(voice)


class VoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "voice.json"
        for name, value in (("CONFIG", self.config), ("VOX_CONFIG", Path(self.temp.name) / "vox.toml")):
            context = patch.object(voice, name, value)
            context.start()
            self.addCleanup(context.stop)

    def session(self):
        session = voice.Session()
        session.installed = True
        return session

    def test_settings_survive_new_session_but_never_resume_listening(self):
        session = self.session()
        settings = session.settings | dict(mode="vad", microphone="USB microphone", language="it", auto_send=True)
        result = session.request(dict(action="save", settings=settings))
        self.assertTrue(result["settings"]["configured"])
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        restored = self.session()
        self.assertEqual(restored.settings, result["settings"])
        self.assertEqual(restored.status, "stopped")
        self.assertFalse(restored.active)
        self.assertIsNone(restored.thread)

    def test_invalid_save_preserves_previous_configuration(self):
        session = self.session()
        session.request(dict(action="save", settings=session.settings))
        original = self.config.read_bytes()
        result = session.request(dict(action="save", settings=session.settings | {"mode": "bad"}))
        self.assertIn("Mode", result["error"])
        self.assertEqual(self.config.read_bytes(), original)

    def test_text_waits_for_ack_and_is_never_sent_to_clipboard(self):
        session = self.session()
        session.buffer = "hello agent"
        first = session.request(dict(action="send"))["events"]
        self.assertEqual(first[0]["text"], "hello agent")
        self.assertEqual(session.request(dict(action="status"))["events"], first)
        self.assertEqual(session.request(dict(action="status", ack=first[0]["sequence"]))["events"], [])
        self.assertEqual(session.buffer, "")

    def test_ptt_requires_configuration_and_rejects_vad(self):
        session = self.session()
        self.assertIn("configuration", session.request(dict(action="ptt"))["error"])
        self.assertIsNone(session.thread)
        session.settings.update(configured=True, mode="vad")
        self.assertIn("PTT mode", session.request(dict(action="ptt"))["error"])
        self.assertIsNone(session.thread)

    def test_mute_cancels_inflight_speech_and_stop_terminates_worker(self):
        session = self.session()
        session.active = True
        session.recording = True
        epoch = session.epoch
        self.assertEqual(session.request(dict(action="mute"))["status"], "muted")
        self.assertFalse(session.recording)
        self.assertGreater(session.epoch, epoch)
        self.assertEqual(session.request(dict(action="mute"))["status"], "listening")
        self.assertEqual(session.request(dict(action="stop"))["status"], "stopped")
        self.assertFalse(session.active)
        self.assertTrue(session.shutdown)

    def test_invalid_config_cannot_start_audio(self):
        session = self.session()
        self.assertIn("configuration", session.request(dict(action="start"))["error"])
        self.assertFalse(session.active)

    def test_socket_worker_persists_settings_across_shutdown(self):
        env = {**os.environ, "HOME": self.temp.name, "XDG_RUNTIME_DIR": self.temp.name}

        def request(action, **kwargs):
            result = subprocess.run(
                [
                    str(ROOT / "lince-voice"),
                    "--controller",
                    "test",
                    "--request",
                    json.dumps(dict(action=action, **kwargs)),
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
            return json.loads(result.stdout)

        try:
            initial = request("status")
            self.assertFalse(initial["settings"]["configured"])
            self.assertEqual(initial["status"], "stopped")
            saved = request("save", settings=initial["settings"] | {"language": "it"})
            self.assertTrue(saved["settings"]["configured"])
            request("shutdown")
            time.sleep(0.1)
            restored = request("status")
            self.assertEqual(restored["settings"], saved["settings"])
            self.assertEqual(restored["status"], "stopped")
        finally:
            request("shutdown")

    def test_audio_ptt_mute_resume_and_late_result(self):
        import numpy as np

        opened = threading.Event()
        closed = threading.Event()
        transcribing = threading.Event()
        release = threading.Event()
        audio_queue = queue.Queue()

        class Capture:
            def __init__(self, **kwargs):
                self.audio_queue = audio_queue

            def start(self):
                closed.clear()
                opened.set()

            def stop(self):
                opened.clear()
                closed.set()

            def get_frame(self, timeout):
                return audio_queue.get(timeout=timeout)

            @staticmethod
            def get_level(frame):
                return 0.05

        class Model:
            def ensure_loaded(self):
                pass

            def transcribe(self, audio, language):
                transcribing.set()
                release.wait(2)
                return types.SimpleNamespace(text="delayed speech", language="it")

        cfg = types.SimpleNamespace(
            general=types.SimpleNamespace(language="it"),
            whisper=types.SimpleNamespace(),
            vad=types.SimpleNamespace(threshold=0.01, silence_duration=0.1, pre_roll=0.1),
            commands=types.SimpleNamespace(prefix="comando", enabled=True),
        )
        modules = {
            "voxcode": types.ModuleType("voxcode"),
            "sounddevice": types.SimpleNamespace(),
            "voxcode.audio": types.SimpleNamespace(AudioCapture=Capture),
            "voxcode.config": types.SimpleNamespace(load_config=lambda path: cfg),
            "voxcode.vad": types.SimpleNamespace(
                EnergyVAD=lambda **kw: types.SimpleNamespace(reset=lambda: None), VADState=object()
            ),
            "voxcode.transcriber": types.SimpleNamespace(create_transcriber=lambda cfg: Model()),
            "voxcode.commands": types.SimpleNamespace(
                parse_transcription=lambda *a, **kw: types.SimpleNamespace(is_command=False, text="delayed speech"),
                CommandType=object(),
            ),
        }
        session = self.session()
        session.settings.update(configured=True, auto_send=True)
        with patch.dict(sys.modules, modules):
            try:
                session.request(dict(action="ptt"))
                self.assertTrue(opened.wait(2))
                audio_queue.put(np.ones(480, dtype=np.float32))
                time.sleep(0.05)
                session.request(dict(action="ptt"))
                audio_queue.put(np.ones(480, dtype=np.float32))
                self.assertTrue(transcribing.wait(2))
                session.request(dict(action="mute"))
                self.assertTrue(closed.wait(2))
                release.set()
                session.request(dict(action="mute"))
                self.assertTrue(opened.wait(2))
                audio_queue.put(np.ones(480, dtype=np.float32))
                time.sleep(0.1)
                self.assertEqual(session.events, [])
                self.assertEqual(session.buffer, "")
            finally:
                release.set()
                session.request(dict(action="stop"))
                session.thread.join(2)
                self.assertFalse(session.thread.is_alive())
                self.assertTrue(closed.is_set())


if __name__ == "__main__":
    unittest.main()
