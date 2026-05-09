
import time
import statistics
import json
import uuid
import random
import threading
from typing import Callable, List
import redis
from pymongo import MongoClient, InsertOne
from cassandra.cluster import Cluster
from cassandra.query import BatchStatement, BatchType

def measure_latency(fn: Callable, iterations: int = 1000) -> dict:

    latencies = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - start) * 1000)  

    latencies.sort()
    return {
        "mean_ms":        statistics.mean(latencies),
        "p50_ms":         latencies[int(0.50 * len(latencies))],
        "p95_ms":         latencies[int(0.95 * len(latencies))],
        "p99_ms":         latencies[int(0.99 * len(latencies))],
        "max_ms":         max(latencies),
        "throughput_rps": 1000 / statistics.mean(latencies),
    }


def print_results(name: str, results: dict):
    print(f"\n{'='*50}")
    print(f" {name}")
    print(f"{'='*50}")
    for k, v in results.items():
        print(f"  {k:20s}: {v:.2f}")


def _random_sensor_record(i: int) -> dict:

    return {
        "capteur_id": str(uuid.uuid4()),
        "index":      i,
        "tension_v":  round(220 + random.gauss(0, 5), 2),
        "courant_a":  round(random.uniform(0.5, 15.0), 2),
        "puissance_kw": round(random.uniform(0.1, 3.3), 3),
        "frequence_hz": round(50 + random.gauss(0, 0.1), 2),
        "temperature":  round(random.uniform(20, 65), 1),
        "alerte":       random.random() < 0.05,
        "wilaya":       random.choice(["Alger", "Oran", "Constantine", "Annaba", "Blida"]),
    }

def benchmark_write_redis(n: int = 100_000):

    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    r.flushdb()

    BATCH = 500
    start = time.perf_counter()

    for i in range(0, n, BATCH):
        pipe = r.pipeline(transaction=False)   
        for j in range(i, min(i + BATCH, n)):
            rec = _random_sensor_record(j)
            key = f"sensor:{rec['capteur_id']}"
   
            pipe.hset(key, mapping={k: str(v) for k, v in rec.items()})
 
            pipe.zadd("sensors:by_index", {key: j})
        pipe.execute()

    elapsed = time.perf_counter() - start
    throughput = n / elapsed
    print_results("Redis — Écriture pipeline", {
        "total_records":    n,
        "elapsed_s":        elapsed,
        "throughput_rec_s": throughput,
    })
    return throughput


def benchmark_write_mongodb(n: int = 100_000):

    client = MongoClient("mongodb://localhost:27017/")
    db = client["benchmark"]
    db.sensors.drop()

    BATCH = 1000
    start = time.perf_counter()

    for i in range(0, n, BATCH):
        ops = [InsertOne(_random_sensor_record(j)) for j in range(i, min(i + BATCH, n))]
        db.sensors.bulk_write(ops, ordered=False)  

    elapsed = time.perf_counter() - start
    throughput = n / elapsed
    print_results("MongoDB — Écriture bulk_write", {
        "total_records":    n,
        "elapsed_s":        elapsed,
        "throughput_rec_s": throughput,
    })
    client.close()
    return throughput


