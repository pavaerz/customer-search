"""Bounded, non-preemptive resource scheduling; no change to network policy."""
import asyncio
from contextlib import asynccontextmanager


class ResourceSlots:
    def __init__(self, limit):
        self.limit=limit;self.active=0;self.sequence=0
        self.waiting=[];self.condition=asyncio.Condition()

    @asynccontextmanager
    async def acquire(self, kind):
        priority=0 if kind in ('document','stylesheet','script','font') else 1
        ticket=(priority,self.sequence);self.sequence+=1
        acquired=False
        async with self.condition:
            self.waiting.append(ticket)
            try:
                await self.condition.wait_for(lambda:self.active<self.limit and ticket==min(self.waiting))
                self.active+=1;acquired=True
            finally:
                self.waiting.remove(ticket);self.condition.notify_all()
        try:
            yield
        finally:
            if acquired:
                async with self.condition:
                    self.active-=1;self.condition.notify_all()
