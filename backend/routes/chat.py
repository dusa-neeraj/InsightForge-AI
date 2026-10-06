from fastapi import APIRouter

from schemas import ChatHistoryResponse, ChatRequest, ChatResponse
from services import chat_service, file_service

router = APIRouter(prefix="/datasets", tags=["Chat"])


@router.post("/{dataset_id}/chat", response_model=ChatResponse)
def chat(dataset_id: str, request: ChatRequest):
    answer = chat_service.ask(dataset_id, request.question, request.session_id)
    return ChatResponse(dataset_id=dataset_id, **answer)


@router.get("/{dataset_id}/chat/{session_id}", response_model=ChatHistoryResponse)
def chat_history(dataset_id: str, session_id: str):
    file_service.require_dataset(dataset_id)
    turns = file_service.load_chat_history(dataset_id, session_id)
    return ChatHistoryResponse(dataset_id=dataset_id, session_id=session_id, turns=turns)