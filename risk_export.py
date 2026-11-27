"""Load an aggregate snapshot into a new BigQuery table in a chosen dataset."""
import argparse
from collections import Counter
from datetime import datetime, timezone

from storage import Store


def main():
    from google.cloud import bigquery
    import json
    from contextlib import closing
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", help="Existing project.dataset")
    dataset = parser.parse_args().dataset
    project, _ = dataset.split(".", 1)
    store = Store()
    if store.cloud is not None:
        records = (s.to_dict() for s in store.cloud.select(["state", "created", "finding.status"]).stream())
        counts = aggregate(records)
    else:
        with closing(store.connect()) as db:
            counts = aggregate(json.loads(row[0]) for row in db.execute("SELECT data FROM packets"))
    if not counts:
        print("No reviews to export.")
        return
    rows = [dict(day=day, verdict=verdict, state=state, packets=n) for (day, verdict, state), n in sorted(counts.items())]
    table = dataset + ".handoff_risk_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    schema = [bigquery.SchemaField(name, kind) for name,kind in
              [("day","DATE"),("verdict","STRING"),("state","STRING"),("packets","INTEGER")]]
    job = bigquery.LoadJobConfig(schema=schema, write_disposition="WRITE_EMPTY")
    bigquery.Client(project=project).load_table_from_json(rows, table, job_config=job).result()
    print("Risk counts available in", table)


def aggregate(records):
    return Counter((datetime.fromtimestamp(r["created"], timezone.utc).date().isoformat(),
                    (r.get("finding") or {}).get("status", "checking"), r["state"]) for r in records)


if __name__ == "__main__":
    main()

