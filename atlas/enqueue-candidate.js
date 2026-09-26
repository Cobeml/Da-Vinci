// Database Trigger: candidates INSERT only; unordered delivery is supported.
exports = async function(changeEvent) {
  const doc = changeEvent.fullDocument;
  if (changeEvent.operationType !== "insert" || !doc?.run_id) return;
  const db = context.services.get("mongodb-atlas").db(context.values.get("DAVINCI_DATABASE"));
  const key = "evaluate_candidate:" + doc._id;
  const timestamp = new Date().toISOString();
  await db.collection("jobs").updateOne({_id: key}, {$setOnInsert: {
    _id: key, schema_version: 1, job_key: key, kind: "evaluate_candidate",
    subject_id: doc._id, run_id: doc.run_id, status: "pending", attempt: 0,
    lease_token: null, lease_expires_at: timestamp, created_at: timestamp
  }}, {upsert: true});
};
