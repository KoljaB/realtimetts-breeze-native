"""Stream speech from a running RealtimeTTS Breeze or Qwen server.

Install the routing and playback extras, then:
    python examples/remote_server_client.py --url http://127.0.0.1:18086
"""
from __future__ import annotations

import argparse

from RealtimeTTS import RemoteTTSEngine, TextToAudioStream


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:18086")
    parser.add_argument("--voice", default="demo-neutral")
    parser.add_argument("--language", default="en")
    parser.add_argument("--text", default="Hello! This speech is streamed while it is generated.")
    args = parser.parse_args()
    engine = RemoteTTSEngine(args.url, voice=args.voice, language=args.language)
    stream = TextToAudioStream(engine)
    try:
        stream.feed(args.text).play()
    finally:
        stream.close()


if __name__ == "__main__":
    main()
