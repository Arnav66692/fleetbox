import argparse

from fleetbox import sandbox
from fleetbox.api import serve

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the fleetbox server")
    parser.add_argument("--port", type=int, default=8790)
    args = parser.parse_args()
    removed = sandbox.destroy_all()
    if removed:
        print(f"removed {removed} leftover sandboxes")
    serve(port=args.port)
