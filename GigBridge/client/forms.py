import phonenumbers
from decimal import Decimal
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import UserProfile, Project, Proposal, Review, ContactMessage, Message, Category
from .currency import get_usd_inr_rate, convert_inr_to_usd, convert_usd_to_inr, resolve_currency_for_user_or_request
from .helpers import get_user_specialized_category


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
    # Visible phone input (attached to intl-tel-input widget)
    phone = forms.CharField(
        max_length=30,
        required=True,
        error_messages={'required': 'Please enter your phone number.'},
        widget=forms.TextInput(attrs={
            'class': 'auth-luxe-input',
            'id': 'id_phone',
            'placeholder': 'e.g. 98765 43210',
            'autocomplete': 'tel'
        })
    )
    # Hidden fields populated automatically by intl-tel-input
    country = forms.CharField(
        required=False,
        initial='IN',
        widget=forms.HiddenInput(attrs={'id': 'id_country'})
    )
    phone_country_code = forms.CharField(
        required=False,
        initial='+91',
        widget=forms.HiddenInput(attrs={'id': 'id_phone_country_code'})
    )
    phone_number = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_phone_number'})
    )
    phone_e164 = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_phone_e164'})
    )
    country_fallback = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_country_fallback'})
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

        # Server-side International Phone Number Validation via phonenumbers
        phone_raw = (cleaned_data.get('phone') or '').strip()
        country_code = (self.data.get('country') or cleaned_data.get('country') or self.data.get('country_fallback') or 'IN').strip().upper()
        phone_e164_raw = (self.data.get('phone_e164') or '').strip()

        if not phone_raw and not phone_e164_raw:
            self.add_error('phone', 'Please enter your phone number.')
        else:
            parsed = None
            try:
                if phone_raw:
                    parsed = phonenumbers.parse(phone_raw, country_code)
            except phonenumbers.NumberParseException:
                parsed = None

            if (not parsed or not phonenumbers.is_valid_number(parsed)) and phone_e164_raw:
                try:
                    parsed_e164 = phonenumbers.parse(phone_e164_raw, country_code)
                    if phonenumbers.is_valid_number(parsed_e164):
                        parsed = parsed_e164
                except phonenumbers.NumberParseException:
                    pass

            if not parsed or not phonenumbers.is_valid_number(parsed):
                COUNTRY_NAMES = {
                    'IN': 'India', 'US': 'United States', 'GB': 'United Kingdom',
                    'AE': 'United Arab Emirates', 'CA': 'Canada', 'AU': 'Australia',
                    'DE': 'Germany', 'FR': 'France', 'SG': 'Singapore'
                }
                region = (parsed and phonenumbers.region_code_for_number(parsed)) or country_code
                country_name = COUNTRY_NAMES.get(region, region)
                self.add_error('phone', f"Enter a valid phone number for {country_name}.")
            else:
                e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                cleaned_data['phone'] = e164
                cleaned_data['phone_e164'] = e164
                cleaned_data['phone_number'] = str(parsed.national_number)
                cleaned_data['phone_country_code'] = f"+{parsed.country_code}"
                cleaned_data['country'] = phonenumbers.region_code_for_number(parsed) or country_code

        return cleaned_data


class ProjectForm(forms.ModelForm):
    deadline = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    class Meta:
        model = Project
        fields = [
            'title', 'category', 'image', 'description', 'required_skills',
            'budget_type', 'budget_min', 'budget_max',
            'deadline', 'deliverables', 'attachment', 'status'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Build a Django REST API with authentication'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 6, 'placeholder': 'Describe the project in detail...'}),
            'required_skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Python, Django, PostgreSQL, REST API'}),
            'budget_type': forms.Select(attrs={'class': 'form-select'}),
            'budget_min': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '500', 'min': 0, 'step': 'any'}),
            'budget_max': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '2000', 'min': 0, 'step': 'any'}),
            'deliverables': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'List key deliverables and expectations...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.user_currency = resolve_currency_for_user_or_request(user=user)
        super().__init__(*args, **kwargs)

        self.fields['category'].empty_label = "- Select Specialized Category -"
        self.fields['category'].required = False
        self.fields['image'].required = False

        # Pre-select client's specialized category if creating a new project
        if not self.is_bound and not (self.instance and self.instance.pk):
            if not self.initial.get('category'):
                cat = get_user_specialized_category(user)
                if cat:
                    self.initial['category'] = cat.pk

        rate = get_usd_inr_rate()
        symbol = '$' if self.user_currency == 'USD' else '₹'
        code = self.user_currency

        self.fields['budget_min'].label = f"Minimum Budget ({symbol} {code})"
        self.fields['budget_max'].label = f"Maximum Budget ({symbol} {code})"

        # If editing an existing project and client is USD, display initial values converted to USD
        if self.instance and self.instance.pk and self.user_currency == 'USD':
            if not self.is_bound:
                if self.instance.budget_min:
                    self.initial['budget_min'] = float(convert_inr_to_usd(self.instance.budget_min, rate=rate))
                if self.instance.budget_max:
                    self.initial['budget_max'] = float(convert_inr_to_usd(self.instance.budget_max, rate=rate))

    def clean_category(self):
        category = self.cleaned_data.get('category')
        if not category and self.user:
            cat = get_user_specialized_category(self.user)
            if cat:
                return cat
        if not category:
            raise forms.ValidationError("Please select a Specialized Category.")
        return category

    def clean(self):
        cleaned_data = super().clean()
        budget_min = cleaned_data.get('budget_min')
        budget_max = cleaned_data.get('budget_max')

        if budget_min is not None and budget_max is not None:
            if budget_max < budget_min:
                raise forms.ValidationError("Maximum budget cannot be less than minimum budget.")

            # If user submitted amounts in USD, convert to base currency (INR) before saving
            if self.user_currency == 'USD':
                rate = get_usd_inr_rate()
                base_min = convert_usd_to_inr(budget_min, rate=rate)
                base_max = convert_usd_to_inr(budget_max, rate=rate)
                cleaned_data['budget_min'] = base_min
                cleaned_data['budget_max'] = base_max

                # Minimum validation in base currency: at least ₹100 INR
                if base_min < Decimal('100.00'):
                    min_usd = convert_inr_to_usd(Decimal('100.00'), rate=rate)
                    raise forms.ValidationError(f"Minimum budget must be at least ${min_usd:.2f} USD (₹100 INR).")
            else:
                if budget_min < Decimal('100.00'):
                    raise forms.ValidationError("Minimum budget must be at least ₹100 INR.")

        return cleaned_data


