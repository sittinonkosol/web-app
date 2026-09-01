import json
import uuid
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.cache import cache
from scquizz.models import Message, Poll, QuizSession
from core.views import get_mounted_app_url

class AppSpecificAuthAndTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.app_url = get_mounted_app_url('scquizz')
        # Create test superuser in central User database
        self.user = User.objects.create_superuser(
            username='admin',
            password='admin1234',
            email='admin@example.com'
        )
        self.test_session = QuizSession.objects.create(
            title='Test Default Session',
            is_active=True,
            cooldown_seconds=0
        )

    def test_landing_page(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.app_url, response.content.decode('utf-8'))

    def test_app_login_redirects_to_central_login(self):
        login_url = self.app_url.rstrip('/') + '/login'
        response = self.client.get(login_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

    def test_central_login_renders(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        response = self.client.get(f'/login/?next={admin_url}')
        self.assertEqual(response.status_code, 200)
        self.assertIn('เข้าสู่ระบบ', response.content.decode('utf-8'))

    def test_admin_redirects_to_central_login(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        response = self.client.get(admin_url)
        # Should redirect to central login page with next parameter
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
        self.assertIn(admin_url, response.url)

    def test_app_login_success_with_central_db(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        
        # Post credentials to central login endpoint
        login_response = self.client.post('/login/', {
            'username': 'admin',
            'password': 'admin1234',
            'next': admin_url
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.url, admin_url)

        # Now access admin page as authenticated superuser
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

    def test_messages_api_sanitization_and_validation(self):
        messages_url = self.app_url.rstrip('/') + '/api/messages'
        
        # Test empty message rejected
        response = self.client.post(
            messages_url,
            data=json.dumps({"name": "Test", "text": "   "}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        # Test long input clipping & default name
        payload = {
            "name": "   ",
            "text": "A" * 1500
        }
        response = self.client.post(
            messages_url,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "ไม่บอกชื่อ")
        self.assertEqual(len(data["text"]), 1000)

    def test_multi_session_crud_and_isolation(self):
        sessions_url = self.app_url.rstrip('/') + '/api/sessions'
        messages_url = self.app_url.rstrip('/') + '/api/messages'
        polls_url = self.app_url.rstrip('/') + '/api/polls'

        # 1. Create two sessions: Science Day and Freshmen Day
        res = self.client.post(sessions_url, data=json.dumps({
            'title': 'วันวิทยาศาสตร์ 2569',
            'description': 'กิจกรรมวันวิทยาศาสตร์',
            'is_active': True
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        science_session_id = res.json()['id']

        res = self.client.post(sessions_url, data=json.dumps({
            'title': 'วันรับน้อง ICT',
            'description': 'กิจกรรมรับน้อง',
            'is_active': False
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        welcome_session_id = res.json()['id']

        # 2. Post message to Science Day session
        res = self.client.post(messages_url, data=json.dumps({
            'name': 'น้องวิทย์',
            'text': 'คำถามงานวันวิทย์',
            'session_id': science_session_id
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        # 3. Post message to Welcome Day session
        res = self.client.post(messages_url, data=json.dumps({
            'name': 'รุ่นพี่',
            'text': 'ยินดีต้อนรับน้องใหม่',
            'session_id': welcome_session_id
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        # 4. Verify message isolation
        res_science = self.client.get(f'{messages_url}?session_id={science_session_id}')
        self.assertEqual(res_science.status_code, 200)
        science_msgs = res_science.json()
        self.assertEqual(len(science_msgs), 1)
        self.assertEqual(science_msgs[0]['text'], 'คำถามงานวันวิทย์')

        res_welcome = self.client.get(f'{messages_url}?session_id={welcome_session_id}')
        self.assertEqual(res_welcome.status_code, 200)
        welcome_msgs = res_welcome.json()
        self.assertEqual(len(welcome_msgs), 1)
        self.assertEqual(welcome_msgs[0]['text'], 'ยินดีต้อนรับน้องใหม่')

        # 5. Create poll in Science Day and verify poll isolation
        res_poll = self.client.post(polls_url, data=json.dumps({
            'question': 'ชอบฐานการทดลองไหน?',
            'options': ['ฟิสิกส์', 'เคมี', 'คอมพิวเตอร์'],
            'session_id': science_session_id
        }), content_type='application/json')
        self.assertEqual(res_poll.status_code, 200)

        res_science_polls = self.client.get(f'{polls_url}?session_id={science_session_id}')
        self.assertEqual(len(res_science_polls.json()), 1)

        res_welcome_polls = self.client.get(f'{polls_url}?session_id={welcome_session_id}')
        self.assertEqual(len(res_welcome_polls.json()), 0)

        # 6. Test Activate session
        activate_url = f'{sessions_url}/{welcome_session_id}/activate'
        res_act = self.client.post(activate_url)
        self.assertEqual(res_act.status_code, 200)

        # 7. Test Delete session
        del_url = f'{sessions_url}/{science_session_id}'
        res_del = self.client.delete(del_url)
        self.assertEqual(res_del.status_code, 200)

        # 8. Delete all remaining sessions (allow deleting until 0 sessions exist)
        res_del2 = self.client.delete(f'{sessions_url}/{welcome_session_id}')
        self.assertEqual(res_del2.status_code, 200)
        res_del3 = self.client.delete(f'{sessions_url}/{self.test_session.id}')
        self.assertEqual(res_del3.status_code, 200)

        # 9. Verify client index view displays 'ไม่มี Session ในขณะนี้'
        res_index = self.client.get(self.app_url)
        self.assertEqual(res_index.status_code, 200)
        self.assertIn('ไม่มี Session ในขณะนี้', res_index.content.decode('utf-8'))

    def test_edit_session_api(self):
        sessions_url = self.app_url.rstrip('/') + '/api/sessions'
        
        # Create a session
        res = self.client.post(sessions_url, data=json.dumps({
            'title': 'Original Session',
            'description': 'Original Description',
            'is_active': False
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        session_id = res.json()['id']

        # Get session detail
        detail_url = f'{sessions_url}/{session_id}'
        res_get = self.client.get(detail_url)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()['title'], 'Original Session')

        # Edit session using PATCH
        patch_payload = {
            'title': 'Updated Session Title',
            'description': 'Updated Session Description',
            'is_active': True,
            'rate_limit_per_minute': 15,
            'cooldown_seconds': 45
        }
        res_patch = self.client.patch(
            detail_url,
            data=json.dumps(patch_payload),
            content_type='application/json'
        )
        self.assertEqual(res_patch.status_code, 200)
        data = res_patch.json()
        self.assertEqual(data['title'], 'Updated Session Title')
        self.assertEqual(data['description'], 'Updated Session Description')
        self.assertTrue(data['is_active'])
        self.assertEqual(data['rate_limit_per_minute'], 15)
        self.assertEqual(data['cooldown_seconds'], 45)

        # Verify in DB
        sess = QuizSession.objects.get(id=session_id)
        self.assertEqual(sess.title, 'Updated Session Title')
        self.assertEqual(sess.description, 'Updated Session Description')
        self.assertTrue(sess.is_active)
        self.assertEqual(sess.rate_limit_per_minute, 15)
        self.assertEqual(sess.cooldown_seconds, 45)

        # Edit with empty title should return 400
        res_err = self.client.patch(
            detail_url,
            data=json.dumps({'title': '   '}),
            content_type='application/json'
        )
        self.assertEqual(res_err.status_code, 400)

    def test_profanity_filter(self):
        """Test blocking messages containing Thai or English profanity"""
        self.client.login(username='superadmin', password='superpassword123')
        msg_url = f'{self.app_url}api/messages'

        # Test Thai profanity
        res = self.client.post(msg_url, data=json.dumps({
            'name': 'น้องทดสอบ',
            'text': 'ข้อความนี้มี ควย อยู่ข้างใน',
            'session_id': str(self.test_session.id)
        }), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('ไม่เหมาะสม', res.json().get('error', ''))

        # Test English profanity in name
        res2 = self.client.post(msg_url, data=json.dumps({
            'name': 'fuckyou',
            'text': 'สวัสดีครับอาจารย์',
            'session_id': str(self.test_session.id)
        }), content_type='application/json')
        self.assertEqual(res2.status_code, 400)
        self.assertIn('ไม่เหมาะสม', res2.json().get('error', ''))

        # Test clean message passes
        res3 = self.client.post(msg_url, data=json.dumps({
            'name': 'นักศึกษาคนดี',
            'text': 'สอบถามเรื่องเนื้อหาการบรรยายวันนี้ครับ',
            'session_id': str(self.test_session.id)
        }), content_type='application/json')
        self.assertEqual(res3.status_code, 200)

    def test_pagination(self):
        """Test pagination and total count in messages API"""
        self.client.login(username='superadmin', password='superpassword123')
        msg_url = f'{self.app_url}api/messages'

        for i in range(15):
            Message.objects.create(
                id=str(uuid.uuid4()),
                session=self.test_session,
                name=f'ผู้ใช้คนที่ {i+1}',
                text=f'คำถามหมายเลข {i+1}',
                ts=1000 + i,
                answered=0
            )

        # Request first page limit=5 offset=0
        res = self.client.get(f'{msg_url}?session_id={self.test_session.id}&limit=5&offset=0')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data), 5)
        self.assertEqual(res.headers.get('X-Total-Count'), '15')

        # Request second page limit=5 offset=5
        res2 = self.client.get(f'{msg_url}?session_id={self.test_session.id}&limit=5&offset=5')
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(len(data2), 5)

    def test_session_settings_and_rate_limit(self):
        """Test updating rate limit and cooldown settings via PATCH"""
        self.client.login(username='superadmin', password='superpassword123')
        settings_url = f'{self.app_url}api/sessions/{self.test_session.id}/settings'

        res = self.client.patch(settings_url, data=json.dumps({
            'rate_limit_per_minute': 5,
            'cooldown_seconds': 30
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['rate_limit_per_minute'], 5)
        self.assertEqual(res.json()['cooldown_seconds'], 30)

        # Verify DB updated
        self.test_session.refresh_from_db()
        self.assertEqual(self.test_session.rate_limit_per_minute, 5)
        self.assertEqual(self.test_session.cooldown_seconds, 30)

    def test_rate_limit_middleware(self):
        """Test rate limit middleware blocks spamming messages"""
        self.client.login(username='superadmin', password='superpassword123')
        msg_url = f'{self.app_url}api/messages'

        self.test_session.rate_limit_per_minute = 3
        self.test_session.cooldown_seconds = 0
        self.test_session.save()

        # Send 3 messages (should succeed)
        for i in range(3):
            res = self.client.post(msg_url, data=json.dumps({
                'name': f'Tester {i}',
                'text': f'Clean message {i}',
                'session_id': str(self.test_session.id)
            }), content_type='application/json')
            self.assertEqual(res.status_code, 200)

        # 4th message should get 429 Too Many Requests
        res = self.client.post(msg_url, data=json.dumps({
            'name': 'Spammer',
            'text': 'Spam message',
            'session_id': str(self.test_session.id)
        }), content_type='application/json')
        self.assertEqual(res.status_code, 429)
        self.assertIn('ขีดจำกัด', res.json().get('error', ''))

    def test_cooldown_seconds_middleware(self):
        """Test rate limit middleware enforces per-message cooldown_seconds"""
        self.client.login(username='superadmin', password='superpassword123')
        msg_url = f'{self.app_url}api/messages'

        self.test_session.rate_limit_per_minute = 10
        self.test_session.cooldown_seconds = 30
        self.test_session.save()

        # Message 1 (succeeds)
        res1 = self.client.post(msg_url, data=json.dumps({
            'name': 'User 1',
            'text': 'First message',
            'session_id': str(self.test_session.id)
        }), content_type='application/json')
        self.assertEqual(res1.status_code, 200)

        # Message 2 sent immediately (should be blocked by 30s cooldown with 429 status)
        res2 = self.client.post(msg_url, data=json.dumps({
            'name': 'User 1',
            'text': 'Immediate second message',
            'session_id': str(self.test_session.id)
        }), content_type='application/json')
        self.assertEqual(res2.status_code, 429)
        self.assertTrue(res2.json().get('cooldown', False))
        self.assertIn('รอ', res2.json().get('error', ''))



