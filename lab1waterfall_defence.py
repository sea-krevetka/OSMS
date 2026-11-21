import numpy as np
import keyboard
import sounddevice as sd
import threading
import time
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt


def note_freq(semitone_from_A4: int) -> float:
    return 440.0 * 2 ** (semitone_from_A4 / 12)


NOTES = {
    'C4': -9, 'C#4': -8, 'D4': -7, 'D#4': -6, 'E4': -5, 'F4': -4,
    'F#4': -3, 'G4': -2, 'G#4': -1, 'A4': 0, 'A#4': 1, 'B4': 2,
    'C5': 3, 'C#5': 4, 'D5': 5, 'D#5': 6, 'E5': 7, 'F5': 8,
}
FREQS = {k: note_freq(v) for k, v in NOTES.items()}


FS = 44100
BLOCK = 2048
ATTACK = 0.005
RELEASE = 0.15
AMP = 0.2
#HARMONICS = (1.0, 0.5, 0.25) #piano
HARMONICS = tuple(1.0 / n for n in range(1, 12))

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

    def render(self, n):
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
            for h_idx, h_amp in enumerate(self.harmonics):
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


class SpectrumVisualizer:
    def __init__(self, notes_dict):
        self.notes_dict = notes_dict
        self.events = []
        self.active_notes = set()
        self.t0 = time.time()
        self.lock = threading.Lock()

        self.fig, (self.ax_wf, self.ax_spectrum) = plt.subplots(
            2, 1, figsize=(12, 6),
            gridspec_kw={'height_ratios': [3, 1]}
        )

        self.freq_bins = np.linspace(200, 1200, 200)
        self.num_time_slots = 80
        self.waterfall_data = np.zeros(
            (self.num_time_slots, len(self.freq_bins))
        )
        self.img = self.ax_wf.imshow(
            self.waterfall_data,
            aspect='auto', origin='lower',
            extent=[self.freq_bins[0], self.freq_bins[-1], 0, self.num_time_slots],
            cmap='inferno', vmin=0, vmax=1,
            interpolation='nearest'
        )
        self.ax_wf.set_xlabel('Freq(Hz)')
        self.ax_wf.set_ylabel('Time')
        self.ax_wf.set_title('Waterfall spectrum')

        for name, f in self.notes_dict.items():
            self.ax_wf.axvline(f, color='cyan', alpha=0.15, lw=0.6)

        self.line, = self.ax_spectrum.plot(
            self.freq_bins, np.zeros_like(self.freq_bins),
            color='lime', lw=1.5
        )
        self.ax_spectrum.set_xlim(self.freq_bins[0], self.freq_bins[-1])
        self.ax_spectrum.set_ylim(0, 1.1)
        self.ax_spectrum.set_xlabel('Frequency (Hz)')
        self.ax_spectrum.set_ylabel('Amplitude')
        self.ax_spectrum.grid(True, alpha=0.3)
        self.ax_spectrum.set_title('Current spectrum')

        self.fig.tight_layout()
        plt.ion()
        plt.show()


    def _build_spectrum(self, freqs):
        spec = np.zeros_like(self.freq_bins, dtype=float)
        for f in freqs:
            for h, amp in enumerate(HARMONICS, start=1):
                fh = f * h
                if self.freq_bins[0] <= fh <= self.freq_bins[-1]:
                    sigma = 2.0 * h 
                    spec += amp * np.exp(-0.5 * ((self.freq_bins - fh) / sigma) ** 2)
        if spec.max() > 0:
            spec /= spec.max()
        return spec

    def add_event(self, note_name, pressed: bool):
        with self.lock:
            if pressed:
                self.active_notes.add(note_name)
            else:
                self.active_notes.discard(note_name)

            freqs = [self.notes_dict[n] for n in self.active_notes]
            spec = self._build_spectrum(freqs)


            self.waterfall_data = np.roll(self.waterfall_data, 1, axis=0)
            self.waterfall_data[0, :] = spec

            self.img.set_data(self.waterfall_data)
            self.line.set_ydata(spec)
            self.fig.canvas.draw_idle()
            self.fig.canvas.flush_events()


synth = Synth()
visualizer = SpectrumVisualizer(FREQS)

arr = []


def on_key(event):
    if event.name not in KEYMAP:
        return
    name = KEYMAP[event.name]
    if event.event_type == 'down':
        if name not in arr or arr.count(name) == 0:
            pass
        arr.append(name)
        print(arr)
        synth.note_on(name)
        visualizer.add_event(name, pressed=True)
    elif event.event_type == 'up':
        synth.note_off(name)
        visualizer.add_event(name, pressed=False)


keyboard.hook(on_key)
print("meow")

while True:
    plt.pause(0.05)
    if keyboard.is_pressed('esc'):
        break

keyboard.unhook_all()
synth.close()
plt.ioff()
plt.show()
