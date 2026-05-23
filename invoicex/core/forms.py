from django import forms
from .models import CompanyProfile
from django.contrib.auth.models import User

class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ['company_name', 'address', 'phone', 'email', 'industry', 'description']
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            # Add Bootstrap classes to the new fields
            'industry': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., Pharmacy'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe the types of products you sell...'}),
        }
class AccountForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'password', 'email']
        
        labels = {
            'username': 'Profile username (used for login)',
            'password': 'Profile password (used for login)',
            'email': 'Profile email address (used for login)',
        }
        
        widgets = {
            'username': forms.TextInput(attrs={'class':'form-control mt-2 mb-3'}),
            'password': forms.PasswordInput(attrs={'class': 'form-control mt-2 mb-3'}),
            'email': forms.EmailInput(attrs={'class': 'form-control mt-2 mb-3'})
        }