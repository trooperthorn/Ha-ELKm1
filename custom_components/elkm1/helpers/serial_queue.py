"""Serial command queue for Elk-M1 writes."""
from __future__ import annotations

import asyncio
import logging
from asyncio import Queue
from typing import Any

from elkm1_lib import Elk

_LOGGER: logging.Logger = logging.getLogger(__name__)


class ElkSerialQueue:
    """Queue commands to serial port with rate limiting."""

    def __init__(self, elk: Elk, interval: float = 0.1) -> None:
        """Initialize queue."""
        self._elk = elk
        self._interval = interval
        self._queue: Queue[Any] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the queue worker."""
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        """Stop the queue worker."""
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def async_send_command(
        self, encoder_name: str, **kwargs: Any
    ) -> Any:
        """Queue a command for sending."""
        # Put item in queue and wait for result
        future: asyncio.Future[Any] = asyncio.Future()
        await self._queue.put((encoder_name, kwargs, future))
        
        try:
            result = await asyncio.wait_for(future, timeout=5.0)
            return result
        except asyncio.TimeoutError:
            _LOGGER.warning(f"Timeout sending {encoder_name}")
            raise

    async def _worker(self) -> None:
        """Worker task that processes queue."""
        while True:
            try:
                encoder_name, kwargs, future = await self._queue.get()
                
                try:
                    # Send command via elkm1_lib
                    # Get the encoder function
                    encoder = getattr(
                        self._elk,
                        encoder_name,
                        None,
                    )
                    
                    if not encoder:
                        raise AttributeError(f"Unknown encoder: {encoder_name}")
                    
                    result = await encoder(**kwargs)
                    future.set_result(result)
                    
                except Exception as err:
                    future.set_exception(err)
                
                # Rate limit: wait before processing next command
                await asyncio.sleep(self._interval)
                
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error(f"Queue worker error: {err}")
                await asyncio.sleep(1)
