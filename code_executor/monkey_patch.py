import uuid
import matplotlib.pyplot as plt
from io import BytesIO
from redis_cache import RedisCacheManager
import os
import redis

# Overrides plt.show to exfiltate image to redis and formats url to make it accessible

try:
    cache_manager = RedisCacheManager(
        redis.from_url(os.getenv("REDIS_URL"))
    )
    url_template = os.getenv("URL_TEMPLATE")

    def custom_show():
        doc_id = str(uuid.uuid4()) + ".png"
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)
        png_bytes = buffer.getvalue()
        buffer.close()
        plt.clf()
        plt.close()
        print(png_bytes)
        cache_manager.set(key=doc_id, value=png_bytes, ttl=18000, suppress=False)
        document_url = url_template.format(doc_id=doc_id)
        return f"{document_url} Give this link as it is to the user dont add sandbox prefix to it, user wont recieve file until you explicitly read out the link to him"

    plt.show = custom_show
except Exception as e:
    print("Error in monkey patch: ", e)