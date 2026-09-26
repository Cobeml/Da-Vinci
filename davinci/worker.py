import argparse
import logging
import signal
import threading
import time

from davinci.config import Settings
from davinci.engine import Engine


def work(stop, settings):
    engine = Engine(settings)
    reconciled = 0
    while not stop.is_set():
        try:
            if time.monotonic() - reconciled > 15:
                engine.reconcile()
                reconciled = time.monotonic()
            job = engine.store.claim()
            if not job:
                stop.wait(0.5)
                continue
            heartbeat_stop = threading.Event()

            def heartbeat():
                while not heartbeat_stop.wait(20):
                    if not engine.store.renew(job):
                        return

            pulse = threading.Thread(target=heartbeat, daemon=True)
            pulse.start()
            try:
                engine.execute_job(job)
            finally:
                heartbeat_stop.set()
                pulse.join()
        except Exception:
            logging.exception("Worker loop failed; retrying")
            stop.wait(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=2, choices=[1, 2])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    threads = [threading.Thread(target=work, args=(stop, Settings())) for _ in range(args.workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()


if __name__ == "__main__":
    main()
