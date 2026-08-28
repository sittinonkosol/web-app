import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from map_locator.models import LocationMarker
from core.views import get_mounted_app_url

class MapLocatorAppTests(TestCase):
    databases = {'default', 'map_locator_db'}

    def setUp(self):
        self.client = Client()
        self.app_url = get_mounted_app_url('map_locator')
        # Create test admin user in central User database
        self.user = User.objects.create_user(
            username='admin',
            password='admin1234',
            email='admin@example.com'
        )

    def test_dynamic_landing_page_includes_map_locator(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('Map Locator', content)
        self.assertIn(self.app_url, content)

    def test_map_locator_index_public_access(self):
        response = self.client.get(self.app_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Map Locator', response.content.decode('utf-8'))
        self.assertIn('leaflet', response.content.decode('utf-8').lower())

    def test_admin_requires_login(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        login_url = self.app_url.rstrip('/') + '/login'
        response = self.client.get(admin_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(login_url, response.url)

    def test_admin_login_and_access(self):
        admin_url = self.app_url.rstrip('/') + '/admin'
        login_url = self.app_url.rstrip('/') + '/login'

        # Post login to map_locator's login endpoint
        login_response = self.client.post(login_url, {
            'username': 'admin',
            'password': 'admin1234',
            'next': admin_url
        })
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(login_response.url, admin_url)

        # Authenticated access
        admin_response = self.client.get(admin_url)
        self.assertEqual(admin_response.status_code, 200)
        self.assertIn('แดชบอร์ดจัดการ Map Locator', admin_response.content.decode('utf-8'))

    def test_location_markers_crud_api(self):
        api_url = self.app_url.rstrip('/') + '/api/locations'
        
        # 1. Create Location Marker via POST
        payload = {
            "title": "มหาวิทยาลัยอุบลราชธานี",
            "category": "จุดบริการ",
            "description": "ประตูทางเข้าหลัก",
            "latitude": 15.1189,
            "longitude": 104.9023,
            "address": "ตำบลเมืองศรีไค อำเภอวารินชำราบ อุบลราชธานี",
            "created_by": "ทดสอบ"
        }
        res_post = self.client.post(api_url, data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res_post.status_code, 200)
        data = res_post.json()
        self.assertTrue(data.get("success"))
        marker_id = data.get("id")

        # Verify saved in map_locator_db database
        marker = LocationMarker.objects.using('map_locator_db').filter(id=marker_id).first()
        self.assertIsNotNone(marker)
        self.assertEqual(marker.title, "มหาวิทยาลัยอุบลราชธานี")

        # 2. Retrieve Location Markers via GET
        res_get = self.client.get(api_url)
        self.assertEqual(res_get.status_code, 200)
        markers_list = res_get.json()
        self.assertTrue(len(markers_list) >= 1)
        self.assertEqual(markers_list[0]["title"], "มหาวิทยาลัยอุบลราชธานี")

        # 3. Delete Location Marker via DELETE
        res_del = self.client.delete(f'{api_url}/{marker_id}')
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json().get("success"))

        # Verify deleted
        self.assertIsNone(LocationMarker.objects.using('map_locator_db').filter(id=marker_id).first())
