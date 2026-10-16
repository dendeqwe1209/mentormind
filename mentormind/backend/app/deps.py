from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from functools import lru_cache

from mentormind.core.config import get_settings
from mentormind.knowledge_base.kg.client import Neo4jGraph
from mentormind.knowledge_base.kg.loader import KnowledgeGraphLoader
from mentormind.knowledge_base.store.profile_store import ProfileStore
from mentormind.knowledge_base.store.vector_store import VectorStore, get_vector_store

#: Opens Neo4j + pgvector when called (spec 08 §2 "Xoá dữ liệu": deleting drafts never needs them).
LoaderOpener = Callable[[], AbstractContextManager[KnowledgeGraphLoader]]
#: Connects to the vector store when called, so an unreachable one is reported instead of failing DI.
VectorStoreOpener = Callable[[], VectorStore]


@lru_cache
def get_profile_store() -> ProfileStore:
    settings = get_settings()
    return ProfileStore(db_path=settings.profile_db)


@contextmanager
def open_knowledge_loader() -> Iterator[KnowledgeGraphLoader]:
    graph = Neo4jGraph()
    try:
        yield KnowledgeGraphLoader(graph, get_vector_store())
    finally:
        graph.close()


def get_knowledge_loader() -> Iterator[KnowledgeGraphLoader]:
    with open_knowledge_loader() as loader:
        yield loader


def get_loader_opener() -> LoaderOpener:
    return open_knowledge_loader


def get_vector_store_opener() -> VectorStoreOpener:
    return get_vector_store
