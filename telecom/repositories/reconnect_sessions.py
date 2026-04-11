from __future__ import annotations

from functools import lru_cache

from django.conf import settings

from telecom.exceptions import ActiveReconnectSessionConflict


@lru_cache(maxsize=4)
def _build_mongo_client(uri: str):
    from pymongo import MongoClient

    return MongoClient(uri)


class MongoReconnectSessionRepository:
    def __init__(self, *, client, database_name: str, collection_name: str):
        self.collection = client[database_name][collection_name]

    @classmethod
    def from_settings(cls):
        client = _build_mongo_client(settings.RECONNECT_MONGO_URI)
        return cls(
            client=client,
            database_name=settings.RECONNECT_MONGO_DATABASE,
            collection_name=settings.RECONNECT_MONGO_COLLECTION,
        )

    def find_active_session_by_phone(self, phone_number: str):
        return self.collection.find_one(
            {
                "phone_number": phone_number,
                "active_lock": True,
                "status": {"$nin": ["CONNECTED", "FAILED", "CANCELLED"]},
            }
        )

    def create_session(self, document: dict):
        from pymongo.errors import DuplicateKeyError

        try:
            self.collection.insert_one(document)
        except DuplicateKeyError as exc:
            raise ActiveReconnectSessionConflict from exc
        return self.collection.find_one({"_id": document["_id"]}) or document

    def has_active_session_unique_index(self) -> bool:
        for index in self.collection.list_indexes():
            partial_filter = index.get("partialFilterExpression") or {}
            keys = list((index.get("key") or {}).items())
            if (
                index.get("unique") is True
                and keys == [("phone_number", 1)]
                and partial_filter.get("active_lock") is True
            ):
                return True
        return False

    def get_session(self, session_id: str):
        return self.collection.find_one({"_id": session_id})

    def submit_pair_code(self, *, session_id: str, attempt: int, pair_code: str, submitted_at):
        result = self.collection.update_one(
            {
                "_id": session_id,
                "status": "WAITING_FOR_CODE",
                "attempt": attempt,
                "$or": [
                    {"pair_code": {"$exists": False}},
                    {"pair_code": None},
                    {"pair_code": ""},
                ],
            },
            {
                "$set": {
                    "pair_code": pair_code,
                    "pair_code_attempt": attempt,
                    "pair_code_submitted_at": submitted_at,
                    "last_pair_code": pair_code,
                    "last_pair_code_attempt": attempt,
                    "last_pair_code_submitted_at": submitted_at,
                    "updated_at": submitted_at,
                }
            },
        )
        return result.modified_count > 0

    def cancel_session(self, *, session_id: str, requested_at):
        result = self.collection.update_one(
            {
                "_id": session_id,
                "status": {"$nin": ["CONNECTED", "FAILED", "CANCELLED"]},
            },
            {
                "$set": {
                    "cancel_requested_at": requested_at,
                    "updated_at": requested_at,
                }
            },
        )
        return result.modified_count > 0
