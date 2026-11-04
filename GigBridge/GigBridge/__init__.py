# Patch Django 3.2 SMTP EmailBackend for Python 3.12+ (which dropped keyfile & certfile from smtplib.starttls)
try:
    from django.core.mail.backends.smtp import EmailBackend
    from django.core.mail.utils import DNS_NAME

    def _py312_compatible_open(self):
        if self.connection:
            return False
        connection_params = {'local_hostname': DNS_NAME.get_fqdn()}
        if self.timeout is not None:
            connection_params['timeout'] = self.timeout
        if self.use_ssl:
            connection_params.update({
                'keyfile': self.ssl_keyfile,
                'certfile': self.ssl_certfile,
            })
        try:
            self.connection = self.connection_class(self.host, self.port, **connection_params)
            if not self.use_ssl and self.use_tls:
                try:
                    self.connection.starttls(keyfile=self.ssl_keyfile, certfile=self.ssl_certfile)
                except TypeError:
                    self.connection.starttls()
            if self.username and self.password:
                self.connection.login(self.username, self.password)
            return True
        except OSError:
            if not self.fail_silently:
                raise

    EmailBackend.open = _py312_compatible_open
except Exception:
    pass
