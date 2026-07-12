import argparse

from .server import main

ap = argparse.ArgumentParser(description="opis workbench UI server")
ap.add_argument("--port", type=int, default=8787)
main(port=ap.parse_args().port)