def benchmark_write_cassandra(n: int = 100_000):

    cluster = Cluster(['localhost'])
    session = cluster.connect()

    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS benchmark
        WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
    """)
    session.set_keyspace("benchmark")
    session.execute("""
        CREATE TABLE IF NOT EXISTS sensors (
            capteur_id  TEXT,
            idx         INT,
            tension_v   FLOAT,
            courant_a   FLOAT,
            puissance_kw FLOAT,
            frequence_hz FLOAT,
            temperature FLOAT,
            alerte      BOOLEAN,
            wilaya      TEXT,
            PRIMARY KEY (capteur_id)
        )
    """)
    session.execute("TRUNCATE sensors")

    prepared = session.prepare("""
        INSERT INTO sensors (capteur_id, idx, tension_v, courant_a,
            puissance_kw, frequence_hz, temperature, alerte, wilaya)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """)

    BATCH_SIZE = 50
    start = time.perf_counter()

    records = [_random_sensor_record(i) for i in range(n)]
    for i in range(0, n, BATCH_SIZE):
        chunk = records[i: i + BATCH_SIZE]
        batch = BatchStatement(batch_type=BatchType.UNLOGGED)
        for rec in chunk:
            batch.add(prepared, (
                rec["capteur_id"], rec["index"], rec["tension_v"],
                rec["courant_a"], rec["puissance_kw"], rec["frequence_hz"],
                rec["temperature"], rec["alerte"], rec["wilaya"],
            ))
        session.execute(batch)

    elapsed = time.perf_counter() - start
    throughput = n / elapsed
    print_results("Cassandra — Écriture UNLOGGED BATCH", {
        "total_records":    n,
        "elapsed_s":        elapsed,
        "throughput_rec_s": throughput,
    })
    cluster.shutdown()
    return throughput

def benchmark_read_redis():
  
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)

    sample_keys = r.zrange("sensors:by_index", 0, 99)
    if not sample_keys:
        print("  [Redis] Aucune donnée — lancer benchmark_write_redis() d'abord.")
        return

    def point_lookup():
        r.hgetall(random.choice(sample_keys))

    res_point = measure_latency(point_lookup, iterations=1000)
    print_results("Redis — Lecture point lookup (HGETALL)", res_point)

    def range_query():
        r.zrange("sensors:by_index", 0, 49, withscores=False)

    res_range = measure_latency(range_query, iterations=1000)
    print_results("Redis — Lecture range (ZRANGE 50 éléments)", res_range)

    def multi_get():
        keys = random.choices(sample_keys, k=10)
        pipe = r.pipeline(transaction=False)
        for k in keys:
            pipe.hgetall(k)
        pipe.execute()

    res_multi = measure_latency(multi_get, iterations=500)
    print_results("Redis — Lecture pipeline multi-get (×10)", res_multi)


def benchmark_read_mongodb():

    client = MongoClient("mongodb://localhost:27017/")
    col = client["benchmark"].sensors

    col.create_index("capteur_id")
    col.create_index("tension_v")
    col.create_index("wilaya")

    sample_ids = [doc["capteur_id"] for doc in col.find({}, {"capteur_id": 1}).limit(100)]
    if not sample_ids:
        print("  [MongoDB] Aucune donnée — lancer benchmark_write_mongodb() d'abord.")
        client.close()
        return

    def find_one():
        col.find_one({"capteur_id": random.choice(sample_ids)})

    res_point = measure_latency(find_one, iterations=1000)
    print_results("MongoDB — Lecture find_one (index)", res_point)

    def range_query():
        list(col.find({"tension_v": {"$gte": 215, "$lte": 225}}).limit(50))

    res_range = measure_latency(range_query, iterations=500)
    print_results("MongoDB — Lecture range tension_v [215-225V]", res_range)

    def aggregate_pipeline():
        list(col.aggregate([
            {"$group": {"_id": "$wilaya", "avg_puissance": {"$avg": "$puissance_kw"}}},
            {"$sort": {"avg_puissance": -1}},
        ]))

    res_agg = measure_latency(aggregate_pipeline, iterations=200)
    print_results("MongoDB — Aggregate avg puissance par wilaya", res_agg)

    client.close()

def benchmark_concurrent(
    db_fn: Callable,
    n_clients: int = 50,
    requests_per_client: int = 200,
):

    all_latencies: list[float] = []
    lock = threading.Lock()
    errors = [0]

    def worker():
        local_lat = []
        for _ in range(requests_per_client):
            try:
                t0 = time.perf_counter()
                db_fn()
                local_lat.append((time.perf_counter() - t0) * 1000)
            except Exception:
                with lock:
                    errors[0] += 1
        with lock:
            all_latencies.extend(local_lat)

    ref_latencies = []
    for _ in range(200):
        t0 = time.perf_counter()
        db_fn()
        ref_latencies.append((time.perf_counter() - t0) * 1000)
    ref_mean = statistics.mean(ref_latencies)

    start = time.perf_counter()
    threads = [threading.Thread(target=worker) for _ in range(n_clients)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.perf_counter() - start

    if not all_latencies:
        print("  Aucune latence enregistrée (toutes les requêtes ont échoué).")
        return

    all_latencies.sort()
    total_requests = n_clients * requests_per_client
    concurrent_mean = statistics.mean(all_latencies)

    print_results(f"Charge concurrente ({n_clients} clients × {requests_per_client} req)", {
        "total_requests":     total_requests,
        "errors":             errors[0],
        "elapsed_s":          elapsed,
        "throughput_rps":     total_requests / elapsed,
        "mean_ms":            concurrent_mean,
        "p50_ms":             all_latencies[int(0.50 * len(all_latencies))],
        "p95_ms":             all_latencies[int(0.95 * len(all_latencies))],
        "p99_ms":             all_latencies[int(0.99 * len(all_latencies))],
        "degradation_factor": concurrent_mean / ref_mean,  # >1 = dégradation
    })


if __name__ == "__main__":
    print(" Benchmark NoSQL - Comparatif des 4 technologies")
    print("=" * 60)

    N = 10_000   
    print(f"\n Benchmark Écriture ({N:,} enregistrements)")
    benchmark_write_redis(N)
    benchmark_write_mongodb(N)
    benchmark_write_cassandra(N)

    print(f"\n Benchmark Lecture (1 000 requêtes)")
    benchmark_read_redis()
    benchmark_read_mongodb()

    print(f"\n⚡ Test Charge Concurrente (50 clients — Redis point lookup)")
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    sample_keys = r.zrange("sensors:by_index", 0, 99) or ["sensor:fallback"]

    def redis_point_lookup():
        r.hgetall(random.choice(sample_keys))

    benchmark_concurrent(redis_point_lookup, n_clients=50, requests_per_client=200)

    print("\n Benchmark terminé ! Consultez RAPPORT.md pour l'analyse.")