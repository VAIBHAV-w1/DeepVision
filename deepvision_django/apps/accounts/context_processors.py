"""
Context processors for accounts app.
Makes current_user available across all templates.
"""

def auth_user(request):
    user = getattr(request, 'user', None)
    return {
        'current_user': user if (user and user.is_authenticated) else None,
    }
