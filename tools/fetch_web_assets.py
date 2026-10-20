"""Download pinned Three.js assets during hosting builds; verify exact bytes."""
from hashlib import sha256
from pathlib import Path
from urllib.request import urlopen

BASE = "https://cdn.jsdelivr.net/npm/three@0.166.1/"
ASSETS = {
    "three.module.js": ("build/three.module.js", "7d8a8113afd346464aa1854c1f47aaa0aca4c9a07f0a709f8b417f16d0b6b5fd"),
    "OrbitControls.js": ("examples/jsm/controls/OrbitControls.js", "f260591ef315aa04888152e7f121865214e33fb54727145cf4e4445058db1297"),
}


def main():
    directory = Path(__file__).resolve().parents[1] / "dashboard" / "vendor"
    directory.mkdir(parents=True, exist_ok=True)
    for name, (source, expected) in ASSETS.items():
        destination = directory / name
        if destination.exists() and sha256(destination.read_bytes()).hexdigest() == expected:
            continue
        with urlopen(BASE + source, timeout=30) as response:
            data = response.read(3_000_000)
        if sha256(data).hexdigest() != expected:
            raise RuntimeError(f"Checksum verification failed for {name}")
        destination.write_bytes(data)


if __name__ == "__main__":
    main()
