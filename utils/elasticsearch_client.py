from elasticsearch import Elasticsearch, helpers
from decouple import config

import logging

logger = logging.getLogger(__name__)

# es = Elasticsearch("http://localhost:9200")

# Production configuration for Elastic Cloud
es = Elasticsearch(
    config("ELASTIC_CLOUD_ID"),
    api_key=config("ELASTIC_API_KEY"),
    max_retries=10,
    retry_on_timeout=True,
    timeout=45,
)


# Timeout to allow machine learning model loading and semantic ingestion to complete
ingestion_timeout=300

def data_to_elasticsearch(docs, index_name):
    bulk_response = helpers.bulk(
        es.options(request_timeout=ingestion_timeout),
        docs,
        index=index_name
    )
    logger.info("Bulk indexing response: %s", bulk_response)
    return bulk_response

# For local development, you can run Elasticsearch using Docker:
# ```
# docker run -d --name elasticsearch -p 9200:9200 -e "discovery.type=single-node" -e "xpack.security.enabled=false" docker.elastic.co/elasticsearch/elasticsearch:8.12.
# ```
