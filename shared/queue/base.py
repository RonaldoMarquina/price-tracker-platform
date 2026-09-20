"""Queue abstraction interfaces shared between API and Worker."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class QueueMessage(BaseModel):
    """Normalized message representation received from a queue provider."""

    message_id: str
    receipt_handle: str
    body: str
    attempts: int = Field(default=1, description="Contador real de intentos gestionado por la cola")
    attributes: dict[str, Any] = Field(default_factory=dict)


class BaseQueue(ABC):
    """Abstract interface for message queue operations."""

    @abstractmethod
    def send_message(self, queue_name: str, message: BaseModel | dict[str, Any] | str) -> str:
        """Publish a message to the specified queue. Returns message ID."""
        pass

    @abstractmethod
    def receive_messages(
        self, queue_name: str, max_messages: int = 1, visibility_timeout: int = 30
    ) -> list[QueueMessage]:
        """Claim up to max_messages safely using transaction locking."""
        pass

    @abstractmethod
    def delete_message(self, queue_name: str, receipt_handle: str) -> None:
        """Acknowledge and mark or delete a message after successful processing."""
        pass

    @abstractmethod
    def change_message_visibility(
        self, queue_name: str, receipt_handle: str, visibility_timeout: int
    ) -> None:
        """Reset or postpone message visibility for retry or backoff."""
        pass

    @abstractmethod
    def send_to_dlq(
        self,
        dlq_name: str,
        message_payload: dict[str, Any] | str,
        error_reason: str,
        attempts: int,
        receipt_handle: str | None = None,
    ) -> str:
        """Transfer exhausted or corrupted message to Dead Letter Queue."""
        pass

    @abstractmethod
    def get_queue_size(self, queue_name: str) -> int:
        """Return the number of messages currently visible/available."""
        pass

    @abstractmethod
    def purge_queue(self, queue_name: str) -> None:
        """Purge all messages from the specified queue (testing/cleanup)."""
        pass
