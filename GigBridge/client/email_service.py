import os
from django.conf import settings
from django.urls import reverse
from django.core.mail import get_connection, EmailMultiAlternatives
from django.template.loader import render_to_string


def _reload_env():
    """Dynamically re-read .env from disk so changes take effect immediately."""
    env_file = getattr(settings, 'BASE_DIR', None)
    if env_file:
        env_path = env_file / '.env'
        if env_path.exists():
            try:
                with open(env_path, 'r', encoding='utf-8') as _f:
                    for _line in _f:
                        _line = _line.strip()
                        if _line and not _line.startswith('#') and '=' in _line:
                            _k, _v = _line.split('=', 1)
                            _k = _k.strip()
                            _v = _v.strip()
                            if len(_v) >= 2 and ((_v[0] == '"' and _v[-1] == '"') or (_v[0] == "'" and _v[-1] == "'")):
                                _v = _v[1:-1].strip()
                            os.environ[_k] = _v
            except Exception:
                pass


def _get_smtp_connection():
    """Create a configured SMTP email connection with clean credentials."""
    _reload_env()

    host_user = os.getenv("EMAIL_HOST_USER", getattr(settings, 'EMAIL_HOST_USER', '')).strip().strip("'\"")
    host_password = os.getenv("EMAIL_HOST_PASSWORD", getattr(settings, 'EMAIL_HOST_PASSWORD', '')).strip().strip("'\"").replace(" ", "")
    from_email = os.getenv("DEFAULT_FROM_EMAIL", getattr(settings, 'DEFAULT_FROM_EMAIL', '')).strip().strip("'\"")
    if not from_email:
        from_email = f"GigBridge Support <{host_user}>" if host_user else "support@gigbridge.com"

    backend_name = os.getenv("EMAIL_BACKEND", getattr(settings, 'EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')).strip().strip("'\"")
    host = os.getenv("EMAIL_HOST", getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com')).strip().strip("'\"")
    port = int(str(os.getenv("EMAIL_PORT", getattr(settings, 'EMAIL_PORT', 587))).strip().strip("'\""))
    use_tls = str(os.getenv("EMAIL_USE_TLS", getattr(settings, 'EMAIL_USE_TLS', True))).strip().strip("'\"").lower() in ('1', 'true', 'yes', 'on')

    connection = get_connection(
        backend=backend_name,
        host=host,
        port=port,
        username=host_user,
        password=host_password,
        use_tls=use_tls,
        fail_silently=False
    )
    return connection, from_email, host_user


def send_client_registered_email(request, user, profile=None):
    """Notify client that their account has been created and is pending admin verification."""
    if not user or not user.email:
        return False, "User has no email address."

    try:
        connection, from_email, _ = _get_smtp_connection()
        subject = "GigBridge - Client Account Created (Pending Administrator Verification)"

        try:
            login_url = request.build_absolute_uri(reverse('login'))
        except Exception:
            login_url = "http://127.0.0.1:8000/accounts/login/"

        context = {
            'user': user,
            'profile': profile,
            'login_url': login_url,
        }
        html_content = render_to_string('emails/client_registration_email.html', context)
        plain_body = (
            f"Hello {user.first_name or user.username},\n\n"
            f"Welcome to GigBridge! Your client account has been registered successfully.\n\n"
            f"Account Status: Pending Administrator Verification\n"
            f"Our team reviews new client accounts to maintain high marketplace trust. "
            f"You will receive an email confirmation once your account has been verified, "
            f"granting full access to post project listings and hire talent.\n\n"
            f"Sign in to your portal: {login_url}\n\n"
            f"- The GigBridge Team"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[user.email],
            connection=connection
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"\n[GigBridge Email Delivered] Client Registration Email sent to {user.email}\n")
        return True, None
    except Exception as e:
        err = str(e)
        print(f"\n[GigBridge Email Notice] Client registration email failed to send to {user.email}: {err}\n")
        return False, err


