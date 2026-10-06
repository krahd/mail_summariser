"""Launch the existing browser app against an ephemeral synthetic-only backend."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8767)
    args = parser.parse_args()
    os.environ['MAIL_SUMMARISER_DEMO'] = 'true'
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import uvicorn
    print(f'Isolated synthetic demo: http://127.0.0.1:{args.port}', flush=True)
    print('No account needed. Local excerpts only. Stop with Ctrl+C; demo state is discarded.', flush=True)
    uvicorn.run('backend.app:app', host='127.0.0.1', port=args.port, workers=1)


if __name__ == '__main__':
    main()
