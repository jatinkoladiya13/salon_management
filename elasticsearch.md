# 🚀 Elasticsearch — Complete Guide (DRF + Production)

---

## 1. What is Elasticsearch?

Elasticsearch is a **distributed search & analytics engine** used for:

- 🔍 Full-text search  
- ⚡ Fast filtering  
- 📊 Analytics on large data  
- 🔄 Real-time search systems  

> “Search millions of records in milliseconds”

---

## 2. Problem with Django DB Search

Example: 10 million users/products  

**Problems:**
- Full table scan  
- Slow LIKE queries  
- Not scalable  

---

## 3. Elasticsearch Solution

Elasticsearch uses **Inverted Index**

```
word → document IDs
```

Result:

- Ultra-fast search
- Scalable
- Advanced querying

---

## 4. Local Setup (Docker)

```
docker run -d \
--name elasticsearch \
-p 9200:9200 \
-e "discovery.type=single-node" \
-e "xpack.security.enabled=false" \
docker.elastic.co/elasticsearch/elasticsearch:8.12.0
```

Check container:

```
docker ps -a
docker start elasticsearch
```

---

## 5. Install Python Client

```
pip install elasticsearch
```

```
from elasticsearch import Elasticsearch

es = Elasticsearch("http://localhost:9200")
```

---

## 6. Index & Mapping (Schema Design)

```
es.indices.delete(index="users", ignore=[400, 404])

mapping = {
    "mappings": {
        "properties": {
            "username": {"type": "text"},
            "email": {
                "type": "text",
                "fields": {"keyword": {"type": "keyword"}}
            },
            "role": {"type": "keyword"},
            "is_active": {"type": "boolean"},
            "is_verify": {"type": "boolean"},
            "last_login": {"type": "date"},
            "mobile": {"type": "keyword"},
            "date_of_birth": {"type": "date"}
        }
    }
}

es.indices.create(index="users", body=mapping)

```

---

## 7. Insert Data (Indexing)

```
for user in User.objects.all():
    doc = {
        "username": user.username,
        "email": user.email,
        "role": user.get_role,
        "is_active": user.is_active,
        "is_verify": user.is_verify,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "mobile": user.mobile,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
    }

    es.index(index="users", id=user.id, document=doc)
```

---

## 8. Bulk Insert (Production)

```
from elasticsearch import helpers

actions = []

for user in User.objects.all():
    actions.append({
        "_index": "users",
        "_id": user.id,
        "_source": {
            "username": user.username,
            "email": user.email,
        }
    })

helpers.bulk(es, actions, chunk_size=500)

```

---

## 9. Search Query (Core Logic)

```
query = {
    "bool": {
        "must": [],
        "filter": [],
        "must_not": [],
        "should": []
    }
}
```

---

## 10. Full-Text Search

```
query["bool"]["must"].append({
    "multi_match": {
        "query": search_query,
        "fields": ["username", "email"],
        "type": "phrase_prefix"
    }
})
```

---

## 11. Filters

Term Filter
```
{"term": {"role": "admin"}}
```

Boolean Filter
```
{"term": {"role": "admin"}}
```

---

## 12. Range Filter(Dates)

```
{
    "range": {
        "last_login": {
            "gte": "2024-01-01",
            "lte": "2024-12-31"
        }
    }
}
```

---

## 13. Exclude Data (must_not)

```
query["bool"]["must_not"].append({
    "term": {"email.keyword": "test@gmail.com"}
})
```

---

## 14. Multiple Filter (Important)

```
status_list = ["active", "pending"]

query["bool"]["filter"].append({
    "terms": {
        "status.keyword": status_list
    }
})

```

---

## 15. Execute Search

```
results = es.search(
    index="users",
    query=query
)

hits = results["hits"]["hits"]
user_ids = [int(hit["_id"]) for hit in hits]
```

---

## 16. Sync with Django

```
users = User.objects.filter(id__in=user_ids)
```

---

## 17. Production Setup (Elastic Cloud)

```
from elasticsearch import Elasticsearch

es = Elasticsearch(
    config("ELASTIC_CLOUD_ID"),
    api_key=config("ELASTIC_API_KEY"),
    max_retries=10,
    retry_on_timeout=True,
    timeout=45,
)
```
---

## 18. Real Production Architecture

```
Django DB
   ↓
Celery Worker (async)
   ↓
Elasticsearch (indexing)
   ↓
Search API (fast response)
```

---

## 19. Common Mistakes

| Mistake | Fix |
|--------|-----|
| Using `match` for exact value | use `term` |
| Wrong date format | use ISO format |
| Not using `.keyword` | required for exact match |
| Large bulk crash | use `chunk_size` |

---

## 🧠 20. Important Concepts

| Concept | Meaning |
|--------|--------|
| Index | Table |
| Document | Row |
| Mapping | Schema |
| `_source` | Data |
| `_id` | Primary key |
| Bulk API | Fast insert |

---

## 🎯 Final Summary

### 👉 Use Database for:
- Transactions  
- Relations  

### 👉 Use Elasticsearch for:
- Search  
- Filters  
- Analytics  

---

## 🚀 One-Liner

> Elasticsearch is used alongside Django to handle fast, scalable full-text search using inverted indexing, while the database remains the source of truth.

