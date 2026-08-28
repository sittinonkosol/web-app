from django.apps import apps
from django.shortcuts import render, redirect
from django.urls import get_resolver, URLResolver
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages

def get_mounted_app_url(app_name):
    """
    Dynamically scan the root URL configuration to find where the app's urls.py is included.
    """
    resolver = get_resolver()
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            urlconf = pattern.urlconf_module
            module_name = getattr(urlconf, '__name__', str(urlconf))
            # Match app_name in included module or namespace or app_name
            if app_name in module_name or pattern.namespace == app_name or pattern.app_name == app_name:
                prefix = str(pattern.pattern).lstrip('^').rstrip('$')
                if not prefix.startswith('/'):
                    prefix = '/' + prefix
                if not prefix.endswith('/'):
                    prefix = prefix + '/'
                return prefix
    return None

def landing_page(request):
    user_apps = []
    
    exclude_apps = [
        'admin', 'auth', 'contenttypes', 'sessions', 'messages', 'staticfiles',
        'daphne', 'channels', 'core'
    ]
    
    for app_config in apps.get_app_configs():
        if app_config.name not in exclude_apps:
            # Dynamically resolve URL based on current routing in core/urls.py
            dynamic_url = get_mounted_app_url(app_config.name)
            
            # If the app is not currently routed in core/urls.py, skip it automatically
            if not dynamic_url:
                continue
                
            name = getattr(app_config, 'verbose_name', app_config.name.replace('_', ' ').title())
            icon = getattr(app_config, 'landing_icon', '🚀')
            description = getattr(app_config, 'landing_description', f'Explore the {name} application.')
            
            user_apps.append({
                'name': name,
                'url': dynamic_url,
                'icon': icon,
                'description': description,
            })
            
    return render(request, 'core/landing.html', {
        'apps': user_apps,
        'user': request.user
    })

def login_view(request):
    next_url = request.GET.get('next') or request.POST.get('next') or '/'
    
    if request.user.is_authenticated:
        return redirect(next_url)
        
    error_message = None
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect(next_url)
        else:
            error_message = 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
            
    return render(request, 'core/login.html', {
        'next': next_url,
        'error_message': error_message
    })

def logout_view(request):
    next_url = request.GET.get('next') or request.POST.get('next')
    if not next_url:
        referer = request.META.get('HTTP_REFERER')
        if referer:
            clean_ref = referer.split('?')[0].rstrip('/')
            for suffix in ['/admin.html', '/admin', '/index.html']:
                if clean_ref.endswith(suffix):
                    clean_ref = clean_ref[:-len(suffix)]
                    break
            next_url = clean_ref + '/'
        else:
            next_url = '/'
            
    logout(request)
    return redirect(next_url)
