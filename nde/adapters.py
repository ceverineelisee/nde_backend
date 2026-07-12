from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not user.name:
            first = data.get('first_name', '')
            last = data.get('last_name', '')
            full = f"{first} {last}".strip()
            if not full:
                full = data.get('name', '') or data.get('email', '').split('@')[0]
            user.name = full
        return user
