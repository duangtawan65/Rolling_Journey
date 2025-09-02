import requests

class GameAPIClient:
    def __init__(self, base_url="http://127.0.0.1:8000/api/"):
        self.base_url = base_url
    
    def send_action(self, action):
        # HTTP call to Django
        pass