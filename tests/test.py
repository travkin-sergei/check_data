import requests
import json
import time


url = 'http://*******************/sso/oauth2/access_token'

url = "http://127.0.0.1:8000/"
payload = {'client_id': 'rec_elk_m2m', 'client_secret': 'password', 'realm': '/customer',
           'grant_type': 'urn:roox:params:oauth:grant-type:m2m', 'service': 'dispatcher'}
headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}

res = requests.post(url, data=payload, headers=headers)
execution = json.loads(res.content)['execution']

payload = {'client_id': 'rec_elk_m2m',
           'client_secret': 'password',
           'realm': '/customer',
           'grant_type': 'urn:roox:params:oauth:grant-type:m2m',
           'service': 'dispatcher',
           '_eventId': 'next',
           # 'username': 'demo_exporter',
           # 'username': 'demo_executor',
           # 'username': 'bpmn_admin',
           'username': 'mdm_admin',
           'password': 'password',
           'execution': execution

           }

headers = {'Accept': 'application/json', 'Content-Type': 'application/x-www-form-urlencoded'}
res = requests.post(url, data=payload, headers=headers)
token_ = 'Bearer sso_1.0_' + json.loads(res.content)['access_token']
print(token_)
headers = {'Authorization': token_}

arm_url = 'http://*******************/api/v1/org'
result = requests.get(arm_url, headers=headers)
print('result:' + result.content.decode('UTF-8'))