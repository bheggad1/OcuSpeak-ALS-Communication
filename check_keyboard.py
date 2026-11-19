"""Mac check: lists the windows on screen so we can see what the Accessibility Keyboard is called."""
import dock

try:
    windows = dock.mac_windows()
except ImportError:
    print("PROBLEM: the Quartz package isn't installed. Run:  .venv/bin/pip install pyobjc-framework-Quartz")
    raise SystemExit

print("Keyboard found at:", dock.find_keyboard_rect([]) or "NOT FOUND")
print("\nBig windows on screen (owner | name | x, y, width, height):")
for owner, name, x, y, w, h in windows:
    if w >= 200 and h >= 100:
        print(f"  {owner} | {name} | {x}, {y}, {w}, {h}")
