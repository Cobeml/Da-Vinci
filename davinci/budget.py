from datetime import datetime, timezone

from davinci.models import identity


class BudgetExceeded(RuntimeError):
    pass


class Budget:
    def __init__(self, store, daily_limit):
        self.store, self.daily_limit = store, daily_limit

    def reserve(self, run_id, amount):
        day = datetime.now(timezone.utc).date().isoformat()
        ledger_id = f"budget-{day}"
        self.store.insert(
            "budgets", {"_id": ledger_id, "revision": 0, "spent": 0.0, "reservations": {}, "runs": {}}
        )
        run = self.store.get("runs", run_id)
        token = identity("reservation")

        def change(doc):
            held = sum(x["amount"] for x in doc["reservations"].values())
            run_held = sum(x["amount"] for x in doc["reservations"].values() if x["run_id"] == run_id)
            # Cumulative run spending spans midnight; the run stores settled usage.
            if (
                doc["spent"] + held + amount > self.daily_limit
                or run.get("spent_usd", 0) + run_held + amount > run["budget_usd"]
            ):
                raise BudgetExceeded("API budget cannot cover the next request")
            doc["reservations"][token] = {"run_id": run_id, "amount": amount}
            return doc

        self.store.mutate("budgets", ledger_id, change)
        return ledger_id, token

    def settle(self, reservation, actual):
        ledger_id, token = reservation
        holder = {}

        def change(doc):
            item = doc["reservations"].pop(token, None)
            if item:
                holder.update(item)
                doc["spent"] += actual
                doc["runs"][item["run_id"]] = doc["runs"].get(item["run_id"], 0) + actual
            return doc

        self.store.mutate("budgets", ledger_id, change)
        if holder:
            self.store.mutate("runs", holder["run_id"], lambda run: {"spent_usd": run["spent_usd"] + actual})
