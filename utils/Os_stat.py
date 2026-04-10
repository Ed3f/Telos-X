import os
import psutil
from time import sleep
import requests

def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor
def information_sistem(): 
        partitions = psutil.disk_partitions()
        filename= "/home/sl3p3r/Desktop/TEx_venv/data_local.db"
        size = os.path.getsize(filename) 
        for partition in partitions:
            print(f"=== Device: {partition.device} ===")
            print(f"  Mountpoint: {partition.mountpoint}")
            print(f"  File system type: {partition.fstype}")
            try:
                partition_usage = psutil.disk_usage(partition.mountpoint)
            except PermissionError:
                continue
            headers = {"Content-type": "application/json"}
            SLACK_WEBHOOK=  "https://hooks.slack.com/services/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" 
            print(f"  Total Size: {get_size(partition_usage.total)}")
            print(f"  Used: {get_size(partition_usage.used)}")
            print(f"  Free: {get_size(partition_usage.free)}")
            print(f"  Percentage: {partition_usage.percent}%")
            if partition_usage.percent >= 90.0:
                message_error= "Memory is running out"
                data= {"text":f"Message:{message_error}"}
                requests.post(SLACK_WEBHOOK, headers=headers, json= data)
        #sleep(wait_time) 
        data= {"text":f"Total Size:{get_size(partition_usage.total)}\nUsed: {get_size(partition_usage.used)}\nFree: {get_size(partition_usage.free)}\nPercentage: {partition_usage.percent}%"}
        print(f"send alert:{data}")
        requests.post(SLACK_WEBHOOK, headers=headers, json= data)