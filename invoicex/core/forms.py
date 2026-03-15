from django import forms
from .models import CompanyProfile
from django.contrib.auth.models import User

class CompanyProfileForm(forms.ModelForm):
    class Meta:
        model = CompanyProfile
        exclude = ['user']
        labels = {
            'company_name':'Your company name:',
            'address': 'Company address (Shown in invoice)',
            'phone': 'Phone number (Shown in invoice)',
            'email': 'Email address (Shown in invoice)',
        }
        widgets = {
            'company_name': forms.TextInput(attrs={'class':'form-control mt-2 mb-3'}),
            'address': forms.TextInput(attrs={'class':'form-control mt-2 mb-3'}),
            'phone': forms.TextInput(attrs={'class':'form-control mt-2 mb-3'}),
            'email': forms.EmailInput(attrs={'class':'form-control mt-2'})
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