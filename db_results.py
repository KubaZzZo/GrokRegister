import time

# In-memory task store used by the local solver.
results_db = {}


async def init_db():
    print("[system] Result store initialized (in-memory mode)")


async def save_result(task_id, task_type, data):
    results_db[task_id] = data
    status = data.get("value", "processing") if isinstance(data, dict) else "processing"
    print(f"[system] Task {task_id} updated: {status}")


async def load_result(task_id):
    return results_db.get(task_id)


async def cleanup_old_results(days_old=7):
    now = time.time()
    to_delete = []
    for tid, res in results_db.items():
        if isinstance(res, dict) and now - res.get("createTime", now) > days_old * 86400:
            to_delete.append(tid)
    for tid in to_delete:
        del results_db[tid]
    return len(to_delete)
