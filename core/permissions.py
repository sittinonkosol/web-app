from functools import wraps
from django.shortcuts import redirect, render
from django.http import JsonResponse
from django.contrib.auth.models import Group
from .models import AppSetting, UserAppPermission, GroupAppPermission

ROLE_LEVELS = {
    'none': 0,
    'viewer': 1,
    'moderator': 2,
    'admin': 3,
}

def get_app_setting(app_name):
    """Retrieve or create default AppSetting for an app."""
    setting, _ = AppSetting.objects.get_or_create(
        app_name=app_name,
        defaults={
            'display_name': app_name.replace('_', ' ').title(),
            'is_public': True,
            'min_role_required': 'viewer'
        }
    )
    return setting

def is_app_public(app_name):
    """Check if app is configured to allow public unauthenticated access."""
    setting = get_app_setting(app_name)
    return setting.is_public

def get_user_app_role(user, app_name):
    """
    Compute effective role for a user on a given app.
    Takes into account Superuser status, direct UserAppPermission, and GroupAppPermissions.
    """
    if not user or not user.is_authenticated:
        return 'viewer' if is_app_public(app_name) else 'none'

    if user.is_superuser:
        return 'admin'

    # 1. Direct user permission
    user_perm = UserAppPermission.objects.filter(user=user, app_name=app_name).first()
    max_level = 0
    effective_role = 'viewer'  # Default for logged-in users

    if user_perm:
        effective_role = user_perm.role
        max_level = ROLE_LEVELS.get(user_perm.role, 0)

    # 2. Group permissions
    user_groups = user.groups.all()
    if user_groups.exists():
        group_roles = GroupAppPermission.objects.filter(group__in=user_groups, app_name=app_name).values_list('role', flat=True)
        for g_role in group_roles:
            g_level = ROLE_LEVELS.get(g_role, 0)
            if g_level > max_level:
                max_level = g_level
                effective_role = g_role

    return effective_role

def has_app_permission(user, app_name, min_role='viewer'):
    """
    Check if user has at least `min_role` on `app_name`.
    """
    role = get_user_app_role(user, app_name)
    user_level = ROLE_LEVELS.get(role, 0)
    required_level = ROLE_LEVELS.get(min_role, 1)
    return user_level >= required_level

def require_app_access(app_name, min_role='viewer'):
    """
    Decorator for views to enforce app public status, login requirements, and permission levels.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            setting = get_app_setting(app_name)
            
            # 1. If app is NOT public, require authentication
            if not setting.is_public and not request.user.is_authenticated:
                return redirect(f'/login/?next={request.path}')

            # 2. Check permission level
            effective_role = get_user_app_role(request.user, app_name)
            user_level = ROLE_LEVELS.get(effective_role, 0)
            required_level = ROLE_LEVELS.get(min_role, 1)

            if user_level < required_level:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({'error': 'Permission denied. Insufficient privileges.'}, status=403)
                
                return render(request, 'core/permission_denied.html', {
                    'app_name': app_name,
                    'display_name': setting.display_name or app_name,
                    'required_role': min_role,
                    'user_role': effective_role,
                    'user': request.user
                }, status=403)

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
