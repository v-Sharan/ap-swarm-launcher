"""PyInstaller entry point.

`ap_swarm_launcher.cli.__main__` uses a relative import, which PyInstaller
cannot use as a top-level script. This wrapper does an absolute import instead.
"""

from ap_swarm_launcher.cli.main import start

if __name__ == "__main__":
    start()
