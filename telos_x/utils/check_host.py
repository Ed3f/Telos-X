import requests
from time import sleep
import re

def check_host(message):
    headers= {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Firefox/102.0',
        'Accept': 'application/json',
    }
    find= re.compile('https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[i][t]')
    host_found = find.search(message)
    if host_found: 
        params= {
                'host': f'{host_found.group()}'
                }
        link= f'https://check-host.net/check-http'
        data = requests.get(link,params=params, headers=headers).json()
        r= data['request_id']
        link2:str='https://check-host.net/check-result/'+str(r)
        sleep(10)
        response2= requests.get(link2, headers=headers).json()
        return (response2)
