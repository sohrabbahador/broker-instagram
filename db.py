from pymongo import MongoClient
import config
_client = MongoClient(config.MONGODB_URI) if config.MONGODB_URI else None
db = _client["broker_database"] if _client is not None else None
