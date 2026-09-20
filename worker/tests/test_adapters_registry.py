"""Tests for AdapterRegistry and deactivated store skipping logic."""

import json
import uuid
from unittest.mock import MagicMock

import pytest
from shared.queue.base import BaseQueue, QueueMessage
from sqlalchemy.orm import Session

from app.adapters.base import (
    FatalScrapingError,
    StoreDisabledError,
)
from app.adapters.memorykings_adapter import MemoryKingsAdapter
from app.adapters.necs_adapter import NecsAdapter
from app.adapters.registry import AdapterRegistry
from app.adapters.sercoplus_adapter import SercoplusAdapter
from app.consumers.scraping_consumer import ScrapingConsumer
from app.db.models import Store
from app.services.scraping_service import ScrapingWorkerService


def test_registry_dispatches_known_domains():
    """Registry returns appropriate adapter instance for official domains and aliases."""
    registry = AdapterRegistry(disabled_domains=set())

    assert isinstance(registry.get_adapter("necs.pe"), NecsAdapter)
    assert isinstance(registry.get_adapter("https://www.necs.pe/"), NecsAdapter)
    assert isinstance(registry.get_adapter("memorykings.pe"), MemoryKingsAdapter)
    assert isinstance(registry.get_adapter("https://www.memorykings.pe/"), MemoryKingsAdapter)
    assert isinstance(registry.get_adapter("sercoplus.com"), SercoplusAdapter)
    assert isinstance(registry.get_adapter("https://www.sercoplus.com/"), SercoplusAdapter)


def test_registry_sercoplus_disabled_by_default():
    """Sercoplus is disabled by default as an offline-only / blocked store."""
    registry = AdapterRegistry()

    with pytest.raises(StoreDisabledError, match="currently disabled"):
        registry.get_adapter("sercoplus.com")


def test_registry_raises_for_disabled_domain():
    """Registry raises StoreDisabledError when domain is in disabled set."""
    registry = AdapterRegistry(disabled_domains={"necs.pe"})

    with pytest.raises(StoreDisabledError, match="currently disabled"):
        registry.get_adapter("necs.pe")


def test_registry_raises_for_unregistered_domain():
    """Registry raises FatalScrapingError for unsupported domain."""
    registry = AdapterRegistry()

    with pytest.raises(FatalScrapingError, match="No scraping adapter registered"):
        registry.get_adapter("amazon.com")


def test_consumer_skips_deactivated_store_without_dlq():
    """When a store is marked inactive, consumer acknowledges it with skip note and avoids DLQ."""
    store_id = uuid.uuid4()
    job_id = uuid.uuid4()
    receipt_handle = str(uuid.uuid4())

    from datetime import datetime, timezone

    message_payload = {
        "job_id": str(job_id),
        "store_id": str(store_id),
        "product_ids": [str(uuid.uuid4())],
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

    raw_msg = QueueMessage(
        message_id=str(uuid.uuid4()),
        receipt_handle=receipt_handle,
        body=json.dumps(message_payload),
        attempts=1,
    )

    mock_queue = MagicMock(spec=BaseQueue)
    mock_queue.receive_messages.return_value = [raw_msg]

    # Mock DB session returning an inactive store
    inactive_store = Store(
        id=store_id,
        name="Tienda Inactiva",
        domain="tienda-inactiva.com",
        is_active=False,
    )
    mock_db = MagicMock(spec=Session)
    mock_db.get.return_value = inactive_store
    session_factory = MagicMock()
    session_factory.return_value.__enter__.return_value = mock_db

    service = ScrapingWorkerService(registry=AdapterRegistry())
    consumer = ScrapingConsumer(
        queue=mock_queue,
        service=service,
        session_factory=session_factory,
    )

    handled = consumer.process_next_message()

    assert handled is True
    # Message must be acknowledged / deleted with traceable skip reason
    mock_queue.delete_message.assert_called_once()
    call_args = mock_queue.delete_message.call_args
    assert call_args[0][1] == receipt_handle
    assert "SKIPPED_STORE_DISABLED" in call_args[1].get("error_reason", "")

    # Must NOT send to DLQ
    mock_queue.send_to_dlq.assert_not_called()
