import requests


BASE_URL = 'https://gameinfo-ams.albiononline.com/api/gameinfo'
SEARCH_ENDPOINT = '/search?q='


def _get_search_url(query):
    return BASE_URL + SEARCH_ENDPOINT + query


def get_player_by_nickname(nickname):
    url = _get_search_url(nickname)
    response = requests.get(url).json()
    players = response.get('players', [])
    if not players:
        return None
    return players[0]
