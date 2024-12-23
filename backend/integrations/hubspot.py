# hubspot.py
import json
import secrets
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
import httpx
import asyncio
import base64
import hashlib
import logging
import requests
from integrations.integration_item import IntegrationItem
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = 'XXX'
CLIENT_SECRET = 'XXX'
REDIRECT_URI = 'http://localhost:8000/integrations/hubspot/oauth2callback'
AUTHORIZATION_URL = 'https://app.hubspot.com/oauth/authorize'
TOKEN_URL = 'https://api.hubapi.com/oauth/v1/token'
SCOPES = 'oauth crm.objects.companies.read crm.objects.contacts.read crm.objects.deals.read'
encoded_client_id_secret = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def authorize_hubspot(user_id, org_id):
    """Generate OAuth2 authorization URL with state and code challenge"""
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_data).encode('utf-8')).decode('utf-8')
    scope_string = "%20".join(SCOPES.split())
    code_verifier = secrets.token_urlsafe(32)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).decode('utf-8').replace('=', '')
    auth_url = f'{AUTHORIZATION_URL}?client_id={CLIENT_ID}&scope={scope_string}&redirect_uri={REDIRECT_URI}&state={encoded_state}&code_challenge={code_challenge}&code_challenge_method=S256'
    
    # Store state and code_verifier in Redis
    asyncio.gather(
        add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', json.dumps(state_data), expire=600),
        add_key_value_redis(f'hubspot_verifier:{org_id}:{user_id}', code_verifier, expire=600),
    )
    return auth_url

async def oauth2callback_hubspot(request: Request):
    """Handle HubSpot OAuth2 callback to exchange code for access token"""
    if error := request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error_description'))

    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(base64.urlsafe_b64decode(encoded_state).decode('utf-8'))
    original_state, user_id, org_id = state_data.get('state'), state_data.get('user_id'), state_data.get('org_id')

    # Check state consistency
    saved_state = await get_value_redis(f'hubspot_state:{org_id}:{user_id}')
    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    # Retrieve the code_verifier from Redis
    code_verifier = await get_value_redis(f'hubspot_verifier:{org_id}:{user_id}')

    if not code_verifier:
        raise HTTPException(status_code=400, detail='Code verifier not found')

    async with httpx.AsyncClient() as client:
        response = await client.post(
            TOKEN_URL,
            data={
                'grant_type': 'authorization_code',
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'redirect_uri': REDIRECT_URI,
                'code': code,
                'code_verifier': code_verifier  # Use code_verifier here for PKCE
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if response.status_code != 200:
            logger.error(f"Failed to fetch token: {response.text}")
            raise HTTPException(status_code=500, detail="Failed to exchange code for access token")

    # Store access token in Redis and clean up
    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(response.json()), expire=600)
    await asyncio.gather(
        delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
        delete_key_redis(f'hubspot_verifier:{org_id}:{user_id}')
    )

    close_window_script = "<html><script>window.close();</script></html>"
    return HTMLResponse(content=close_window_script)


async def get_hubspot_credentials(user_id, org_id):
    print(user_id, org_id)
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')

    return credentials

def create_integration_item_metadata_object(response_json: dict, item_type: str) -> IntegrationItem:
    
    creation_time = datetime.strptime(response_json.get('createdAt'), '%Y-%m-%dT%H:%M:%S.%fZ')
    last_modified_time = datetime.strptime(response_json.get('updatedAt'), '%Y-%m-%dT%H:%M:%S.%fZ')

    integration_item_metadata = IntegrationItem(
        id=response_json.get('id', None),
        name=response_json.get('properties', {}).get('name', ''),
        type=item_type,
        creation_time=creation_time,
        last_modified_time=last_modified_time,
        properties=response_json.get('properties', {})
    )
    return integration_item_metadata


async def get_items_hubspot(credentials: str) -> list[IntegrationItem]:
    credentials = json.loads(credentials)
    list_of_responses = []
    list_of_integration_item_metadata = []
    url = 'https://api.hubapi.com/crm/v3/objects/contacts'
    
    await fetch_items(credentials.get('access_token'), url, list_of_responses)
    
    for response in list_of_responses:
        list_of_integration_item_metadata.append(
            create_integration_item_metadata_object(response, 'hubspot_object_contacts')
        )
        print(list_of_integration_item_metadata)
    return list_of_integration_item_metadata

async def fetch_items(
    access_token: str, url: str, aggregated_response: list) -> None:
    """Fetching the list of items"""
    headers = {'Authorization': f'Bearer {access_token}'}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # This will raise an HTTPError for bad responses

        if response.status_code == 200:
            results = response.json().get('results', [])
            print(f"API response for {url}: {response.json()}")

            for item in results:
                aggregated_response.append(item)
        else:
            print(f"Failed to fetch data from {url} - Status Code: {response.status_code}")
    except requests.exceptions.HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')
        print(f'Response content: {response.content}')
        raise HTTPException(status_code=response.status_code, detail=f'HTTP error: {http_err}')
    except Exception as err:
        print(f'Other error occurred: {err}')
        raise HTTPException(status_code=500, detail=f'Other error: {err}')

