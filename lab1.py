import numpy as np
import keyboard
import sounddevice as sd
import threading
import time


def note_freq(semitone_from_A4: int) -> float:
    return 440.0 * 2 ** (semitone_from_A4 / 12)


NOTES = {
    'C4': -9, 'C#4': -8, 'D4': -7, 'D#4': -6, 'E4': -5, 'F4': -4,
    'F#4': -3, 'G4': -2, 'G#4': -1, 'A4': 0, 'A#4': 1, 'B4': 2,
    'C5': 3, 'C#5': 4, 'D5': 5, 'D#5': 6, 'E5': 7, 'F5': 8,
}
FREQS = {k: note_freq(v) for k, v in NOTES.items()}


FS = 44100
BLOCK = 1024
ATTACK = 0.005
RELEASE = 0.15
AMP = 0.2
HARMONICS = (1.0, 0.5, 0.25)


class Voice:
    def __init__(self, freq, fs, amp=AMP, harmonics=HARMONICS):
        self.fs = fs
        self.t = 0
        self.phase = 0.0
        self.freq = freq
        self.amp = amp
        self.harmonics = harmonics
        self.released = False
        self.done = False
        self.gain = 0.0
        self.attack_step = 1.0 / max(1, int(ATTACK * fs))
        self.release_step = 1.0 / max(1, int(RELEASE * fs))

    def render(self, n): #огибающая появление -> затухание
        out = np.zeros(n, dtype=np.float32)
        for i in range(n):
            if self.released:
                self.gain -= self.release_step
            else:
                self.gain = min(1.0, self.gain + self.attack_step)
            if self.gain <= 0:
                self.done = True
                break
            s = 0.0
            for h_idx, h_amp in enumerate(self.harmonics): # сумма гармоник
                s += h_amp * np.sin(self.phase * (h_idx + 1))
            out[i] = self.amp * self.gain * s
            self.phase += 2 * np.pi * self.freq / self.fs
            if self.phase > 2 * np.pi:
                self.phase -= 2 * np.pi
        return out


class Synth:
    def __init__(self, fs=FS, block=BLOCK):
        self.fs = fs
        self.block = block
        self.voices = []
        self.active = {} 
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(
            samplerate=fs, channels=1, blocksize=block,
            dtype='float32', callback=self._callback, latency='low')
        self.stream.start()

    def _callback(self, outdata, frames, time_info, status):
        out = np.zeros(frames, dtype=np.float32)
        with self.lock:
            for v in self.voices:
                out += v.render(frames)
            self.voices = [v for v in self.voices if not v.done]
        outdata[:, 0] = np.clip(out, -1.0, 1.0)

    def note_on(self, name):
        with self.lock:
            if name in self.active and not self.active[name].released:
                return
            v = Voice(FREQS[name], self.fs)
            self.active[name] = v
            self.voices.append(v)

    def note_off(self, name):
        with self.lock:
            v = self.active.pop(name, None)
            if v is not None:
                v.released = True

    def close(self):
        self.stream.stop()
        self.stream.close()


KEYMAP = {
    'a': 'C4', 'w': 'C#4', 's': 'D4', 'e': 'D#4', 'd': 'E4', 'f': 'F4',
    't': 'F#4', 'g': 'G4', 'y': 'G#4', 'h': 'A4', 'u': 'A#4', 'j': 'B4',
    'k': 'C5',
}

synth = Synth()

arr=[]
def on_key(event):
    if event.name not in KEYMAP:
        return
    name = KEYMAP[event.name]
    arr.append(name)
    print(arr)
    if event.event_type == 'down':
        synth.note_on(name)
    elif event.event_type == 'up':
        synth.note_off(name)



keyboard.hook(on_key)
print("meow")
keyboard.wait('esc')

t=np.arrange(len(arr))
freq

plt.figure(figsize=(12, 4))
plt.plot(t,
         arr)

synth.close()
