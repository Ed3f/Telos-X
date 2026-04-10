import requests
import json
def information():
    f=open("not_active_group.txt", "r")
    groups= f.read()
    f.close()
    headers = {"Content-type": "application/json"}
    SLACK_WEBHOOK=  "https://hooks.slack.com/services/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"
    data= {"text":f"Group List:{groups}"}
    print(data)
    requests.post(SLACK_WEBHOOK, json= data,headers= headers)