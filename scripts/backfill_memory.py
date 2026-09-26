"""Retry pending Atlas embeddings using each original run's remaining budget."""

from davinci.config import Settings
from davinci.engine import Engine


def main():
    engine = Engine(Settings())
    count = 0
    for memory in engine.store.list("memories", {"embedding_status": "pending"}, limit=10000):
        run = engine.store.get("runs", memory["run_id"])
        provider = engine.provider(run)
        embedding = provider.embed(memory["summary"], run["_id"])
        engine.store.update("memories", memory["_id"], {"embedding": embedding, "embedding_status": "ready"})
        count += 1
    print(f"Embedded {count} pending memories.")


if __name__ == "__main__":
    main()
