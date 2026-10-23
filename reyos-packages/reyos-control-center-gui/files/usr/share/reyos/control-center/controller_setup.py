"""The step-by-step controller setup ("press the button shown"), shared by
Control Center (Gaming page) and ReyOS Games (the library's controller
window), so both run the same steps and write the same RetroArch profile."""
from PySide6.QtCore import QThread, Signal

import emulation


class ControllerSetupWorker(QThread):
    """Walks CONTROLLER_STEPS on one pad, then writes the RetroArch profile."""
    step = Signal(int, int, str, str, str, str)
    done = Signal(bool, str)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.skip = False
        self.cancelled = False

    def run(self):
        try:
            reader = emulation.ControllerReader(self.path)
        except OSError as e:
            self.done.emit(False, f"Couldn't read the controller ({e.strerror}). Unplug it, plug it back in and try again.")
            return
        name = reader.info["name"]
        brand = emulation.controller_brand(reader.info["vendor"], name)
        binds = {}
        steps = emulation.CONTROLLER_STEPS
        try:
            for i, (key, title, hint) in enumerate(steps):
                self.skip = False
                title, hint = emulation.step_text(key, title, hint, brand)
                self.step.emit(i, len(steps), key, brand, title, hint)
                bind = reader.wait_bind(lambda: self.skip or self.cancelled)
                # Clicking a stick in moves it a little too: those steps take
                # a button only (a DS4's R3 was saved as the stick's axis).
                while bind and bind[0] == "axis" and key in ("l3", "r3") and not (self.skip or self.cancelled):
                    bind = reader.wait_bind(lambda: self.skip or self.cancelled)
                if self.cancelled:
                    self.done.emit(False, "Controller setup cancelled — nothing was changed.")
                    return
                if bind:
                    binds[key] = bind
            if not binds:
                self.done.emit(False, "Every step was skipped, so nothing was saved.")
                return
            emulation.write_profile(reader.info, binds)
            self.done.emit(True, f"{name} is set up. Start + Select opens the emulator menu in a game.")
        except OSError:
            self.done.emit(False, f"{name} was disconnected during setup — nothing was saved.")
        finally:
            reader.close()
