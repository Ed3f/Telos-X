from telethon import functions, types
from typing import Dict, List, cast
#from . import Notifier

async def translate( message, client):
    if message:
        result = await client(functions.messages.TranslateTextRequest(
            to_lang= 'en',
            peer= None,
            id= None,
            text= [types.TextWithEntities(
            text= message,
                entities= [types.MessageEntityUnknown(
                    offset= 42,
                    length= 42
                )]
            )]))  
    for item in result.result:
        traduzione = item.text
    print(traduzione)
    return(traduzione)