class ProposalForm(forms.ModelForm):
    class Meta:
        model = Proposal
        fields = ['bid_amount', 'delivery_days', 'cover_letter', 'attachment']
        widgets = {
            'bid_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '500.00', 'min': 1, 'step': 'any'}),
            'delivery_days': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '14', 'min': 1}),
            'cover_letter': forms.Textarea(attrs={'class': 'form-control', 'rows': 7, 'placeholder': 'Explain why you are the best choice for this project...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.user_currency = resolve_currency_for_user_or_request(user=user)
        super().__init__(*args, **kwargs)

        rate = get_usd_inr_rate()
        symbol = '$' if self.user_currency == 'USD' else '₹'
        code = self.user_currency
        self.fields['bid_amount'].label = f"Your Bid Amount ({symbol} {code})"

        # If editing existing proposal and user is USD, display in USD
        if self.instance and self.instance.pk and self.user_currency == 'USD':
            if not self.is_bound and self.instance.bid_amount:
                self.initial['bid_amount'] = float(convert_inr_to_usd(self.instance.bid_amount, rate=rate))

    def clean_bid_amount(self):
        bid = self.cleaned_data.get('bid_amount')
        if bid is not None:
            if self.user_currency == 'USD':
                rate = get_usd_inr_rate()
                base_bid = convert_usd_to_inr(bid, rate=rate)
                if base_bid < Decimal('50.00'):
                    min_usd = convert_inr_to_usd(Decimal('50.00'), rate=rate)
                    raise forms.ValidationError(f"Bid amount must be at least ${min_usd:.2f} USD (₹50 INR).")
                return base_bid
            else:
                if bid < Decimal('50.00'):
                    raise forms.ValidationError("Bid amount must be at least ₹50 INR.")
        return bid


class ReviewForm(forms.ModelForm):
    quality_of_work = forms.IntegerField(min_value=1, max_value=5, initial=5, widget=forms.HiddenInput(attrs={'id': 'id_quality_of_work'}))
    communication = forms.IntegerField(min_value=1, max_value=5, initial=5, widget=forms.HiddenInput(attrs={'id': 'id_communication'}))
    deadline_adherence = forms.IntegerField(min_value=1, max_value=5, initial=5, widget=forms.HiddenInput(attrs={'id': 'id_deadline_adherence'}))
    professionalism = forms.IntegerField(min_value=1, max_value=5, initial=5, widget=forms.HiddenInput(attrs={'id': 'id_professionalism'}))
    tags = forms.CharField(required=False, widget=forms.HiddenInput(attrs={'id': 'id_selected_tags'}))

    class Meta:
        model = Review
        fields = [
            'quality_of_work', 'communication', 'deadline_adherence',
            'professionalism', 'comment', 'would_recommend', 'tags'
        ]
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Write at least 20 characters describing the quality, turnaround speed, technical competence, and communication experience...',
                'id': 'reviewCommentTextarea',
                'maxlength': '1000'
            }),
            'would_recommend': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'wouldRecommendSwitch'
            }),
        }

    def clean_comment(self):
        comment = self.cleaned_data.get('comment', '').strip()
        if len(comment) < 20:
            raise forms.ValidationError(f"Please write at least 20 characters (currently {len(comment)} characters).")
        if len(comment) > 1000:
            raise forms.ValidationError(f"Comment cannot exceed 1000 characters (currently {len(comment)} characters).")
        return comment


