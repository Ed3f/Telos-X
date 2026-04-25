from typing import Dict, cast
from configparser import ConfigParser

import threading

from datetime import datetime
from datetime import timedelta
from telos_x.core.base_module import BaseModule
from utils import Os_stat, active_groups
    
class Job(threading.Thread):
    def __init__(self, hour, minute, execute, *args, **kwargs):
        threading.Thread.__init__(self)
        self.daemon = True
        self.stopped = threading.Event()
        self.hour = hour
        self.minute = minute
        self.execute = execute
        self.args = args
        self.kwargs = kwargs
        
    def __compute_interval(self):
        now = datetime.now()
        target = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        interval = 0

        if now < target:
            interval = (target - now).total_seconds()
        else:
            interval = (target + timedelta(days=1) - now).total_seconds()


        print(interval) 
        return interval
    
    def run(self):
            while not self.stopped.wait(self.__compute_interval()):
                self.execute(*self.args, **self.kwargs)

class StatsNotifier(BaseModule):
    def __init__(self):
        self.jobs = []
    
    async def can_activate(self, config: ConfigParser, args: Dict, data: Dict) -> bool:
        """
        Abstract Method for Module Activation Function.
        :return:
        """
        
        return cast(bool, args['listen'])
    
    async def run(self, config: ConfigParser, args: Dict, data: Dict) -> None:
        # il codice per mandare le notifiche in maniera periodica
        
        hour = int(config['STATS_NOTIFIER']['hour'])
        minute = int(config['STATS_NOTIFIER']['minute'])

        #Get Update message whit information Sistem
        system_info_notify_job = Job(hour, minute, self.__system_info_notify)
        active_groups_notify_job = Job(hour, minute, self.__active_groups_notify)

        self.jobs.append(system_info_notify_job)
        self.jobs.append(active_groups_notify_job)

        system_info_notify_job.start()
        active_groups_notify_job.start()

    def __system_info_notify(self):
        Os_stat.information_sistem()
        pass

    def __active_groups_notify(sefl):
        active_groups.information()
        pass