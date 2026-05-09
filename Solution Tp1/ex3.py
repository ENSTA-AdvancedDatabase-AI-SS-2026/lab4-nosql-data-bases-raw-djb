
import redis
import json
import time
from typing import Optional

r = redis.Redis(host='localhost', port=6379, decode_responses=True)


def slow_db_get_product(product_id: int) -> Optional[dict]:

    time.sleep(2)
    products = {
        1: {"id": 1, "name": "Samsung Galaxy A54", "price": 65000, "stock": 15},
        2: {"id": 2, "name": "Laptop HP 15-inch", "price": 120000, "stock": 8},
        3: {"id": 3, "name": "Casque JBL Bluetooth", "price": 12000, "stock": 50},
        4: {"id": 4, "name": "Clavier Mécanique", "price": 8000, "stock": 30},
    }
    return products.get(product_id)


def get_product_cached(r, product_id: int, ttl: int = 600) -> Optional[dict]:

    start = time.time()
    cache_key = f"product_cache:{product_id}"

    cached = r.get(cache_key)
    if cached is not None:
        elapsed = (time.time() - start) * 1000
        print(f"  CACHE HIT  ({elapsed:.1f}ms)")
        return json.loads(cached)

    product = slow_db_get_product(product_id)
    if product is not None:
        r.setex(cache_key, ttl, json.dumps(product))

    elapsed = (time.time() - start) * 1000
    print(f"  CACHE MISS ({elapsed:.1f}ms)")
    return product


def invalidate_product_cache(r, product_id: int):

    r.delete(f"product_cache:{product_id}")
    print(f"  Cache invalidé pour le produit #{product_id}")


def benchmark_cache(r, product_id: int, iterations: int = 20):

    hit_times = []
    miss_times = []

    invalidate_product_cache(r, product_id)

    for i in range(iterations):
        cache_key = f"product_cache:{product_id}"
        is_cached = r.exists(cache_key)

        start = time.time()
        get_product_cached(r, product_id)
        elapsed = (time.time() - start) * 1000

        if is_cached:
            hit_times.append(elapsed)
        else:
            miss_times.append(elapsed)

    total = len(hit_times) + len(miss_times)
    hit_rate = len(hit_times) / total * 100

    print(f"\n--- Résultats Benchmark ({iterations} itérations) ---")
    print(f"  MISS : {len(miss_times)} appel(s) | temps moyen : {sum(miss_times)/len(miss_times):.1f}ms" if miss_times else "  MISS : 0 appel")
    print(f"  HIT  : {len(hit_times)} appel(s) | temps moyen  : {sum(hit_times)/len(hit_times):.1f}ms" if hit_times else "  HIT  : 0 appel")
    print(f"  Taux de cache hit : {hit_rate:.1f}%")


if __name__ == "__main__":
    r.flushdb()

    print(" Test Cache-Aside ")
    print("\nPremier appel (MISS attendu):")
    get_product_cached(r, 1)

    print("\nDeuxième appel (HIT attendu):")
    get_product_cached(r, 1)

    print("\nInvalidation du cache :")
    invalidate_product_cache(r, 1)

    print("\nAprès invalidation (MISS attendu):")
    get_product_cached(r, 1)

    print("\n Benchmark")
    benchmark_cache(r, 1, iterations=10)