import requests
from telos_x.database.telegram_group_database import TelegramGroupDatabaseManager
from telos_x.models.database.telegram_db_model import TelegramGroupOrmEntity

def comunication_group_message(message, group_id, id):
    db_group= TelegramGroupDatabaseManager.get_by_id(group_id)
    username: str = db_group.group_username
    headers = {"Content-type": "application/json"}
    standard_stream= {"text":f"URL: https://t.me/{username}/{str(id)}\nMessage: {message}"}
    SLACK_WEBHOOK=  "https://hooks.slack.com/services/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"
    #requests.post(SLACK_WEBHOOK, headers=headers, json= standard_stream)


def alertUserToJoinGroup(user):
    headers = {"Content-type": "application/json"}
    stream_user_info= {"text": f"user information: {user}"}
    SLACK_WEBHOOK_CHAT_ACTION= "https://hooks.slack.com/services/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"
    requests.post(SLACK_WEBHOOK_CHAT_ACTION, headers=headers, json= stream_user_info)

def alertcheckHost(message,name_host): 
    headers = {"Content-type": "application/json"}
    stream_user_info= {"text": f"host information of {name_host}: {message}"}
    SLACK_WEBHOOK_CHAT_ACTION= "https://hooks.slack.com/services/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"
    requests.post(SLACK_WEBHOOK_CHAT_ACTION, headers=headers, json= stream_user_info)