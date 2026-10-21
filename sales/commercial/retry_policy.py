"""Respect access cooldowns and release an idle worker without losing retries."""
from datetime import datetime,timezone
from sales.access_status import describe

def retry_at(error,provider_retry=None):
    return provider_retry or (describe(error) or {}).get('retry_at')

def park_until_manual_resume(available_at,now=None):
    return (datetime.fromisoformat(available_at)-(now or datetime.now(timezone.utc))).total_seconds()>30
