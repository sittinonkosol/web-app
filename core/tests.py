import json
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from core.models import AppSetting, UserAppPermission, GroupAppPermission, UserLoginLog
from core.permissions import get_user_app_role, has_app_permission

class CentralAdminAndPermissionTests(TestCase):
    def setUp(self):
        self.client = Client()
        
        # 1. Create Superuser (Admin)
        self.admin = User.objects.create_superuser(
            username='admin',
            password='adminpassword123',
            email='admin@example.com'
        )
        
        # 2. Create Staff User
        self.staff_user = User.objects.create_user(
            username='staffuser',
            password='staffpassword123',
            email='staff@example.com',
            is_staff=True
        )

        # 3. Create Normal User
        self.normal_user = User.objects.create_user(
            username='normaluser',
            password='normalpassword123',
            email='normal@example.com'
        )

        # Ensure default setting for scquizz
        self.scquizz_setting, _ = AppSetting.objects.get_or_create(
            app_name='scquizz',
            defaults={
                'display_name': 'SC Quiz',
                'is_public': True,
                'min_role_required': 'viewer'
            }
        )

    def test_admin_dashboard_access_control(self):
        # Unauthenticated -> redirect to login
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

        # Normal user -> 403 Forbidden
        self.client.login(username='normaluser', password='normalpassword123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 403)

        # Staff user -> 200 OK
        self.client.login(username='staffuser', password='staffpassword123')
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('Central Management', response.content.decode('utf-8'))

    def test_user_crud_api(self):
        self.client.login(username='admin', password='adminpassword123')

        # 1. Create User via API
        payload = {
            'username': 'john_doe',
            'password': 'password123',
            'email': 'john@example.com',
            'first_name': 'John',
            'last_name': 'Doe',
            'is_active': True,
            'is_staff': False,
            'app_permissions': {'scquizz': 'moderator'}
        }
        res = self.client.post(
            '/api/admin/users',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        user_id = res.json()['id']

        # Verify in DB
        created_user = User.objects.get(id=user_id)
        self.assertEqual(created_user.username, 'john_doe')
        self.assertEqual(get_user_app_role(created_user, 'scquizz'), 'moderator')

        # 2. Get Users List
        res = self.client.get('/api/admin/users')
        self.assertEqual(res.status_code, 200)
        users = res.json()['users']
        self.assertTrue(any(u['username'] == 'john_doe' for u in users))

        # 3. Update User
        update_payload = {
            'first_name': 'Johnny',
            'is_staff': True,
            'app_permissions': {'scquizz': 'admin'}
        }
        res = self.client.put(
            f'/api/admin/users/{user_id}',
            data=json.dumps(update_payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        created_user.refresh_from_db()
        self.assertEqual(created_user.first_name, 'Johnny')
        self.assertTrue(created_user.is_staff)
        self.assertEqual(get_user_app_role(created_user, 'scquizz'), 'admin')

        # 4. Self Delete Prevention
        res = self.client.delete(f'/api/admin/users/{self.admin.id}')
        self.assertEqual(res.status_code, 400)

        # 5. Delete User
        res = self.client.delete(f'/api/admin/users/{user_id}')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(User.objects.filter(id=user_id).exists())

    def test_group_crud_api(self):
        self.client.login(username='admin', password='adminpassword123')

        # 1. Create Group
        payload = {
            'name': 'Moderators Team',
            'members': [self.normal_user.id],
            'app_permissions': {'scquizz': 'moderator'}
        }
        res = self.client.post(
            '/api/admin/groups',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        group_id = res.json()['id']

        # Normal user should now inherit moderator role from group
        self.assertEqual(get_user_app_role(self.normal_user, 'scquizz'), 'moderator')

        # 2. Get Groups List
        res = self.client.get('/api/admin/groups')
        self.assertEqual(res.status_code, 200)
        groups = res.json()['groups']
        self.assertTrue(any(g['name'] == 'Moderators Team' for g in groups))

        # 3. Update Group
        update_payload = {
            'name': 'Senior Moderators',
            'app_permissions': {'scquizz': 'admin'}
        }
        res = self.client.put(
            f'/api/admin/groups/{group_id}',
            data=json.dumps(update_payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(get_user_app_role(self.normal_user, 'scquizz'), 'admin')

        # 4. Delete Group
        res = self.client.delete(f'/api/admin/groups/{group_id}')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Group.objects.filter(id=group_id).exists())

    def test_app_settings_and_visibility(self):
        self.client.login(username='admin', password='adminpassword123')

        # 1. Get App Settings
        res = self.client.get('/api/admin/app-settings')
        self.assertEqual(res.status_code, 200)
        apps = res.json()['apps']
        self.assertTrue(any(a['app_name'] == 'scquizz' for a in apps))

        # 2. Set App to Login Required (is_public = False)
        res = self.client.put(
            '/api/admin/app-settings/scquizz',
            data=json.dumps({'is_public': False, 'min_role_required': 'viewer'}),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)

        # Anonymous request to scquizz client should now redirect to login
        anon_client = Client()
        response = anon_client.get('/ict/scquizz/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)

        # Logged in user can access
        self.client.login(username='normaluser', password='normalpassword123')
        response = self.client.get('/ict/scquizz/')
        self.assertEqual(response.status_code, 200)

        # 3. User with 'none' role gets 403
        UserAppPermission.objects.create(
            user=self.normal_user,
            app_name='scquizz',
            role='none'
        )
        response = self.client.get('/ict/scquizz/')
        self.assertEqual(response.status_code, 403)

    def test_login_logs_tracking_and_apis(self):
        # 1. Trigger Successful Login via central login
        self.client.post('/login/', {
            'username': 'normaluser',
            'password': 'normalpassword123'
        })
        
        # Verify success log created
        success_log = UserLoginLog.objects.filter(username_attempted='normaluser', status='success').first()
        self.assertIsNotNone(success_log)
        self.assertEqual(success_log.user, self.normal_user)

        # 2. Trigger Failed Login via wrong password (after logout)
        self.client.logout()
        self.client.post('/login/', {
            'username': 'normaluser',
            'password': 'wrongpassword'
        })

        # Verify failed log created
        failed_log = UserLoginLog.objects.filter(username_attempted='normaluser', status='failed').first()
        self.assertIsNotNone(failed_log)

        # 3. Admin can query login logs API
        self.client.login(username='admin', password='adminpassword123')
        res = self.client.get('/api/admin/login-logs')
        self.assertEqual(res.status_code, 200)
        logs = res.json()['logs']
        self.assertTrue(len(logs) >= 2)

        # Filter by status
        res = self.client.get('/api/admin/login-logs?status=failed')
        self.assertEqual(res.status_code, 200)
        failed_logs = res.json()['logs']
        self.assertTrue(all(l['status'] == 'failed' for l in failed_logs))

        # Query specific user logs API
        res = self.client.get(f'/api/admin/users/{self.normal_user.id}/login-logs')
        self.assertEqual(res.status_code, 200)
        user_logs = res.json()['logs']
        self.assertTrue(len(user_logs) >= 1)
        self.assertEqual(res.json()['username'], 'normaluser')

