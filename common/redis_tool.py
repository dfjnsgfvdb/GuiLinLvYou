import os

import redis
from redis.exceptions import ConnectionError

class RedisTool:
    """
    redis 工具类
    """

    def __init__(self, host=None, port=None, db=None, password=None):
        host = host or os.getenv("REDIS_HOST", "localhost")
        port = int(port or os.getenv("REDIS_PORT", "16379"))
        db = int(db if db is not None else os.getenv("REDIS_DB", "0"))
        password = password if password is not None else os.getenv("REDIS_PASSWORD") or None
        self.redis_client = redis.Redis(
            host=host, port=port, db=db, password=password, decode_responses=True
        )

    def set_key(self, key, value, ex=None):
        try:
            return self.redis_client.set(key, value, ex=ex)
        except ConnectionError as e:
            print(f"Connection error: {e}")
            return False

    def get_key(self, key):
        try:
            return self.redis_client.get(key)
        except ConnectionError as e:
            print(f"Connection error: {e}")
            return None

    def delete_key(self, key):
        try:
            return self.redis_client.delete(key)
        except ConnectionError as e:
            print(f"Connection error: {e}")
            return False

    def exists(self, key):
        try:
            return self.redis_client.exists(key)
        except ConnectionError as e:
            print(f"Connection error: {e}")
            return False

    def ping(self):
        try:
            return self.redis_client.ping()
        except ConnectionError as e:
            print(f"Connection error: {e}")
            return False

    def close(self):
        self.redis_client.close()


# 使用示例
if __name__ == "__main__":
    redis_tool = RedisTool(host="localhost", port=16379, password="difyai123456")

    # 设置键值对
    result = redis_tool.set_key("test_key", "Hello, Redis!")
    print(f"Set key: {result}")

    # 获取键值对
    value = redis_tool.get_key("test_key")
    print(f"Get key: {value}")

    # 删除键
    deleted = redis_tool.delete_key("test_key")
    print(f"Deleted key: {deleted}")

    # 检查键是否存在
    exists = redis_tool.exists("test_key")
    print(f"Key exists: {exists}")

    # 测试连接
    ping_result = redis_tool.ping()
    print(f"Ping: {ping_result}")

    # 关闭连接
    redis_tool.close()
