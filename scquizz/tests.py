import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from scquizz.models import Message, Poll
from core.views import get_mounted_app_url

class AppSpecificAuthAndTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.app_url = get_mounted_app_url('scquizz')
        # Create test admin user in central User database
        self.user = User.objects.create_user(
            username='admin',
            password='admin1234',
            email='admin@example.com'
        )

    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.app_url, response.content.decode('utf-8'))

    def test_app_login_page_renders(self):
        login_url = self.app_url.rstrip('/') + '/login'
        response = self.client.get(login_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('เข้าสู่ระบบแอดมิน', response.content.decode('utf-8'))
        self.assertIn('SC Quiz', response.content.decode('utf-8'))

    def test_admin_redirects_to_app_login(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        login_url = self.app_url.rstrip('/') + '/login'
        response = self.client.get(admin_url)
        # Should redirect to app's own login page with next parameter
        self.assertEqual(response.status_code, 302)
        self.assertIn(login_url, response.url)
        self.assertIn(admin_url, response.url)

    def test_app_login_success_with_central_db(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        login_url = self.app_url.rstrip('/') + '/login'
        
        # Post credentials to app's login endpoint
        login_response = self.client.post(login_url, {
            'username': 'admin',
            'password': 'admin1234',
            'next': admin_url
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.url, admin_url)

        # Now access admin page as authenticated user
        admin_response = self.client.get(admin_url)
        self.assertEqual(admin_response.status_code, 200)
        self.assertIn('admin', admin_response.content.decode('utf-8'))

    def test_logout_redirects_to_app_index(self):
        self.client.login(username='admin', password='admin1234')
        # Test logout from admin with next param to app index
        response = self.client.get(f'/logout/?next={self.app_url}')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self.app_url)

    def test_scquizz_index_public_access(self):
        # Client public page should NOT require login
        response = self.client.get(self.app_url)
        self.assertEqual(response.status_code, 200)

    def test_messages_api(self):
        messages_url = self.app_url.rstrip('/') + '/api/messages'
        payload = {"name": "Test User", "text": "Hello Quiz"}
        response = self.client.post(
            messages_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "Test User")
        msg_id = data["id"]

        # Get messages
        response = self.client.get(messages_url)
        self.assertEqual(response.status_code, 200)
        msgs = response.json()
        self.assertEqual(len(msgs), 1)

        # Answer message
        response = self.client.post(f'{messages_url}/{msg_id}/answer')
        self.assertEqual(response.status_code, 200)

        # Delete message
        response = self.client.delete(f'{messages_url}/{msg_id}')
        self.assertEqual(response.status_code, 200)

    def test_polls_api(self):
        polls_url = self.app_url.rstrip('/') + '/api/polls'
        payload = {
            "question": "What is your favorite language?",
            "options": ["Python", "JS"],
            "type": "standard"
        }
        response = self.client.post(
            polls_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        poll_id = response.json()["id"]

        # Activate poll
        response = self.client.post(f'{polls_url}/{poll_id}/activate')
        self.assertEqual(response.status_code, 200)

        # Get active poll
        response = self.client.get(f'{polls_url}/active')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], poll_id)

        # Vote
        vote_payload = {"option_index": 0}
        response = self.client.post(
            f'{polls_url}/{poll_id}/vote',
            data=json.dumps(vote_payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

    def test_ws_probe(self):
        ws_url = self.app_url.rstrip('/') + '/api/messages/ws'
        response = self.client.get(ws_url)
        self.assertEqual(response.status_code, 426)

    def test_sse_poll_events_endpoint(self):
        sse_url = self.app_url.rstrip('/') + '/api/polls/events'
        response = self.client.get(sse_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/event-stream')