class FreelancerReplyForm(forms.Form):
    reply = forms.CharField(
        min_length=5,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Write a polite, professional public response to this client feedback...',
            'maxlength': '500',
            'id': 'freelancerReplyTextarea'
        })
    )

    def clean_reply(self):
        reply = self.cleaned_data.get('reply', '').strip()
        if len(reply) < 5:
            raise forms.ValidationError("Please enter at least 5 characters for your response.")
        if len(reply) > 500:
            raise forms.ValidationError("Reply cannot exceed 500 characters.")
        return reply


class ContactForm(forms.ModelForm):
    topic = forms.CharField(max_length=100, required=False, widget=forms.HiddenInput(attrs={'id': 'contact_topic'}))
    # Optional phone number enhanced by intl-tel-input
    phone = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_contact_phone',
            'placeholder': 'e.g. 98765 43210'
        })
    )
    country = forms.CharField(
        required=False,
        initial='IN',
        widget=forms.HiddenInput(attrs={'id': 'id_contact_country'})
    )

    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'subject', 'topic', 'message']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your full name', 'id': 'contact_name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com', 'id': 'contact_email'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'How can we help you?', 'id': 'contact_subject'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Describe your question or issue in detail...', 'id': 'contact_message', 'maxlength': '1000'}),
        }

    def clean_phone(self):
        phone_raw = self.cleaned_data.get('phone', '').strip()
        country_code = (self.data.get('country') or 'IN').strip().upper()
        if phone_raw:
            try:
                parsed = phonenumbers.parse(phone_raw, country_code)
                if not phonenumbers.is_valid_number(parsed):
                    region = phonenumbers.region_code_for_number(parsed) or country_code
                    raise forms.ValidationError(f"Enter a valid phone number for {region}.")
                return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                raise forms.ValidationError("Invalid phone number format.")
        return ''


class UserProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=50, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))

    # Visible phone input (enhanced by intl-tel-input)
    phone = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_profile_phone',
            'placeholder': 'Phone number'
        })
    )
    country = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_profile_country'})
    )
    phone_country_code = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_profile_phone_country_code'})
    )
    phone_number = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={'id': 'id_profile_phone_number'})
    )

    class Meta:
        model = UserProfile
        fields = [
            'country', 'phone_country_code', 'phone_number', 'phone',
            'company_name', 'title', 'bio', 'avatar', 'location',
            'skills', 'hourly_rate', 'website'
        ]
        widgets = {
            'company_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your company or organisation'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Full-Stack Developer or Product Manager'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell freelancers a bit about yourself and your projects...'}),
            'avatar': forms.FileInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City, Country or Remote'}),
            'skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Python, Django, React'}),
            'hourly_rate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0.00', 'min': 0, 'step': 'any'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://yourwebsite.com'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        self.user_currency = resolve_currency_for_user_or_request(user=user)
        super().__init__(*args, **kwargs)

        rate = get_usd_inr_rate()
        symbol = '$' if self.user_currency == 'USD' else '₹'
        code = self.user_currency
        self.fields['hourly_rate'].label = f"Hourly Rate ({symbol} {code}/hr)"

        if self.instance and self.instance.pk:
            if not self.is_bound:
                if self.instance.country:
                    self.initial['country'] = self.instance.country
                if self.instance.phone_country_code:
                    self.initial['phone_country_code'] = self.instance.phone_country_code
                if self.instance.phone_number:
                    self.initial['phone_number'] = self.instance.phone_number
                if self.instance.phone:
                    self.initial['phone'] = self.instance.phone

                if self.user_currency == 'USD' and self.instance.hourly_rate:
                    self.initial['hourly_rate'] = float(convert_inr_to_usd(self.instance.hourly_rate, rate=rate))

    def clean(self):
        cleaned_data = super().clean()
        phone_raw = cleaned_data.get('phone', '').strip()
        country_code = (cleaned_data.get('country') or 'IN').strip().upper()

        if phone_raw:
            try:
                parsed = phonenumbers.parse(phone_raw, country_code)
                if not phonenumbers.is_valid_number(parsed):
                    region = phonenumbers.region_code_for_number(parsed) or country_code
                    country_name = "India" if region == "IN" else ("United States" if region == "US" else region)
                    self.add_error('phone', f"Enter a valid phone number for {country_name}.")
                else:
                    e164 = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
                    cleaned_data['phone'] = e164
                    cleaned_data['phone_number'] = str(parsed.national_number)
                    cleaned_data['phone_country_code'] = f"+{parsed.country_code}"
                    cleaned_data['country'] = phonenumbers.region_code_for_number(parsed) or country_code
            except phonenumbers.NumberParseException:
                self.add_error('phone', "Invalid phone number format.")

        # Convert hourly_rate if entered in USD
        hourly = cleaned_data.get('hourly_rate')
        if hourly is not None and self.user_currency == 'USD':
            rate = get_usd_inr_rate()
            cleaned_data['hourly_rate'] = convert_usd_to_inr(hourly, rate=rate)

        return cleaned_data


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ['content', 'attachment']
        widgets = {
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Type your message...'}),
            'attachment': forms.FileInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
