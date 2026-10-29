from django import forms
from client.models import ContactReply


class ContactReplyForm(forms.ModelForm):
    subject = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'replySubject',
            'placeholder': 'Subject of reply email...',
            'required': 'required',
        })
    )
    body = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'id': 'replyBody',
            'rows': 7,
            'placeholder': 'Type your official response to the client here...',
            'required': 'required',
        })
    )

    class Meta:
        model = ContactReply
        fields = ['subject', 'body']
