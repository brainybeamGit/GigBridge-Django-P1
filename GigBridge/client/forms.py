from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Project, Proposal, Review, ContactMessage, Message, Category


class RegistrationForm(UserCreationForm):
    role = forms.ChoiceField(
        choices=[('freelancer', 'Freelancer'), ('client', 'Client / Employer')],
        required=False,
        initial='freelancer'
    )
    first_name = forms.CharField(
        max_length=50,
        required=True,
        error_messages={'required': 'Please enter your first name.'},
        widget=forms.TextInput(attrs={'class': 'auth-luxe-input', 'placeholder': 'First name'})
    )
    last_name = forms.CharField(
        max_length=50,
        required=True,
        error_messages={'required': 'Please enter your last name.'},
        widget=forms.TextInput(attrs={'class': 'auth-luxe-input', 'placeholder': 'Last name'})
    )
    email = forms.EmailField(
        required=True,
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address (e.g. name@example.com).'
        },
        widget=forms.EmailInput(attrs={'class': 'auth-luxe-input', 'placeholder': 'name@example.com'})
    )
    phone = forms.CharField(
        max_length=20,
        required=True,
        error_messages={'required': 'Please enter your phone number.'},
        widget=forms.TextInput(attrs={'class': 'auth-luxe-input', 'placeholder': 'e.g. +1 (555) 000-0000'})
    )
    company_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-luxe-input', 'placeholder': 'e.g. Apex Technologies Inc.'})
    )
    title = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.Select(attrs={'class': 'auth-luxe-input'})
    )
    skills = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.TextInput(attrs={'class': 'auth-luxe-input', 'placeholder': 'e.g. Python, React, Django, Machine Learning'})
    )
    terms = forms.BooleanField(
        required=True,
        error_messages={'required': 'You must accept the Terms of Service to continue.'},
        widget=forms.CheckboxInput(attrs={'class': 'auth-luxe-checkbox'})
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        category_choices = [('', 'Select Category / Specialization')] + [
            (cat.name, cat.name) for cat in Category.objects.all().order_by('name')
        ]
        self.fields['title'].widget = forms.Select(choices=category_choices, attrs={'class': 'auth-luxe-input'})
        self.fields['username'].error_messages = {
            'required': 'Please choose a username.',
            'unique': 'This username is already taken. Please choose another.',
            'invalid': 'Enter a valid username with letters, digits, and @/./+/-/_ only.'
        }
        self.fields['username'].widget.attrs.update({'class': 'auth-luxe-input', 'placeholder': 'Choose username'})
        self.fields['password1'].error_messages = {
            'required': 'Please create a password.'
        }
        self.fields['password1'].widget.attrs.update({'class': 'auth-luxe-input', 'placeholder': 'Create strong password', 'id': 'id_password1'})
        self.fields['password2'].error_messages = {
            'required': 'Please confirm your password.'
        }
        self.fields['password2'].widget.attrs.update({'class': 'auth-luxe-input', 'placeholder': 'Confirm password', 'id': 'id_password2'})

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email address already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            self.add_error('password2', 'The passwords you entered do not match.')
        return cleaned_data


class ProjectForm(forms.ModelForm):
    deadline = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    class Meta:
        model = Project
        fields = [
            'title', 'category', 'description', 'required_skills',
            'budget_type', 'budget_min', 'budget_max',
            'deadline', 'deliverables', 'attachment', 'status'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Build a Django REST API with authentication'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Describe the project in detail...'}),
            'required_skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Python, Django, PostgreSQL, REST API'}),
            'budget_type': forms.Select(attrs={'class': 'form-select'}),
            'budget_min': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '500', 'min': 0}),
            'budget_max': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '2000', 'min': 0}),
            'deliverables': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'List key deliverables and expectations...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        budget_min = cleaned_data.get('budget_min')
        budget_max = cleaned_data.get('budget_max')
        if budget_min is not None and budget_max is not None:
            if budget_max < budget_min:
                raise forms.ValidationError("Maximum budget cannot be less than minimum budget.")
        return cleaned_data


class ProposalForm(forms.ModelForm):
    class Meta:
        model = Proposal
        fields = ['bid_amount', 'delivery_days', 'cover_letter', 'attachment']
        widgets = {
            'bid_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '500.00', 'min': 1}),
            'delivery_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '14', 'min': 1}),
            'cover_letter': forms.Textarea(attrs={'class': 'form-control', 'rows': 7, 'placeholder': 'Explain why you are the best choice for this project...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }


class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Share your experience working with this freelancer...'}),
        }


class ContactForm(forms.ModelForm):
    topic = forms.CharField(max_length=100, required=False, widget=forms.HiddenInput(attrs={'id': 'contact_topic'}))

    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'subject', 'topic', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full name', 'id': 'contact_name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com', 'id': 'contact_email'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'How can we help you?', 'id': 'contact_subject'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Describe your question or issue in detail...', 'id': 'contact_message', 'maxlength': '1000'}),
        }


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))

    class Meta:
        model = UserProfile
        fields = ['phone', 'company_name', 'title', 'bio', 'avatar', 'location', 'skills', 'hourly_rate', 'website']
        widgets = {
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+91 9876543210'}),
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your company or organisation'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Full-Stack Developer or Product Manager'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell freelancers a bit about yourself and your projects...'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City, Country or Remote'}),
            'skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Python, Django, React'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': 0}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://yourwebsite.com'}),
        }


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'attachment']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Type your message...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
        }
