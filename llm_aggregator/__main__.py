import sys
from pathlib import Path

# Add project root to path so server.py is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    import server
    server.mcp.run()


if __name__ == "__main__":
    main()
