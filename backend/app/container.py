from __future__ import annotations

from dataclasses import dataclass

from backend.app.config import Settings
from backend.app.services.documents import DocumentService
from backend.app.services.generator import GeneratorFactory
from backend.app.services.indexing import IndexRebuildManager
from backend.app.services.llm_settings import LLMSettingsManager
from backend.app.services.rag import RAGService
from backend.app.services.question_suggestions import QuestionSuggestionService
from backend.app.services.retriever import RetrievalEngine


@dataclass
class AppContainer:
    settings: Settings
    retriever: RetrievalEngine
    generators: GeneratorFactory
    llm_settings: LLMSettingsManager
    rag: RAGService
    documents: DocumentService
    indexing: IndexRebuildManager
    question_suggestions: QuestionSuggestionService


def build_container(settings: Settings) -> AppContainer:
    retriever = RetrievalEngine(settings)
    generators = GeneratorFactory(settings)
    llm_settings = LLMSettingsManager(settings)
    rag = RAGService(settings, retriever, generators, llm_settings)
    documents = DocumentService(settings)
    indexing = IndexRebuildManager(settings, reload_callback=retriever.load)
    question_suggestions = QuestionSuggestionService(settings)
    return AppContainer(
        settings=settings,
        retriever=retriever,
        generators=generators,
        llm_settings=llm_settings,
        rag=rag,
        documents=documents,
        indexing=indexing,
        question_suggestions=question_suggestions,
    )
