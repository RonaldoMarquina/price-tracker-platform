"""Amazon SQS implementation of the BaseQueue interface."""

import json
import logging
from typing import Any

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel

from shared.queue.base import BaseQueue, QueueMessage

logger = logging.getLogger("price-tracker.shared.queue.sqs")


class SqsQueue(BaseQueue):
    """Queue provider backed by Amazon Simple Queue Service (SQS)."""

    def __init__(
        self,
        client: Any | None = None,
        queue_url_map: dict[str, str] | None = None,
        region_name: str | None = None,
    ) -> None:
        import os

        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.client = client or boto3.client("sqs", region_name=self.region_name)
        mapping: dict[str, str] = {}
        if os.getenv("SCRAPING_QUEUE_URL"):
            mapping["scraping-jobs"] = os.environ["SCRAPING_QUEUE_URL"]
        if os.getenv("SCRAPING_DLQ_URL"):
            mapping["scraping-jobs-dlq"] = os.environ["SCRAPING_DLQ_URL"]
        if queue_url_map:
            mapping.update(queue_url_map)
        self._queue_url_map = mapping

    def get_queue_url(self, queue_name: str) -> str:
        """Resolve queue URL from direct URL, environment cache, or SQS API."""
        if queue_name.startswith("http://") or queue_name.startswith("https://"):
            return queue_name
        if queue_name in self._queue_url_map:
            return self._queue_url_map[queue_name]
        try:
            response = self.client.get_queue_url(QueueName=queue_name)
            url = response["QueueUrl"]
            self._queue_url_map[queue_name] = url
            return url
        except ClientError as exc:
            logger.error("Failed to resolve SQS queue URL for '%s': %s", queue_name, exc)
            raise

    def send_message(
        self,
        queue_name: str,
        message: BaseModel | dict[str, Any] | str,
        session: Any = None,
    ) -> str:
        """Publish a message to the specified queue. Returns SQS MessageId."""
        queue_url = self.get_queue_url(queue_name)
        if isinstance(message, BaseModel):
            body_str = message.model_dump_json()
        elif isinstance(message, dict):
            body_str = json.dumps(message)
        else:
            body_str = str(message)

        try:
            response = self.client.send_message(
                QueueUrl=queue_url,
                MessageBody=body_str,
            )
            return response["MessageId"]
        except ClientError as exc:
            logger.error("Failed to send message to SQS queue '%s': %s", queue_name, exc)
            raise

    def send_message_batch(
        self,
        queue_name: str,
        entries: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Publish up to 10 messages in batch to SQS. Returns dict with Successful and Failed."""
        if not entries:
            return {"Successful": [], "Failed": []}
        queue_url = self.get_queue_url(queue_name)
        try:
            response = self.client.send_message_batch(
                QueueUrl=queue_url,
                Entries=entries,
            )
            return {
                "Successful": response.get("Successful", []),
                "Failed": response.get("Failed", []),
            }
        except ClientError as exc:
            logger.error("Failed to send batch to SQS queue '%s': %s", queue_name, exc)
            raise

    def receive_messages(
        self,
        queue_name: str,
        max_messages: int = 1,
        visibility_timeout: int = 30,
    ) -> list[QueueMessage]:
        """Receive up to max_messages from SQS."""
        queue_url = self.get_queue_url(queue_name)
        try:
            response = self.client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=min(max_messages, 10),
                VisibilityTimeout=visibility_timeout,
                WaitTimeSeconds=0,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
            raw_messages = response.get("Messages", [])
            results: list[QueueMessage] = []
            for raw in raw_messages:
                attributes = raw.get("Attributes", {})
                receive_count_str = attributes.get("ApproximateReceiveCount", "1")
                try:
                    attempts = int(receive_count_str)
                except ValueError:
                    attempts = 1

                results.append(
                    QueueMessage(
                        message_id=raw["MessageId"],
                        receipt_handle=raw["ReceiptHandle"],
                        body=raw["Body"],
                        attempts=attempts,
                        attributes=attributes,
                    )
                )
            return results
        except ClientError as exc:
            logger.error("Failed to receive messages from SQS queue '%s': %s", queue_name, exc)
            raise

    def delete_message(
        self,
        queue_name: str,
        receipt_handle: str,
        error_reason: str | None = None,
    ) -> None:
        """Acknowledge and delete message from SQS using receipt handle."""
        queue_url = self.get_queue_url(queue_name)
        try:
            self.client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
            )
        except ClientError as exc:
            logger.error("Failed to delete message from SQS queue '%s': %s", queue_name, exc)
            raise

    def change_message_visibility(
        self,
        queue_name: str,
        receipt_handle: str,
        visibility_timeout: int,
    ) -> None:
        """Change visibility timeout for a message."""
        queue_url = self.get_queue_url(queue_name)
        try:
            self.client.change_message_visibility(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
                VisibilityTimeout=visibility_timeout,
            )
        except ClientError as exc:
            logger.error("Failed to change visibility in SQS queue '%s': %s", queue_name, exc)
            raise

    def send_to_dlq(
        self,
        dlq_name: str,
        message_payload: dict[str, Any] | str,
        error_reason: str,
        attempts: int,
        receipt_handle: str | None = None,
        source_queue: str | None = None,
    ) -> str:
        """Transfer exhausted or corrupted message to Dead Letter Queue."""
        msg_id = self.send_message(dlq_name, message_payload)
        if receipt_handle and source_queue:
            try:
                self.delete_message(source_queue, receipt_handle)
            except ClientError as exc:
                logger.warning(
                    "Failed to delete message from source queue %s during DLQ transfer: %s",
                    source_queue,
                    exc,
                )
        return msg_id

    def get_queue_size(self, queue_name: str) -> int:
        """Return the approximate number of messages available."""
        queue_url = self.get_queue_url(queue_name)
        try:
            response = self.client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=["ApproximateNumberOfMessages"],
            )
            count_str = response.get("Attributes", {}).get("ApproximateNumberOfMessages", "0")
            return int(count_str)
        except (ClientError, ValueError) as exc:
            logger.error("Failed to get SQS queue size for '%s': %s", queue_name, exc)
            return 0

    def purge_queue(self, queue_name: str) -> None:
        """Purge all messages from SQS queue."""
        queue_url = self.get_queue_url(queue_name)
        try:
            self.client.purge_queue(QueueUrl=queue_url)
        except ClientError as exc:
            logger.error("Failed to purge SQS queue '%s': %s", queue_name, exc)
            raise