def send_client_approved_email(request, user, profile=None):
    """Notify client that their account has been approved/verified by an administrator."""
    if not user or not user.email:
        return False, "User has no email address."

    try:
        connection, from_email, _ = _get_smtp_connection()
        subject = "GigBridge - Your Account is Verified by Admin!"

        try:
            project_create_url = request.build_absolute_uri(reverse('client_project_create'))
        except Exception:
            project_create_url = "http://127.0.0.1:8000/client/projects/create/"

        context = {
            'user': user,
            'profile': profile,
            'project_create_url': project_create_url,
        }
        html_content = render_to_string('emails/client_approved_email.html', context)
        plain_body = (
            f"Hello {user.first_name or user.username},\n\n"
            f"Great news! Your GigBridge client account has been officially verified and approved by an administrator.\n\n"
            f"You now have full access to create project listings, receive proposals from specialized talent, and hire securely.\n\n"
            f"Post your first project: {project_create_url}\n\n"
            f"- The GigBridge Team"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[user.email],
            connection=connection
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"\n[GigBridge Email Delivered] Client Verification / Approval Email sent to {user.email}\n")
        return True, None
    except Exception as e:
        err = str(e)
        print(f"\n[GigBridge Email Notice] Client approval email failed to send to {user.email}: {err}\n")
        return False, err


def send_freelancer_welcome_email(request, user, profile=None):
    """Welcome freelancer and outline steps to start bidding."""
    if not user or not user.email:
        return False, "User has no email address."

    try:
        connection, from_email, _ = _get_smtp_connection()
        subject = "Welcome to GigBridge! Your Freelancer Account is Ready"

        try:
            browse_projects_url = request.build_absolute_uri(reverse('project_list'))
        except Exception:
            browse_projects_url = "http://127.0.0.1:8000/projects/"

        context = {
            'user': user,
            'profile': profile,
            'browse_projects_url': browse_projects_url,
        }
        html_content = render_to_string('emails/freelancer_welcome_email.html', context)
        plain_body = (
            f"Hello {user.first_name or user.username},\n\n"
            f"Welcome to GigBridge! Your freelancer profile is ready and active.\n\n"
            f"Get started in 3 steps:\n"
            f"1. Complete your profile and set your hourly rate in Profile Settings.\n"
            f"2. Explore curated projects matching your skill set.\n"
            f"3. Submit tailored bids and work under milestone protection.\n\n"
            f"Browse open projects: {browse_projects_url}\n\n"
            f"- The GigBridge Team"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[user.email],
            connection=connection
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"\n[GigBridge Email Delivered] Freelancer Welcome Email sent to {user.email}\n")
        return True, None
    except Exception as e:
        err = str(e)
        print(f"\n[GigBridge Email Notice] Freelancer welcome email failed to send to {user.email}: {err}\n")
        return False, err


def send_otp_email(user, otp_code, title="GigBridge - Your Password Reset Verification Code"):
    """Send single-use 6-digit OTP verification email for password resets."""
    if not user or not user.email:
        return False, "User has no email address."

    try:
        connection, from_email, _ = _get_smtp_connection()
        subject = title

        context = {
            'user': user,
            'otp_code': otp_code,
            'validity_minutes': 10,
        }
        html_content = render_to_string('emails/otp_verification_email.html', context)
        plain_body = (
            f"Hello {user.first_name or user.username},\n\n"
            f"Your 6-digit verification code to reset your GigBridge account password is:\n\n"
            f"   {otp_code}\n\n"
            f"This code is strictly valid for 10 minutes only.\n"
            f"If you did not request this, please disregard this email.\n\n"
            f"- The GigBridge Team"
        )

        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[user.email],
            connection=connection
        )
        msg.attach_alternative(html_content, "text/html")
        msg.send(fail_silently=False)
        print(f"\n[GigBridge Email Delivered] Verification code {otp_code} dispatched successfully to {user.email}\n")
        return True, None
    except Exception as e:
        err = str(e)
        print("\n" + "="*70)
        print(f"[GigBridge EMAIL ERROR - VERIFICATION CODE DELIVERY FAILED]")
        print(f"Recipient Email : {user.email}")
        print(f"SMTP Error      : {err}")
        print(f">>> YOUR 6-DIGIT VERIFICATION CODE (OTP) IS: {otp_code} <<<")
        print("Validity: 10 minutes.")
        print("="*70 + "\n")
        return False, err
