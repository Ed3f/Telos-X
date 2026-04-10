from datetime import datetime, timedelta
from time import sleep
import asyncio
import Os_stat

def scheduled_message(h,m):
        now = datetime.now()
        target = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
        diff = (target - now).total_seconds()
        return diff



